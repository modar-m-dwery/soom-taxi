"""
اختبار E2E لغرفة الرحلة (Part E) بعملية واحدة، بلا نوافذ متعددة ولا
اعتماد على توقيت بشري:

    1) يجدد موقع/حالة السائق للحظة التنفيذ فعليًا (لا قبلها).
    2) ينشئ رحلة جديدة فورًا.
    3) يفتح WebSocket في thread منفصل (لا يحجب باقي الاختبار).
    4) يستدعي MatchingService.create_offer() مباشرة (بدون أي
       with transaction.atomic() إضافية من حولها - هي أصلًا atomic،
       وبذلك on_commit تعمل تلقائيًا بلا أي تدخل يدوي).
    5) يستدعي MatchingService.select_offer() مباشرة لنفس السبب.
    6) يتحقق أن كل حدث وصل عبر WebSocket بالترتيب الصحيح، بمهلة قصيرة.

يتطلب أن يكون Daphne يعمل بالفعل بشكل منفصل (نفس الطريقة المستخدمة
سابقًا: daphne -b 0.0.0.0 -p 8001 config.asgi:application).

الاستخدام:
    python manage.py test_ride_room_e2e \
        --customer-phone "+96399819335875" \
        --driver-id 5
"""
import os
import json
import queue
import threading
from decimal import Decimal

import websocket
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "End-to-end test for Ride Room realtime events (Part E), single process."

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
        parser.add_argument("--timeout", type=float, default=5.0, help="ثوانٍ لكل حدث منتظر")

    def handle(self, *args, **options):
        from matching.services.matching import MatchingService
        from rest_framework.authtoken.models import Token
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
        from users.models import DriverProfile

        User = get_user_model()
        timeout = options["timeout"]

        customer = User.objects.get(phone=options["customer_phone"])
        customer_token, _ = Token.objects.get_or_create(user=customer)

        driver = DriverProfile.objects.get(id=options["driver_id"])

        pickup = Point(36.2765, 33.5138, srid=4326)
        destination = Point(36.2913, 33.5102, srid=4326)

        # -----------------------------------------------------------
        # 0) تنظيف بقايا اختبارات سابقة: لو هذا السائق "مشغول" برحلة
        #    قديمة معلّقة (عرض ACCEPTED على رحلة لم تُكمَل/تُلغَ)، فهو
        #    يُستبعد بحق من get_busy_driver_ids() في أي رحلة جديدة -
        #    هذا سلوك MatchingService الصحيح، وليس خطأ. نظّفه هنا فقط
        #    كجزء من تحضير بيئة الاختبار (يحاكي "السائق أنهى رحلته
        #    السابقة")، ولا نلمس أي كود في matching/services.
        # -----------------------------------------------------------
        from matching.models import RideOffer, OfferStatus

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
                self.style.WARNING(
                    f"Cleaned up {len(stale_ride_ids)} stale busy ride(s) "
                    f"for driver {driver.id} from previous test runs: {stale_ride_ids}"
                )
            )

        # -----------------------------------------------------------
        # 1) تجديد حالة السائق الآن فقط - لا قبل الاختبار بدقائق
        # -----------------------------------------------------------
        driver.current_location = pickup
        driver.last_location_at = timezone.now()
        driver.online = True
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.current_occupancy = 0
        driver.available_seats = 4
        driver.save(
            update_fields=[
                "current_location", "last_location_at", "online",
                "status", "current_occupancy", "available_seats",
            ]
        )
        self.stdout.write(f"Driver {driver.id} refreshed: online, location just now.")

        # -----------------------------------------------------------
        # 2) رحلة جديدة، تُستخدم فورًا
        # -----------------------------------------------------------
        ride = RideRequest.objects.create(
            customer=customer,
            pickup=pickup,
            destination=destination,
            mode=RideMode.STANDARD,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
        )
        self.stdout.write(f"Created ride id={ride.id} status={ride.status}")

        # -----------------------------------------------------------
        # 3) WebSocket في thread منفصل يجمع كل حدث في queue
        # -----------------------------------------------------------
        events = queue.Queue()
        connection_error = []
        stop_event = threading.Event()

        def _listen():
            try:
                ws = websocket.create_connection(
                    f"{options['ws_url']}/ws/rides/{ride.id}/?token={customer_token.key}",
                )
            except Exception as exc:
                connection_error.append(exc)
                return

            # مهلة قراءة قصيرة داخل الحلقة فقط لنستطيع التحقق دوريًا من
            # stop_event (حتى لا يبقى الـthread عالقًا للأبد لو انتهى
            # الاختبار). هذا مختلف تمامًا عن وضع timeout على create_connection
            # نفسها: هناك كان أي غياب رسالة لأكثر من 5 ثوانٍ يُغلق الاتصال
            # فعليًا (WebSocketTimeoutException غير مُعالجة) - هنا فقط
            # نتجاهل مهلة القراءة الفردية ونعيد المحاولة.
            ws.settimeout(1.0)

            while not stop_event.is_set():
                try:
                    events.put(json.loads(ws.recv()))
                except websocket.WebSocketTimeoutException:
                    continue  # لا رسالة خلال ثانية - طبيعي، أعد المحاولة
                except Exception:
                    break

            ws.close()

        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()

        def _expect(expected_type, label):
            try:
                event = events.get(timeout=timeout)
            except queue.Empty:
                self.stderr.write(
                    self.style.ERROR(f"[FAIL] {label}: timed out waiting for '{expected_type}'")
                )
                return None

            actual_type = event.get("event_type")

            if actual_type == expected_type:
                self.stdout.write(self.style.SUCCESS(f"[OK]   {label}: received '{actual_type}'"))
            else:
                self.stderr.write(
                    self.style.ERROR(
                        f"[FAIL] {label}: expected '{expected_type}', got '{actual_type}' -> {event}"
                    )
                )

            return event

        # امنح الـthread فرصة حقيقية ليتصل قبل أول انتظار حدث
        import time
        time.sleep(0.3)

        if connection_error:
            self.stderr.write(self.style.ERROR(f"[FAIL] WebSocket connection error: {connection_error[0]}"))
            return

        _expect("connection.established", "1) WebSocket connect")
        _expect("ride.snapshot", "2) Initial snapshot")

        # -----------------------------------------------------------
        # 4) تقديم العرض - نداء مباشر، بلا with transaction.atomic()
        #    إضافية. _create_offer_atomic هي بذاتها أعلى atomic هنا،
        #    لذلك on_commit تعمل تلقائيًا فور عودة هذا الاستدعاء.
        # -----------------------------------------------------------
        offer = MatchingService.create_offer(
            ride_id=ride.id,
            driver=driver,
            gross_fare=Decimal("25.00"),
            eta_minutes=6,
        )
        self.stdout.write(f"Created offer id={offer.id} status={offer.status}")

        _expect("offer.created", "3) offer.created broadcast")

        # -----------------------------------------------------------
        # 5) قبول العميل للعرض - نفس المبدأ، نداء مباشر بلا لفّ إضافي
        # -----------------------------------------------------------
        offer = MatchingService.select_offer(
            ride_id=ride.id,
            offer_id=offer.id,
            customer=customer,
        )
        self.stdout.write(f"Offer accepted, status={offer.status}")

        _expect("offer.accepted", "4) offer.accepted broadcast")

        # -----------------------------------------------------------
        # 6) اختبار سلبي: محاولة تقديم عرض ثانٍ على نفس الرحلة من نفس
        #    السائق يجب أن تفشل (الرحلة لم تعد SEARCHING/OFFERS_RECEIVED)
        #    ويجب ألا يصل أي حدث جديد إطلاقًا - يثبت أن on_commit لا يبث
        #    شيئًا عند فشل العملية (rollback).
        # -----------------------------------------------------------
        from matching.services.matching import MatchingError

        try:
            MatchingService.create_offer(
                ride_id=ride.id,
                driver=driver,
                gross_fare=Decimal("30.00"),
                eta_minutes=5,
            )
            self.stderr.write(self.style.ERROR("[FAIL] 5) expected MatchingError but offer was created"))
        except MatchingError as exc:
            self.stdout.write(self.style.SUCCESS(f"[OK]   5) rejected as expected: {exc}"))

        try:
            leaked_event = events.get(timeout=1.0)
            self.stderr.write(
                self.style.ERROR(f"[FAIL] 6) an event leaked after a failed operation: {leaked_event}")
            )
        except queue.Empty:
            self.stdout.write(self.style.SUCCESS("[OK]   6) no phantom event after failed operation"))

        # -----------------------------------------------------------
        # 7) إلغاء الرحلة - يختبر التصحيح الثالث (ride.cancelled) من
        #    INTEGRATION_PART_E.md، وهو الوحيد الذي لم يُختبر بعد.
        #    نستخدم نفس اتصال WebSocket المفتوح أصلاً على ride_{id}؛
        #    اسم المجموعة لا يتغير بإلغاء الرحلة، فلا حاجة لاتصال جديد.
        # -----------------------------------------------------------
        cancelled_ride = MatchingService.cancel_ride(
            ride_id=ride.id,
            customer=customer,
        )
        self.stdout.write(f"Ride cancelled, status={cancelled_ride.status}")

        _expect("ride.cancelled", "7) ride.cancelled broadcast")

        self.stdout.write(self.style.SUCCESS(f"\nE2E test finished for ride_id={ride.id}."))
        stop_event.set()