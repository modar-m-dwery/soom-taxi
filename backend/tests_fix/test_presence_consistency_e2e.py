"""
اختبار E2E لاتساق تعريف "السائق المتاح" عبر Presence / Matching / Marketplace.

هذا الاختبار يغطي السيناريوهات التي لم تُغطَّ في اختبارات E/F/G السابقة، وهي
تحديدًا السيناريوهات 4 و5 و30 و31 من خطة المرحلة 6/7:

    4)  السائق يقبل رحلة -> BUSY -> يختفي من الماركت بليس والبحث القريب.
    5)  انتهاء/إلغاء الرحلة -> يعود متاحًا -> يظهر مجددًا.
    30) موقع قديم (heartbeat حيّ لكن بلا GPS) -> UNAVAILABLE -> يختفي.
    31) لا يمكن لزبون ثانٍ رؤية سيارة أصبحت مشغولة قبل لحظات.

بالإضافة إلى:
    - إعادة تسليح السائق تلقائيًا بعد sweep (كان فشلًا صامتًا).
    - بثّ offer.expired من Celery task (كان صامتًا تمامًا).
    - وجود available_seats في حمولة الماركت بليس (متطلّب صريح في الوثيقة).

يفترض:
    - Daphne يعمل بشكل منفصل على 8001.
    - `python manage.py locations_resolve_test` شُغّل مرة على الأقل (ServiceArea JAB).
    - سائق وعميل حقيقيان موجودان في DB، وللسائق مركبة فعّالة.

الاستخدام:
    python manage.py test_presence_consistency_e2e \
        --customer-phone "+96399819335875" \
        --driver-id 5
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


# نقطة داخل منطقة خدمة جبلة (نفس إحداثيات locations_resolve_test)
JABLEH_LNG = 35.9
JABLEH_LAT = 35.36


def _ws_listener(url, out_queue, connection_errors, stop_event):
    try:
        ws = websocket.create_connection(url)
    except Exception as exc:
        connection_errors.append(exc)
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
    help = "E2E test: unified availability across Presence / Matching / Marketplace."

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

    # -----------------------------------------------------------

    def handle(self, *args, **options):
        from rest_framework.authtoken.models import Token
        from django.conf import settings

        from locations.services import LocationService
        from matching.models import OfferStatus, RideOffer
        from matching.services.matching import MatchingService
        from presence.constants import LAST_SEEN_KEY, PresenceState
        from presence.redis_client import get_redis
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
        from users.models import DriverProfile
        from vehicles.models import Vehicle

        User = get_user_model()
        self.timeout = options["timeout"]
        ws_url = options["ws_url"]

        self.passed = 0
        self.failed = 0

        customer = User.objects.get(phone=options["customer_phone"])
        customer_token, _ = Token.objects.get_or_create(user=customer)

        driver = DriverProfile.objects.get(id=options["driver_id"])
        driver_token, _ = Token.objects.get_or_create(user=driver.user)

        pickup = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)
        destination = Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.01, srid=4326)

        # -------------------------------------------------------
        # 0) تحضير بيئة نظيفة
        # -------------------------------------------------------
        active_statuses = [
            RideStatus.DRIVER_SELECTED,
            RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED,
            RideStatus.IN_PROGRESS,
        ]

        stale_ride_ids = list(
            RideOffer.objects
            .filter(
                driver=driver,
                status=OfferStatus.ACCEPTED,
                ride__status__in=active_statuses,
            )
            .values_list("ride_id", flat=True)
        )

        if stale_ride_ids:
            RideRequest.objects.filter(id__in=stale_ride_ids).update(
                status=RideStatus.COMPLETED
            )
            self.stdout.write(
                self.style.WARNING(f"Cleaned stale busy rides: {stale_ride_ids}")
            )

        MarketplaceService.handle_offline(driver.id)
        PresenceService.go_offline(driver.id)

        if not Vehicle.objects.filter(driver=driver, active=True).exists():
            self.stderr.write(self.style.ERROR(
                "[SETUP FAIL] السائق لا يملك مركبة فعّالة - فعّل مركبة أولًا."
            ))
            return

        driver.current_location = pickup
        driver.last_location_at = timezone.now()
        driver.online = True
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.current_occupancy = 0
        driver.available_seats = 4
        driver.save(update_fields=[
            "current_location", "last_location_at", "online",
            "status", "current_occupancy", "available_seats", "updated_at",
        ])

        area_id = LocationService.compute_marketplace_cell_id(JABLEH_LNG, JABLEH_LAT)

        if area_id is None:
            self.stderr.write(self.style.ERROR(
                "[SETUP FAIL] لا توجد ServiceArea تغطي جبلة. "
                "شغّل `python manage.py locations_resolve_test` أولًا."
            ))
            return

        self.stdout.write(f"area_id = {area_id}\n")

        # -------------------------------------------------------
        # 1) مستمع الماركت بليس (زبون ثانٍ يراقب الخلية)
        # -------------------------------------------------------
        market_events = queue.Queue()
        connection_errors = []
        stop_event = threading.Event()

        market_url = f"{ws_url}/ws/marketplace/{area_id}/?token={customer_token.key}"

        threading.Thread(
            target=_ws_listener,
            args=(market_url, market_events, connection_errors, stop_event),
            daemon=True,
        ).start()
        time.sleep(0.4)

        if connection_errors:
            self.stderr.write(
                self.style.ERROR(f"[FAIL] connection error: {connection_errors[0]}")
            )
            return

        self._expect(market_events, "connection.established", "1) marketplace listener connects")
        self._expect(market_events, "marketplace.snapshot", "2) marketplace initial snapshot")

        # -------------------------------------------------------
        # 2) السائق يتصل، يذهب أونلاين، ويرسل موقعًا
        # -------------------------------------------------------
        driver_ws = websocket.create_connection(
            f"{ws_url}/ws/driver/{driver.id}/?token={driver_token.key}"
        )
        driver_ws.recv()  # connection.established

        driver_ws.send(json.dumps({"type": "go_online"}))
        driver_ws.recv()  # presence.ack
        time.sleep(0.15)

        # go_online بعد الإصلاح لا يزرع موقعًا قديمًا. الموقع في DB حديث الآن،
        # فيجب أن يُزرع فعلًا -> نتحقق أن الحالة ليست UNAVAILABLE بسبب الموقع.
        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.PRESENT,
            f"3) after go_online with fresh DB location -> PRESENT (got '{state}')",
        )

        driver_ws.send(json.dumps({
            "type": "location.update",
            "lng": JABLEH_LNG, "lat": JABLEH_LAT,
            "heading": 45, "speed": 0, "accuracy": 8,
        }))

        entered = self._expect(
            market_events, "vehicle.entered_area", "4) vehicle.entered_area"
        )

        # -------------------------------------------------------
        # 3) الوثيقة تتطلب عرض المقاعد المتاحة على الخريطة
        # -------------------------------------------------------
        if entered:
            payload = entered.get("payload") or {}
            self._check(
                "available_seats" in payload,
                f"5) marketplace payload carries available_seats (payload={payload})",
            )

        radius = float(getattr(settings, "MATCHING_NORMAL_RADIUS_KM", 5))

        nearby = PresenceService.get_available_nearby_driver_ids(
            JABLEH_LNG, JABLEH_LAT, radius_km=radius
        )
        self._check(
            driver.id in nearby,
            f"6) driver appears in nearby search (nearby={nearby})",
        )

        # -------------------------------------------------------
        # 4) السيناريو 30: heartbeat حيّ لكن الموقع قديم -> UNAVAILABLE
        # -------------------------------------------------------
        r = get_redis()
        key = PresenceService._key(driver.id)
        saved_location_at = r.hget(key, "last_location_at")

        r.hset(key, "last_location_at", time.time() - 9999)
        r.hset(key, "last_heartbeat", time.time())  # النبض حيّ عمدًا

        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.UNAVAILABLE,
            f"7) fresh heartbeat + stale location -> UNAVAILABLE (got '{state}')",
        )

        nearby = PresenceService.get_available_nearby_driver_ids(
            JABLEH_LNG, JABLEH_LAT, radius_km=radius
        )
        self._check(
            driver.id not in nearby,
            f"8) stale-location driver excluded from nearby (nearby={nearby})",
        )

        # استعادة الموقع
        r.hset(key, "last_location_at", saved_location_at)
        self._check(
            PresenceService.get_state(driver.id) == PresenceState.PRESENT,
            "9) location restored -> PRESENT again",
        )

        # -------------------------------------------------------
        # 5) السيناريو 4 و31: قبول العرض -> BUSY -> يختفي فورًا
        # -------------------------------------------------------
        ride = RideRequest.objects.create(
            customer=customer,
            pickup=pickup,
            destination=destination,
            mode=RideMode.STANDARD,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
        )
        self.stdout.write(f"    created ride id={ride.id}")

        driver.refresh_from_db()

        offer = MatchingService.create_offer(
            ride_id=ride.id,
            driver=driver,
            gross_fare=Decimal("25.00"),
            eta_minutes=6,
        )

        MatchingService.select_offer(
            ride_id=ride.id,
            offer_id=offer.id,
            customer=customer,
        )
        time.sleep(0.3)

        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.BUSY,
            f"10) after offer accepted -> BUSY in Redis (got '{state}')",
        )

        nearby = PresenceService.get_available_nearby_driver_ids(
            JABLEH_LNG, JABLEH_LAT, radius_km=radius
        )
        self._check(
            driver.id not in nearby,
            f"11) busy driver invisible to a second customer (nearby={nearby})",
        )

        self._expect(
            market_events, "vehicle.left_area",
            "12) vehicle.left_area broadcast immediately on accept",
        )

        cell = PresenceService.get_current_cell(driver.id)
        self._check(
            cell is None,
            f"13) marketplace cell cleared for busy driver (cell={cell})",
        )

        # -------------------------------------------------------
        # 6) السيناريو 5: إلغاء الرحلة -> يعود متاحًا
        # -------------------------------------------------------
        MatchingService.cancel_ride(ride_id=ride.id, customer=customer)
        time.sleep(0.3)

        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.PRESENT,
            f"14) after ride cancelled -> driver released from BUSY (got '{state}')",
        )

        # لقطة ما قبل النبضة: بها نعرف متى وصلت فعلًا لا متى ظننّا.
        location_before_ping = r.hget(key, "last_location_at")

        driver_ws.send(json.dumps({
            "type": "location.update",
            "lng": JABLEH_LNG, "lat": JABLEH_LAT, "heading": 50,
        }))

        self._expect(
            market_events, "vehicle.entered_area",
            "15) driver re-enters marketplace on next GPS ping",
        )

        # -------------------------------------------------------
        # 7) sweep ثم heartbeat -> إعادة تسليح تلقائية (كان فشلًا صامتًا)
        # -------------------------------------------------------
        #
        # ننتظر أثر النبضة في Redis قبل أن نُقدّم الساعة.
        #
        # vehicle.entered_area وحده لم يعد دليلًا كافيًا: تحرير السائق عند
        # إلغاء الرحلة (الفحص 14) صار يُعيده إلى خليّته ويبثّ الحدث نفسه.
        # فقد يلتقط _expect حدث التحرير لا حدث النبضة، فنُقدّم الساعة ثم
        # تصل النبضة متأخرة فتُنعش last_heartbeat وlast_seen - والمكنسة لا
        # تجد أحدًا. سباق كشفه تغييرُ سلوكٍ صحيح، لا عطلٌ في المكنسة.
        deadline = time.time() + 5

        while time.time() < deadline:
            if r.hget(key, "last_location_at") != location_before_ping:
                break
            time.sleep(0.1)

        ancient = time.time() - 9999
        r.hset(key, "last_heartbeat", ancient)
        r.zadd(LAST_SEEN_KEY, {str(driver.id): ancient})

        swept = PresenceService.sweep_stale_drivers()
        self._check(
            driver.id in swept,
            f"16) sweep detects the silent driver (swept={swept})",
        )

        self._check(
            PresenceService.get_state(driver.id) == PresenceState.OFFLINE,
            "17) swept driver is OFFLINE",
        )

        driver_ws.send(json.dumps({"type": "heartbeat"}))

        # لا ننام رقمًا ثابتًا: go_online صارت تستعلم القاعدة لتشتقّ
        # الارتباط (BUSY أم SHARING أم حرّ)، فإعادة التسليح لم تعد كتابةً
        # في Redis وحدها. ننتظر النتيجة نفسها بدل أن نراهن على مدّتها.
        deadline = time.time() + 5
        state = PresenceService.get_state(driver.id)

        while state == PresenceState.OFFLINE and time.time() < deadline:
            time.sleep(0.1)
            state = PresenceService.get_state(driver.id)
        self._check(
            state in (PresenceState.PRESENT, PresenceState.UNAVAILABLE),
            f"18) heartbeat after sweep re-arms presence instead of failing "
            f"silently (got '{state}')",
        )

        # -------------------------------------------------------
        # 8) انتهاء صلاحية العرض يجب أن يُبثّ (كان صامتًا)
        # -------------------------------------------------------
        ride2 = RideRequest.objects.create(
            customer=customer,
            pickup=pickup,
            destination=destination,
            mode=RideMode.STANDARD,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
        )

        ride2_events = queue.Queue()
        threading.Thread(
            target=_ws_listener,
            args=(
                f"{ws_url}/ws/rides/{ride2.id}/?token={customer_token.key}",
                ride2_events, connection_errors, stop_event,
            ),
            daemon=True,
        ).start()
        time.sleep(0.4)

        self._expect(ride2_events, "connection.established", "19) ride2 listener connects")
        self._expect(ride2_events, "ride.snapshot", "20) ride2 snapshot")

        driver_ws.send(json.dumps({
            "type": "location.update",
            "lng": JABLEH_LNG, "lat": JABLEH_LAT, "heading": 60,
        }))
        time.sleep(0.4)
        driver.refresh_from_db()

        offer2 = MatchingService.create_offer(
            ride_id=ride2.id,
            driver=driver,
            gross_fare=Decimal("30.00"),
            eta_minutes=5,
        )
        self._expect(ride2_events, "offer.created", "21) offer.created on ride2")

        RideOffer.objects.filter(id=offer2.id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        from matching.tasks import expire_stale_offers
        result = expire_stale_offers()
        self.stdout.write(f"    expire_stale_offers() -> {result}")

        self._expect(
            ride2_events, "offer.expired",
            "22) offer.expired reaches the customer over WebSocket",
        )

        offer2.refresh_from_db()
        self._check(
            offer2.status == OfferStatus.EXPIRED,
            f"23) offer2 marked EXPIRED in DB (status={offer2.status})",
        )

        # -------------------------------------------------------
        # 9) مسار REST يجب أن يزامن Presence مثل مسار WebSocket
        # -------------------------------------------------------
        from drivers.services.availability import DriverAvailabilityService

        driver.refresh_from_db()
        DriverAvailabilityService.go_offline(driver)
        time.sleep(0.3)

        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.OFFLINE,
            f"24) REST go_offline syncs Redis presence too (got '{state}')",
        )

        self._expect(
            market_events, "vehicle.left_area",
            "25) REST go_offline removes the car from the live map",
        )

        # -------------------------------------------------------
        # تنظيف + تقرير
        # -------------------------------------------------------
        RideRequest.objects.filter(id__in=[ride.id, ride2.id]).update(
            status=RideStatus.CANCELLED
        )

        stop_event.set()
        driver_ws.close()

        total = self.passed + self.failed
        self.stdout.write("")

        if self.failed == 0:
            self.stdout.write(self.style.SUCCESS(
                f"Presence consistency E2E: {self.passed}/{total} passed."
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"Presence consistency E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
            ))

    # -----------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
        else:
            self.failed += 1
            self.stderr.write(self.style.ERROR(f"[FAIL] {label}"))
        return condition

    def _expect(self, q, expected_type, label):
        """
        ينتظر حدثًا من النوع المطلوب ويتجاهل ما قبله من أحداث غير ذات صلة
        (مثل driver.location المتدفق باستمرار) بدل الفشل عند أول حدث مختلف.
        """
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
            f"[FAIL] {label}: timed out waiting for '{expected_type}'. "
            f"seen instead: {seen}"
        ))
        return None