from django.contrib import admin

from payments.models import (
    DriverBalance,
    LedgerEntry,
    Payment,
    PaymentAttempt,
    Refund,
)


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    can_delete = False
    readonly_fields = [
        "gateway_code", "action", "ok", "permanent_failure",
        "error", "response_payload", "created_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id", "trip_id", "amount", "currency",
        "gateway_code", "status", "paid_at",
    ]
    list_filter = ["status", "gateway_code", "currency"]
    search_fields = ["id", "trip__id", "gateway_reference", "idempotency_key"]
    date_hierarchy = "created_at"
    inlines = [PaymentAttemptInline]

    # المال لا يُعدَّل من لوحة الإدارة. التغيير يمرّ عبر PaymentService
    # وحدها، وإلّا انفصلت الحالة عن الدفتر بلا أثر.
    readonly_fields = [
        "trip", "customer", "driver", "amount", "platform_fee",
        "driver_net", "amount_refunded", "currency", "gateway_code",
        "gateway_reference", "gateway_payload", "status",
        "idempotency_key", "failure_reason", "attempts",
        "created_at", "updated_at", "paid_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        "id", "created_at", "account", "account_ref",
        "direction", "amount", "currency", "entry_type", "transaction_ref",
    ]
    list_filter = ["account", "direction", "entry_type", "currency"]
    search_fields = ["transaction_ref", "account_ref", "payment__id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["id", "payment_id", "amount", "currency", "status", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["payment__id", "gateway_reference"]
    readonly_fields = [
        "payment", "amount", "currency", "reason", "status",
        "gateway_reference", "idempotency_key", "requested_by",
        "created_at", "completed_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DriverBalance)
class DriverBalanceAdmin(admin.ModelAdmin):
    list_display = [
        "driver_id", "currency", "net_balance",
        "lifetime_earned", "lifetime_commission", "updated_at",
    ]
    list_filter = ["currency"]
    search_fields = ["driver__id", "driver__user__phone"]
    readonly_fields = [
        "driver", "currency", "net_balance",
        "lifetime_earned", "lifetime_commission", "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
