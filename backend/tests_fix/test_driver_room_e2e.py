"""
اختبار E2E للجزء F: driver.location الحي + driver.offline عند انقطاع
مفاجئ أثناء رحلة نشطة. بعملية واحدة، بلا نوافذ متعددة.

يفترض:
    - Daphne يعمل بشكل منفصل (نفس ما سبق).
    - سائق وعميل حقيقيان موجودان في DB.

الاستخدام:
    python manage.py test_driver_room_e2e \
        --customer-phone "+96399819335875" \
        --driver-id 5
"""
import os
import json
import queue
import threading
import time
from decimal import Decimal

import websocket
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone


def _ws_listener(url, out_queue, connection_error, stop_event):
    try:
        ws = websocket.create_connection(url)
    except Exception as exc:
        connection_error.append(exc)
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
    help = "End-to-end test for Driver Room + driver.location/offline events (Part F)."

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
        parser.add_argument("--timeout", type=float, default=5.0)

    def handle(self, *args, **options):
        from matching.services.matching import MatchingService
        from rest_framework.authtoken.models import Token
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
        from users.models import DriverProfile
        from matching.models import RideOffer, OfferStatus
        from presence.services import PresenceService
        from presence.redis_client import get_redis
        from presence.constants import LAST_SEEN_KEY

        User = get_user_model()
        timeout = options["timeout"]
        ws_url = options["ws_url"]

        customer = User.objects.get(phone=options["customer_phone"])
        customer_token, _ = Token.objects.get_or_create(user=customer)

        driver = DriverProfile.objects.get(id=options["driver_id"])
        driver_token, _ = Token.objects.get_or_create(user=driver.user)

        pickup = Point(36.2765, 33.5138, srid=4326)
        destination = Point(36.2913, 33.5102, srid=4326)

        # -----------------------------------------------------------
        # 0) تنظيف بقايا اختبارات سابقة (نفس أسلوب test_ride_room_e2e)
        # -----------------------------------------------------------
        active_statuses = [
            RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
        ]
        stale_ride_ids = list(
            RideOffer.objects
            .filter(driver=driver, status=OfferStatus.ACCEPTED, ride__status__in=active_statuses)
            .values_list("ride_id", flat=True)
        )
        if stale_ride_ids:
            RideRequest.objects.filter(id__in=stale_ride_ids).update(status=RideStatus.COMPLETED)
            self.stdout.write(self.style.WARNING(f"Cleaned up stale rides: {stale_ride_ids}"))

        # -----------------------------------------------------------
        # 1) تجهيز السائق + رحلة جديدة + عرض مقبول (نصل مباشرة لحالة
        #    "سائق بصدد التوجه للعميل" بدون إعادة اختبار الجزء E كله)
        # -----------------------------------------------------------
        driver.current_location = pickup
        driver.last_location_at = timezone.now()
        driver.online = True
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.current_occupancy = 0
        driver.available_seats = 4
        driver.save(update_fields=[
            "current_location", "last_location_at", "online",
            "status", "current_occupancy", "available_seats",
        ])

        ride = RideRequest.objects.create(
            customer=customer, pickup=pickup, destination=destination,
            mode=RideMode.STANDARD, trip_category=TripCategory.CITY,
            passenger_count=1, status=RideStatus.SEARCHING,
        )
        self.stdout.write(f"Created ride id={ride.id}")

        offer = MatchingService.create_offer(
            ride_id=ride.id, driver=driver, gross_fare=Decimal("25.00"), eta_minutes=6,
        )
        MatchingService.select_offer(ride_id=ride.id, offer_id=offer.id, customer=customer)
        self.stdout.write(f"Offer {offer.id} accepted -> ride now DRIVER_SELECTED")

        # -----------------------------------------------------------
        # 2) اتصالان: العميل بغرفة الرحلة، والسائق بغرفته الشخصية
        # -----------------------------------------------------------
        ride_events = queue.Queue()
        driver_events = queue.Queue()
        connection_errors = []
        stop_event = threading.Event()

        ride_ws_url = f"{ws_url}/ws/rides/{ride.id}/?token={customer_token.key}"
        driver_ws_url = f"{ws_url}/ws/driver/{driver.id}/?token={driver_token.key}"

        ride_thread = threading.Thread(
            target=_ws_listener, args=(ride_ws_url, ride_events, connection_errors, stop_event), daemon=True,
        )
        driver_thread = threading.Thread(
            target=_ws_listener, args=(driver_ws_url, driver_events, connection_errors, stop_event), daemon=True,
        )
        ride_thread.start()
        driver_thread.start()
        time.sleep(0.3)

        if connection_errors:
            self.stderr.write(self.style.ERROR(f"[FAIL] connection error: {connection_errors[0]}"))
            return

        def _expect(q, expected_type, label):
            try:
                event = q.get(timeout=timeout)
            except queue.Empty:
                self.stderr.write(self.style.ERROR(f"[FAIL] {label}: timed out waiting for '{expected_type}'"))
                return None
            actual = event.get("event_type")
            if actual == expected_type:
                self.stdout.write(self.style.SUCCESS(f"[OK]   {label}: received '{actual}'"))
            else:
                self.stderr.write(self.style.ERROR(f"[FAIL] {label}: expected '{expected_type}', got '{actual}' -> {event}"))
            return event

        _expect(ride_events, "connection.established", "1) customer connects to ride room")
        _expect(ride_events, "ride.snapshot", "2) initial ride snapshot")
        _expect(driver_events, "connection.established", "3) driver connects to driver room")

        # -----------------------------------------------------------
        # 4) السائق يرسل go_online ثم موقعًا حيًا عبر WebSocket
        # -----------------------------------------------------------
        driver_ws = websocket.create_connection(driver_ws_url)  # اتصال ثانٍ للإرسال فقط
        driver_ws.send(json.dumps({"type": "go_online"}))
        time.sleep(0.2)

        driver_ws.send(json.dumps({
            "type": "location.update", "lng": 36.2800, "lat": 33.5150,
            "speed": 22.5, "heading": 90,
        }))
        self.stdout.write("Driver sent location.update via WebSocket")

        event = _expect(ride_events, "driver.location", "5) customer receives driver.location")
        if event:
            data = event.get("payload", {})
            self.stdout.write(f"    -> lng={data.get('lng')} lat={data.get('lat')} speed={data.get('speed')}")

        # -----------------------------------------------------------
        # 6) تأكيد أن DB تزامنت فعليًا (current_location/last_location_at)
        # -----------------------------------------------------------
        driver.refresh_from_db()
        db_ok = driver.current_location is not None and driver.current_location.x == 36.28
        if db_ok:
            self.stdout.write(self.style.SUCCESS("[OK]   6) DriverProfile.current_location synced to DB"))
        else:
            self.stderr.write(self.style.ERROR(f"[FAIL] 6) DB not synced: {driver.current_location}"))

        # -----------------------------------------------------------
        # 7) محاكاة انقطاع مفاجئ: نزوّر last_heartbeat في الماضي البعيد
        #    مباشرة في Redis (بدل انتظار 61 ثانية فعليًا) ثم نشغّل sweep
        #    يدويًا - يجب أن يصل driver.offline لغرفة الرحلة لأن السائق
        #    ما زال مرتبطًا برحلة نشطة (DRIVER_SELECTED).
        # -----------------------------------------------------------
        r = get_redis()
        ancient = time.time() - 999
        r.hset(PresenceService._key(driver.id), "last_heartbeat", ancient)
        r.zadd(LAST_SEEN_KEY, {str(driver.id): ancient})

        from presence.tasks import sweep_stale_driver_presence
        result = sweep_stale_driver_presence()  # استدعاء مباشر متزامن، بدون Celery worker
        self.stdout.write(f"Sweep result: {result}")

        _expect(ride_events, "driver.offline", "8) customer notified of driver.offline mid-ride")

        self.stdout.write(self.style.SUCCESS(f"\nE2E test finished for ride_id={ride.id}, driver_id={driver.id}."))
        stop_event.set()
        driver_ws.close()