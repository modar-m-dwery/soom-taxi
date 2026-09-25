"""
عقد بوابة الدفع.

كل بوابة — نقدية كانت أو محفظة محلّية أو مزوّدًا عالميًا يُفتح غدًا —
ترث `PaymentGateway` وتُعلن قدراتها. النظام لا يسأل "أي بوابة هذه؟" بل
يسأل "ماذا تستطيع؟"، فلا يوجد في المشروع كلّه شرط واحد على اسم بوابة.

التقسيم المهم في `GatewayResult` ليس بين نجاح وفشل، بل بين **فشل عابر**
و**فشل دائم** — وهو نفس التمييز المعتمد في `notifications/backends/base.py`:

    عابر : انقطاع شبكة، مهلة، ضغط على المزوّد.  → يُعاد.
    دائم : بطاقة مرفوضة، حساب مغلق، مبلغ مخالف. → لا يُعاد، ويُبلَّغ المستخدم.

خلط الحالتين هو ما يجعل طوابير الدفع تُعيد محاولة عمليات مرفوضة إلى الأبد،
أو — وهو أسوأ — تتوقّف عن محاولة عمليات كان انقطاع الشبكة سببها الوحيد.
"""
from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentGatewayError(Exception):
    """خطأ عام في طبقة البوابات."""


class NotConfigured(PaymentGatewayError):
    """
    البوابة غير مهيّأة — ليست خطأً بل حالة تشغيل مشروعة.

    بوابة بلا بيانات اعتماد يجب أن تُستبعد من قائمة المتاح للمستخدم،
    لا أن تنهار عند أول استخدام.
    """


class WebhookVerificationError(PaymentGatewayError):
    """
    فشل التحقّق من توقيع إشعار وارد.

    يُعامَل دائمًا كمحاولة تزوير لا كخطأ تقني: لا يُعاد، ولا يُغيَّر شيء في
    قاعدة البيانات، ويُسجَّل.
    """


class GatewayResult:
    """نتيجة نداء واحد لبوابة."""

    __slots__ = ("ok", "permanent_failure", "error", "reference", "payload")

    def __init__(
        self,
        ok,
        permanent_failure=False,
        error="",
        reference="",
        payload=None,
    ):
        self.ok = bool(ok)
        self.permanent_failure = bool(permanent_failure)
        self.error = str(error)[:300]
        self.reference = str(reference)[:255]
        self.payload = payload if isinstance(payload, dict) else {}

    def __repr__(self):
        return (
            f"GatewayResult(ok={self.ok}, permanent={self.permanent_failure}, "
            f"ref={self.reference!r}, error={self.error!r})"
        )

    # -- بناة مريحون --------------------------------------------------

    @classmethod
    def success(cls, reference="", payload=None):
        return cls(True, reference=reference, payload=payload)

    @classmethod
    def transient(cls, error, payload=None):
        return cls(False, permanent_failure=False, error=error, payload=payload)

    @classmethod
    def permanent(cls, error, payload=None):
        return cls(False, permanent_failure=True, error=error, payload=payload)


class PaymentGateway(ABC):
    """
    الواجهة التي تنفّذها كل بوابة.

    لإضافة بوابة جديدة:

        1. ملفّ جديد في payments/gateways/  يرث هذا الصنف.
        2. سطر واحد في settings.PAYMENT_GATEWAYS.

    لا ترحيل قاعدة بيانات، ولا تعديل على النماذج، ولا شرط جديد في الخدمات.
    """

    #: هل يؤكّد التحصيلَ إنسانٌ (نقد) أم مزوّدٌ خارجي (بطاقة/محفظة)؟
    #:
    #: الافتراضي False: بوّابة إلكترونية لا تُؤكَّد يدويًّا إطلاقًا — المزوّد
    #: يُبلّغ عبر webhook موقَّع. الرايةُ True تجعل
    #: `PaymentService._authorize_charge` يشترط أن يكون المؤكِّد سائق
    #: الرحلة نفسه أو مشغّلًا. اتركها False ما لم يكن القبض نقديًّا.
    requires_manual_confirmation = False

    #: رمز فريد يُخزَّن في Payment.gateway_code. لا يتغيّر بعد أول استخدام
    #: في الإنتاج — تغييره يقطع ربط الدفعات القديمة ببوابتها.
    code = ""

    #: اسم يُعرض للمستخدم في التطبيق.
    display_name = ""

    # -- القدرات ------------------------------------------------------
    # النظام يقرأ هذه لا اسم البوابة. بوابة جديدة تُعلن قدراتها فيعرف
    # النظام كيف يعاملها بلا سطر شرطي واحد.

    #: هل يمرّ المال عبر مزوّد خارجي؟ النقدي: لا.
    is_online = False

    #: هل يصل المال إلى حساب المنصّة؟ إن لا، فالسائق يقبض والمنصّة تدين له
    #: بالعكس (عمولة على السائق) — وهو حال الدفع النقدي.
    settles_to_platform = False

    #: هل تدعم الحجز ثم التثبيت على مرحلتين؟
    supports_authorize_capture = False

    #: هل ينتهي `charge` بالمال محصَّلًا فعلًا؟ ضعها False في بوابة تحجز
    #: أوّلًا وتنتظر `capture` لاحقًا — عندها تنتقل الدفعة إلى AUTHORIZED
    #: لا إلى PAID، ولا تُكتب قيود الاستحقاق قبل التثبيت.
    captures_immediately = True

    #: هل تدعم الإعادة برمجيًا؟
    supports_refund = False

    #: هل تستقبل إشعارات واردة؟
    supports_webhook = False

    #: العملات المدعومة. فارغ = كل العملات.
    supported_currencies = ()

    # =================================================================
    # دورة الحياة
    # =================================================================

    def check_ready(self):
        """
        يرفع `NotConfigured` إن نقص إعداد. يُستدعى قبل أي استخدام، ويُستخدم
        كذلك لبناء قائمة البوابات المتاحة للمستخدم.
        """
        return True

    def supports_currency(self, currency):
        if not self.supported_currencies:
            return True
        return currency in self.supported_currencies

    # =================================================================
    # العمليات
    # =================================================================

    @abstractmethod
    def charge(self, payment, context=None):
        """
        يبدأ تحصيل `payment`.

        يجب أن تكون العملية **متكافئة** (idempotent) من طرف البوابة:
        مرّر `payment.idempotency_key` إلى المزوّد كلّما دعم ذلك، فإعادة
        النداء بعد انقطاع شبكة يجب ألّا تسحب المبلغ مرتين.

        ترجع `GatewayResult`. لا ترفع استثناءً لفشل متوقّع — الفشل المتوقّع
        نتيجة لا استثناء.
        """
        raise NotImplementedError

    def capture(self, payment, context=None):
        """تثبيت مبلغ محجوز. تُنفَّذ فقط إن كانت supports_authorize_capture."""
        if not self.supports_authorize_capture:
            return GatewayResult.permanent(
                f"البوابة {self.code} لا تدعم الحجز والتثبيت."
            )
        raise NotImplementedError

    def refund(self, payment, amount, reason="", context=None):
        """إعادة مبلغ. تُنفَّذ فقط إن كانت supports_refund."""
        if not self.supports_refund:
            return GatewayResult.permanent(
                f"البوابة {self.code} لا تدعم الإعادة البرمجية."
            )
        raise NotImplementedError

    def cancel(self, payment, context=None):
        """إلغاء عملية لم تُحصَّل بعد."""
        return GatewayResult.success()

    # =================================================================
    # الإشعارات الواردة
    # =================================================================

    def verify_webhook(self, headers, raw_body):
        """
        يتحقّق من صحّة إشعار وارد ويعيده مُحلَّلًا.

        يرفع `WebhookVerificationError` عند فشل التحقّق. لا تتساهل هنا:
        إشعار غير موثَّق يعني أن أي أحد يستطيع أن يعلن أن رحلةً دُفعت.
        """
        raise WebhookVerificationError(
            f"البوابة {self.code} لا تستقبل إشعارات."
        )

    def extract_webhook_reference(self, event):
        """يستخرج معرّف العملية من حدث تم التحقّق منه."""
        return str(event.get("reference") or "")

    def extract_webhook_status(self, event):
        """
        يترجم حدث المزوّد إلى حالة من `PaymentStatus`، أو `None` إن كان
        الحدث لا يعني تغيّر حالة.
        """
        return None

    # =================================================================

    def describe(self):
        """وصف يُعرض في واجهة اختيار وسيلة الدفع."""
        return {
            "code": self.code,
            "display_name": self.display_name,
            "is_online": self.is_online,
            "supports_refund": self.supports_refund,
            "supported_currencies": list(self.supported_currencies),
        }

    def __repr__(self):
        return f"<{self.__class__.__name__} code={self.code!r}>"


def normalize_amount(value):
    """تحويل آمن إلى Decimal. لا يُسمح بـfloat في المال إطلاقًا."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError(
            "لا تمرّر float للمبالغ المالية — استخدم Decimal أو نصًّا."
        )
    return Decimal(str(value))
