"""
قالب البوابة الإلكترونية — الجاهز لليوم الذي يُفتح فيه مزوّد للسوق.

هذا ليس مثالًا تعليميًا بل بوابة عاملة: تنفّذ HTTP والمهل والتكافؤ
والتحقّق من التوقيع وتصنيف الفشل. ما ينقصها هو ثلاثة أشياء يختلف شكلها
من مزوّد لآخر، وقد عُزلت كلّها في دوالّ صغيرة تُعاد كتابتها بالوراثة:

    _charge_body()        شكل جسم طلب التحصيل
    _parse_reference()    أين معرّف العملية في ردّ المزوّد
    _classify()           أي أخطاء المزوّد دائمة وأيّها عابرة

للاشتراك بمزوّد جديد غدًا:

    class PaymobGateway(OnlineGateway):
        code = "paymob"
        display_name = "بايموب"
        settings_prefix = "PAYMOB"

        def _charge_body(self, payment):
            return {"amount_cents": int(payment.amount * 100), ...}

ثم سطر في PAYMENT_GATEWAYS. لا ترحيل، ولا تعديل نماذج، ولا شرط جديد في
الخدمات.

—————
تحذير مقصود: هذا الصنف مجرَّد (`code = ""`) فلا يُسجَّل بنفسه. يجب أن ترثه.
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings

from payments.gateways.base import (
    GatewayResult,
    NotConfigured,
    PaymentGateway,
    WebhookVerificationError,
)


logger = logging.getLogger(__name__)

#: مهلة قصيرة عمدًا. طلب دفع معلّق ثلاثين ثانية يُجمّد خيط الطلب ويُبقي
#: المستخدم أمام شاشة دوّارة — والأفضل أن يفشل عابرًا ويُعاد.
DEFAULT_TIMEOUT_SECONDS = 15

#: رموز HTTP التي تعني "أعد المحاولة" لا "ارفض العملية".
TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class OnlineGateway(PaymentGateway):
    """قاعدة كل بوابة تتحدّث إلى مزوّد عبر HTTP."""

    code = ""
    display_name = ""

    is_online = True
    settles_to_platform = True
    supports_authorize_capture = True
    supports_refund = True
    supports_webhook = True

    #: بادئة مفاتيح الإعدادات. المزوّد "PAYMOB" يقرأ PAYMOB_BASE_URL و
    #: PAYMOB_API_KEY و PAYMOB_WEBHOOK_SECRET.
    settings_prefix = ""

    timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    # =================================================================
    # الإعدادات
    # =================================================================

    def _setting(self, name, default=""):
        if not self.settings_prefix:
            raise NotConfigured(
                f"البوابة {self.__class__.__name__} بلا settings_prefix."
            )
        return getattr(settings, f"{self.settings_prefix}_{name}", default) or default

    @property
    def base_url(self):
        return self._setting("BASE_URL").rstrip("/")

    @property
    def api_key(self):
        return self._setting("API_KEY")

    @property
    def webhook_secret(self):
        return self._setting("WEBHOOK_SECRET")

    def check_ready(self):
        missing = [
            name
            for name in ("BASE_URL", "API_KEY")
            if not self._setting(name)
        ]

        if missing:
            raise NotConfigured(
                f"{self.settings_prefix}: الإعدادات الناقصة "
                f"{', '.join(missing)}."
            )

        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise NotConfigured(f"اعتمادية ناقصة: {exc}") from exc

        return True

    # =================================================================
    # نقاط التخصيص — أعِد كتابتها في الصنف الوارث
    # =================================================================

    def _charge_body(self, payment):
        """جسم طلب التحصيل. الشكل الافتراضي شائع لكنه ليس عالميًا."""
        return {
            "amount": str(payment.amount),
            "currency": payment.currency,
            "reference": payment.idempotency_key,
            "description": f"Trip #{payment.trip_id}",
        }

    def _refund_body(self, payment, amount, reason):
        return {
            "transaction_id": payment.gateway_reference,
            "amount": str(amount),
            "reason": (reason or "")[:255],
        }

    def _parse_reference(self, data):
        """أين معرّف العملية في ردّ المزوّد."""
        for key in ("id", "transaction_id", "reference", "order_id"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    def _classify(self, status_code, data):
        """
        هل هذا الفشل دائم أم عابر؟

        القاعدة الافتراضية: 4xx دائم (المزوّد رفض العملية نفسها)، و5xx
        والمهل عابرة (المزوّد نفسه متعثّر). الاستثناءات في
        TRANSIENT_HTTP_CODES — أهمّها 429: تجاوز حدّ المعدّل ليس رفضًا
        للعملية بل طلبًا للتمهّل.
        """
        if status_code in TRANSIENT_HTTP_CODES:
            return False
        return 400 <= status_code < 500

    def _error_text(self, data, response_text):
        if isinstance(data, dict):
            for key in ("message", "error", "detail", "error_message"):
                value = data.get(key)
                if value:
                    return str(value)
        return (response_text or "")[:300]

    # =================================================================
    # نداء HTTP واحد — كل الطلبات تمرّ من هنا
    # =================================================================

    def _post(self, path, body, idempotency_key=""):
        """
        ينفّذ الطلب ويعيد ثلاثيّة (result, status_code, data).

        لا يرفع استثناءً لفشل متوقّع. كل ما قد يحدث للشبكة يُترجم إلى
        `GatewayResult` عابر — وهذا ما يمنع خطأ شبكة من أن يصير 500 في
        وجه المستخدم.
        """
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # التكافؤ من طرف المزوّد: إعادة النداء بالمفتاح نفسه بعد انقطاع
        # شبكة يجب ألّا تسحب المبلغ مرّتين. المزوّد الذي لا يدعم هذه
        # الترويسة يتجاهلها بلا ضرر.
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            response = requests.post(
                url,
                data=json.dumps(body),
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            # مهلة، DNS، رفض اتصال، شهادة… كلّها عابرة بلا استثناء.
            logger.warning("فشل اتصال ببوابة %s: %s", self.code, exc)
            return GatewayResult.transient(f"فشل الاتصال بالمزوّد: {exc}"), 0, {}

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not isinstance(data, dict):
            data = {"raw": data}

        if 200 <= response.status_code < 300:
            return (
                GatewayResult.success(
                    reference=self._parse_reference(data),
                    payload=data,
                ),
                response.status_code,
                data,
            )

        error = self._error_text(data, getattr(response, "text", ""))
        permanent = self._classify(response.status_code, data)

        detail = f"{response.status_code}: {error}"
        result = (
            GatewayResult.permanent(detail, payload=data)
            if permanent
            else GatewayResult.transient(detail, payload=data)
        )

        return result, response.status_code, data

    # =================================================================
    # العمليات
    # =================================================================

    def charge(self, payment, context=None):
        self.check_ready()

        if not self.supports_currency(payment.currency):
            return GatewayResult.permanent(
                f"البوابة {self.code} لا تدعم العملة {payment.currency}."
            )

        result, _status, _data = self._post(
            "charges",
            self._charge_body(payment),
            idempotency_key=payment.idempotency_key,
        )
        return result

    def capture(self, payment, context=None):
        self.check_ready()

        if not payment.gateway_reference:
            return GatewayResult.permanent(
                "لا يوجد معرّف عملية لدى المزوّد — لا شيء لتثبيته."
            )

        result, _status, _data = self._post(
            f"charges/{payment.gateway_reference}/capture",
            {},
            idempotency_key=f"cap-{payment.idempotency_key}",
        )
        return result

    def refund(self, payment, amount, reason="", context=None):
        self.check_ready()

        if not payment.gateway_reference:
            return GatewayResult.permanent(
                "لا يوجد معرّف عملية لدى المزوّد — لا شيء لإعادته."
            )

        result, _status, _data = self._post(
            "refunds",
            self._refund_body(payment, amount, reason),
            idempotency_key=f"ref-{payment.idempotency_key}-{amount}",
        )
        return result

    def cancel(self, payment, context=None):
        self.check_ready()

        if not payment.gateway_reference:
            # لم تصل العملية للمزوّد أصلًا — لا شيء يُلغى، والإلغاء ناجح.
            return GatewayResult.success()

        result, _status, _data = self._post(
            f"charges/{payment.gateway_reference}/cancel",
            {},
            idempotency_key=f"cnl-{payment.idempotency_key}",
        )
        return result

    # =================================================================
    # الإشعارات الواردة
    # =================================================================

    def verify_webhook(self, headers, raw_body):
        """
        يتحقّق من HMAC-SHA256 ويعيد الحدث مُحلَّلًا.

        ثلاث احتياطات مقصودة:
          * المقارنة بـ`compare_digest` لا `==` — لمنع هجوم التوقيت.
          * التحقّق على **الجسم الخام** لا على النتيجة المحلَّلة، لأن
            إعادة الترميز تغيّر البايتات فيسقط التوقيع الصحيح.
          * غياب السرّ خطأ لا تساهل: بوابة تستقبل إشعارات بلا سرّ تعني
            أن أي أحد يستطيع إعلان أن رحلةً دُفعت.
        """
        secret = self.webhook_secret

        if not secret:
            raise WebhookVerificationError(
                f"{self.settings_prefix}_WEBHOOK_SECRET غير مضبوط."
            )

        signature = ""
        for key in ("X-Signature", "x-signature", "X-Hub-Signature-256"):
            if key in headers:
                signature = headers[key]
                break

        if not signature:
            raise WebhookVerificationError("الإشعار بلا توقيع.")

        if isinstance(raw_body, str):
            raw_body = raw_body.encode("utf-8")

        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()

        # بعض المزوّدين يسبقون التوقيع بـ"sha256="
        provided = signature.split("=", 1)[-1].strip()

        if not hmac.compare_digest(expected, provided):
            raise WebhookVerificationError("توقيع الإشعار غير صحيح.")

        try:
            event = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise WebhookVerificationError(
                f"جسم الإشعار ليس JSON صالحًا: {exc}"
            ) from exc

        if not isinstance(event, dict):
            raise WebhookVerificationError("جسم الإشعار ليس كائنًا.")

        return event

    def extract_webhook_reference(self, event):
        return self._parse_reference(event) or str(event.get("reference") or "")

    def extract_webhook_status(self, event):
        """
        يترجم حالة المزوّد إلى حالة داخلية.

        `None` تعني "حدث لا يغيّر الحالة" — وهي الحالة الافتراضية
        الصحيحة: حدث غير معروف يجب أن يُتجاهَل لا أن يُخمَّن.
        """
        from payments.models import PaymentStatus

        raw = str(event.get("status") or event.get("event") or "").lower()

        mapping = {
            "succeeded": PaymentStatus.PAID,
            "success": PaymentStatus.PAID,
            "paid": PaymentStatus.PAID,
            "captured": PaymentStatus.PAID,
            "completed": PaymentStatus.PAID,
            "authorized": PaymentStatus.AUTHORIZED,
            "pending": PaymentStatus.PROCESSING,
            "processing": PaymentStatus.PROCESSING,
            "failed": PaymentStatus.FAILED,
            "declined": PaymentStatus.FAILED,
            "error": PaymentStatus.FAILED,
            "cancelled": PaymentStatus.CANCELLED,
            "canceled": PaymentStatus.CANCELLED,
            "refunded": PaymentStatus.REFUNDED,
        }

        return mapping.get(raw)
