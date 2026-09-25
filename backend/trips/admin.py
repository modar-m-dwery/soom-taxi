from django.contrib import admin

from trips.models import Trip, TripCompletionRecord, TripLocation


class TripLocationInline(admin.TabularInline):
    model = TripLocation
    extra = 0
    max_num = 0
    can_delete = False
    readonly_fields = ("location", "speed", "heading", "accuracy", "source", "timestamp")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "id", "ride", "driver", "customer", "status",
        "final_fare", "distance_m", "duration_s", "gps_points_count",
        "pickup_verified", "dropoff_verified", "needs_review",
        "started_at", "completed_at",
    )
    list_filter = ("status", "needs_review", "pickup_verified", "dropoff_verified")
    search_fields = (
        "ride__id", "driver__user__phone", "driver__user__name", "customer__phone",
    )
    list_select_related = ("ride", "driver", "driver__user", "customer", "vehicle")
    readonly_fields = (
        "created_at", "arriving_at", "arrived_at", "started_at",
        "completed_at", "cancelled_at", "updated_at",
    )
    inlines = [TripLocationInline]


@admin.register(TripCompletionRecord)
class TripCompletionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id", "trip", "completed_at", "distance_m", "duration_s",
        "final_fare", "currency", "completion_source",
        "gps_start_verified", "gps_arrival_verified", "gps_end_verified",
    )
    list_filter = ("completion_source", "gps_end_verified")
    search_fields = ("trip__id", "trip__ride__id")
    readonly_fields = [f.name for f in TripCompletionRecord._meta.fields]


from trips.models import CancellationRecord  # noqa: E402


@admin.register(CancellationRecord)
class CancellationRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ride", "actor", "kind", "strikes", "customer", "driver")
    list_filter = ("actor", "kind")
    search_fields = ("customer__phone", "driver__user__phone", "reason")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in CancellationRecord._meta.fields]

    def has_add_permission(self, request):
        return False
