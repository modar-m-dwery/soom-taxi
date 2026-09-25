"""
اختيار خلفية إيصال رمز الدخول.

القيمة الافتراضية هي الطابعة — وهي ترفض العمل في الإنتاج بنفسها،
و`settings.py` يرفض الإقلاع بها في الإنتاج أصلًا. حارسان لأن نسيان ضبط
مزوّد الرسائل خطأٌ صامت ومكلف: يبدو كل شيء سليمًا ولا أحد يستطيع الدخول.
"""
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from users.services.delivery.base import (  # noqa: F401  (إعادة تصدير مقصودة)
    DeliveryResult,
    NotConfigured,
    OTPDeliveryBackend,
    OTPDeliveryError,
)


logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "users.services.delivery.console.ConsoleOTPBackend"

#: أسماء مختصرة مقبولة في الإعدادات، للتوافق مع القيمة القديمة "console".
ALIASES = {
    "console": DEFAULT_BACKEND,
    "sms": "users.services.delivery.sms.HTTPSMSBackend",
}

_cached = None


def reset_backend_cache():
    """للاختبارات: يُبطل النسخة المحفوظة ليُقرأ الإعداد من جديد."""
    global _cached
    _cached = None


def get_otp_backend():
    """
    يعيد نسخة الخلفية المضبوطة. تُبنى مرّة وتُحفظ.

    يرفع `ImproperlyConfigured` عند مسار خاطئ — عند أول استخدام لا عند
    الإقلاع، حتى لا يمنع خطأ مطبعي في إعداد الرسائل تشغيل بقية النظام.
    """
    global _cached

    if _cached is not None:
        return _cached

    path = getattr(settings, "OTP_DELIVERY_BACKEND", DEFAULT_BACKEND)
    path = ALIASES.get(path, path)

    try:
        backend_class = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"تعذّر استيراد خلفية إيصال OTP '{path}': {exc}"
        ) from exc

    if not (
        isinstance(backend_class, type)
        and issubclass(backend_class, OTPDeliveryBackend)
    ):
        raise ImproperlyConfigured(
            f"'{path}' ليست صنفًا يرث OTPDeliveryBackend."
        )

    _cached = backend_class()
    return _cached


def deliver_otp(phone, code):
    """
    يرسل الرمز ويعيد `DeliveryResult`. لا يرفع استثناءً أبدًا.

    السبب: الإرسال يجري داخل مهمّة Celery، ومهمّة تنهار باستثناء غير
    ملتقط تُسجَّل كخطأ نظام لا كفشل إيصال — فيضيع الفرق بين "المزوّد
    متوقّف" و"الكود مكسور".
    """
    try:
        backend = get_otp_backend()
    except ImproperlyConfigured as exc:
        logger.error("خلفية OTP غير صالحة: %s", exc)
        return DeliveryResult.permanent(str(exc))

    try:
        backend.check_ready()
    except NotConfigured as exc:
        logger.error("خلفية OTP غير مهيّأة: %s", exc)
        return DeliveryResult.permanent(str(exc))

    try:
        result = backend.send(phone, code)
    except NotConfigured as exc:
        return DeliveryResult.permanent(str(exc))
    except Exception as exc:  # noqa: BLE001 — مقصود
        logger.exception("استثناء غير متوقّع أثناء إرسال OTP إلى %s", phone)
        return DeliveryResult.transient(f"خطأ غير متوقّع: {exc}")

    if not isinstance(result, DeliveryResult):
        logger.error(
            "خلفية OTP أعادت نوعًا غير متوقّع: %r", type(result)
        )
        return DeliveryResult.permanent("الخلفية أعادت نتيجة غير صالحة.")

    return result
