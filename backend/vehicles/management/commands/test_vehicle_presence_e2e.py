"""
اختبار أثر تغيير المركبة على الحضور والخريطة.

الفكرة التي يقيسها: القاعدة والـRedis والخريطة يجب أن يقولوا الشيء نفسه
بعد كل تغيير في المركبات. قبل هذه الدفعة كانوا يفترقون في ثلاث حالات.

لا يحتاج Daphne ولا Celery.
"""
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

from locations.services import LocationService
from presence.constants import PresenceState
from presence.services import PresenceService
from realtime.marketplace import MarketplaceService
from users.models import DriverProfile
from vehicles.models import Vehicle
from vehicles.services import VehicleError, VehicleService


JABLEH_LNG = 35.9200
JABLEH_LAT = 35.3600


class Command(BaseCommand):
    help = "اختبار مزامنة المركبة مع الحضور والخريطة الحيّة"

    def add_arguments(self, parser):
        parser.add_argument("--driver-id", type=int, required=True)

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0

        driver = DriverProfile.objects.filter(id=options["driver_id"]).first()
        if driver is None:
            return self._fail_setup("لا يوجد سائق بهذا المعرّف.")

        vehicles = list(Vehicle.objects.filter(driver=driver).order_by("-seats"))
        if not vehicles:
            return self._fail_setup("لا مركبات مسجَّلة لهذا السائق.")

        self.driver = driver
        self.vehicles = vehicles
        self.primary = next((v for v in vehicles if v.active), vehicles[0])

        self.stdout.write(self.style.WARNING(
            f"المركبة الأساسية: #{self.primary.id} بـ{self.primary.seats} مقاعد. "
            f"سيُعاد تفعيلها في النهاية."
        ))

        try:
            self._run()
        finally:
            self._restore()

        total = self.passed + self.failed

        if self.failed:
            self.stdout.write(self.style.ERROR(
                f"\nVehicle presence E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nVehicle presence E2E: {self.passed}/{total} passed."
            ))

    # =================================================================

    def _run(self):
        self._arm()

        self._phase_deactivate()
        self._phase_reactivate()
        self._phase_active_trip()

    # -----------------------------------------------------------------

    def _phase_deactivate(self):
        self._section("أ: إطفاء آخر مركبة")

        state = PresenceService.get_state(self.driver.id)
        cell = PresenceService.get_current_cell(self.driver.id)

        self._check(
            state == PresenceState.PRESENT,
            f"1) السائق حاضر قبل الإطفاء (state={state})",
        )
        self._check(
            cell is not None and self.driver.id in MarketplaceService.get_cell_member_ids(cell),
            f"2) وعضو في خليّة الخريطة (cell={cell})",
        )

        # نُطفئ كل المركبات: الأخيرة هي المهمّة
        for vehicle in Vehicle.objects.filter(driver=self.driver, active=True):
            VehicleService.deactivate_vehicle(self.driver, vehicle.id)

        self.driver.refresh_from_db()

        self._check(
            self.driver.available_seats == 0 and not self.driver.online,
            f"3) القاعدة: مقاعد صفر وonline=False "
            f"(seats={self.driver.available_seats}, online={self.driver.online})",
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.OFFLINE,
            f"4) ★ وRedis يقول الشيء نفسه — كان يبقى حاضرًا (state={state})",
        )

        members = MarketplaceService.get_cell_member_ids(cell) if cell else []
        self._check(
            self.driver.id not in members,
            f"5) ★ وأُزيل من خليّة الخريطة — لا سيارة شبح مرسومة "
            f"(members={members})",
        )
        self._check(
            PresenceService.get_current_cell(self.driver.id) is None,
            "6) ولم تبقَ له خليّة مسجَّلة",
        )

    # -----------------------------------------------------------------

    def _phase_reactivate(self):
        self._section("ب: إعادة التفعيل")

        VehicleService.set_active_vehicle(self.driver, self.primary.id)
        self.driver.refresh_from_db()

        self._check(
            self.driver.available_seats == self.primary.seats,
            f"7) المقاعد عادت من المركبة "
            f"({self.driver.available_seats}/{self.primary.seats})",
        )

        # go_online هي ما يُعيد الحضور فعلًا - تفعيل المركبة وحده لا يجعل
        # السائق متصلًا، وهذا صحيح: قرار الاتصال بيده لا بيد مركبته.
        state_before = PresenceService.get_state(self.driver.id)
        self._check(
            state_before == PresenceState.OFFLINE,
            f"8) تفعيل المركبة وحده لا يُعيده للخدمة — القرار بيده "
            f"(state={state_before})",
        )

        self._arm()

        snapshot = PresenceService.get_snapshot(self.driver.id)
        self._check(
            int(float(snapshot.get("available_seats") or 0)) == self.primary.seats,
            f"9) ★ وبعد الاتصال وصلت المقاعد إلى Redis "
            f"({snapshot.get('available_seats')})",
        )
        self._check(
            PresenceService.get_state(self.driver.id) == PresenceState.PRESENT,
            "10) وعاد حاضرًا",
        )

    # -----------------------------------------------------------------

    def _phase_active_trip(self):
        self._section("ج: التبديل أثناء رحلة جارية")

        trip = self._assign_trip()

        if trip is None:
            self._check(False, "11) تعذّر تثبيت رحلة للاختبار")
            self._check(False, "12) — تخطّي")
            return

        self._check(
            trip is not None,
            f"11) رحلة مثبَّتة للاختبار (ride={trip.ride_id})",
        )

        try:
            VehicleService.set_active_vehicle(self.driver, self.primary.id)
            self._check(False, "12) ★ تبديل المركبة أثناء رحلة جارية — مرّ بلا رفض!")
        except VehicleError as exc:
            self._check(True, f"12) ★ تبديل المركبة أثناء رحلة جارية مرفوض — {exc}")
        except Exception as exc:
            self._check(False, f"12) ★ استثناء غير متوقع: {exc!r}")

        self._cancel_trip(trip)

    # =================================================================
    # أدوات
    # =================================================================

    def _arm(self):
        """إعادة السائق إلى الخدمة: قاعدة + Redis + خليّة خريطة."""
        point = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)

        self.driver.refresh_from_db()
        self.driver.current_location = point
        self.driver.last_location_at = timezone.now()
        self.driver.online = True
        self.driver.status = DriverProfile.DriverStatus.ACTIVE
        self.driver.current_occupancy = 0
        self.driver.save(update_fields=[
            "current_location", "last_location_at", "online",
            "status", "current_occupancy", "updated_at",
        ])

        PresenceService.go_online(self.driver)
        PresenceService.update_location(self.driver.id, JABLEH_LNG, JABLEH_LAT)

        cell_id = LocationService.compute_marketplace_cell_id(JABLEH_LNG, JABLEH_LAT)

        if cell_id:
            snapshot = PresenceService.get_snapshot(self.driver.id)
            payload = MarketplaceService.build_vehicle_payload(
                self.driver.id, snapshot=snapshot
            )
            MarketplaceService.handle_location_update(
                self.driver.id, cell_id, payload, True
            )

    def _assign_trip(self):
        from decimal import Decimal

        from matching.services.matching import MatchingService
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
        from trips.models import Trip
        from users.models import User

        area = LocationService.resolve_area(JABLEH_LNG, JABLEH_LAT)
        customer = (
            User.objects
            .exclude(driver_profile__isnull=False)
            .order_by("-id")
            .first()
        )

        if area is None or customer is None:
            return None

        ride = RideRequest.objects.create(
            customer=customer,
            pickup=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            destination=Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.04, srid=4326),
            mode=RideMode.FAST,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=area,
            gross_fare=Decimal("25.00"),
            customer_total=Decimal("25.00"),
            driver_net=Decimal("25.00"),
            pricing_policy="platform_fixed",
            currency=area.currency_code,
            route_distance_km=Decimal("4.50"),
        )

        try:
            offer = MatchingService.create_offer(
                ride_id=ride.id, driver=self.driver,
                gross_fare=Decimal("25.00"), eta_minutes=4,
            )
            MatchingService.select_offer(
                ride_id=ride.id, offer_id=offer.id, customer=customer
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"تعذّر التثبيت: {exc}"))
            return None

        return Trip.objects.filter(ride_id=ride.id).first()

    def _cancel_trip(self, trip):
        from trips.services.trip import TripService

        try:
            TripService.cancel(ride_id=trip.ride_id, actor="customer", reason="اختبار")
        except Exception:
            pass

    def _restore(self):
        """إعادة الحالة كما كانت: مركبة فعّالة وسائق متصل."""
        try:
            Vehicle.objects.filter(id=self.primary.id).update(active=True)
            self.driver.refresh_from_db()
            self.driver.available_seats = self.primary.seats
            self.driver.online = True
            self.driver.save(update_fields=["available_seats", "online", "updated_at"])
            self._arm()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"تعذّرت الاستعادة: {exc}"))

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

    def _fail_setup(self, message):
        self.stderr.write(self.style.ERROR(f"[SETUP FAIL] {message}"))
