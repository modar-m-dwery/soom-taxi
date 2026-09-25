from rest_framework import serializers

from drf_spectacular.utils import inline_serializer


ErrorResponse = inline_serializer(
    name="ErrorResponse",
    fields={
        "detail": serializers.CharField(),
    },
)


RateLimitResponse = inline_serializer(
    name="RateLimitResponse",
    fields={
        "detail": serializers.CharField(),
        "retry_after": serializers.IntegerField(),
    },
)


RequestOTPResponse = inline_serializer(
    name="RequestOTPResponse",
    fields={
        "detail": serializers.CharField(),
        "expires_at": serializers.DateTimeField(),
        "development_code": serializers.CharField(
            required=False,
        ),
    },
)


VerifyOTPResponse = inline_serializer(
    name="VerifyOTPResponse",
    fields={
        "token": serializers.CharField(),
        "is_new_user": serializers.BooleanField(),
        "user": serializers.DictField(),
    },
)


BecomeDriverResponse = inline_serializer(
    name="BecomeDriverResponse",
    fields={
        "detail": serializers.CharField(),
        "user_id": serializers.IntegerField(),
        "role": serializers.CharField(),
        "driver_profile_id": serializers.IntegerField(),
        "driver_status": serializers.CharField(),
        "is_new_driver_profile": serializers.BooleanField(),
    },
)


DriverProfileResponse = inline_serializer(
    name="DriverProfileResponse",
    fields={
        "user_id": serializers.IntegerField(),
        "phone": serializers.CharField(),
        "role": serializers.CharField(),
        "status": serializers.CharField(),
        "rating": serializers.DecimalField(
            max_digits=3,
            decimal_places=2,
        ),
        "online": serializers.BooleanField(),
        "current_occupancy": serializers.IntegerField(),
        "available_seats": serializers.IntegerField(),
        "last_location_at": serializers.DateTimeField(
            allow_null=True,
        ),
    },
)


DriverAvailabilityResponse = inline_serializer(
    name="DriverAvailabilityResponse",
    fields={
        "detail": serializers.CharField(),
        "online": serializers.BooleanField(),
        "status": serializers.CharField(),
    },
)


CancelRideResponse = inline_serializer(
    name="CancelRideResponse",
    fields={
        "status": serializers.CharField(),
        "ride_id": serializers.IntegerField(),
    },
)


SharedJoinAcceptResponse = inline_serializer(
    name="SharedJoinAcceptResponse",
    fields={
        "status": serializers.CharField(),
    },
)


ScheduledTripJoinResponse = inline_serializer(
    name="ScheduledTripJoinResponse",
    fields={
        "status": serializers.CharField(),
        "trip_id": serializers.IntegerField(),
        "ride_id": serializers.IntegerField(),
    },
)


BookTripResponse = inline_serializer(
    name="BookTripResponse",
    fields={
        "status": serializers.CharField(),
        "ride_id": serializers.IntegerField(),
        "trip_id": serializers.IntegerField(),
    },
)


RouteResponse = inline_serializer(
    name="RouteResponse",
    fields={
        "distance_km": serializers.FloatField(),
        "duration_minutes": serializers.IntegerField(),
        "geometry": serializers.DictField(
            allow_null=True,
        ),
        "legs": serializers.ListField(
            child=serializers.DictField(),
        ),
        "waypoints": serializers.ListField(
            child=serializers.DictField(),
        ),
    },
)


ScheduledSharedTripWithScoreResponse = inline_serializer(
    name="ScheduledSharedTripWithScoreResponse",
    fields={
        # هذه الحقول موجودة أصلًا في
        # ScheduledSharedTripSerializer.
        "id": serializers.IntegerField(),
        "trip_category": serializers.CharField(),
        "title": serializers.CharField(
            allow_blank=True,
            allow_null=True,
        ),
        "description": serializers.CharField(
            allow_blank=True,
            allow_null=True,
        ),
        "origin_city": serializers.CharField(
            allow_blank=True,
            allow_null=True,
        ),
        "destination_city": serializers.CharField(
            allow_blank=True,
            allow_null=True,
        ),
        "price_per_seat": serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            allow_null=True,
        ),
        "features": serializers.ListField(
            child=serializers.CharField(),
        ),
        "driver_id": serializers.IntegerField(),
        "driver_name": serializers.CharField(
            allow_null=True,
        ),
        "driver_rating": serializers.DecimalField(
            max_digits=3,
            decimal_places=2,
        ),
        "vehicle_type": serializers.CharField(
            allow_null=True,
        ),
        "vehicle_make": serializers.CharField(
            allow_null=True,
        ),
        "vehicle_model": serializers.CharField(
            allow_null=True,
        ),
        "vehicle_color": serializers.CharField(
            allow_null=True,
        ),
        "scheduled_at": serializers.DateTimeField(),
        "pickup": serializers.DictField(),
        "destination": serializers.DictField(),
        "capacity": serializers.IntegerField(),
        "total_reserved_passengers": serializers.IntegerField(),
        "remaining_capacity": serializers.IntegerField(),
        "status": serializers.CharField(),
        "created_at": serializers.DateTimeField(),
        "updated_at": serializers.DateTimeField(),

        # يضاف يدويًا في الـ View.
        "compatibility_score": serializers.DecimalField(
            max_digits=5,
            decimal_places=1,
        ),
    },
)