"""
سجلّ البوابات.

نقطة التوسّع الوحيدة في نظام الدفع. إضافة بوابة = ملفّ + سطر في الإعدادات:

    PAYMENT_GATEWAYS = [
        "payments.gateways.cash.CashGateway",
        "payments.gateways.your_provider.YourGateway",   # ← السطر الجديد
    ]

السجلّ كسول (lazy): يُبنى عند أول استخدام لا عند استيراد الوحدة، حتى لا
يفشل إقلاع Django بسبب بوابة تحتاج إعدادات غير جاهزة بعد.
"""
import logging
import threading

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from payments.gateways.base import (  # noqa: F401  (إعادة تصدير مقصودة)
    GatewayResult,
    NotConfigured,
    PaymentGateway,
    PaymentGatewayError,
    WebhookVerificationError,
    normalize_amount,
)


logger = logging.getLogger(__name__)

DEFAULT_GATEWAYS = ("payments.gateways.cash.CashGateway",)

_registry = {}
_loaded = False
_lock = threading.Lock()


def _load():
    """
    يبني السجلّ مرّة واحدة. آمن أمام التوازي: عمليتان تصلان معًا لن تبنيا
    السجلّ مرّتين ولن ترى إحداهما سجلًّا نصف مبنيّ.
    """
    global _loaded

    if _loaded:
        return

    with _lock:
        if _loaded:
            return

        paths = getattr(settings, "PAYMENT_GATEWAYS", None) or DEFAULT_GATEWAYS
        registry = {}

        for path in paths:
            try:
                gateway_class = import_string(path)
            except ImportError as exc:
                raise ImproperlyConfigured(
                    f"تعذّر استيراد بوابة الدفع '{path}': {exc}"
                ) from exc

            if not (
                isinstance(gateway_class, type)
                and issubclass(gateway_class, PaymentGateway)
            ):
                raise ImproperlyConfigured(
                    f"'{path}' ليست صنفًا يرث PaymentGateway."
                )

            instance = gateway_class()
            code = (instance.code or "").strip()

            if not code:
                raise ImproperlyConfigured(
                    f"البوابة '{path}' بلا رمز code."
                )

            if code in registry:
                raise ImproperlyConfigured(
                    f"رمز البوابة '{code}' مكرَّر بين '{path}' و"
                    f"'{registry[code].__class__.__module__}'."
                )

            registry[code] = instance

        _registry.clear()
        _registry.update(registry)
        _loaded = True


def reset_registry():
    """للاختبارات فقط: يفرغ السجلّ ليُعاد بناؤه بإعدادات جديدة."""
    global _loaded
    with _lock:
        _registry.clear()
        _loaded = False


def get_gateway(code):
    """
    يعيد نسخة البوابة صاحبة الرمز.

    يرفع `PaymentGatewayError` إن لم توجد — ولا يسقط على بوابة افتراضية
    صامتًا: دفعة أُنشئت لبوابة اختفت من الإعدادات مشكلةٌ يجب أن تُرى، لا
    أن تُحوَّل إلى نقدي بلا علم أحد.
    """
    _load()

    gateway = _registry.get(code)

    if gateway is None:
        raise PaymentGatewayError(
            f"بوابة دفع غير معروفة: '{code}'. "
            f"المتاح: {sorted(_registry)}"
        )

    return gateway


def all_gateways():
    """كل البوابات المسجَّلة، مهيّأة كانت أو لا."""
    _load()
    return dict(_registry)


def available_gateways(currency=None):
    """
    البوابات الجاهزة فعلًا للاستخدام الآن.

    البوابة غير المهيّأة تُستبعد بصمت من هنا — وهذا هو المقصود: مزوّد
    ستشترك به لاحقًا يبقى في الكود بلا أن يظهر للمستخدم قبل أوانه.
    """
    _load()
    ready = []

    for code, gateway in _registry.items():
        try:
            gateway.check_ready()
        except NotConfigured as exc:
            logger.debug("بوابة %s غير مهيّأة: %s", code, exc)
            continue
        except Exception:
            logger.exception("فشل غير متوقّع في فحص جاهزية البوابة %s", code)
            continue

        if currency and not gateway.supports_currency(currency):
            continue

        ready.append(gateway)

    return ready


def default_gateway_code():
    """
    البوابة الافتراضية حين لا يختار المستخدم شيئًا.

    تُضبط بـ`settings.PAYMENT_DEFAULT_GATEWAY`، وتسقط على النقدي — وهو
    الخيار الصحيح في سوق يغلب عليه النقد.
    """
    return getattr(settings, "PAYMENT_DEFAULT_GATEWAY", "cash")
