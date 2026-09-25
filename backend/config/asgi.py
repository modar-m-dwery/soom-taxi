import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()  # يجب أن يُستدعى قبل أي import لموديلات Django

from django.conf import settings  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from realtime.auth_middleware import TokenAuthMiddlewareStack  # noqa: E402
from realtime.routing import websocket_urlpatterns  # noqa: E402


# ---------------------------------------------------------------
# خدمة الملفّات الساكنة تحت daphne
#
# `runserver` يلفّ التطبيق تلقائيًا بـASGIStaticFilesHandler، أمّا daphne
# فلا يفعل — لا يخدم /static/ إطلاقًا. والنتيجة أنّ /api/docs/ تُعيد صفحة
# HTML سليمة بينما كلّ ملفّات Swagger UI (القادمة من drf-spectacular-sidecar)
# تُعيد 404، فتظهر الصفحة بيضاء. وهذا بالضبط ما يحدث عند التشغيل بدوكر.
#
# الحلّ هنا للتطوير فقط. في الإنتاج يخدم Nginx مجلّد staticfiles/ مباشرة،
# فاضبط SERVE_STATIC_FILES=False.
# ---------------------------------------------------------------
if getattr(settings, "SERVE_STATIC_FILES", settings.DEBUG):
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402

    http_application = ASGIStaticFilesHandler(django_asgi_app)
else:
    http_application = django_asgi_app


application = ProtocolTypeRouter(
    {
        "http": http_application,
        "websocket": TokenAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)