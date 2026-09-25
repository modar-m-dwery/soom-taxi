from django.contrib import admin

from .models import RideRequest


@admin.register(RideRequest)
class RideRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "mode",
        "requested_vehicle_type",
        "passenger_count",
        "status",
        "gross_fare",
        "customer_total",
        "driver_net",
        "scheduled_at",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "mode",
        "status",
        "requested_vehicle_type",
    )

    search_fields = (
        "customer__phone",
        "customer__name",
    )

    list_select_related = (
        "customer",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Customer",
            {
                "fields": (
                    "customer",
                )
            },
        ),
        (
            "Ride",
            {
                "fields": (
                    "mode",
                    "status",
                    "passenger_count",
                    "requested_vehicle_type",
                    "scheduled_at",
                    "expires_at",
                )
            },
        ),
        (
            "Locations",
            {
                "fields": (
                    "pickup",
                    "destination",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": (
                    "base_fare",
                    "distance_fare",
                    "time_fare",
                    "gross_fare",
                    "platform_fee",
                    "customer_total",
                    "driver_net",
                )
            },
        ),
        (
            "Routing",
            {
                "fields": (
                    "estimated_distance_km",
                    "estimated_duration_minutes",
                    "route_distance_km",
                    "route_duration_minutes",
                    "route_geometry",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )