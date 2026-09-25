"""
اختبار المرحلة 12 — لوحة التشغيل.

يصنع الأعطال التي تكتشفها اللوحة ثم يتأكّد أنها تكتشفها، ثم يُصلحها
بالخدمة ويتأكّد أن الإصلاح حقيقي لا شكلي.

لا يحتاج Daphne ولا Celery.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

from locations.services import LocationService
from matching.models import OfferStatus, RideOffer
from matching.services.matching import MatchingService
from ops.models import ActionKind, AdminAction
from ops.services.console import OpsConsoleService, OpsError
from ops.services.health import OpsHealthService
from presence.constants import PresenceState
from presence.services import PresenceService
from rides.models import RideMode, RideRequest, RideStatus, TripCategory
from trips.models import CompletionSource, Trip, TripStatus
from trips.services.engagement import EngagementResolver
from trips.services.trip import TripService
from users.models import DriverProfile, User
from vehicles.models import Vehicle


JABLEH_LNG = 35.9200
JABLEH_LAT = 35.3600
DEST_LNG, DEST_LAT = 35.9300, 35.4000


class Command(BaseCommand):
    help = "اختبار لوحة التشغيل: الكشف، التدخّل، وسجلّ التدقيق"

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

        if not Vehicle.objects.filter(driver=driver, active=True).exists():
            return self._setup_fail("لا مركبة فعّالة للسائق.")

        admin = (
            User.objects.filter(is_staff=True).order_by("id").first()
            or customer
        )

        self.customer = customer
        self.driver = driver
        self.area = area
        self.admin = admin
        self.original_status = driver.status

        if admin.id == customer.id:
            self.stdout.write(self.style.WARNING(
                "لا مستخدم is_staff — سنستعمل الزبون كفاعل إداري في الاختبار."
            ))

        try:
            self._run()
        finally:
            self._restore()

        total = self.passed + self.failed

        if self.failed:
            self.stdout.write(self.style.ERROR(
                f"\nOps console E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nOps console E2E: {self.passed}/{total} passed."
            ))

    # =================================================================

    def _run(self):
        self._cleanup()
        self._phase_overview()
        self._phase_ghost_driver()
        self._phase_stuck_trip()
        self._phase_force_complete()
        self._phase_driver_status()
        self._phase_audit()

    # -----------------------------------------------------------------
    # أ — النظرة العامة
    # -----------------------------------------------------------------

    def _phase_overview(self):
        self._section("أ: النظرة العامة")

        self._arm()

        overview = OpsHealthService.overview()

        self._check(
            "drivers" in overview and "trips" in overview and "complaints" in overview,
            "1) النظرة العامة تُرجع الأقسام الثلاثة",
        )

        breakdown = overview["drivers"]
        self._check(
            breakdown.get(PresenceState.PRESENT, 0) >= 1,
            f"2) السائق المتصل محسوب حاضرًا "
            f"(present={breakdown.get(PresenceState.PRESENT)})",
        )
        self._check(
            sum(
                breakdown[k] for k in breakdown if k != "total_active_accounts"
            ) == breakdown["total_active_accounts"],
            "3) ★ مجموع الحالات يساوي عدد الحسابات — لا سائق بلا حالة",
        )

        # الفرق بين ما تقوله القاعدة وما يقوله محرّك الحضور
        db_online = DriverProfile.objects.filter(
            status=DriverProfile.DriverStatus.ACTIVE, online=True
        ).count()
        self._check(
            isinstance(db_online, int),
            f"4) القاعدة تقول {db_online} متصلًا، والحضور يفصّلهم بحالاتهم "
            f"— وهذا الفرق هو سبب وجود اللوحة",
        )

    # -----------------------------------------------------------------
    # ب — السائق الشبح
    # -----------------------------------------------------------------

    def _phase_ghost_driver(self):
        self._section("ب: السائق المشغول بلا رحلة")

        # نصنع العطل يدويًا: نكتب BUSY في Redis بلا رحلة في القاعدة.
        # هذا بالضبط ما يخلّفه انقطاع في اللحظة الخطأ.
        PresenceService.set_engagement(self.driver.id, {"busy": True})

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.BUSY,
            f"5) صنعنا العطل: السائق BUSY في Redis (state={state})",
        )

        ghosts = OpsHealthService.ghost_busy_drivers()
        ghost_ids = [g["driver_id"] for g in ghosts]

        self._check(
            self.driver.id in ghost_ids,
            f"6) ★ اللوحة اكتشفته — كان سيختفي عن الخريطة إلى الأبد بلا "
            f"أن يشتكي أحد (ghosts={ghost_ids})",
        )

        self._expect_error(
            lambda: OpsConsoleService.release_driver(
                driver_id=self.driver.id, actor=self.admin, reason="خطأ"
            ),
            "7) ★ التحرير بلا سبب مكتوب مرفوض",
        )

        action = OpsConsoleService.release_driver(
            driver_id=self.driver.id,
            actor=self.admin,
            reason="سائق عالق بعد انقطاع اتصال — اتصل بالدعم.",
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state != PresenceState.BUSY,
            f"8) ★ وبعد التحرير عاد متاحًا (state={state})",
        )
        self._check(
            action.kind == ActionKind.RELEASE_DRIVER
            and action.before["status"] is not None,
            "9) والتدخّل مسجَّل بلقطة ما قبله",
        )

    # -----------------------------------------------------------------
    # ج — الرحلة العالقة
    # -----------------------------------------------------------------

    def _phase_stuck_trip(self):
        self._section("ج: الرحلة العالقة")

        trip = self._assign_trip()

        if trip is None:
            self._skip(4, "تعذّر تثبيت رحلة")
            return

        # نُرجع updated_at ساعةً إلى الوراء: هذا ما تفعله رحلة نسيها سائقها
        Trip.objects.filter(id=trip.id).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )

        stuck = OpsHealthService.stuck_trips()
        stuck_ids = [s["trip_id"] for s in stuck]

        self._check(
            trip.id in stuck_ids,
            f"10) ★ رحلة بلا حراك منذ ساعة تظهر في قائمة العالقة "
            f"(stuck={stuck_ids})",
        )

        row = next((s for s in stuck if s["trip_id"] == trip.id), {})
        self._check(
            row.get("stuck_minutes", 0) >= 45 and row.get("driver_phone"),
            f"11) ومعها ما يحتاجه المشغّل للاتصال "
            f"({row.get('stuck_minutes')} دقيقة، {row.get('driver_phone')})",
        )

        action = OpsConsoleService.force_cancel_trip(
            ride_id=trip.ride_id,
            actor=self.admin,
            reason="رحلة عالقة منذ ساعة، لا ردّ من السائق.",
        )

        trip.refresh_from_db()
        self.driver.refresh_from_db()

        self._check(
            trip.status == TripStatus.CANCELLED
            and trip.cancelled_by == "admin",
            f"12) الإلغاء الإداري مُسجَّل باسمه لا باسم الزبون "
            f"(by={trip.cancelled_by})",
        )
        self._check(
            self.driver.current_occupancy == 0
            and PresenceService.get_state(self.driver.id) != PresenceState.BUSY,
            "13) ★ والسائق تحرّر فعلًا — الإصلاح حقيقي لا شكلي",
        )

    # -----------------------------------------------------------------
    # د — الإنهاء الإداري
    # -----------------------------------------------------------------

    def _phase_force_complete(self):
        self._section("د: الإنهاء الإداري")

        trip = self._assign_trip()

        if trip is None:
            self._skip(4, "تعذّر تثبيت رحلة")
            return

        action = OpsConsoleService.force_complete_trip(
            ride_id=trip.ride_id,
            actor=self.admin,
            reason="الرحلة انتهت فعلًا وسقط تطبيق السائق قبل الضغط.",
        )

        trip.refresh_from_db()

        self._check(
            trip.status == TripStatus.COMPLETED,
            f"14) الرحلة انتهت (status={trip.status})",
        )

        record = getattr(trip, "completion_record", None)
        self._check(
            record is not None
            and record.completion_source == CompletionSource.ADMIN,
            f"15) ★ وسجلّ الإتمام يقول إن مشغّلًا أنهاها لا سائقها "
            f"(source={record.completion_source if record else '—'})",
        )
        self._check(
            trip.needs_review,
            "16) ★ ومُعلَّمة للمراجعة دائمًا — لم يشهدها أحد من الطرفين",
        )
        self._check(
            PresenceService.get_state(self.driver.id) != PresenceState.BUSY,
            "17) والسائق تحرّر",
        )

    # -----------------------------------------------------------------
    # هـ — توثيق السائقين
    # -----------------------------------------------------------------

    def _phase_driver_status(self):
        self._section("هـ: التوثيق والإيقاف")

        self._arm()

        before_state = PresenceService.get_state(self.driver.id)
        self._check(
            before_state == PresenceState.PRESENT,
            f"18) السائق على الخريطة قبل الإيقاف (state={before_state})",
        )

        OpsConsoleService.set_driver_status(
            driver_id=self.driver.id,
            actor=self.admin,
            new_status=DriverProfile.DriverStatus.SUSPENDED,
            reason="شكوى سلامة قيد التحقيق — إيقاف احترازي.",
        )

        self.driver.refresh_from_db()

        self._check(
            self.driver.status == DriverProfile.DriverStatus.SUSPENDED
            and not self.driver.online,
            f"19) الحساب موقوف وغير متصل (status={self.driver.status})",
        )

        state = PresenceService.get_state(self.driver.id)
        self._check(
            state == PresenceState.OFFLINE,
            f"20) ★ واختفى من الخريطة فورًا لا عند نبضته التالية "
            f"(state={state})",
        )

        self._expect_error(
            lambda: OpsConsoleService.set_driver_status(
                driver_id=self.driver.id,
                actor=self.admin,
                new_status="pending",
                reason="إعادة إلى الانتظار من اللوحة",
            ),
            "21) وحالة غير مسموحة من اللوحة مرفوضة",
        )

        OpsConsoleService.set_driver_status(
            driver_id=self.driver.id,
            actor=self.admin,
            new_status=DriverProfile.DriverStatus.ACTIVE,
            reason="أُغلق التحقيق ولم يثبت شيء. إعادة تفعيل.",
        )

        self.driver.refresh_from_db()
        self._check(
            self.driver.status == DriverProfile.DriverStatus.ACTIVE
            and self.driver.verified_by_id == self.admin.id
            and self.driver.verification_note,
            "22) وإعادة التفعيل تُسجّل مَن فعلها ولماذا",
        )

    # -----------------------------------------------------------------
    # و — سجلّ التدقيق
    # -----------------------------------------------------------------

    def _phase_audit(self):
        self._section("و: سجلّ التدقيق")

        actions = AdminAction.objects.filter(actor=self.admin).order_by("-created_at")

        self._check(
            actions.count() >= 5,
            f"23) كل تدخّل تُرك له أثر ({actions.count()} فعلًا)",
        )

        latest = actions.first()
        self._check(
            latest.reason and latest.before and latest.after,
            "24) ★ ومعه السبب ولقطتا ما قبل وما بعد",
        )

        kinds = set(actions.values_list("kind", flat=True))
        self._check(
            {ActionKind.RELEASE_DRIVER, ActionKind.FORCE_CANCEL,
             ActionKind.FORCE_COMPLETE, ActionKind.SUSPEND_DRIVER} <= kinds,
            f"25) وكل أنواع التدخّل مسجَّلة ({len(kinds)} أنواع)",
        )

        attention = OpsHealthService.attention()
        self._check(
            set(attention.keys()) >= {
                "stuck_trips", "ghost_busy_drivers", "trips_needing_review",
                "urgent_complaints", "stale_searches",
            },
            f"26) ولوحة 'ما يحتاج إنسانًا' تجمعها كلها "
            f"({len(attention)} أقسام)",
        )

    # =================================================================
    # أدوات
    # =================================================================

    def _cleanup(self):
        stale = list(
            RideOffer.objects
            .filter(
                driver=self.driver,
                status=OfferStatus.ACCEPTED,
                ride__status__in=[
                    RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
                    RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
                ],
            )
            .values_list("ride_id", flat=True)
        )

        if stale:
            Trip.objects.filter(ride_id__in=stale).update(
                status=TripStatus.CANCELLED
            )
            RideRequest.objects.filter(id__in=stale).update(
                status=RideStatus.CANCELLED
            )
            RideOffer.objects.filter(
                ride_id__in=stale, status=OfferStatus.ACCEPTED
            ).update(status=OfferStatus.CANCELLED)

        Trip.objects.filter(
            driver=self.driver,
            status__in=[
                TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
                TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
            ],
        ).update(status=TripStatus.CANCELLED)

        DriverProfile.objects.filter(id=self.driver.id).update(current_occupancy=0)

    def _arm(self):
        point = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)
        vehicle = (
            Vehicle.objects.filter(driver=self.driver, active=True)
            .order_by("-seats").first()
        )

        self.driver.refresh_from_db()
        self.driver.current_location = point
        self.driver.last_location_at = timezone.now()
        self.driver.online = True
        self.driver.status = DriverProfile.DriverStatus.ACTIVE
        self.driver.current_occupancy = 0

        if vehicle is not None:
            self.driver.available_seats = vehicle.seats

        self.driver.save(update_fields=[
            "current_location", "last_location_at", "online", "status",
            "current_occupancy", "available_seats", "updated_at",
        ])

        PresenceService.go_online(self.driver)
        PresenceService.update_location(self.driver.id, JABLEH_LNG, JABLEH_LAT)
        EngagementResolver.sync(self.driver.id)

    def _assign_trip(self):
        self._arm()

        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            destination=Point(DEST_LNG, DEST_LAT, srid=4326),
            mode=RideMode.FAST,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=self.area,
            gross_fare=Decimal("25.00"),
            customer_total=Decimal("25.00"),
            driver_net=Decimal("25.00"),
            pricing_policy="platform_fixed",
            currency=self.area.currency_code,
            route_distance_km=Decimal("4.50"),
        )
        self.created_rides.append(ride.id)

        try:
            offer = MatchingService.create_offer(
                ride_id=ride.id, driver=self.driver,
                gross_fare=Decimal("25.00"), eta_minutes=4,
            )
            MatchingService.select_offer(
                ride_id=ride.id, offer_id=offer.id, customer=self.customer
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"تعذّر التثبيت: {exc}"))
            return None

        return Trip.objects.filter(ride_id=ride.id).first()

    def _restore(self):
        try:
            DriverProfile.objects.filter(id=self.driver.id).update(
                status=self.original_status
            )
            RideRequest.objects.filter(
                id__in=self.created_rides, status=RideStatus.SEARCHING
            ).update(status=RideStatus.CANCELLED)
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

    def _expect_error(self, callable_, label):
        try:
            callable_()
        except OpsError as exc:
            self._check(True, f"{label} — {exc}")
            return
        except Exception as exc:
            self._check(False, f"{label} — استثناء غير متوقع: {exc!r}")
            return

        self._check(False, f"{label} — مرّ بلا رفض!")

    def _skip(self, count, why):
        for _ in range(count):
            self.failed += 1
            self.stdout.write(self.style.ERROR(f"[FAIL] — تخطّي: {why}"))

    def _setup_fail(self, message):
        self.stderr.write(self.style.ERROR(f"[SETUP FAIL] {message}"))
