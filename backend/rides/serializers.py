from rest_framework import serializers

from rides.models import RideRequest, RideMode, RideSubscription, TripCategory
from vehicles.fields import VehicleCategoryCodeField


class CreateRideRequestSerializer(serializers.Serializer):

    # يُتحقَّق منه من القاعدة لا من enum: الفئات صارت صفوفًا يضيفها المشغّل،
    # وقائمةٌ مجمَّدة وقت الاستيراد ترفض فئةً أُضيفت بعد آخر إقلاع.
    requested_vehicle_type = VehicleCategoryCodeField(
        required=False,
        allow_null=True,
    )

    pickup_lat = serializers.FloatField()

    pickup_lng = serializers.FloatField()

    destination_lat = serializers.FloatField()

    destination_lng = serializers.FloatField()

    mode = serializers.ChoiceField(
        choices=RideMode.choices
    )

    passenger_count = serializers.IntegerField(
        min_value=1,
        max_value=8,
    )

    scheduled_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )

    trip_category = serializers.ChoiceField(
        choices=TripCategory.choices,
        required=False,
        default=TripCategory.CITY,
    )

    origin_city = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=100,
    )

    destination_city = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=100,
    )

    # نطاق البحث من خيارات المنطقة (`geometry.search_radius_options_km`).
    search_radius_km = serializers.FloatField(
        required=False,
        allow_null=True,
        min_value=0.1,
        max_value=100,
    )

    # «الأقرب»: الخادم يدعو أقرب سائق بالتتابع.
    auto_dispatch = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):

        category = attrs.get("trip_category", TripCategory.CITY)

        if category == TripCategory.RECREATIONAL:
            raise serializers.ValidationError(
                "Recreational trips must be booked via /matching/trips/<id>/book/."
            )

        if category in (TripCategory.INTERCITY, TripCategory.SERVICE_LINE):
            if not attrs.get("origin_city") or not attrs.get("destination_city"):
                raise serializers.ValidationError(
                    "origin_city and destination_city are required for this trip category."
                )

        return attrs


class ProposeFareSerializer(serializers.Serializer):
    # نصّ عشريّ كبقيّة المال — لا float.
    proposed_fare = serializers.DecimalField(max_digits=12, decimal_places=2)


class RideRequestSerializer(serializers.ModelSerializer):

    pickup_lat = serializers.SerializerMethodField()

    pickup_lng = serializers.SerializerMethodField()

    destination_lat = serializers.SerializerMethodField()

    destination_lng = serializers.SerializerMethodField()

    # شارةٌ للسائق: كم مخالفة إلغاء متأخّر على صاحب الطلب هذا الأسبوع.
    customer_late_cancels = serializers.SerializerMethodField()

    def get_customer_late_cancels(self, obj) -> int:
        from trips.services.cancellation import CancellationPolicy

        return CancellationPolicy.customer_strikes(obj.customer, obj.service_area)

    class Meta:

        model = RideRequest

        fields = [

            "id",

            "requested_vehicle_type",

            "pickup_lat",
            "pickup_lng",

            "destination_lat",
            "destination_lng",

            "mode",

            "trip_category",
            "origin_city",
            "destination_city",
            "published_trip",

            "passenger_count",

            "scheduled_at",

            "search_radius_km",
            "auto_dispatch",
            "customer_late_cancels",

            "status",

            "expires_at",

            # Haversine
            "estimated_distance_km",
            "estimated_duration_minutes",

            # المسار — provider أو estimated، راجع route_source
            "route_distance_km",
            "route_duration_minutes",
            "route_geometry",
            "route_source",

            # Pricing
            "base_fare",
            "distance_fare",
            "time_fare",
            "gross_fare",
            "platform_fee",
            "customer_total",
            "driver_net",
            "pricing_policy",
            "currency",
            "fare_floor",
            "fare_cap",
            "customer_proposed_fare",
            "surge_multiplier",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_pickup_lat(self, obj) -> float | None:

        return obj.pickup.y

    def get_pickup_lng(self, obj) -> float | None:

        return obj.pickup.x

    def get_destination_lat(self, obj) -> float | None:

        return obj.destination.y

    def get_destination_lng(self, obj) -> float | None:

        return obj.destination.x

class RideSubscriptionSerializer(serializers.ModelSerializer):
    """اشتراك الصباح كما يقرؤه التطبيق ويكتبه."""

    pickup_lat = serializers.FloatField(write_only=True)
    pickup_lng = serializers.FloatField(write_only=True)
    destination_lat = serializers.FloatField(write_only=True)
    destination_lng = serializers.FloatField(write_only=True)
    pickup = serializers.SerializerMethodField(read_only=True)
    destination = serializers.SerializerMethodField(read_only=True)
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        help_text="0=الاثنين … 6=الأحد. فارغ = الأحد–الخميس.",
    )
    requested_vehicle_type = VehicleCategoryCodeField(required=False, allow_null=True)
    next_occurrence = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RideSubscription
        fields = [
            "id", "label", "pickup", "destination",
            "pickup_lat", "pickup_lng", "destination_lat", "destination_lng",
            "departure_time", "weekdays", "mode", "passenger_count",
            "requested_vehicle_type", "lead_minutes", "is_active",
            "last_materialized_on", "next_occurrence", "created_at",
        ]
        read_only_fields = ["id", "is_active", "last_materialized_on", "created_at"]

    @staticmethod
    def _point(point):
        return {"lat": point.y, "lng": point.x} if point else None

    def get_pickup(self, obj) -> dict | None:
        return self._point(obj.pickup)

    def get_destination(self, obj) -> dict | None:
        return self._point(obj.destination)

    def get_next_occurrence(self, obj) -> str | None:
        from rides.services.subscription import SubscriptionService

        when = SubscriptionService.next_occurrence(obj)
        return when.isoformat() if when else None

    def validate_weekdays(self, value):
        return sorted(set(value))

    def validate_passenger_count(self, value):
        if not 1 <= value <= 8:
            raise serializers.ValidationError("عدد الركّاب بين 1 و8.")
        return value

    def create(self, validated):
        from django.contrib.gis.geos import Point

        pickup = Point(validated.pop("pickup_lng"), validated.pop("pickup_lat"), srid=4326)
        destination = Point(
            validated.pop("destination_lng"), validated.pop("destination_lat"), srid=4326,
        )
        return RideSubscription.objects.create(
            customer=self.context["request"].user,
            pickup=pickup, destination=destination, **validated,
        )
