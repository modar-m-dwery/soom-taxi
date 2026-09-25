from math import (
    radians,
    sin,
    cos,
    sqrt,
    atan2,
)

from datetime import timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db import transaction
from django.utils import timezone

from matching.models import (
    ScheduledSharedTrip,
    ScheduledSharedTripMember,
    ScheduledSharedTripStatus,
    ScheduledSharedTripCategory,
    RideOffer,
    OfferStatus,
)

from rides.models import (
    RideRequest,
    RideMode,
    RideStatus,
)


class ScheduledSharedMatchingError(Exception):
    pass


class ScheduledSharedTripService:

    # =========================================================
    # HAVERSINE
    # =========================================================

    @staticmethod
    def _haversine_km(a, b):

        lat1 = radians(a.y)
        lon1 = radians(a.x)

        lat2 = radians(b.y)
        lon2 = radians(b.x)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        h = (
            sin(dlat / 2) ** 2
            +
            cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        return (
            6371.0
            * 2
            * atan2(
                sqrt(h),
                sqrt(1 - h),
            )
        )

    # =========================================================
    # CHECK SHARED + SCHEDULED
    # =========================================================

    @staticmethod
    def _validate_shared_scheduled_ride(ride):

        if ride.mode != RideMode.SHARED:

            raise ScheduledSharedMatchingError(
                "Ride is not shared."
            )

        if ride.scheduled_at is None:

            raise ScheduledSharedMatchingError(
                "Ride is not scheduled."
            )

    # =========================================================
    # حدود المدينة
    # =========================================================

    @staticmethod
    def _limits(ride):
        """
        (نطاق الالتقاط، نطاق الوجهة، نافذة الوقت) لمدينة هذا الطلب.

        كانت هذه الأرقام ثلاثة ثوابت عامّة — وواحدها مكتوب في الدالّة —
        فكان ضبط المشاركة المجدولة لمدينة يفسدها لكلّ المدن. والمشاركة
        بالذات أشدّ حساسية للجغرافيا من غيرها: خمسة عشر كيلومترًا لتوافق
        الوجهة في مدينة صغيرة تعني «أيّ وجهة تقريبًا».
        """
        area = getattr(ride, "service_area", None)

        if area is not None:
            return (
                area.effective_shared_scheduled_pickup_radius_km,
                area.effective_shared_scheduled_dest_radius_km,
                area.effective_shared_scheduled_time_window_minutes,
            )

        return (
            getattr(settings, "MATCHING_SHARED_SCHEDULED_PICKUP_RADIUS_KM", 10),
            getattr(settings, "MATCHING_SHARED_SCHEDULED_DEST_RADIUS_KM", 15),
            getattr(settings, "MATCHING_SHARED_SCHEDULED_TIME_WINDOW_MINUTES", 60),
        )

    # =========================================================
    # COMPATIBILITY SCORE
    # =========================================================

    @classmethod
    def _compatibility_score(
        cls,
        ride,
        trip,
    ):

        pickup_distance = cls._haversine_km(
            ride.pickup,
            trip.pickup,
        )

        destination_distance = (
            cls._haversine_km(
                ride.destination,
                trip.destination,
            )
        )

        pickup_limit, destination_limit, _ = cls._limits(ride)

        if pickup_limit <= 0:

            pickup_limit = 10

        if destination_limit <= 0:

            destination_limit = 15

        pickup_score = max(
            0,
            100
            - (
                pickup_distance
                / pickup_limit
            )
            * 100,
        )

        destination_score = max(
            0,
            100
            - (
                destination_distance
                / destination_limit
            )
            * 100,
        )

        score = (
            pickup_score * 0.5
            + destination_score * 0.5
        )

        return round(
            score,
            1,
        )

    # =========================================================
    # CREATE SCHEDULED SHARED TRIP
    # FROM ACCEPTED DRIVER OFFER (رحلات المدينة العادية فقط)
    # =========================================================

    @staticmethod
    @transaction.atomic
    def create_from_accepted_offer(
        offer: RideOffer,
    ):

        ride = offer.ride

        if ride.mode != RideMode.SHARED:

            raise ScheduledSharedMatchingError(
                "Ride is not shared."
            )

        if ride.scheduled_at is None:

            raise ScheduledSharedMatchingError(
                "Ride is not scheduled."
            )

        if offer.status != OfferStatus.ACCEPTED:

            raise ScheduledSharedMatchingError(
                "Offer must be accepted first."
            )

        existing = (
            ScheduledSharedTrip.objects
            .filter(
                source_offer=offer
            )
            .first()
        )

        if existing:

            return existing

        vehicle = (
            offer.driver.vehicles
            .filter(
                active=True,
                seats__gte=ride.passenger_count,
            )
            .order_by("-seats")
            .first()
        )

        if not vehicle:

            raise ScheduledSharedMatchingError(
                "Driver has no suitable active vehicle."
            )

        trip = (
            ScheduledSharedTrip.objects.create(

                driver=offer.driver,

                vehicle=vehicle,

                pickup=ride.pickup,

                destination=ride.destination,

                scheduled_at=ride.scheduled_at,

                capacity=vehicle.seats,

                status=(
                    ScheduledSharedTripStatus.OPEN
                ),

                trip_category=ScheduledSharedTripCategory.CITY,

                source_offer=offer,
            )
        )

        ScheduledSharedTripMember.objects.create(

            trip=trip,

            ride=ride,

            is_host=True,

            is_active=True,
        )

        trip.refresh_status()

        return trip

    # =========================================================
    # نشر رحلة مباشرة من السائق/لوحة التحكم
    # يغطي: سفريات بين مدن، خطوط سرفيس ثابتة، رحلات ترفيهية
    # بدون الحاجة لعملية مطابقة/عرض مسبق
    # =========================================================

    @classmethod
    @transaction.atomic
    def publish_trip(
        cls,
        driver,
        vehicle,
        trip_category,
        scheduled_at,
        capacity,
        pickup,
        destination,
        origin_city=None,
        destination_city=None,
        price_per_seat=None,
        title=None,
        description=None,
        features=None,
        route_geometry=None,
    ):

        if trip_category == ScheduledSharedTripCategory.CITY:

            raise ScheduledSharedMatchingError(
                "City trips are created automatically from accepted offers, "
                "not published directly."
            )

        if scheduled_at <= timezone.now():

            raise ScheduledSharedMatchingError(
                "scheduled_at must be in the future."
            )

        if capacity < 1:

            raise ScheduledSharedMatchingError(
                "Capacity must be at least 1."
            )

        if vehicle.driver_id != driver.id or not vehicle.active:

            raise ScheduledSharedMatchingError(
                "Vehicle does not belong to driver or is inactive."
            )

        if vehicle.seats < capacity:

            raise ScheduledSharedMatchingError(
                "Vehicle does not have enough seats for requested capacity."
            )

        if trip_category in (
            ScheduledSharedTripCategory.INTERCITY,
            ScheduledSharedTripCategory.SERVICE_LINE,
        ):

            if not origin_city or not destination_city:

                raise ScheduledSharedMatchingError(
                    "origin_city and destination_city are required for this trip category."
                )

        if price_per_seat is not None and price_per_seat < 0:

            raise ScheduledSharedMatchingError(
                "price_per_seat cannot be negative."
            )

        trip = ScheduledSharedTrip.objects.create(
            driver=driver,
            vehicle=vehicle,
            pickup=pickup,
            destination=destination,
            scheduled_at=scheduled_at,
            capacity=capacity,
            status=ScheduledSharedTripStatus.OPEN,
            trip_category=trip_category,
            title=title,
            description=description,
            origin_city=origin_city,
            destination_city=destination_city,
            price_per_seat=price_per_seat,
            features=features or [],
            route_geometry=route_geometry,
            source_offer=None,
        )

        return trip

    # =========================================================
    # تصفح الرحلات المنشورة (سفريات / سرفيس / ترفيهية)
    # =========================================================

    @classmethod
    def get_published_trips(
        cls,
        trip_category=None,
        origin_city=None,
        destination_city=None,
    ):

        qs = (
            ScheduledSharedTrip.objects
            .filter(
                status__in=[
                    ScheduledSharedTripStatus.OPEN,
                    ScheduledSharedTripStatus.FULL,
                ],
                scheduled_at__gt=timezone.now(),
            )
            .exclude(
                trip_category=ScheduledSharedTripCategory.CITY
            )
        )

        if trip_category:
            qs = qs.filter(trip_category=trip_category)

        if origin_city:
            qs = qs.filter(origin_city__iexact=origin_city)

        if destination_city:
            qs = qs.filter(destination_city__iexact=destination_city)

        return (
            qs
            .select_related("driver", "driver__user", "vehicle")
            .order_by("scheduled_at")
        )

    # =========================================================
    # حجز مباشر في رحلة منشورة (بدون طلب رحلة مسبق)
    # =========================================================

    @classmethod
    @transaction.atomic
    def book_published_trip(
        cls,
        trip_id,
        customer,
        passenger_count=1,
    ):

        trip = (
            ScheduledSharedTrip.objects
            .select_for_update()
            .select_related("driver", "vehicle")
            .get(id=trip_id)
        )

        if trip.trip_category == ScheduledSharedTripCategory.CITY:

            raise ScheduledSharedMatchingError(
                "This trip is not directly bookable; join it via its originating ride."
            )

        if trip.status not in {
            ScheduledSharedTripStatus.OPEN,
            ScheduledSharedTripStatus.FULL,
        }:

            raise ScheduledSharedMatchingError(
                "Trip is not available for booking."
            )

        if trip.scheduled_at <= timezone.now():

            raise ScheduledSharedMatchingError(
                "Trip departure time has passed."
            )

        if trip.remaining_capacity < passenger_count:

            raise ScheduledSharedMatchingError(
                "Not enough seats available."
            )

        fare = (trip.price_per_seat or 0) * passenger_count

        ride = RideRequest.objects.create(
            customer=customer,
            pickup=trip.pickup,
            destination=trip.destination,
            mode=RideMode.SHARED if trip.capacity > 1 else RideMode.STANDARD,
            trip_category=trip.trip_category,
            origin_city=trip.origin_city,
            destination_city=trip.destination_city,
            published_trip=trip,
            passenger_count=passenger_count,
            scheduled_at=trip.scheduled_at,
            status=RideStatus.DRIVER_SELECTED,
            gross_fare=fare,
            customer_total=fare,
        )

        member = ScheduledSharedTripMember.objects.create(
            trip=trip,
            ride=ride,
            is_host=False,
            is_active=True,
        )

        trip.refresh_status()

        return member

    # =========================================================
    # GET AVAILABLE SHARED SCHEDULED TRIPS (رحلات المدينة العادية)
    # =========================================================

    @classmethod
    def get_available_trips_for_ride(
        cls,
        ride: RideRequest,
    ):

        if ride.mode != RideMode.SHARED:

            return []

        if ride.scheduled_at is None:

            return []

        pickup_radius_km, _, time_window_minutes = cls._limits(ride)

        trips = (
            ScheduledSharedTrip.objects
            .filter(

                trip_category=ScheduledSharedTripCategory.CITY,

                status__in=[
                    ScheduledSharedTripStatus.OPEN,
                    ScheduledSharedTripStatus.FULL,
                ],

                scheduled_at__gte=(
                    ride.scheduled_at
                    - timedelta(
                        minutes=(
                            time_window_minutes
                        )
                    )
                ),

                scheduled_at__lte=(
                    ride.scheduled_at
                    + timedelta(
                        minutes=(
                            time_window_minutes
                        )
                    )
                ),
            )

            .annotate(
                pickup_distance=Distance(
                    "pickup",
                    ride.pickup,
                )
            )

            .filter(
                pickup_distance__lte=D(
                    km=pickup_radius_km
                )
            )

            .select_related(
                "driver",
                "driver__user",
                "vehicle",
            )
        )

        result = []

        for trip in trips:

            if (
                trip.remaining_capacity
                < ride.passenger_count
            ):

                continue

            destination_distance = (
                cls._haversine_km(
                    ride.destination,
                    trip.destination,
                )
            )

            _, destination_limit, _ = cls._limits(ride)

            if (
                destination_distance
                > destination_limit
            ):

                continue

            score = (
                cls._compatibility_score(
                    ride,
                    trip,
                )
            )

            min_score = getattr(
                settings,
                "MATCHING_SHARED_SCHEDULED_MIN_SCORE",
                60,
            )

            if score < min_score:

                continue

            result.append(
                (
                    trip,
                    score,
                )
            )

        result.sort(
            key=lambda item: (
                -item[1],
                item[0].scheduled_at,
            )
        )

        return result

    # =========================================================
    # JOIN EXISTING SHARED SCHEDULED TRIP (رحلات المدينة العادية)
    # =========================================================

    @classmethod
    @transaction.atomic
    def join_trip(
        cls,
        ride_id,
        trip_id,
        customer,
    ):

        ride = (
            RideRequest.objects
            .select_for_update()
            .get(
                id=ride_id,
                customer=customer,
            )
        )

        trip = (
            ScheduledSharedTrip.objects
            .select_for_update()
            .select_related(
                "driver",
                "vehicle",
            )
            .get(
                id=trip_id,
            )
        )

        if ride.mode != RideMode.SHARED:

            raise ScheduledSharedMatchingError(
                "Ride must be shared."
            )

        if ride.scheduled_at is None:

            raise ScheduledSharedMatchingError(
                "Ride must be scheduled."
            )

        if ride.status not in {
            RideStatus.SEARCHING,
            RideStatus.OFFERS_RECEIVED,
        }:

            raise ScheduledSharedMatchingError(
                "Ride is no longer available."
            )

        if trip.status not in {
            ScheduledSharedTripStatus.OPEN,
            ScheduledSharedTripStatus.FULL,
        }:

            raise ScheduledSharedMatchingError(
                "Scheduled shared trip is not available."
            )

        if (
            trip.scheduled_at
            <= timezone.now()
        ):

            raise ScheduledSharedMatchingError(
                "Trip departure time has passed."
            )

        existing_member = (
            ScheduledSharedTripMember.objects
            .filter(
                ride=ride,
                is_active=True,
            )
            .first()
        )

        if existing_member:

            raise ScheduledSharedMatchingError(
                "Ride is already joined to a scheduled shared trip."
            )

        if (
            trip.remaining_capacity
            < ride.passenger_count
        ):

            raise ScheduledSharedMatchingError(
                "Not enough seats available."
            )

        member = (
            ScheduledSharedTripMember.objects.create(

                trip=trip,

                ride=ride,

                is_host=False,

                is_active=True,
            )
        )

        ride.status = (
            RideStatus.DRIVER_SELECTED
        )

        ride.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        trip.refresh_status()

        return member

    # =========================================================
    # إلغاء عضوية راكب في رحلة مشتركة مجدولة
    #
    # المطلب: لو اللي بيلغي هو المضيف (أول راكب) ولسه فيه ركاب آخرون،
    # لا يتم إلغاء رحلاتهم؛ يُرقّى أقدم راكب متبقٍ ليكون المضيف الجديد،
    # وتستمر الرحلة. تُلغى الرحلة بالكامل فقط إذا لم يتبقَّ أي راكب.
    # =========================================================

    @classmethod
    @transaction.atomic
    def cancel_ride_membership(
        cls,
        ride_id,
    ):

        membership = (
            ScheduledSharedTripMember.objects
            .select_for_update()
            .select_related("trip")
            .filter(
                ride_id=ride_id,
                is_active=True,
            )
            .first()
        )

        if not membership:

            return None

        trip = (
            ScheduledSharedTrip.objects
            .select_for_update()
            .get(
                id=membership.trip_id
            )
        )

        was_host = membership.is_host

        membership.is_active = False

        membership.cancelled_at = (
            timezone.now()
        )

        membership.save(
            update_fields=[
                "is_active",
                "cancelled_at",
            ]
        )

        remaining_members = list(
            ScheduledSharedTripMember.objects
            .select_for_update()
            .filter(
                trip=trip,
                is_active=True,
            )
            .exclude(id=membership.id)
            .order_by("joined_at")
        )

        if remaining_members:

            # ترقية أقدم راكب متبقٍ ليكون المضيف الجديد
            # (المركبة والسائق يفضلوا كما هم - مرتبطين بالرحلة مباشرة)
            if was_host and not any(m.is_host for m in remaining_members):

                new_host = remaining_members[0]

                new_host.is_host = True

                new_host.save(update_fields=["is_host"])

            trip.refresh_status()

            return trip

        # لا يوجد ركاب متبقين -> يمكن إلغاء الرحلة المشتركة بالكامل
        trip.status = (
            ScheduledSharedTripStatus.CANCELLED
        )

        trip.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return trip