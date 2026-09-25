from rest_framework import serializers

from trips.models import Trip, TripCompletionRecord, TripLocation


class TripLocationSerializer(serializers.ModelSerializer):
    lng = serializers.SerializerMethodField()
    lat = serializers.SerializerMethodField()

    class Meta:
        model = TripLocation
        fields = ["lng", "lat", "speed", "heading", "accuracy", "source", "timestamp"]

    def get_lng(self, obj) -> float | None:
        return obj.location.x

    def get_lat(self, obj) -> float | None:
        return obj.location.y


class TripCompletionRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripCompletionRecord
        fields = [
            "completed_at", "start_time", "end_time",
            "distance_m", "duration_s", "final_fare", "currency",
            "gps_start_verified", "gps_arrival_verified", "gps_end_verified",
            "gps_points_count", "completion_source",
        ]
        read_only_fields = fields


class TripSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source="driver.user.name", read_only=True)
    driver_rating = serializers.DecimalField(
        source="driver.rating", max_digits=3, decimal_places=2, read_only=True
    )
    vehicle_type = serializers.CharField(source="vehicle.type_id", read_only=True)
    vehicle_make = serializers.CharField(source="vehicle.make", read_only=True)
    vehicle_model = serializers.CharField(source="vehicle.model", read_only=True)
    vehicle_color = serializers.CharField(source="vehicle.color", read_only=True)
    vehicle_plate = serializers.CharField(source="vehicle.plate_number", read_only=True)

    # الطرفان يحتاجان الاتّصال ببعضهما أثناء الرحلة: «أنا عند الباب الخلفي».
    # الرقم يُعطى ما دامت الرحلة نشطة وحدها، ثمّ يُحجب — السجلّ القديم لا
    # يصير دفتر أرقام. والمسلسِل لا يصل غير طرفَي الرحلة (غرفتها ومالكاها).
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    driver_phone = serializers.SerializerMethodField()

    def get_customer_name(self, obj) -> str:
        name = (getattr(obj.customer, "name", "") or "").strip()
        return name.split()[0] if name else ""

    def get_customer_phone(self, obj) -> str | None:
        return obj.customer.phone if obj.is_active else None

    def get_driver_phone(self, obj) -> str | None:
        return obj.driver.user.phone if obj.is_active else None

    class Meta:
        model = Trip
        fields = [
            "id", "ride", "status",
            "driver", "driver_name", "driver_rating", "driver_phone",
            "customer_name", "customer_phone",
            "vehicle_type", "vehicle_make", "vehicle_model",
            "vehicle_color", "vehicle_plate",
            "created_at", "arriving_at", "arrived_at",
            "started_at", "completed_at", "cancelled_at",
            "distance_m", "duration_s", "gps_points_count",
            "final_fare", "currency",
            "pickup_verified", "dropoff_verified",
            "needs_review", "review_reason",
            "cancelled_by", "cancel_reason",
        ]
        read_only_fields = fields


class CancelTripSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class DriverCancelTripSerializer(serializers.Serializer):
    # إلزاميّ للسائق: الإدارة تقرأ لماذا يلغي، والنمط يكشف المتلاعب.
    reason = serializers.CharField(min_length=3, max_length=255)


# =====================================================================
# استعادة الحالة والسجلّ
# =====================================================================

class RealtimeRoomsSerializer(serializers.Serializer):
    """مسارات WebSocket الجاهزة للاشتراك. يبنيها الخادم لا التطبيق."""

    ride_room = serializers.CharField(allow_null=True)
    driver_room = serializers.CharField(allow_null=True)


class ActiveRideSnapshotSerializer(serializers.Serializer):
    """
    لقطة كاملة لحالة المستخدم. النقطة الأولى التي يناديها التطبيق عند
    الإقلاع، والوحيدة التي لا تحتاج معرفة `ride_id` مسبقًا.
    """

    has_active_ride = serializers.BooleanField()
    role = serializers.ChoiceField(choices=["customer", "driver"])
    stage = serializers.CharField(
        help_text=(
            "idle | searching | choosing_offer | driver_assigned | "
            "driver_arriving | driver_arrived | in_progress | awaiting_payment"
        )
    )
    ride = serializers.SerializerMethodField()
    trip = serializers.SerializerMethodField()
    pending_payment = serializers.SerializerMethodField()
    realtime = RealtimeRoomsSerializer()
    other_trips = serializers.SerializerMethodField(
        help_text="للسائق في رحلة مشتركة: رحلات الركّاب الآخرين النشطة، كلٌّ بـride وtrip.",
    )

    def get_other_trips(self, obj) -> list[dict]:
        from rides.serializers import RideRequestSerializer

        return [
            {
                "ride": RideRequestSerializer(entry["ride"]).data,
                "trip": TripSerializer(entry["trip"]).data if entry["trip"] else None,
                # المسار يبنيه الخادم كما في `realtime.ride_room` — لا التطبيق.
                "ride_room": f"/ws/rides/{entry['ride'].id}/",
            }
            for entry in obj.get("other_trips") or []
        ]

    def get_ride(self, obj) -> dict | None:
        from rides.serializers import RideRequestSerializer

        ride = obj.get("ride")
        return RideRequestSerializer(ride).data if ride is not None else None

    def get_trip(self, obj) -> dict | None:
        trip = obj.get("trip")
        return TripSerializer(trip).data if trip is not None else None

    def get_pending_payment(self, obj) -> dict | None:
        payment = obj.get("pending_payment")

        if payment is None:
            return None

        from payments.serializers import PaymentSerializer

        return PaymentSerializer(payment).data
