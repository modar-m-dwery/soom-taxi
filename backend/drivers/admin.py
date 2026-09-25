from django.contrib import admin
from django.utils import timezone

from .models import (
    DriverDocument,
    DocumentStatus,
    DocumentType,
)


@admin.register(DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver",
        "type",
        "status",
        "expires_at",
        "is_expired_display",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )

    list_filter = (
        "type",
        "status",
    )

    search_fields = (
        "driver__user__phone",
        "driver__user__name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "reviewed_at",
    )

    actions = [
        "approve_documents",
        "reject_documents",
    ]

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        return obj.is_expired

    @admin.action(description="Approve selected documents")
    def approve_documents(self, request, queryset):
        queryset.update(
            status=DocumentStatus.APPROVED,
            rejection_reason="",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    @admin.action(description="Reject selected documents")
    def reject_documents(self, request, queryset):
        queryset.update(
            status=DocumentStatus.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )