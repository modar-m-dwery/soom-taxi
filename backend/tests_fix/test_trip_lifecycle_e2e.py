"""
اختبار E2E للمرحلة 9أ — دورة حياة الرحلة الفعلية.

هذا هو الاختبار الذي يثبت أن المنصّة قادرة على إتمام رحلة واحدة كاملة من
أوّلها إلى آخرها. قبله كانت الرحلة تقف عند "سائق مثبَّت" إلى الأبد.

يغطّي:
    - إنشاء Trip تلقائيًا عند تثبيت السائق
    - التسلسل الإلزامي: لا بدء قبل وصول، ولا إنهاء قبل بدء
    - تحقق GPS عند الوصول (منع وصول كاذب)
    - تسجيل المسار أثناء الرحلة فقط، بخنق المسافة والزمن
    - حساب المسافة والمدة من المسار المسجَّل
    - سجل إتمام الرحلة (§17.3)
    - ★ تحرير السائق وعودته للخريطة — الحلقة التي كانت مفقودة
    - التكرار الآمن لكل فعل

يفترض: Daphne على 8001، locations_resolve_test مُشغَّل، سائق بمركبة فعّالة.

الاستخدام:
    python manage.py test_trip_lifecycle_e2e \
        --customer-phone "+96399819335875" --driver-id 5
"""
import os
import json
import queue
import threading
import time
from datetime import timedelta
from decimal import Decimal

import websocket
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone


JABLEH_LNG = 35.9
JABLEH_LAT = 35.36
DEST_LNG = 35.91
DEST_LAT = 35.37


def _listen(url, out_queue, errors, stop_event):
    try:
        ws = websocket.create_connection(url)
    except Exception as exc:
        errors.append(exc)
        return

    ws.settimeout(1.0)
    while not stop_event.is_set():
        try:
            out_queue.put(json.loads(ws.recv()))
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
    ws.close()


class Command(BaseCommand):
    help = "End-to-end test for the trip lifecycle (stage 9a)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ws-url",
            # 8000 هو منفذ daphne في Dockerfile وفي التوثيق. كان
            # 8001 موروثًا من تشغيل يدوي على ويندوز، فكانت كلّ فحوص
            # الأحداث تسقط بصمت خارج ذلك الجهاز.
            default=os.environ.get("E2E_WS_URL", "ws://localhost:8000"),
        )
        parser.add_argument("--customer-phone", required=True)
        parser.add_argument("--driver-id", type=int, required=True)
        parser.add_argument("--timeout", type=float, default=6.0)

    # =================================================================

    def handle(self, *args, **options):
        from rest_framework.authtoken.models import Token

        from locations.services import LocationService
        from matching.models import OfferStatus, RideOffer
        from matching.services.matching import MatchingService
        from presence.constants import PresenceState
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
        from trips.models import Trip, TripCompletionRecord, TripStatus
        from trips.services.trip import TripError, TripService
        from users.models import DriverProfile
        from vehicles.models import Vehicle

        self.passed = self.failed = 0
        self.timeout = options["timeout"]
        ws_url = options["ws_url"]

        User = get_user_model()
        customer = User.objects.get(phone=options["customer_phone"])
        customer_token, _ = Token.objects.get_or_create(user=customer)

        driver = DriverProfile.objects.get(id=options["driver_id"])
        driver_token, _ = Token.objects.get_or_create(user=driver.user)

        pickup = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)
        destination = Point(DEST_LNG, DEST_LAT, srid=4326)

        area = LocationService.resolve_area(JABLEH_LNG, JABLEH_LAT)
        if area is None:
            self.stderr.write(self.style.ERROR(
                "[SETUP FAIL] لا توجد ServiceArea تغطي جبلة."
            ))
            return

        if not Vehicle.objects.filter(driver=driver, active=True).exists():
            self.stderr.write(self.style.ERROR("[SETUP FAIL] لا مركبة فعّالة للسائق."))
            return

        # -------------------------------------------------------------
        # تنظيف بيئة
        # -------------------------------------------------------------
        active = [
            RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
        ]
        stale = list(
            RideOffer.objects
            .filter(driver=driver, status=OfferStatus.ACCEPTED, ride__status__in=active)
            .values_list("ride_id", flat=True)
        )
        if stale:
            Trip.objects.filter(ride_id__in=stale).update(status=TripStatus.CANCELLED)
            RideRequest.objects.filter(id__in=stale).update(status=RideStatus.CANCELLED)
            RideOffer.objects.filter(
                ride_id__in=stale, status=OfferStatus.ACCEPTED
            ).update(status=OfferStatus.CANCELLED)
            self.stdout.write(self.style.WARNING(f"نُظّفت رحلات عالقة: {stale}"))

        # وأي رحلة نشطة أخرى مهما كانت حالة طلبها أو عرضها.
        #
        # الفلتر أعلاه يشترط "طلب نشط + عرض مقبول"، ورحلة يتيمة خارج هذا
        # الوصف كانت تنجو منه. ثم يشتقّ go_online منها BUSY، فيمرّ فحص
        # "السائق مشغول أثناء الرحلة" لسبب خاطئ، ويبقى السائق مشغولًا بها
        # بعد إنهاء رحلة الاختبار - فتسقط فحوص التحرير بلا ذنب للكود.
        orphans = Trip.objects.filter(
            driver=driver,
            status__in=[
                TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
                TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
            ],
        )
        orphan_count = orphans.update(status=TripStatus.CANCELLED)

        if orphan_count:
            self.stdout.write(self.style.WARNING(
                f"أُغلقت {orphan_count} رحلة يتيمة."
            ))

        DriverProfile.objects.filter(id=driver.id).update(current_occupancy=0)

        # القاعدة نُظّفت، وRedis لا يعرف. .update() لا تُطلق أي إشارة.
        from trips.services.engagement import EngagementResolver

        EngagementResolver.sync(driver.id)

        MarketplaceService.handle_offline(driver.id)
        PresenceService.go_offline(driver.id)

        self.errors = []
        self.stop = threading.Event()

        def refresh_driver(at_point=pickup, rearm=True):
            """
            rearm=False مهم: go_online تصفّر busy، ولو استدعيناها قبل
            الإنهاء لنجح فحص "تحرّر السائق" حتى لو كان تحرير الإنهاء
            غير مبنيّ أصلًا — أي اختبار يكذب.
            """
            driver.refresh_from_db()
            driver.current_location = at_point
            driver.last_location_at = timezone.now()
            driver.online = True
            driver.status = DriverProfile.DriverStatus.ACTIVE
            driver.current_occupancy = 0
            driver.available_seats = 4
            driver.save(update_fields=[
                "current_location", "last_location_at", "online", "status",
                "current_occupancy", "available_seats", "updated_at",
            ])
            if rearm:
                PresenceService.go_online(driver)
            PresenceService.update_location(
                driver.id, at_point.x, at_point.y, heading=45
            )
            return driver

        def lock_a_ride():
            """ينشئ طلبًا ويثبّت السائق عليه عبر مسار العروض."""
            refresh_driver()
            r = RideRequest.objects.create(
                customer=customer, pickup=pickup, destination=destination,
                mode=RideMode.FAST, trip_category=TripCategory.CITY,
                passenger_count=1, status=RideStatus.SEARCHING,
                service_area=area, gross_fare=Decimal("25.00"),
                customer_total=Decimal("25.00"), driver_net=Decimal("25.00"),
                pricing_policy="platform_fixed", currency=area.currency_code,
                route_distance_km=Decimal("1.50"),
            )
            q = queue.Queue()
            threading.Thread(
                target=_listen,
                args=(f"{ws_url}/ws/rides/{r.id}/?token={customer_token.key}",
                      q, self.errors, self.stop),
                daemon=True,
            ).start()
            time.sleep(0.4)
            self._drain(q, 2)

            driver.refresh_from_db()
            offer = MatchingService.create_offer(
                ride_id=r.id, driver=driver,
                gross_fare=Decimal("25.00"), eta_minutes=4,
            )
            MatchingService.select_offer(
                ride_id=r.id, offer_id=offer.id, customer=customer
            )
            time.sleep(0.3)
            self._drain(q, 2)  # offer.created + offer.accepted
            return r, q

        # =============================================================
        # المرحلة أ — الإنشاء والتسلسل الإلزامي
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("— أ: الإنشاء والتسلسل —"))

        ride, ride_events = lock_a_ride()

        trip = Trip.objects.filter(ride=ride).first()
        if trip is None:
            trip = TripService.ensure_trip(ride)

        self._check(
            trip is not None and trip.status == TripStatus.DRIVER_ARRIVING,
            f"1) الرحلة أُنشئت تلقائيًا عند التثبيت (status={trip.status if trip else '—'})",
        )
        self._check(
            trip.final_fare == Decimal("25.00") and trip.driver_id == driver.id,
            f"2) السعر والسائق منقولان من العرض ({trip.final_fare})",
        )

        # التسلسل: لا بدء قبل وصول
        self._expect_error(
            lambda: TripService.start(ride.id, driver),
            "3) يرفض بدء رحلة لم يصل سائقها", TripError,
        )
        self._expect_error(
            lambda: TripService.complete(ride.id, driver),
            "4) يرفض إنهاء رحلة لم تبدأ", TripError,
        )

        # =============================================================
        # المرحلة ب — تحقق GPS عند الوصول
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— ب: تحقق الوصول —"))

        # سائق بعيد: 0.05 درجة ≈ 4.5 كم
        driver.current_location = Point(JABLEH_LNG + 0.05, JABLEH_LAT, srid=4326)
        driver.last_location_at = timezone.now()
        driver.save(update_fields=["current_location", "last_location_at", "updated_at"])

        self._expect_error(
            lambda: TripService.arrived(ride.id, driver),
            "5) يرفض وصولًا كاذبًا من مسافة بعيدة", TripError,
        )

        # موقع قديم
        driver.current_location = pickup
        driver.last_location_at = timezone.now() - timedelta(seconds=9999)
        driver.save(update_fields=["current_location", "last_location_at", "updated_at"])

        self._expect_error(
            lambda: TripService.arrived(ride.id, driver),
            "6) يرفض الوصول بموقع قديم برسالة مختلفة عن 'أنت بعيد'", TripError,
        )

        # وصول صحيح
        refresh_driver(pickup)
        trip = TripService.arrived(ride.id, driver)
        time.sleep(0.3)

        ride.refresh_from_db()
        self._check(
            trip.status == TripStatus.DRIVER_ARRIVED
            and trip.pickup_verified
            and ride.status == RideStatus.DRIVER_ARRIVED,
            f"7) الوصول سُجّل ومُحقَّق (trip={trip.status}, ride={ride.status})",
        )
        self._expect(ride_events, "driver.arrived", "8) الزبون أُخطر بالوصول")

        again = TripService.arrived(ride.id, driver)
        self._check(
            again.id == trip.id and again.status == TripStatus.DRIVER_ARRIVED,
            "9) تسجيل وصول مكرر: عملية واحدة لا خطأ",
        )

        # =============================================================
        # المرحلة ج — البدء والمسار
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— ج: البدء وتسجيل المسار —"))

        trip = TripService.start(ride.id, driver)
        time.sleep(0.3)

        ride.refresh_from_db()
        self._check(
            trip.status == TripStatus.IN_PROGRESS
            and ride.status == RideStatus.IN_PROGRESS
            and trip.started_at is not None,
            f"10) الرحلة بدأت (trip={trip.status}, ride={ride.status})",
        )
        self._expect(ride_events, "trip.started", "11) الزبون أُخطر بالبدء")

        # نقاط المسار: 0.001 درجة طول ≈ 91م عند خط عرض جبلة
        base = timezone.now()
        recorded = 0
        for i in range(4):
            point = TripService.record_location(
                trip,
                lng=JABLEH_LNG + (i * 0.001),
                lat=JABLEH_LAT,
                speed=25.0,
                heading=90,
                at=base + timedelta(seconds=i * 10),
            )
            if point is not None:
                recorded += 1

        self._check(recorded == 4, f"12) سُجّلت {recorded}/4 نقاط على المسار")

        # الخنق: نقطة قريبة زمنيًا ومكانيًا تُرفض
        throttled = TripService.record_location(
            trip,
            lng=JABLEH_LNG + 0.003,      # نفس آخر نقطة تمامًا
            lat=JABLEH_LAT,
            at=base + timedelta(seconds=60),   # الفاصل الزمني كافٍ عمدًا
        )
        self._check(
            throttled is None,
            "13) الخنق يمنع تسجيل نقطة لم تتحرك (سائق واقف في زحمة)",
        )

        # =============================================================
        # المرحلة د — الإنهاء وتحرير السائق
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— د: الإنهاء وتحرير السائق —"))

        state_before = PresenceService.get_state(driver.id)
        self._check(
            state_before == PresenceState.BUSY,
            f"14) السائق BUSY أثناء الرحلة (state={state_before})",
        )

        refresh_driver(destination, rearm=False)
        trip = TripService.complete(ride.id, driver)
        time.sleep(0.5)

        ride.refresh_from_db()
        self._check(
            trip.status == TripStatus.COMPLETED
            and ride.status == RideStatus.COMPLETED,
            f"15) الرحلة انتهت (trip={trip.status}, ride={ride.status})",
        )
        self._check(
            trip.dropoff_verified and not trip.needs_review,
            f"16) الإنهاء قرب الوجهة مُحقَّق ولا يحتاج مراجعة "
            f"(verified={trip.dropoff_verified}, review={trip.needs_review})",
        )
        self._check(
            trip.distance_m and 150 < trip.distance_m < 500,
            f"17) المسافة محسوبة من المسار المسجَّل ({trip.distance_m}م)",
        )
        self._check(
            trip.duration_s is not None and trip.gps_points_count == 4,
            f"18) المدة {trip.duration_s}ث و{trip.gps_points_count} نقاط GPS",
        )

        record = TripCompletionRecord.objects.filter(trip=trip).first()
        self._check(
            record is not None
            and record.final_fare == Decimal("25.00")
            and record.gps_arrival_verified,
            f"19) سجل إتمام الرحلة أُنشئ ({record.final_fare if record else '—'})",
        )

        self._expect(ride_events, "trip.completed", "20) الزبون أُخطر بالإنهاء")

        state_after = PresenceService.get_state(driver.id)
        self._check(
            state_after == PresenceState.PRESENT,
            f"21) ★ السائق تحرّر وعاد متاحًا (state={state_after})",
        )

        nearby = PresenceService.get_available_nearby_driver_ids(
            DEST_LNG, DEST_LAT, radius_km=5
        )
        self._check(
            driver.id in nearby,
            f"22) ★ ويظهر من جديد في البحث القريب (nearby={nearby})",
        )

        done_again = TripService.complete(ride.id, driver)
        self._check(
            done_again.id == trip.id and done_again.status == TripStatus.COMPLETED,
            "23) إنهاء مكرر: عملية واحدة لا سجل مضاعف",
        )
        self._check(
            TripCompletionRecord.objects.filter(trip=trip).count() == 1,
            "24) وسجل إتمام واحد فقط في القاعدة",
        )

        # =============================================================
        # المرحلة هـ — الحالة الشاذة تُعلَّم للمراجعة لا تُحجب
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— هـ: الحالة الشاذة —"))

        ride2, ride2_events = lock_a_ride()
        driver.refresh_from_db()
        TripService.arrived(ride2.id, driver)
        TripService.start(ride2.id, driver)

        # إنهاء بعيد جدًا عن الوجهة
        refresh_driver(Point(JABLEH_LNG + 0.1, JABLEH_LAT, srid=4326), rearm=False)
        trip2 = TripService.complete(ride2.id, driver)
        time.sleep(0.4)

        self._check(
            trip2.status == TripStatus.COMPLETED and trip2.needs_review,
            f"25) إنهاء بعيد عن الوجهة: لا يُحجب بل يُعلَّم للمراجعة "
            f"({trip2.review_reason})",
        )
        self._check(
            not trip2.dropoff_verified,
            "26) وسجل الإتمام يوثّق أن التحقق الجغرافي فشل",
        )
        self._check(
            PresenceService.get_state(driver.id) == PresenceState.PRESENT,
            "27) والسائق تحرّر رغم الحالة الشاذة",
        )

        # -------------------------------------------------------------
        self.stop.set()

        total = self.passed + self.failed
        self.stdout.write("")
        if self.failed == 0:
            self.stdout.write(self.style.SUCCESS(
                f"Trip lifecycle E2E: {total}/{total} passed."
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"Trip lifecycle E2E: {self.passed}/{total} passed, {self.failed} FAILED."
            ))

    # =================================================================
    # HELPERS
    # =================================================================

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
        else:
            self.failed += 1
            self.stderr.write(self.style.ERROR(f"[FAIL] {label}"))
        return condition

    def _drain(self, q, count):
        for _ in range(count):
            try:
                q.get(timeout=2.0)
            except queue.Empty:
                return

    def _expect(self, q, expected_type, label):
        deadline = time.time() + self.timeout
        seen = []

        while time.time() < deadline:
            try:
                event = q.get(timeout=0.5)
            except queue.Empty:
                continue

            actual = event.get("event_type")
            if actual == expected_type:
                self.passed += 1
                self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
                return event
            seen.append(actual)

        self.failed += 1
        self.stderr.write(self.style.ERROR(
            f"[FAIL] {label}: لم يصل '{expected_type}'. وصل بدلًا منه: {seen}"
        ))
        return None

    def _expect_error(self, fn, label, exc):
        try:
            fn()
        except exc as e:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f"[OK]   {label} — {e}"))
            return True
        except Exception as other:
            self.failed += 1
            self.stderr.write(self.style.ERROR(
                f"[FAIL] {label}: استثناء غير متوقع {type(other).__name__}: {other}"
            ))
            return False
        self.failed += 1
        self.stderr.write(self.style.ERROR(f"[FAIL] {label}: قُبل بينما كان يجب أن يُرفض"))
        return False
