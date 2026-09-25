from django.contrib import admin

from .models import RideOffer


@admin.register(RideOffer)
class RideOfferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ride",
        "driver",
        "gross_fare",
        "eta_minutes",
        "status",
        "expires_at",
        "accepted_at",
        "created_at",
    )

    list_filter = (
        "status",
    )

    search_fields = (
        "driver__user__phone",
        "driver__user__name",
    )

    list_select_related = (
        "ride",
        "driver",
        "driver__user",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "accepted_at",
    )


from django.contrib import admin

from .models import (
    SharedJoinRequest,
    SharedRideGroup,
    SharedRideGroupMember,
    ScheduledSharedTrip,
    ScheduledSharedTripMember,
)


@admin.register(SharedJoinRequest)
class SharedJoinRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "host_ride",
        "host_offer",
        "candidate_ride",
        "compatibility_score",
        "scoring_strategy",
        "status",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "status",
        "scoring_strategy",
    )

    search_fields = (
        "host_ride__customer__phone",
        "candidate_ride__customer__phone",
    )

    list_select_related = (
        "host_ride",
        "host_offer",
        "candidate_ride",
    )


class SharedRideGroupMemberInline(admin.TabularInline):
    model = SharedRideGroupMember
    extra = 0


@admin.register(SharedRideGroup)
class SharedRideGroupAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "host_offer",
        "driver",
        "vehicle",
        "status",
        "total_passengers_display",
        "remaining_capacity_display",
        "created_at",
    )

    list_filter = (
        "status",
    )

    search_fields = (
        "driver__user__phone",
        "driver__user__name",
        "vehicle__plate_number",
    )

    inlines = [
        SharedRideGroupMemberInline,
    ]

    @admin.display(description="Passengers")
    def total_passengers_display(self, obj):
        return obj.total_passengers

    @admin.display(description="Remaining")
    def remaining_capacity_display(self, obj):
        return obj.remaining_capacity


class ScheduledSharedTripMemberInline(admin.TabularInline):
    model = ScheduledSharedTripMember
    extra = 0


@admin.register(ScheduledSharedTrip)
class ScheduledSharedTripAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver",
        "vehicle",
        "scheduled_at",
        "capacity",
        "status",
        "total_reserved_display",
        "remaining_capacity_display",
    )

    list_filter = (
        "status",
        "scheduled_at",
    )

    search_fields = (
        "driver__user__phone",
        "driver__user__name",
        "vehicle__plate_number",
    )

    inlines = [
        ScheduledSharedTripMemberInline,
    ]

    @admin.display(description="Reserved")
    def total_reserved_display(self, obj):
        return obj.total_reserved_passengers

    @admin.display(description="Remaining")
    def remaining_capacity_display(self, obj):
        return obj.remaining_capacity

from .models import RideInvitation


@admin.register(RideInvitation)
class RideInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "ride", "driver", "status", "ttl_seconds",
        "quoted_fare", "eta_minutes", "approximate_distance_m",
        "sent_at", "expires_at", "responded_at",
    )
    list_filter = ("status", "pricing_policy")
    search_fields = ("driver__user__phone", "driver__user__name", "ride__id")
    list_select_related = ("ride", "driver", "driver__user", "vehicle")
    readonly_fields = ("sent_at", "updated_at", "responded_at")