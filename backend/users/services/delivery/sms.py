"""
مزوّد رسائل عبر HTTP — قالب عامل جاهز للاشتراك.

معظم بوابات الرسائل تقبل POST بـJSON فيه المستقبِل والنصّ ومعرّف المُرسِل.
هذا الصنف ينفّذ ذلك مع المهل وتصنيف الفشل، ويعزل ما يختلف بين المزوّدين
في دالّتين تُعادان بالوراثة:

    _payload()   شكل جسم الطلب
    _headers()   شكل المصادقة

للاشتراك بمزوّد سوري أو دولي:

    class MyProviderBackend(HTTPSMSBackend):
        name = "my_provider"
        settings_prefix = "MYPROVIDER"

        def _payload(self, phone, message):
            return {"to": phone, "text": message, "from": self.sender_id}

ثم سطر واحد:  OTP_DELIVERY_BACKEND = "users.services.delivery.sms.MyProviderBackend"
"""
import json
import logging

from django.conf import settings

from users.services.delivery.base import (
    DeliveryResult,
    NotConfigured,
    OTPDeliveryBackend,
)


logger = logging.getLogger(__name__)

#: قصيرة عمدًا: رمز الدخول يصلح خمس دقائق، ومزوّد لا يردّ خلال عشر ثوانٍ
#: لن يُسعف مستخدمًا ينتظر أمام شاشة الإدخال.
DEFAULT_TIMEOUT_SECONDS = 10

TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class HTTPSMSBackend(OTPDeliveryBackend):

    name = "http_sms"
    settings_prefix = "SMS"
    timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    # -----------------------------------------------------------------

    def _setting(self, key, default=""):
        return getattr(settings, f"{self.settings_prefix}_{key}", default) or default

    @property
    def endpoint(self):
        return self._setting("ENDPOINT")

    @property
    def api_key(self):
        return self._setting("API_KEY")

    @property
    def sender_id(self):
        return self._setting("SENDER_ID")

    def check_ready(self):
        missing = [
            key for key in ("ENDPOINT", "API_KEY") if not self._setting(key)
        ]

        if missing:
            raise NotConfigured(
                f"{self.settings_prefix}: الإعدادات الناقصة {', '.join(missing)}."
            )

        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise NotConfigured(f"اعتمادية ناقصة: {exc}") from exc

        return True

    # -- نقاط التخصيص --------------------------------------------------

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _payload(self, phone, message):
        payload = {"to": phone, "message": message}
        if self.sender_id:
            payload["sender"] = self.sender_id
        return payload

    def _classify(self, status_code, data):
        """4xx دائم عدا المستثنيات، 5xx عابر."""
        if status_code in TRANSIENT_HTTP_CODES:
            return False
        return 400 <= status_code < 500

    def _reference(self, data):
        for key in ("message_id", "id", "reference", "messageId"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    # -----------------------------------------------------------------

    def send(self, phone, code, context=None):
        self.check_ready()

        import requests

        message = self.build_message(code)

        try:
            response = requests.post(
                self.endpoint,
                data=json.dumps(self._payload(phone, message)),
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            # لا نسجّل الرمز ولا النصّ — فقط الرقم وسبب الفشل.
            logger.warning("فشل إرسال OTP إلى %s: %s", phone, exc)
            return DeliveryResult.transient(f"فشل الاتصال بمزوّد الرسائل: {exc}")

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        if 200 <= response.status_code < 300:
            return DeliveryResult.success(reference=self._reference(data))

        error = (
            data.get("message")
            or data.get("error")
            or getattr(response, "text", "")[:200]
        )
        detail = f"{response.status_code}: {error}"

        if self._classify(response.status_code, data):
            return DeliveryResult.permanent(detail)

        return DeliveryResult.transient(detail)
