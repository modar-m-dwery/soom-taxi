from django.urls import path

from ops.views_audit import AuditRideStoryView, AuditSearchView
from ops.views_metrics import OpsMetricsSeriesView, OpsMetricsView
from ops.views import (
    OpsActionLogView,
    OpsAttentionView,
    OpsDriverStatusView,
    OpsForceCancelView,
    OpsForceCompleteView,
    OpsLiveDriversView,
    OpsOverviewView,
    OpsReleaseDriverView,
)


# تُضمَّن تحت api/v1/ في config/urls.py
urlpatterns = [
    # القراءة
    path("ops/overview/", OpsOverviewView.as_view(), name="ops-overview"),
    path("ops/attention/", OpsAttentionView.as_view(), name="ops-attention"),
    path("ops/drivers/live/", OpsLiveDriversView.as_view(), name="ops-live-drivers"),
    path("ops/actions/", OpsActionLogView.as_view(), name="ops-actions"),

    # المؤشّرات — نِسب عبر نافذة زمنية لا عدّادات لحظية
    path("ops/metrics/", OpsMetricsView.as_view(), name="ops-metrics"),
    path(
        "ops/metrics/series/",
        OpsMetricsSeriesView.as_view(),
        name="ops-metrics-series",
    ),

    # سجلّ التدقيق — كلّ انتقال حالة في المنصّة
    path("ops/audit/", AuditSearchView.as_view(), name="ops-audit"),
    path(
        "ops/audit/ride/<int:ride_id>/",
        AuditRideStoryView.as_view(),
        name="ops-audit-ride",
    ),

    # التدخّل
    path(
        "ops/drivers/<int:target_id>/release/",
        OpsReleaseDriverView.as_view(),
        name="ops-release-driver",
    ),
    path(
        "ops/drivers/<int:target_id>/status/",
        OpsDriverStatusView.as_view(),
        name="ops-driver-status",
    ),
    path(
        "ops/rides/<int:target_id>/force-complete/",
        OpsForceCompleteView.as_view(),
        name="ops-force-complete",
    ),
    path(
        "ops/rides/<int:target_id>/force-cancel/",
        OpsForceCancelView.as_view(),
        name="ops-force-cancel",
    ),
]
