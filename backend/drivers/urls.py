from django.urls import path

from drivers.views_media import DriverDocumentFileView
from drivers.views import (
    AdminDocumentReviewView,
    AdminPendingDocumentsView,
    AdminPendingDriversView,
    AdminSuspendDriverView,
    AdminVerifyDriverView,
    DriverDocumentListCreateView,
    DriverGoOnlineView,
    DriverGoOfflineView,
)

# GET  /api/v1/drivers/documents/
# POST /api/v1/drivers/documents/
# GET  /api/v1/drivers/admin/documents/pending/
# POST /api/v1/drivers/admin/documents/{id}/review/
# GET  /api/v1/drivers/admin/pending/
# POST /api/v1/drivers/admin/{driver_id}/verify/
# POST /api/v1/drivers/admin/{driver_id}/suspend/
# POST /api/v1/drivers/me/go-online/
# POST /api/v1/drivers/me/go-offline/
urlpatterns = [
    path(
        "documents/",
        DriverDocumentListCreateView.as_view(),
        name="driver-documents",
    ),

    # تسليم الملفّ خلف مصادقة — لا عبر /media/ المكشوف
    path(
        "documents/<int:document_id>/file/",
        DriverDocumentFileView.as_view(),
        name="driver-document-file",
    ),

    path(
        "admin/documents/pending/",
        AdminPendingDocumentsView.as_view(),
        name="admin-pending-documents",
    ),

    path(
        "admin/documents/<int:document_id>/review/",
        AdminDocumentReviewView.as_view(),
        name="admin-review-document",
    ),

    path(
        "admin/pending/",
        AdminPendingDriversView.as_view(),
        name="admin-pending-drivers",
    ),

    path(
        "admin/<int:driver_id>/verify/",
        AdminVerifyDriverView.as_view(),
        name="admin-verify-driver",
    ),

    path(
        "admin/<int:driver_id>/suspend/",
        AdminSuspendDriverView.as_view(),
        name="admin-suspend-driver",
    ),
    path(
        "me/go-online/",
        DriverGoOnlineView.as_view(),
        name="driver-go-online",
    ),

    path(
        "me/go-offline/",
        DriverGoOfflineView.as_view(),
        name="driver-go-offline",
    ),
]