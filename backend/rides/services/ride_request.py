from datetime import timedelta

from math import (
    radians,
    sin,
    cos,
    sqrt,
    atan2,
)

from django.db import transaction
from django.utils import timezone

from pricing.services import PricingService

from rides.models import (
    RideRequest,
    RideMode,
    RideStatus,
    TripCategory,
)

from vehicles.models import VehicleCategory

from maps.services.routing import (
    RoutingError,
    RoutingService,
)


class RideRequestValidationError(Exception):
    pass


class RideRequestConflictError(RideRequestValidationError):
    """للزبون طلبٌ قائم بالفعل — يُردّ 409 لا 400.

    بلا هذا الحارس كان كلّ نقر إضافيّ على «اطلب» — أو إعادة إرسال بعد
    انقطاع — ينشئ طلبًا جديدًا يبحث بالتوازي، فيتلقّى السائقون الطلب
    نفسه مرّتين ويُعلَّق الزبون بين رحلتين. قِيس: ثلاثة طلبات «searching»
    لزبون واحد في أقلّ من دقيقة.
    """


# الحالات التي يُعدّ فيها الطلب قائمًا — ما قبل الاكتمال أو الإلغاء أو
# الانقضاء.
ACTIVE_RIDE_STATUSES = (
    RideStatus.SEARCHING,
    RideStatus.OFFERS_RECEIVED,
    RideStatus.DRIVER_SELECTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)


class RideRequestService:

    DEFAULT_SPEED_KMH = 30

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def validate_ride_request(
        customer,
        pickup,
        destination,
        mode,
        passenger_count,
        scheduled_at=None,
        requested_vehicle_type=None,
        trip_category=TripCategory.CITY,
        origin_city=None,
        destination_city=None,
    ):

        # ---------------------------------
        # Customer
        # ---------------------------------

        if not customer.is_authenticated:

            raise RideRequestValidationError(
                "Authentication is required."
            )

        if not customer.is_verified:

            raise RideRequestValidationError(
                "Customer must be verified."
            )

        if not customer.is_active:

            raise RideRequestValidationError(
                "Customer account is inactive."
            )

        # ---------------------------------
        # Locations
        # ---------------------------------

        if pickup is None:

            raise RideRequestValidationError(
                "Pickup location is required."
            )

        if destination is None:

            raise RideRequestValidationError(
                "Destination location is required."
            )

        if pickup.equals(destination):

            raise RideRequestValidationError(
                "Pickup and destination cannot be the same."
            )

        # ---------------------------------
        # Mode
        # ---------------------------------

        valid_modes = {
            choice[0]
            for choice in RideMode.choices
        }

        if mode not in valid_modes:

            raise RideRequestValidationError(
                "Invalid ride mode."
            )

        # ---------------------------------
        # Trip category
        # ---------------------------------

        valid_categories = {
            choice[0]
            for choice in TripCategory.choices
        }

        if trip_category not in valid_categories:

            raise RideRequestValidationError(
                "Invalid trip category."
            )

        # الرحلات الترفيهية لا تُنشأ من هنا مباشرة، بل عبر كتالوج الرحلات المنشورة
        if trip_category == TripCategory.RECREATIONAL:

            raise RideRequestValidationError(
                "Recreational trips must be booked via the published trips catalog."
            )

        # السفريات وخطوط السرفيس تتطلب اسم مدينة المصدر والوجهة
        if trip_category in (TripCategory.INTERCITY, TripCategory.SERVICE_LINE):

            if not origin_city or not destination_city:

                raise RideRequestValidationError(
                    "origin_city and destination_city are required "
                    "for intercity/service-line trips."
                )

        # ---------------------------------
        # Passenger count
        # ---------------------------------

        if passenger_count < 1:

            raise RideRequestValidationError(
                "Passenger count must be at least 1."
            )

        if passenger_count > 8:

            raise RideRequestValidationError(
                "Passenger count cannot exceed 8."
            )

        # ---------------------------------
        # Scheduled ride
        #
        # إصلاح: أي mode ممكن يكون مجدولاً أو فوريًا، والمعيار الوحيد
        # هو وجود scheduled_at (بدل الاعتماد على mode == "scheduled"
        # الذي لم يكن موجودًا أصلاً في RideMode ويسبب AttributeError).
        # ---------------------------------

        if scheduled_at is not None:

            if scheduled_at <= timezone.now():

                raise RideRequestValidationError(
                    "scheduled_at must be in the future."
                )

    # =========================================================
    # CATALOG — ما أطفأه المشغّل لا يُطلب
    # =========================================================

    @staticmethod
    def _enforce_catalog(area, mode, trip_category, auto_dispatch, scheduled_at):
        from catalog.services import Catalog, ServiceUnavailable

        try:
            Catalog.require_service("taxi", area)
            service = Catalog.service_for_mode(mode)
            if service:
                Catalog.require_service(service, area)
            service = Catalog.service_for_category(trip_category)
            if service:
                Catalog.require_service(service, area)
            if auto_dispatch:
                Catalog.require_feature(
                    "nearest", area, "«الأقرب» متوقّف حاليًّا. اطلب بالعروض."
                )
            if scheduled_at is not None:
                Catalog.require_feature(
                    "scheduled_rides", area, "الحجز في موعد متوقّف حاليًّا."
                )
        except ServiceUnavailable as exc:
            raise RideRequestValidationError(str(exc))

    # =========================================================
    # SEARCH RADIUS
    # =========================================================

    @staticmethod
    def resolve_search_radius(service_area, requested):
        """
        نطاق الزبون من خيارات منطقته، لا رقمٌ حرّ: رقمٌ حرّ يسمح بـ0.01 كم
        فلا يصل الطلب أحدًا، أو بـ100 كم فيوقظ سائقي مدينة أخرى.
        """
        if requested is None:
            return None

        options = (
            service_area.effective_search_radius_options_km
            if service_area is not None
            else []
        )

        if not options:
            # المنطقة لا تعرض اختيارًا: الطلب يمرّ بنصف قطرها كما كان.
            return None

        match = next((o for o in options if abs(o - float(requested)) < 0.01), None)
        if match is None:
            raise RideRequestValidationError(
                f"نطاق البحث يجب أن يكون أحد: {options} كم."
            )

        from decimal import Decimal
        return Decimal(str(match)).quantize(Decimal("0.01"))

    # =========================================================
    # HAVERSINE
    # =========================================================

    @staticmethod
    def calculate_distance_km(
        pickup,
        destination,
    ):

        lat1 = radians(pickup.y)

        lon1 = radians(pickup.x)

        lat2 = radians(destination.y)

        lon2 = radians(destination.x)

        dlat = lat2 - lat1

        dlon = lon2 - lon1

        a = (
            sin(dlat / 2) ** 2
            +
            cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        c = 2 * atan2(
            sqrt(a),
            sqrt(1 - a),
        )

        earth_radius_km = 6371.0

        return earth_radius_km * c

    # =========================================================
    # OLD ETA
    # =========================================================

    @classmethod
    def calculate_eta(
        cls,
        distance_km,
        average_speed_kmh=None,
    ):

        if average_speed_kmh is None:

            average_speed_kmh = (
                cls.DEFAULT_SPEED_KMH
            )

        if distance_km < 0:

            raise ValueError(
                "Distance cannot be negative."
            )

        if average_speed_kmh <= 0:

            raise ValueError(
                "Average speed must be greater than zero."
            )

        duration_minutes = round(
            (
                distance_km
                / average_speed_kmh
            )
            * 60
        )

        return max(
            duration_minutes,
            1,
        )

    # =========================================================
    # CREATE RIDE REQUEST
    # =========================================================

    @classmethod
    @transaction.atomic
    def create_ride_request(
        cls,
        customer,
        pickup,
        destination,
        mode,
        passenger_count,
        scheduled_at=None,
        requested_vehicle_type=None,
        trip_category=TripCategory.CITY,
        origin_city=None,
        destination_city=None,
        search_radius_km=None,
        auto_dispatch=False,
    ):

        # =====================================================
        # 1. VALIDATE
        # =====================================================

        cls.validate_ride_request(

            customer=customer,

            pickup=pickup,

            destination=destination,

            mode=mode,

            passenger_count=passenger_count,

            scheduled_at=scheduled_at,

            requested_vehicle_type=(
                requested_vehicle_type
            ),

            trip_category=trip_category,

            origin_city=origin_city,

            destination_city=destination_city,
        )

        # =====================================================
        # 1b. ONE ACTIVE RIDE PER CUSTOMER
        # =====================================================
        # الفوريّ يحجب الفوريّ فقط: طلبٌ مجدول للغد لا يمنع مشوار اليوم،
        # ومشوار اليوم لا يمنع اشتراك الصباح من إنشاء طلب الغد.
        overlapping = (
            RideRequest.objects
            .filter(customer=customer, status__in=ACTIVE_RIDE_STATUSES)
        )
        if scheduled_at is None:
            overlapping = overlapping.filter(scheduled_at__isnull=True)
        else:
            overlapping = overlapping.filter(scheduled_at=scheduled_at)
        existing = overlapping.order_by("-id").values_list("id", flat=True).first()
        if existing is not None:
            raise RideRequestConflictError(
                "لديك طلب قائم بالفعل. ألغِه أو أكمله قبل طلب رحلة جديدة."
            )

        # =====================================================
        # 2. RESOLVE SERVICE AREA
        # =====================================================

        # منطقة الخدمة تُحدَّد من نقطة الالتقاط لا الوجهة: القواعد التنظيمية
        # تتبع مكان بدء الخدمة. رحلة من جبلة إلى اللاذقية تخضع لقواعد جبلة.
        #
        # وتُحلّ هنا — قبل كلّ شيء — لأنّ ثلاثة قرارات تحتها تعتمد عليها:
        # فئات المركبات المتاحة، ومعايرة التقدير الداخلي عند تعذّر المزوّد،
        # ونافذة البحث عن سائق.
        from locations.services import LocationService

        service_area = LocationService.resolve_area(pickup.x, pickup.y)

        cls._enforce_catalog(
            service_area, mode, trip_category, auto_dispatch, scheduled_at,
        )

        from catalog.services import Catalog

        if not Catalog.feature_enabled("search_radius", service_area):
            search_radius_km = None
        search_radius_km = cls.resolve_search_radius(service_area, search_radius_km)

        if auto_dispatch:
            from trips.services.cancellation import CancellationPolicy

            until = CancellationPolicy.customer_penalty_until(customer, service_area)
            if until is not None:
                raise RideRequestValidationError(
                    "بسبب إلغاءات متأخّرة متكرّرة، «الأقرب» و«اختر سيارتك» "
                    f"متوقّفان لحسابك حتّى {timezone.localtime(until):%H:%M}. "
                    "اطلب بالعروض."
                )
            if scheduled_at is not None:
                raise RideRequestValidationError(
                    "«الأقرب» للطلب الفوري فقط، لا للمجدول."
                )
            if service_area is not None and not service_area.allows_invitation_for_mode(mode):
                raise RideRequestValidationError(
                    f"«الأقرب» غير مفعّل لنمط '{mode}' في {service_area.name}."
                )

        # =====================================================
        # 3. VALIDATE VEHICLE TYPE
        # =====================================================

        if requested_vehicle_type is not None:

            # الفئات صفوف لا enum: نسأل القاعدة، ونسأل عن *المتاح في هذه
            # المدينة* لا عن الموجود عمومًا. فئة أُخفيت أو خُصّصت لمدينة
            # أخرى يجب أن تُرفض هنا كما تُرفض فئة لا وجود لها.
            if requested_vehicle_type not in VehicleCategory.active_codes(
                service_area
            ):
                raise RideRequestValidationError(
                    "Invalid requested vehicle type."
                )

        # =====================================================
        # 4. ROAD ROUTING
        # =====================================================

        try:

            routing = RoutingService.route(
                pickup=pickup,
                destination=destination,
                service_area=service_area,
            )

        except RoutingError as exc:

            # لا يصل هنا إلّا حين MAPS_ROUTING_REQUIRED=True. وإلّا فالخدمة
            # تتراجع إلى تقدير داخلي وتُعلّم النتيجة بـsource=estimated.
            raise RideRequestValidationError(
                f"Routing failed: {exc}"
            )

        route_source = routing.get("source", "provider")

        route_distance_km = (
            routing["distance_km"]
        )

        route_duration_minutes = (
            routing["duration_minutes"]
        )

        route_geometry = (
            routing["geometry"]
        )

        # =====================================================
        # 5. PRICING
        # =====================================================

        pricing = PricingService.quote(
            mode=mode,
            distance_km=route_distance_km,
            duration_minutes=route_duration_minutes,
            service_area=service_area,
        )

        # =====================================================
        # 6. EXPIRATION
        # =====================================================

        now = timezone.now()

        ride_status = RideStatus.SEARCHING

        if scheduled_at is not None:

            expires_at = None

        else:

            # كانت timedelta(minutes=10) مكتوبة هنا حرفيًّا: تغييرها لمدينة
            # واحدة كان يعني تعديل شيفرة ونشرًا. صارت إعداد منطقة يقرأه
            # المشغّل من الأدمن، مع افتراض عامّ لمن لم يضبطه.
            from django.conf import settings

            window_minutes = (
                service_area.effective_ride_search_window_minutes
                if service_area is not None
                else getattr(settings, "RIDE_SEARCH_WINDOW_MINUTES", 10)
            )

            expires_at = now + timedelta(minutes=window_minutes)

        # =====================================================
        # 7. CREATE RIDE
        # =====================================================

        ride = RideRequest.objects.create(

            customer=customer,

            requested_vehicle_type=(
                requested_vehicle_type
            ),

            pickup=pickup,

            destination=destination,

            mode=mode,

            trip_category=trip_category,

            origin_city=origin_city,

            destination_city=destination_city,

            passenger_count=(
                passenger_count
            ),

            scheduled_at=(
                scheduled_at
            ),

            status=ride_status,

            expires_at=expires_at,

            # ---------------------------------
            # Pricing snapshot
            # ---------------------------------

            base_fare=(
                pricing["base_fare"]
            ),

            distance_fare=(
                pricing["distance_fare"]
            ),

            time_fare=(
                pricing["time_fare"]
            ),

            gross_fare=(
                pricing["gross_fare"]
            ),

            platform_fee=(
                pricing["platform_fee"]
            ),

            customer_total=(
                pricing["customer_total"]
            ),

            driver_net=(
                pricing["driver_net"]
            ),
            
            # ---------------------------------
            # Pricing policy snapshot
            # ---------------------------------
            service_area=service_area,
            pricing_policy=pricing["pricing_policy"],
            currency=pricing["currency"],
            fare_floor=pricing["fare_floor"],
            fare_cap=pricing["fare_cap"],
            surge_multiplier=pricing["surge_multiplier"],

            # ---------------------------------
            # Real road estimate
            # ---------------------------------

            estimated_distance_km=(
                route_distance_km
            ),

            estimated_duration_minutes=(
                route_duration_minutes
            ),

            # ---------------------------------
            # Route snapshot
            # ---------------------------------

            route_distance_km=(
                route_distance_km
            ),

            route_duration_minutes=(
                route_duration_minutes
            ),

            route_geometry=(
                route_geometry
            ),

            route_source=route_source,
            search_radius_km=search_radius_km,
            auto_dispatch=bool(auto_dispatch),
        )

        if ride.auto_dispatch:
            from matching.services.auto_dispatch import AutoDispatchService
            AutoDispatchService.schedule(ride.id)

        return ride