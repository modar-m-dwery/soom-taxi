"""
وسيط يفتح حادثة لكل طلب ويغلقها بسطر واحد يصف ما جرى.

سطر واحد لكل طلب لا عشرة: ما تحتاجه بعد شهر هو أن ترى في سطر واحد أن
POST /api/v1/rides/ من هذا المستخدم أخذ 2100 مللي ثانية وعاد بـ400 —
ومعرّفه، لتجد به بقيّة القصّة.
"""
import logging
import time

from config.observability.context import bind

logger = logging.getLogger("http")


HEADER = "HTTP_X_REQUEST_ID"

# مسارات لا تُسجَّل: فحص الصحّة يُنادى كل بضع ثوانٍ من المراقبة، وتسجيله
# يدفن كل ما عداه.
QUIET_PATHS = ("/api/v1/health/", "/static/", "/media/")


class RequestContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get(HEADER, "")

        # الطلب يدخل السياق مع المعرّف ويخرج معه. مصادقة DRF تكتب
        # المستخدم على هذا الكائن نفسه، فيراه سجلّ التدقيق داخل الـview
        # مهما أعلنت الـview من أصناف مصادقة — ولا يبقى بعد انتهاء الطلب.
        unbind = bind(request_id=incoming or None, actor="", request=request)

        started = time.monotonic()

        try:
            response = self.get_response(request)
        finally:
            from config.observability.context import get_request_id
            request_id = get_request_id()

        # الهوية تُقرأ بعد الـview لا قبلها.
        #
        # مصادقة DRF تجري داخل الـview لا في وسيط، فـrequest.user هنا قبل
        # التنفيذ مجهول دائمًا. قراءته بعده تعطي المستخدم الحقيقي — وهذا
        # يكفي لأن سطر الملخّص هو الذي يحمل الهوية، بينما الربط بين
        # الأسطر يقع على المعرّف لا على الاسم.
        from config.observability.context import set_actor
        set_actor(self._actor(request))

        duration_ms = int((time.monotonic() - started) * 1000)

        # الترويسة في الردّ: حين يشتكي مستخدم، يكفي أن يرسل هذا الرمز
        response["X-Request-ID"] = request_id

        if not request.path.startswith(QUIET_PATHS):
            level = logging.WARNING if response.status_code >= 400 else logging.INFO

            logger.log(
                level,
                "%s %s -> %s (%sms)",
                request.method, request.path, response.status_code, duration_ms,
                extra={
                    "event": "http.request",
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

        unbind()

        return response

    @staticmethod
    def _actor(request):
        """
        مَن يفعل هذا. الهاتف لا المعرّف الرقمي، لأن أول سؤال في أي شكوى
        هو «أي مستخدم؟» ولا أحد يعرف المستخدم برقم صفّه.

        بلا استعلام إضافي: request.user يُحلّ كسولًا وقد لا يكون مصادَقًا
        بعد في هذه المرحلة من السلسلة، فنقرأه بحذر.
        """
        try:
            user = getattr(request, "user", None)

            if user is None or not user.is_authenticated:
                return "anon"

            return f"user:{getattr(user, 'phone', user.pk)}"
        except Exception:
            return "?"
