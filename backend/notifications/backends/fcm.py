"""
مزوّد Firebase Cloud Messaging عبر HTTP v1.

لماذا لا نستعمل مكتبة firebase-admin؟ لأنها تجرّ اعتمادية كبيرة من أجل
نداءَي HTTP، ولأن الجزء الوحيد المتغيّر هنا هو الحصول على رمز OAuth -
وهو ما تفعله google-auth وحدها.

إن لم تُضبط بيانات الاعتماد، يرفع NotConfigured، والخدمة تعلّم الإشعار
"متخطّى" لا "فاشل". الفرق ليس لفظيًا: الفاشل يُعاد إلى ما لا نهاية،
والمتخطّى يُترك بسلام إلى أن يصبح المزوّد جاهزًا.
"""
import json

from django.conf import settings

from notifications.backends.base import BaseBackend, NotConfigured, SendResult


FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

# رموز يعتبرها المزوّد نهائية: الرمز نفسه لم يعد صالحًا
PERMANENT_ERRORS = {
    "UNREGISTERED",
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "SENDER_ID_MISMATCH",
}


class FCMBackend(BaseBackend):

    name = "fcm"

    def __init__(self):
        self._credentials = None
        self._project_id = getattr(settings, "FCM_PROJECT_ID", "") or ""
        self._service_account = (
            getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", "") or ""
        )

    # -------------------------------------------------------------

    def check_ready(self):
        if not self._project_id or not self._service_account:
            raise NotConfigured(
                "FCM_PROJECT_ID و FCM_SERVICE_ACCOUNT_FILE غير مضبوطين."
            )

        try:
            from google.oauth2 import service_account  # noqa: F401
            import requests  # noqa: F401
        except ImportError as exc:
            raise NotConfigured(f"اعتمادية ناقصة: {exc}")

        return True

    def _token(self):
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        if self._credentials is None:
            self._credentials = (
                service_account.Credentials.from_service_account_file(
                    self._service_account, scopes=SCOPES
                )
            )

        if not self._credentials.valid:
            self._credentials.refresh(Request())

        return self._credentials.token

    # -------------------------------------------------------------

    def send(self, token, notification):
        import requests

        payload = {
            "message": {
                "token": token.token,
                "notification": {
                    "title": notification.title,
                    "body": notification.body,
                },
                # كل القيم نصوص: FCM يرفض غيرها في data
                "data": {
                    str(key): str(value)
                    for key, value in (notification.data or {}).items()
                },
                "android": {
                    "priority": (
                        "HIGH" if notification.priority == "urgent" else "NORMAL"
                    ),
                    # collapse_key: دعوتان للسائق نفسه لا تتكدّسان على شاشته
                    "collapse_key": notification.event_type,
                    "ttl": self._ttl_seconds(notification),
                    # القناة تحدّد شكل الظهور على أندرويد 8+: العاجل (دعوة،
                    # السائق وصل) ينبثق فوق الشاشة بصوت، والباقي هادئ. القناتان
                    # يُنشئهما التطبيق عند أوّل إقلاع.
                    "notification": {
                        "channel_id": (
                            "soum_urgent"
                            if notification.priority == "urgent"
                            else "soum_general"
                        ),
                        "sound": "default",
                    },
                },
                "apns": {
                    "headers": {
                        "apns-priority": (
                            "10" if notification.priority == "urgent" else "5"
                        ),
                    },
                },
            }
        }

        try:
            response = requests.post(
                FCM_ENDPOINT.format(project_id=self._project_id),
                headers={
                    "Authorization": f"Bearer {self._token()}",
                    "Content-Type": "application/json; UTF-8",
                },
                data=json.dumps(payload),
                timeout=10,
            )
        except Exception as exc:
            return SendResult.transient(exc)

        if response.status_code == 200:
            return SendResult.success()

        detail = self._error_code(response)

        if detail in PERMANENT_ERRORS or response.status_code in (400, 404):
            return SendResult.permanent(f"{response.status_code}:{detail}")

        return SendResult.transient(f"{response.status_code}:{detail}")

    # -------------------------------------------------------------

    @staticmethod
    def _ttl_seconds(notification):
        """
        نمرّر مهلة الإشعار إلى FCM نفسه: جهاز خارج التغطية لن يتسلّم
        دعوةً انقضت، فلا داعي أن يحتفظ بها المزوّد ثم يوصلها متأخرة.
        """
        from django.utils import timezone

        if notification.expires_at is None:
            return "3600s"

        remaining = int((notification.expires_at - timezone.now()).total_seconds())
        return f"{max(remaining, 0)}s"

    @staticmethod
    def _error_code(response):
        try:
            body = response.json()
            return (
                body.get("error", {})
                .get("details", [{}])[0]
                .get("errorCode")
                or body.get("error", {}).get("status")
                or ""
            )
        except Exception:
            return response.text[:120]
