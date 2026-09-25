"""
اختبار E2E للجزء G: دخول/تحديث/مغادرة خلايا الماركت بليس + الانتقال بين
مدينتين مختلفتي الدقة (جبلة precision=7 <-> اللاذقية precision=6) +
تنظيف العضوية عند go_offline. بعملية واحدة، بلا نوافذ متعددة.

يفترض:
    - Daphne يعمل بشكل منفصل.
    - سائق وعميل حقيقيان موجودان في DB.
    - شغّل `python manage.py locations_resolve_test` أولاً لضمان وجود
      ServiceArea لجبلة (JAB) واللاذقية (LAT).

الاستخدام:
    python manage.py test_marketplace_e2e \
        --customer-phone "+96399819335875" \
        --driver-id 5
"""
import os
import json
import queue
import threading
import time

import websocket
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


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
    help = "End-to-end test for Marketplace Rooms (Part G)."

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
        from rest_framework.authtoken.models import Token
        from users.models import DriverProfile
        from locations.services import LocationService
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService

        User = get_user_model()
        timeout = options["timeout"]
        ws_url = options["ws_url"]

        customer = User.objects.get(phone=options["customer_phone"])
        customer_token, _ = Token.objects.get_or_create(user=customer)

        driver = DriverProfile.objects.get(id=options["driver_id"])
        driver_token, _ = Token.objects.get_or_create(user=driver.user)

        # -----------------------------------------------------------
        # 0) تنظيف بقايا اختبارات سابقة: أخرج السائق من أي خلية قديمة
        #    عالقة من تشغيلات ماضية، حتى لا تُفسد فحص "أول ظهور". كذلك
        #    نضمن أن occupancy/available_seats تسمح بالتوفر فعليًا -
        #    وإلا سيفشل الاختبار لسبب لا علاقة له بمنطق الماركت بليس.
        # -----------------------------------------------------------
        MarketplaceService.handle_offline(driver.id)
        PresenceService.go_offline(driver.id)

        driver.current_occupancy = 0
        driver.available_seats = 4
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.save(update_fields=["current_occupancy", "available_seats", "status", "updated_at"])

        # نقاط اختبار: جبلة (داخل JAB) ثم اللاذقية (داخل LAT) - نفس
        # الإحداثيات المستخدمة في locations_resolve_test لضمان التطابق.
        jableh_point = (35.9, 35.36)
        jableh_point_nearby = (35.9005, 35.3605)  # قريبة جدًا - يجب أن تبقى بنفس الخلية
        lattakia_point = (35.78, 35.53)

        area_a = LocationService.compute_marketplace_cell_id(*jableh_point)
        area_a_nearby = LocationService.compute_marketplace_cell_id(*jableh_point_nearby)
        area_b = LocationService.compute_marketplace_cell_id(*lattakia_point)

        if area_a is None or area_b is None:
            self.stderr.write(self.style.ERROR(
                "[SETUP FAIL] لم يتم العثور على ServiceArea لجبلة أو اللاذقية. "
                "شغّل `python manage.py locations_resolve_test` أولاً."
            ))
            return

        same_cell = area_a == area_a_nearby
        self.stdout.write(f"area_a={area_a}  area_a_nearby={area_a_nearby}  (same_cell={same_cell})")
        self.stdout.write(f"area_b={area_b}")

        if not same_cell:
            self.stderr.write(self.style.WARNING(
                "[WARN] النقطة القريبة وقعت في خلية مختلفة عن area_a - سيُعاد "
                "تفسير خطوة 'نفس الخلية' كخطوة انتقال إضافية بدل vehicle.updated."
            ))

        # -----------------------------------------------------------
        # 1) اتصالان مستمعان: خلية جبلة (area_a) وخلية اللاذقية (area_b)،
        #    مفتوحان *قبل* أي حركة للسائق، حتى لا نفوّت أول حدث.
        # -----------------------------------------------------------
        events_a = queue.Queue()
        events_b = queue.Queue()
        connection_errors = []
        stop_event = threading.Event()

        url_a = f"{ws_url}/ws/marketplace/{area_a}/?token={customer_token.key}"
        url_b = f"{ws_url}/ws/marketplace/{area_b}/?token={customer_token.key}"

        threading.Thread(target=_ws_listener, args=(url_a, events_a, connection_errors, stop_event), daemon=True).start()
        threading.Thread(target=_ws_listener, args=(url_b, events_b, connection_errors, stop_event), daemon=True).start()
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

        _expect(events_a, "connection.established", "1) listener A connects (area_a)")
        _expect(events_a, "marketplace.snapshot", "2) listener A initial snapshot (should be empty)")
        _expect(events_b, "connection.established", "3) listener B connects (area_b)")
        _expect(events_b, "marketplace.snapshot", "4) listener B initial snapshot (should be empty)")

        # -----------------------------------------------------------
        # 2) السائق يتصل بغرفته، يذهب أونلاين، ويرسل موقعًا في جبلة
        # -----------------------------------------------------------
        driver_ws_url = f"{ws_url}/ws/driver/{driver.id}/?token={driver_token.key}"
        driver_ws = websocket.create_connection(driver_ws_url)
        driver_ws.recv()  # connection.established - نتجاهله هنا، ليس محور هذا الاختبار

        driver_ws.send(json.dumps({"type": "go_online"}))
        driver_ws.recv()  # presence.ack
        time.sleep(0.1)

        driver_ws.send(json.dumps({
            "type": "location.update", "lng": jableh_point[0], "lat": jableh_point[1], "heading": 45,
        }))

        _expect(events_a, "vehicle.entered_area", "5) listener A: vehicle.entered_area (Jableh)")

        # -----------------------------------------------------------
        # 3) حركة صغيرة داخل نفس الخلية -> تحديث فقط، بلا دخول/خروج
        # -----------------------------------------------------------
        driver_ws.send(json.dumps({
            "type": "location.update",
            "lng": jableh_point_nearby[0], "lat": jableh_point_nearby[1], "heading": 50,
        }))

        expected_same_cell_event = "vehicle.updated" if same_cell else "vehicle.entered_area"
        _expect(events_a, expected_same_cell_event, "6) listener A: same-cell movement")

        # -----------------------------------------------------------
        # 4) انتقال حقيقي لمدينة أخرى (اللاذقية) -> يجب أن يغادر A ويدخل B
        # -----------------------------------------------------------
        driver_ws.send(json.dumps({
            "type": "location.update", "lng": lattakia_point[0], "lat": lattakia_point[1], "heading": 180,
        }))

        _expect(events_a, "vehicle.left_area", "7) listener A: vehicle.left_area (left Jableh)")
        _expect(events_b, "vehicle.entered_area", "8) listener B: vehicle.entered_area (entered Lattakia)")

        # -----------------------------------------------------------
        # 5) تحقق من snapshot لعميل يتصل *بعد* دخول السائق للخلية B
        # -----------------------------------------------------------
        events_b_late = queue.Queue()
        threading.Thread(
            target=_ws_listener,
            args=(url_b, events_b_late, connection_errors, stop_event),
            daemon=True,
        ).start()
        time.sleep(0.3)

        _expect(events_b_late, "connection.established", "9) late listener B connects")
        snapshot_event = _expect(events_b_late, "marketplace.snapshot", "10) late listener B snapshot")

        if snapshot_event:
            vehicles = snapshot_event.get("payload", {}).get("vehicles", [])
            found = any(v.get("driver_id") == driver.id for v in vehicles)
            if found:
                self.stdout.write(self.style.SUCCESS(f"[OK]   11) driver {driver.id} present in late snapshot: {vehicles}"))
            else:
                self.stderr.write(self.style.ERROR(f"[FAIL] 11) driver {driver.id} missing from snapshot: {vehicles}"))

        # -----------------------------------------------------------
        # 6) go_offline -> يجب أن يغادر خلية B فورًا
        # -----------------------------------------------------------
        driver_ws.send(json.dumps({"type": "go_offline"}))
        driver_ws.recv()  # presence.ack

        _expect(events_b, "vehicle.left_area", "12) listener B: vehicle.left_area (driver went offline)")

        self.stdout.write(self.style.SUCCESS("\nE2E test finished for Marketplace Rooms (Part G)."))
        stop_event.set()
        driver_ws.close()