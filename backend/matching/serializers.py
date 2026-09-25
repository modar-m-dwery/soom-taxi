from decimal import Decimal

from drf_spectacular.utils import (
    extend_schema_serializer,
    OpenApiExample,
)
from rest_framework import serializers

from matching.models import (
    RideOffer,
    SharedRideGroup,
    ScheduledSharedTrip,
)


#: تقريب الإحداثيات المعروضة علنًا. ثلاث خانات عشرية ≈ 110 مترًا —
#: نفس الدقّة المستعملة في خريطة السيارات القريبة (matching/services/nearby.py)
#: وفي غرفة السوق (realtime/marketplace.py). كافية لرسم نقطة على خريطة،
#: وغير كافية لتتبّع بابِ مَن.
PUBLIC_COORD_PRECISION = 3


def _public_point(point):
    """نقطة مقرَّبة صالحة للعرض العامّ، أو None."""
    if point is None:
        return None
    return {
        "lat": round(point.y, PUBLIC_COORD_PRECISION),
        "lng": round(point.x, PUBLIC_COORD_PRECISION),
    }


class ScheduledSharedTripSerializer(
    serializers.ModelSerializer
):

    driver_id = serializers.IntegerField(
        source="driver.id",
        read_only=True,
    )

    driver_name = serializers.CharField(
        source="driver.user.name",
        read_only=True,
    )

    driver_rating = serializers.DecimalField(
        source="driver.rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    vehicle_type = serializers.CharField(
        source="vehicle.type_id",
        read_only=True,
    )

    vehicle_make = serializers.CharField(
        source="vehicle.make",
        read_only=True,
    )

    vehicle_model = serializers.CharField(
        source="vehicle.model",
        read_only=True,
    )

    vehicle_color = serializers.CharField(
        source="vehicle.color",
        read_only=True,
    )

    remaining_capacity = serializers.IntegerField(
        read_only=True,
    )

    total_reserved_passengers = serializers.IntegerField(
        read_only=True,
    )

    # الحقلان كانا يخرجان خامَّين في كتالوج عامّ بلا مصادقة، بجانب اسم
    # السائق وتقييمه ومركبته — أي إحداثيات انطلاق دقيقة مربوطة بهويّة
    # وموعد. وهذا يناقض التقريب المطبَّق في كلّ مكان آخر في المشروع.
    pickup = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()

    def get_pickup(self, obj) -> dict | None:
        return _public_point(obj.pickup)

    def get_destination(self, obj) -> dict | None:
        return _public_point(obj.destination)

    class Meta:
        model = ScheduledSharedTrip

        fields = [
            "id",

            "trip_category",
            "title",
            "description",
            "origin_city",
            "destination_city",
            "price_per_seat",
            "features",

            "driver_id",
            "driver_name",
            "driver_rating",

            "vehicle_type",
            "vehicle_make",
            "vehicle_model",
            "vehicle_color",

            "scheduled_at",

            # مقرَّبتان لا خامّتان — راجع get_pickup/get_destination
            "pickup",
            "destination",

            "capacity",

            "total_reserved_passengers",
            "remaining_capacity",

            "status",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Intercity",
            request_only=True,
            value={
                "vehicle_id": 12,
                "trip_category": "intercity",
                "scheduled_at": "2027-01-15T09:00:00Z",
                "capacity": 4,
                "pickup_lat": 33.5138,
                "pickup_lng": 36.2765,
                "destination_lat": 34.7300,
                "destination_lng": 36.7000,
                "origin_city": "Damascus",
                "destination_city": "Homs",
                "price_per_seat": "10.00",
            },
        ),
    ]
)
class PublishTripSerializer(serializers.Serializer):
    """يستخدمها السائق/لوحة التحكم لنشر رحلة سفريات/سرفيس/ترفيهية."""

    vehicle_id = serializers.IntegerField()

    trip_category = serializers.ChoiceField(
        choices=[
            ("intercity", "Intercity"),
            ("service_line", "Service Line"),
            ("recreational", "Recreational"),
        ]
    )

    scheduled_at = serializers.DateTimeField()

    capacity = serializers.IntegerField(min_value=1)

    pickup_lat = serializers.FloatField()
    pickup_lng = serializers.FloatField()
    destination_lat = serializers.FloatField()
    destination_lng = serializers.FloatField()

    origin_city = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=100,
    )
    destination_city = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=100,
    )

    price_per_seat = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
    )

    title = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=150,
    )

    description = serializers.CharField(
        required=False, allow_null=True, allow_blank=True,
    )

    features = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )

    def validate(self, attrs):
        category = attrs["trip_category"]

        if category in ("intercity", "service_line"):
            if not attrs.get("origin_city") or not attrs.get("destination_city"):
                raise serializers.ValidationError(
                    "origin_city and destination_city are required for this trip category."
                )

        return attrs


class BookTripSerializer(serializers.Serializer):
    passenger_count = serializers.IntegerField(
        min_value=1,
        max_value=8,
        default=1,
    )


class CreateRideOfferSerializer(
    serializers.Serializer
):
    gross_fare = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        # Decimal لا float: الحقل نفسه عشري، ومقارنة قيمة عشرية بحدّ
        # ثنائي هي كيف يمرّ سعر يجب أن يُرفض عند الحافة تمامًا.
        # وDRF يحذّر من هذا صراحةً عند كل إقلاع.
        min_value=Decimal("0.01"),
    )

    eta_minutes = serializers.IntegerField(
        min_value=1,
    )


class RideOfferSerializer(serializers.ModelSerializer):
    driver_id = serializers.IntegerField(source="driver.id", read_only=True)
    driver_name = serializers.CharField(source="driver.user.name", read_only=True)
    driver_rating = serializers.DecimalField(
        source="driver.rating", max_digits=3, decimal_places=2, read_only=True
    )
    vehicle = serializers.SerializerMethodField()

    class Meta:
        model = RideOffer
        fields = [
            "id", "ride", "driver_id", "driver_name", "driver_rating",
            "vehicle", "gross_fare", "eta_minutes", "status",
            "expires_at", "created_at", "updated_at", "accepted_at",
        ]
        read_only_fields = fields

    def get_vehicle(self, obj) -> dict | None:
        vehicle = next(
            (v for v in obj.driver.vehicles.all() if v.active), None
        )
        if not vehicle:
            return None
        return {
            "type": vehicle.type_id,
            "make": vehicle.make,
            "model": vehicle.model,
            "color": vehicle.color,
            "plate_number": vehicle.plate_number,
        }


class SharedJoinOfferSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    compatibility_score = serializers.DecimalField(max_digits=5, decimal_places=1)
    expires_at = serializers.DateTimeField()

    vehicle_type = serializers.SerializerMethodField()
    vehicle_make_model = serializers.SerializerMethodField()
    seats_available = serializers.SerializerMethodField()
    fare_estimate = serializers.SerializerMethodField()
    eta_minutes = serializers.SerializerMethodField()
    driver_rating = serializers.SerializerMethodField()
    passengers_gender_summary = serializers.SerializerMethodField()

    def _vehicle(self, obj):
        return obj.host_offer.driver.vehicles.filter(active=True).first()

    def get_vehicle_type(self, obj) -> str | None:
        v = self._vehicle(obj)
        return v.type_id if v else None

    def get_vehicle_make_model(self, obj) -> str | None:
        v = self._vehicle(obj)
        return f"{v.make} {v.model}" if v else None

    def get_seats_available(self, obj) -> int | None:
        try:
            group = obj.host_offer.shared_group
        except SharedRideGroup.DoesNotExist:
            return None
        return group.remaining_capacity

    def get_fare_estimate(self, obj) -> str | None:
        return obj.host_offer.gross_fare

    def get_eta_minutes(self, obj) -> int | None:
        return obj.host_offer.eta_minutes

    def get_driver_rating(self, obj) -> str | None:
        return obj.host_offer.driver.rating

    def get_passengers_gender_summary(self, obj) -> dict | None:
        from django.conf import settings

        if not settings.MATCHING_SHARED_SHOW_GENDER:
            return None

        try:
            group = obj.host_offer.shared_group
        except SharedRideGroup.DoesNotExist:
            return None

        genders = list(
            group.members.values_list("ride__customer__gender", flat=True)
        )

        return {
            "male": genders.count("male"),
            "female": genders.count("female"),
            "undisclosed": genders.count("undisclosed"),
        }


class RideInvitationSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.name", read_only=True)
    driver_rating = serializers.DecimalField(
        source="driver.rating", max_digits=3, decimal_places=2, read_only=True
    )
    vehicle_type = serializers.CharField(source="vehicle.type_id", read_only=True)
    vehicle_make = serializers.CharField(source="vehicle.make", read_only=True)
    vehicle_model = serializers.CharField(source="vehicle.model", read_only=True)
    vehicle_color = serializers.CharField(source="vehicle.color", read_only=True)
    seconds_remaining = serializers.SerializerMethodField()

    class Meta:
        from matching.models import RideInvitation
        model = RideInvitation
        fields = [
            "id", "ride", "driver", "driver_name", "driver_rating",
            "vehicle_type", "vehicle_make", "vehicle_model", "vehicle_color",
            "status", "ttl_seconds", "seconds_remaining",
            "sent_at", "expires_at", "responded_at",
            "approximate_distance_m", "eta_minutes", "available_seats",
            "quoted_fare", "counter_fare", "pricing_policy", "reject_reason",
        ]
        read_only_fields = fields

    def get_seconds_remaining(self, obj) -> int:
        from django.utils import timezone
        if obj.status != "pending":
            return 0
        return max(int((obj.expires_at - timezone.now()).total_seconds()), 0)


class CreateInvitationSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    ttl_seconds = serializers.IntegerField(required=False, allow_null=True)


class RejectInvitationSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class NearbyVehicleSerializer(serializers.Serializer):
    """للتوثيق فقط — الخدمة تُرجع dicts جاهزة."""
    driver_id = serializers.IntegerField()
    driver_name = serializers.CharField()
    rating = serializers.FloatField(allow_null=True)
    vehicle_type = serializers.CharField()
    vehicle_make = serializers.CharField()
    vehicle_model = serializers.CharField()
    vehicle_color = serializers.CharField()
    seats = serializers.IntegerField()
    available_seats = serializers.IntegerField()
    current_occupancy = serializers.IntegerField()
    lng = serializers.FloatField()
    lat = serializers.FloatField()
    heading = serializers.CharField(allow_null=True)
    approximate_distance_m = serializers.IntegerField()
    eta_minutes = serializers.IntegerField()
    quoted_fare = serializers.CharField()
    currency = serializers.CharField()
    is_invited = serializers.BooleanField()
    is_sharing = serializers.BooleanField(
        default=False,
        help_text="سيارة على رحلة مشتركة وفيها مقعد فارغ.",
    )
    onboard_passengers = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="عدد الركّاب على متنها الآن. null لسيارة فارغة.",
    )
    compatibility_score = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="درجة توافق المسار من 100. null لسيارة فارغة.",
    )
    route_bearing = serializers.FloatField(
        required=False, allow_null=True,
        help_text="اتجاه مسارها بالدرجات (0=شمال) لرسم السهم على الخريطة.",
    )
    extra_detour_m = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="كم مترًا يضيف هذا الراكب على طريق الركّاب الحاليين.",
    )