from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from django.conf import settings
from django.contrib import admin

from growth.views import GrowthDashboardView
from integrity.views import IntegrityDashboardView
from ops.views_console import OpsConsoleView
from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings


urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    # لوحة التشغيل (المشغّل) — صفحة واحدة فوق نقاط /api/v1/ops/.
    path("ops/", OpsConsoleView.as_view(), name="ops-console"),
    # النموّ: الطلب والخاملون والعروض — للموظّفين (جلسة الأدمن).
    path("ops/growth/", GrowthDashboardView.as_view(), name="growth-dashboard"),
    # النزاهة: كشف الغش، القضايا، والحسابات المقيّدة — للموظّفين.
    path("ops/integrity/", IntegrityDashboardView.as_view(), name="integrity-dashboard"),
    path("api/v1/", include("growth.urls")),
    path("api/v1/", include("ads.urls")),
    path("api/v1/health/", include("health.urls")),

    # إعداد العميل: أوّل نداء يقوم به التطبيق، وقبل تسجيل الدخول.
    path("api/v1/", include("locations.urls")),

    # users app
    path("api/v1/auth/", include("users.urls")),
    # drivers and vichels
    path("api/v1/vehicles/", include("vehicles.urls")),
    path("api/v1/drivers/", include("drivers.urls")),
    # rides and pricing
    path(
        "api/v1/rides/",
        include("rides.urls"),
    ),
    # matching
    path(
        "api/v1/",
        include("matching.urls"),
    ),
    path(
        "api/v1/",
        include("trips.urls"),
    ),
    path(
        "api/v1/",
        include("feedback.urls"),
    ),
    path(
        "api/v1/",
        include("notifications.urls"),
    ),
    path(
        "api/v1/",
        include("ops.urls"),
    ),
    path(
        "api/v1/",
        include("payments.urls"),
    ),
    path(
        "api/v1/maps/",
        include("maps.urls"),
    ),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema"
        ),
        name="swagger-ui",
    ),

    path(
        "api/redoc/",
        SpectacularRedocView.as_view(
            url_name="schema"
        ),
        name="redoc",
    ),
]


# لا نخدم MEDIA_URL علنًا حتى في التطوير.
#
# المجلّد يحوي صور هويّات ورخصًا. وبيئةُ تطويرٍ تُخدَم على شبكة مكتب
# تكفي لتسريبها، والأسوأ أنّ اختلاف السلوك بين التطوير والإنتاج هو ما
# يجعل ثغرةً كهذه تنجو إلى الإطلاق. الوثائق تُطلب عبر
# /api/v1/drivers/documents/{id}/file/ وهي مفحوصة الملكية.