"""
عقد إيصال رمز الدخول.

نفس بنية `payments/gateways/` و`notifications/backends/` عمدًا: ثلاث
طبقات توصيل في المشروع تتبع الشكل نفسه، فمن فهم واحدة فهم الثلاث.

التمييز الجوهري هو نفسه أيضًا — عابر مقابل دائم:

    عابر : مزوّد الرسائل متوقّف، مهلة، حصّة مستنفدة.  → يُعاد.
    دائم : رقم غير صالح، شبكة غير مدعومة، رصيد منتهٍ. → لا يُعاد.

ولماذا يهمّ هنا تحديدًا؟ لأن إعادة محاولة رمز دخول بعد دقيقة عبثٌ: الرمز
نفسه ينتهي بعد خمس دقائق. الفشل العابر يستحقّ إعادةً واحدة سريعة، والدائم
يستحقّ أن يُقال للمستخدم فورًا "هذا الرقم لا يستقبل رسائل" بدل تركه ينتظر.
"""
from abc import ABC, abstractmethod


class OTPDeliveryError(Exception):
    """خطأ عام في طبقة الإيصال."""


class NotConfigured(OTPDeliveryError):
    """المزوّد غير مهيّأ — حالة تشغيل مشروعة قبل الاشتراك."""


class DeliveryResult:
    """نتيجة محاولة إيصال واحدة."""

    __slots__ = ("ok", "permanent_failure", "error", "reference")

    def __init__(self, ok, permanent_failure=False, error="", reference=""):
        self.ok = bool(ok)
        self.permanent_failure = bool(permanent_failure)
        self.error = str(error)[:300]
        self.reference = str(reference)[:255]

    def __repr__(self):
        return (
            f"DeliveryResult(ok={self.ok}, "
            f"permanent={self.permanent_failure}, error={self.error!r})"
        )

    @classmethod
    def success(cls, reference=""):
        return cls(True, reference=reference)

    @classmethod
    def transient(cls, error):
        return cls(False, permanent_failure=False, error=error)

    @classmethod
    def permanent(cls, error):
        return cls(False, permanent_failure=True, error=error)


class OTPDeliveryBackend(ABC):
    """
    الواجهة التي ينفّذها كل مزوّد.

    لإضافة مزوّد رسائل:
        1. ملفّ في users/services/delivery/ يرث هذا الصنف.
        2. سطر واحد: OTP_DELIVERY_BACKEND = "المسار.إلى.الصنف".
    """

    name = "base"

    def check_ready(self):
        """يرفع `NotConfigured` إن نقص إعداد."""
        return True

    @abstractmethod
    def send(self, phone, code, context=None):
        """
        يرسل `code` إلى `phone`. يعيد `DeliveryResult`.

        **لا يسجّل الرمز أبدًا.** رمز الدخول في ملفّ سجلّ يعادل كلمة مرور
        في ملفّ سجلّ — والاستثناء الوحيد هو خلفية الطابعة في التطوير،
        وهي ترفض العمل في الإنتاج أصلًا.
        """
        raise NotImplementedError

    def build_message(self, code):
        """
        نصّ الرسالة. أُفرد ليُعدَّل بلا لمس منطق الإرسال — وليُترجَم لاحقًا.
        """
        return f"رمز الدخول الخاص بك: {code}"

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"
