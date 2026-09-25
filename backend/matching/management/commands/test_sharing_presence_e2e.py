"""
اختبار المرحلة 8ب — السيارة المشتركة على الخريطة الحيّة.

لا يحتاج Daphne ولا Celery: كل ما يُختبر هنا هو القاعدة وRedis ومنطق
التوافق. شغّله مباشرة.

ملاحظة على طريقة التثبيت: نُنشئ العرض عبر MatchingService حين ينجح، وإلا
نُنشئه مباشرة بالـORM ونُكمل. سبب هذا أن خطّ العروض للرحلات المشتركة يمرّ
بـSharedMatchingService وله اختباره الخاص من المرحلة 7؛ ما يُختبر هنا هو ما
بعد التثبيت لا التثبيت نفسه، فلا نريد لفشل في طبقة أخرى أن يظهر كفشل هنا.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

from locations.services import LocationService
from matching.models import OfferStatus, RideOffer
from matching.services.compat import (
    SharedCompatibilityService,
    bearing_degrees,
    cell_radius_km,
    geohash_decode,
    haversine_km,
)
from matching.services.nearby import NearbyVehiclesService
from presence.constants import PresenceState, SHARED_MODE
from presence.services import PresenceService
from rides.models import RideMode, RideRequest, RideStatus, TripCategory
from trips.models import Trip, TripStatus
from trips.services.engagement import EngagementResolver
from trips.services.trip import TripService
from users.models import DriverProfile, User
from vehicles.models import Vehicle


JABLEH_LNG = 35.9200
JABLEH_LAT = 35.3600

# شمالًا ~4.5كم: وجهة الركّاب الذين على متن السيارة.
# الطول مختلف عمدًا عن طول جبلة: فحص تسريب الوجهة يقارن أرقامًا، ولو
# تطابق الطولان لظنّ موقعَ السائق المعروض تسريبًا للوجهة.
NORTH_LNG, NORTH_LAT = 35.9300, 35.4000

# جنوبًا: الاتجاه المعاكس تمامًا
SOUTH_LNG, SOUTH_LAT = 35.9100, 35.3200


class _FixedPrecisionArea:
    """منطقة وهمية لتثبيت الدقّة في فحوص الوحدة، مهما ضبط الأدمن جبلة."""

    def __init__(self, precision):
        self.shared_destination_precision = precision


class Command(BaseCommand):
    help = "اختبار حالة SHARING وفلترة التوافق على الخريطة الحيّة"

    def add_arguments(self, parser):
        parser.add_argument("--customer-phone", required=True)
        parser.add_argument("--driver-id", type=int, required=True)

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0
        self.created_rides = []

        customer = User.objects.filter(phone=options["customer_phone"]).first()
        if customer is None:
            return self._setup_fail("لا يوجد زبون بهذا الرقم.")

        driver = DriverProfile.objects.filter(id=options["driver_id"]).first()
        if driver is None:
            return self._setup_fail("لا يوجد سائق بهذا المعرّف.")

        area = LocationService.resolve_area(JABLEH_LNG, JABLEH_LAT)
        if area is None:
            return self._setup_fail("لا توجد ServiceArea تغطي جبلة.")

        vehicle = Vehicle.objects.filter(driver=driver, active=True).order_by("-seats").first()
        if vehicle is None:
            return self._setup_fail("لا مركبة فعّالة للسائق.")

        if vehicle.seats < 3:
            return self._setup_fail(
                f"المركبة فيها {vehicle.seats} مقاعد. يحتاج الاختبار 3 على الأقل."
            )

        self.customer = customer
        self.driver = driver
        self.area = area
        self.vehicle = vehicle

        try:
            self._run()
        finally:
            self._cleanup()

        total = self.passed + self.failed

        if self.failed:
            self.stdout.write(self.style.ERROR(
                f"\nSharing presence E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nSharing presence E2E: {self.passed}/{total} passed."
            ))

    # =================================================================

    def _run(self):
        self._reset_driver()

        self._phase_unit()
        self._phase_state()
        self._phase_map()
        self._phase_full()
        self._phase_partial_completion()
        self._phase_real_assignment()

    # -----------------------------------------------------------------
    # أ — منطق التوافق وحده، بلا قاعدة ولا Redis
    # -----------------------------------------------------------------

    def _phase_unit(self):
        self._section("أ: منطق التوافق (دوال خالصة)")

        # لو غُيّرت RideMode.SHARED يومًا ولم تُغيَّر النسخة النصّية في
        # presence.constants، لصمت النظام: كل سيارة مشتركة تختفي من الخريطة
        # بلا خطأ واحد في السجلّ. هذا الفحص هو ما يمنع ذلك.
        self._check(
            SHARED_MODE == RideMode.SHARED,
            f"1) SHARED_MODE في presence يطابق RideMode.SHARED ('{SHARED_MODE}')",
        )

        cell = self._cell(NORTH_LNG, NORTH_LAT, 5)
        decoded = geohash_decode(cell)

        gap_km = haversine_km(NORTH_LNG, NORTH_LAT, decoded[0], decoded[1])
        radius_km = cell_radius_km(cell)

        self._check(
            decoded is not None and gap_km <= radius_km,
            f"2) فكّ الخليّة '{cell}' يرجّع مركزًا ضمن نصف قطرها "
            f"({int(gap_km * 1000)}م ≤ {int(radius_km * 1000)}م)",
        )

        north = bearing_degrees(JABLEH_LNG, JABLEH_LAT, JABLEH_LNG, JABLEH_LAT + 0.05)
        east = bearing_degrees(JABLEH_LNG, JABLEH_LAT, JABLEH_LNG + 0.05, JABLEH_LAT)

        self._check(
            abs(north) < 1 and abs(east - 90) < 1,
            f"3) حساب الاتجاه صحيح (شمال={north:.1f}°، شرق={east:.1f}°)",
        )

        args = dict(
            driver_lng=JABLEH_LNG,
            driver_lat=JABLEH_LAT,
            driver_dest_cell=cell,
            rider_pickup_lng=JABLEH_LNG + 0.001,
            rider_pickup_lat=JABLEH_LAT + 0.004,
            rider_dest_lng=NORTH_LNG - 0.001,
            rider_dest_lat=NORTH_LAT - 0.002,
            free_seats=3,
            passenger_count=1,
            min_score=55,
        )

        good = SharedCompatibilityService.evaluate(**args)
        self._check(
            good["eligible"] and good["score"] >= 55,
            f"4) راكب على نفس المسار: مقبول بدرجة {good['score']}",
        )

        opposite = SharedCompatibilityService.evaluate(
            **{**args, "rider_dest_lng": SOUTH_LNG, "rider_dest_lat": SOUTH_LAT}
        )
        self._check(
            not opposite["eligible"] and "معاكس" in opposite["reason"],
            f"5) وجهة معاكسة: مرفوضة — {opposite['reason']}",
        )

        no_seat = SharedCompatibilityService.evaluate(**{**args, "free_seats": 0})
        self._check(
            not no_seat["eligible"] and "مقاعد" in no_seat["reason"],
            f"6) بلا مقاعد: مرفوض — {no_seat['reason']}",
        )

        two_seats = SharedCompatibilityService.evaluate(
            **{**args, "free_seats": 1, "passenger_count": 2}
        )
        self._check(
            not two_seats["eligible"],
            "7) راكبان ومقعد واحد: مرفوض",
        )

        # منعرج جانبي بعيد: الوجهة شمالًا لكن الراكب يريد النزول شرقًا بعيدًا
        detour = SharedCompatibilityService.evaluate(
            **{
                **args,
                "rider_dest_lng": JABLEH_LNG + 0.09,
                "rider_dest_lat": JABLEH_LAT + 0.005,
            }
        )
        self._check(
            not detour["eligible"],
            f"8) انعراج مكلف: مرفوض — {detour['reason']}",
        )

        strict = SharedCompatibilityService.evaluate(**{**args, "min_score": 99})
        self._check(
            not strict["eligible"] and strict["score"] == good["score"],
            f"9) رفع حدّ الأدمن إلى 99 يرفض نفس الراكب (درجته {strict['score']})",
        )

        # المقايضة التي يقرّرها الأدمن، مقيسة لا موصوفة: خليّة بدقّة 4 تغطي
        # ~20كم، فمركزها يبعد كيلومترات عن الوجهة الحقيقية وتعجز الفلترة عن
        # رفض انعراج بعيد. هذا ليس عيبًا بل ثمن الخصوصية الأعلى، ويجب أن
        # يكون مرئيًا بالأرقام قبل أن يختار الأدمن.
        coarse_detour = SharedCompatibilityService.evaluate(
            **{
                **args,
                "driver_dest_cell": self._cell(NORTH_LNG, NORTH_LAT, 4),
                "rider_dest_lng": JABLEH_LNG + 0.09,
                "rider_dest_lat": JABLEH_LAT + 0.005,
            }
        )
        self._check(
            coarse_detour["eligible"] and not detour["eligible"],
            "10) ثمن الخصوصية مقيس: نفس الراكب يُرفض بدقّة 5 ويُقبل بدقّة 4",
        )

    # -----------------------------------------------------------------
    # ب — الحالة نفسها
    # -----------------------------------------------------------------

    def _phase_state(self):
        self._section("ب: حالة SHARING")

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.PRESENT,
            f"11) السائق قبل أي رحلة: متاح (state={state})",
        )

        self.ride_a = self._assign_shared_ride(
            destination=Point(NORTH_LNG, NORTH_LAT, srid=4326),
            passenger_count=1,
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.SHARING,
            f"12) ★ بعد تثبيت رحلة مشتركة: SHARING لا BUSY (state={state})",
        )

        self.driver.refresh_from_db()
        self._check(
            self.driver.current_occupancy == 1,
            f"13) عدّاد الركّاب صار 1 بعد أن كان صفرًا دائمًا "
            f"(occupancy={self.driver.current_occupancy})",
        )

        snapshot = PresenceService.get_snapshot(self.driver.id)
        dest_cell = snapshot.get("dest_cell") or ""

        self._check(
            len(dest_cell) == self.area.shared_destination_precision,
            f"14) الوجهة مخزَّنة كخليّة خشنة بدقّة الأدمن "
            f"('{dest_cell}' = {len(dest_cell)} محارف)",
        )

        exact_cell = LocationService.coarse_destination_cell(
            NORTH_LNG, NORTH_LAT, self.area
        )
        self._check(
            dest_cell == exact_cell,
            f"15) وهي خليّة وجهة الراكب فعلًا لا قيمة عشوائية",
        )

        self._check(
            PresenceService.is_available(self.driver.id, for_mode=SHARED_MODE),
            "16) ★ متاح لطلب مشترك",
        )
        self._check(
            not PresenceService.is_available(self.driver.id, for_mode=RideMode.FAST),
            "17) ★ وغير متاح لطلب سريع — نفس السائق، جوابان",
        )
        self._check(
            not PresenceService.is_available(self.driver.id),
            "18) والنداء القديم بلا نمط يبقى على سلوكه (غير متاح)",
        )

        # إعادة الاتصال: go_online تشتقّ الارتباط من القاعدة لا تصفّره
        PresenceService.go_online(self.driver)
        PresenceService.update_location(self.driver.id, JABLEH_LNG, JABLEH_LAT)

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.SHARING,
            f"19) ★ إعادة الاتصال وسط رحلة مشتركة تبقيه SHARING (state={state})",
        )

    # -----------------------------------------------------------------
    # ج — ما يراه الزبون على الخريطة
    # -----------------------------------------------------------------

    def _phase_map(self):
        self._section("ج: الرؤية على الخريطة")

        fast_seeker = self._make_ride(
            destination=Point(NORTH_LNG, NORTH_LAT, srid=4326),
            mode=RideMode.FAST,
        )
        listed = self._nearby_ids(fast_seeker)
        self._check(
            self.driver.id not in listed,
            f"20) ★ طالب سيارة فردية لا يراها إطلاقًا (nearby={listed})",
        )

        shared_seeker = self._make_ride(
            pickup=Point(JABLEH_LNG + 0.001, JABLEH_LAT + 0.004, srid=4326),
            destination=Point(NORTH_LNG - 0.001, NORTH_LAT - 0.002, srid=4326),
            mode=RideMode.SHARED,
        )
        rows = NearbyVehiclesService.for_ride(shared_seeker)
        row = next((r for r in rows if r["driver_id"] == self.driver.id), None)

        self._check(
            row is not None,
            f"21) ★ طالب رحلة مشتركة على نفس المسار يراها "
            f"(nearby={[r['driver_id'] for r in rows]})",
        )

        if row is not None:
            self._check(
                row["is_sharing"] and row["compatibility_score"] >= (
                    self.area.shared_min_compatibility_score
                ),
                f"22) وتصله معلَّمة كمشتركة بدرجة توافق "
                f"{row['compatibility_score']} ومقاعد {row['available_seats']}",
            )

            leaked = self._leaks_exact_destination(row)
            self._check(
                not leaked,
                f"23) ★ ولا تكشف وجهة الراكب الحالي بإحداثيات دقيقة"
                + (f" — سُرّبت في {leaked}" if leaked else ""),
            )
        else:
            self._skip(2)

        opposite_seeker = self._make_ride(
            destination=Point(SOUTH_LNG, SOUTH_LAT, srid=4326),
            mode=RideMode.SHARED,
        )
        listed = self._nearby_ids(opposite_seeker)
        self._check(
            self.driver.id not in listed,
            f"24) ★ وطالب مشترك في الاتجاه المعاكس لا يراها (nearby={listed})",
        )

    # -----------------------------------------------------------------
    # د — امتلاء السيارة
    # -----------------------------------------------------------------

    def _phase_full(self):
        self._section("د: امتلاء السيارة")

        remaining = self.driver.available_seats - self.driver.current_occupancy

        self.ride_b = self._assign_shared_ride(
            destination=Point(NORTH_LNG + 0.002, NORTH_LAT, srid=4326),
            passenger_count=remaining,
        )

        self._check(
            self.last_offer_error is None,
            "25) ★ المطابقة تقبل عرضًا ثانيًا من سائق مشترك بمقعد فارغ"
            + (f" — رُفض: {self.last_offer_error}" if self.last_offer_error else ""),
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.BUSY,
            f"26) ★ امتلأت السيارة فصارت BUSY تلقائيًا (state={state})",
        )

        self.driver.refresh_from_db()
        self._check(
            self.driver.current_occupancy == self.driver.available_seats,
            f"27) والعدّاد يساوي السعة "
            f"({self.driver.current_occupancy}/{self.driver.available_seats})",
        )

        third = self._make_ride(
            destination=Point(NORTH_LNG, NORTH_LAT + 0.001, srid=4326),
            mode=RideMode.SHARED,
        )
        listed = self._nearby_ids(third)
        self._check(
            self.driver.id not in listed,
            f"28) ولا يراها راكب مشترك ثالث (nearby={listed})",
        )

    # -----------------------------------------------------------------
    # هـ — إنزال راكب واحد فقط
    # -----------------------------------------------------------------

    def _phase_partial_completion(self):
        self._section("هـ: إنزال راكب وبقاء آخر")

        self._advance_to_completion(self.ride_b)

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.SHARING,
            f"29) ★ أنزل راكبًا وبقي معه آخر: يعود SHARING لا PRESENT "
            f"(state={state})",
        )

        self.driver.refresh_from_db()
        self._check(
            self.driver.current_occupancy == 1,
            f"30) والعدّاد نقص بمقدار مَن نزل فقط "
            f"(occupancy={self.driver.current_occupancy})",
        )

        self._advance_to_completion(self.ride_a)

        state = PresenceService.get_state(self.driver.id)
        self.driver.refresh_from_db()

        self._check(
            state == PresenceState.PRESENT and self.driver.current_occupancy == 0,
            f"31) ★ وبعد نزول الأخير: PRESENT وعدّاد صفر (state={state})",
        )

        fast_seeker = self._make_ride(
            destination=Point(NORTH_LNG, NORTH_LAT, srid=4326),
            mode=RideMode.FAST,
        )
        listed = self._nearby_ids(fast_seeker)
        self._check(
            self.driver.id in listed,
            f"32) ويعود مرئيًا لطالب السيارة الفردية (nearby={listed})",
        )


    # -----------------------------------------------------------------
    # و — التثبيت الحقيقي عبر select_offer، والخريطة
    # -----------------------------------------------------------------

    def _phase_real_assignment(self):
        self._section("و: المسار الحقيقي والخريطة الحيّة")

        from matching.services.matching import MatchingService
        from realtime.marketplace import MarketplaceService, MarketplaceViewer

        self._reset_driver()

        ride = self._make_ride(
            destination=Point(NORTH_LNG, NORTH_LAT, srid=4326),
            mode=RideMode.SHARED,
        )

        offer = MatchingService.create_offer(
            ride_id=ride.id, driver=self.driver,
            gross_fare=Decimal("25.00"), eta_minutes=4,
        )

        # المسار الحقيقي حرفيًا: لا مزامنة يدوية بعده. لو عاد يومًا سطر
        # set_busy(True) إلى _publish_and_lock لسقط الفحص التالي وحده.
        MatchingService.select_offer(
            ride_id=ride.id, offer_id=offer.id, customer=self.customer
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.SHARING,
            f"33) ★ التثبيت عبر select_offer لا يشطب SHARING (state={state})",
        )

        cell = PresenceService.get_current_cell(self.driver.id)
        members = MarketplaceService.get_cell_member_ids(cell) if cell else []

        self._check(
            cell is not None and self.driver.id in members,
            f"34) ★ الخريطة أُعلمت لحظيًا: ما زال عضوًا في خليّته "
            f"(cell={cell})",
        )

        payload = MarketplaceService.build_vehicle_payload(self.driver.id)

        compatible = self._make_ride(
            pickup=Point(JABLEH_LNG + 0.001, JABLEH_LAT + 0.004, srid=4326),
            destination=Point(NORTH_LNG - 0.001, NORTH_LAT - 0.002, srid=4326),
            mode=RideMode.SHARED,
        )
        solo = self._make_ride(
            destination=Point(NORTH_LNG, NORTH_LAT, srid=4326),
            mode=RideMode.FAST,
        )

        visible_shared, score = MarketplaceViewer.from_ride(compatible).evaluate(payload)
        self._check(
            visible_shared,
            f"35) ★ الفلتر يُظهرها لمشاهد مشترك متوافق (درجة {score})",
        )
        self._check(
            not MarketplaceViewer.from_ride(solo).should_show(payload),
            "36) ★ ويُخفيها عن مشاهد يريد سيارة فردية",
        )
        self._check(
            not MarketplaceViewer.anonymous().should_show(payload),
            "37) ويُخفيها عن متصفّح بلا طلب — لا نعرض خيارًا لا يُركَب",
        )

        # ننهيها حتى لا نترك السائق مرتبطًا
        self._advance_to_completion(ride)

    # -----------------------------------------------------------------

    # =================================================================
    # أدوات
    # =================================================================

    def _reset_driver(self):
        """تنظيف: رحلات يتيمة من تشغيل سابق تعني سائقًا مشغولًا إلى الأبد."""
        orphans = Trip.objects.filter(
            driver=self.driver,
            status__in=[
                TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
                TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
            ],
        )
        count = orphans.update(status=TripStatus.CANCELLED)

        if count:
            self.stdout.write(self.style.WARNING(f"أُغلقت {count} رحلة يتيمة."))

        self.driver.current_location = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)
        self.driver.last_location_at = timezone.now()
        self.driver.online = True
        self.driver.status = DriverProfile.DriverStatus.ACTIVE
        self.driver.current_occupancy = 0
        self.driver.available_seats = self.vehicle.seats
        self.driver.save(update_fields=[
            "current_location", "last_location_at", "online", "status",
            "current_occupancy", "available_seats", "updated_at",
        ])

        PresenceService.go_online(self.driver)
        PresenceService.update_location(
            self.driver.id, JABLEH_LNG, JABLEH_LAT, heading=0
        )

    def _make_ride(self, destination, mode, pickup=None, passenger_count=1,
                   status=RideStatus.SEARCHING):
        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=pickup or Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            destination=destination,
            mode=mode,
            trip_category=TripCategory.CITY,
            passenger_count=passenger_count,
            status=status,
            service_area=self.area,
            gross_fare=Decimal("25.00"),
            customer_total=Decimal("25.00"),
            driver_net=Decimal("25.00"),
            pricing_policy="platform_fixed",
            currency=self.area.currency_code,
            route_distance_km=Decimal("4.50"),
        )
        self.created_rides.append(ride.id)
        return ride

    def _assign_shared_ride(self, destination, passenger_count):
        """تثبيت السائق على رحلة مشتركة، ثم إنشاء الرحلة الفعلية."""
        self.last_offer_error = None
        ride = self._make_ride(
            destination=destination,
            mode=RideMode.SHARED,
            passenger_count=passenger_count,
        )

        offer = self._accepted_offer(ride)

        ride.status = RideStatus.DRIVER_SELECTED
        ride.save(update_fields=["status", "updated_at"])

        TripService.ensure_trip(ride, offer=offer)

        # ensure_trip تزامن عبر on_commit، ولا معاملة مفتوحة هنا، لكن نُجبر
        # المزامنة صراحةً حتى لا يعتمد الاختبار على توقيت.
        EngagementResolver.sync(self.driver.id)

        return ride

    def _accepted_offer(self, ride):
        """
        نُسجّل سبب فشل create_offer بدل ابتلاعه: فشلُه على رحلة مشتركة ثانية
        ليس تفصيلًا في الاختبار بل ثغرة في المنتج - الخريطة تعرض السيارة
        والمطابقة ترفضها.
        """
        try:
            from matching.services.matching import MatchingService

            offer = MatchingService.create_offer(
                ride_id=ride.id,
                driver=self.driver,
                gross_fare=Decimal("25.00"),
                eta_minutes=4,
            )
        except Exception as exc:
            self.last_offer_error = str(exc)
            offer = RideOffer.objects.create(
                ride=ride, driver=self.driver, gross_fare=Decimal("25.00"),
                eta_minutes=4,
                expires_at=timezone.now() + timedelta(seconds=120),
            )

        RideOffer.objects.filter(id=offer.id).update(
            status=OfferStatus.ACCEPTED, accepted_at=timezone.now()
        )
        offer.refresh_from_db()

        return offer

    def _advance_to_completion(self, ride):
        """وصل -> بدأ -> انتهى، بموقع صالح في كل خطوة."""
        self.driver.refresh_from_db()
        self.driver.current_location = ride.pickup
        self.driver.last_location_at = timezone.now()
        self.driver.save(update_fields=[
            "current_location", "last_location_at", "updated_at"
        ])

        TripService.arrived(ride_id=ride.id, driver=self.driver)
        TripService.start(ride_id=ride.id, driver=self.driver)

        self.driver.refresh_from_db()
        self.driver.current_location = ride.destination
        self.driver.last_location_at = timezone.now()
        self.driver.save(update_fields=[
            "current_location", "last_location_at", "updated_at"
        ])

        TripService.complete(ride_id=ride.id, driver=self.driver)
        EngagementResolver.sync(self.driver.id)

    @staticmethod
    def _cell(lng, lat, precision):
        """خليّة بدقّة مفروضة — لا تتأثر بما ضبطه الأدمن لجبلة."""
        return LocationService.coarse_destination_cell(
            lng, lat, _FixedPrecisionArea(precision)
        )

    def _nearby_ids(self, ride):
        return [r["driver_id"] for r in NearbyVehiclesService.for_ride(ride)]

    def _leaks_exact_destination(self, row):
        """
        الخصوصية ليست وعدًا في تعليق: نفحص الحمولة فعليًا بحثًا عن أي قيمة
        تقترب من وجهة الراكب الحالي بأكثر مما تسمح به الخليّة.
        """
        tolerance = 0.002   # ~200م

        for key, value in row.items():
            if not isinstance(value, (int, float)):
                continue
            if abs(float(value) - NORTH_LAT) < tolerance:
                return key
            if abs(float(value) - NORTH_LNG) < tolerance:
                return key

        return None

    def _cleanup(self):
        if self.created_rides:
            RideRequest.objects.filter(
                id__in=self.created_rides, status=RideStatus.SEARCHING
            ).update(status=RideStatus.CANCELLED)

    # -----------------------------------------------------------------

    def _section(self, title):
        self.stdout.write(self.style.HTTP_INFO(f"\n— {title} —"))

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(f"[OK]   {label}")
        else:
            self.failed += 1
            self.stdout.write(self.style.ERROR(f"[FAIL] {label}"))

    def _skip(self, count):
        for _ in range(count):
            self.failed += 1
            self.stdout.write(self.style.ERROR("[FAIL] — تخطّي بسبب فشل سابق"))

    def _setup_fail(self, message):
        self.stderr.write(self.style.ERROR(f"[SETUP FAIL] {message}"))
