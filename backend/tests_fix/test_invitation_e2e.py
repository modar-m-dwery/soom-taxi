"""
اختبار E2E للمرحلة 8أ — الدعوة المباشرة لسائق محدد من الخريطة الحيّة.

يغطّي تدفّق الوثيقة §15.1 كاملًا:
    اختيار سيارة -> دعوة بمهلة يختارها الزبون -> قبول أو رفض أو انتهاء
    -> قفل الرحلة عند القبول -> بقاء الطلب في البحث عند الرفض.

وأهم فحص فيه هو رقم 12: بثّ موقع السائق لغرفة الرحلة بعد قبول الدعوة.
هذا ما يثبت أن جسر RideOffer يعمل — ولولاه لكان الزبون يقفل الرحلة ثم لا
يرى سيارته تتحرك أبدًا، وهو فشل صامت لا يظهر في أي فحص آخر.

يفترض:
    - Daphne يعمل على 8001.
    - python manage.py locations_resolve_test  (لوجود ServiceArea لجبلة)
    - سائق بمركبة فعّالة، وعميل.

الاستخدام:
    python manage.py test_invitation_e2e \
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
    help = "End-to-end test for direct ride invitations (stage 8a)."

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
        from matching.models import (
            InvitationStatus,
            OfferStatus,
            RideInvitation,
            RideOffer,
        )
        from matching.services.invitation import InvitationError, InvitationService
        from matching.services.matching import MatchingService
        from matching.services.nearby import NearbyVehiclesService
        from presence.constants import PresenceState
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService
        from rides.models import RideMode, RideRequest, RideStatus, TripCategory
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
        destination = Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.01, srid=4326)

        area = LocationService.resolve_area(JABLEH_LNG, JABLEH_LAT)
        if area is None:
            self.stderr.write(self.style.ERROR(
                "[SETUP FAIL] لا توجد ServiceArea تغطي جبلة. "
                "شغّل locations_resolve_test أولًا."
            ))
            return

        if not area.allows_invitation_for_mode(RideMode.FAST):
            self.stderr.write(self.style.ERROR(
                f"[SETUP FAIL] {area.name}: نمط 'fast' غير مفعّل في "
                f"الأنماط الفعلية = {area.effective_invitation_modes}"
            ))
            return

        if not Vehicle.objects.filter(driver=driver, active=True).exists():
            self.stderr.write(self.style.ERROR("[SETUP FAIL] لا مركبة فعّالة للسائق."))
            return

        self.stdout.write(
            f"area={area.code}  ttl_options={area.effective_ttl_options}  "
            f"max_parallel={area.invitation_max_parallel}\n"
        )

        # -------------------------------------------------------------
        # 0) تنظيف بيئة
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
            RideRequest.objects.filter(id__in=stale).update(status=RideStatus.COMPLETED)
            self.stdout.write(self.style.WARNING(f"نُظّفت رحلات عالقة: {stale}"))

        RideInvitation.objects.filter(
            driver=driver, status=InvitationStatus.PENDING
        ).update(status=InvitationStatus.CANCELLED)

        MarketplaceService.handle_offline(driver.id)
        PresenceService.go_offline(driver.id)

        driver.current_location = pickup
        driver.last_location_at = timezone.now()
        driver.online = True
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.current_occupancy = 0
        driver.available_seats = 4
        driver.save(update_fields=[
            "current_location", "last_location_at", "online", "status",
            "current_occupancy", "available_seats", "updated_at",
        ])
        PresenceService.go_online(driver)
        PresenceService.update_location(driver.id, JABLEH_LNG, JABLEH_LAT, heading=45)

        self.errors = []
        self.stop = threading.Event()

        driver_events = queue.Queue()
        threading.Thread(
            target=_listen,
            args=(f"{ws_url}/ws/driver/{driver.id}/?token={driver_token.key}",
                  driver_events, self.errors, self.stop),
            daemon=True,
        ).start()
        time.sleep(0.4)

        if self.errors:
            self.stderr.write(self.style.ERROR(f"[FAIL] اتصال: {self.errors[0]}"))
            return

        self._expect(driver_events, "connection.established", "1) اتصال غرفة السائق")

        def new_ride():
            r = RideRequest.objects.create(
                customer=customer, pickup=pickup, destination=destination,
                mode=RideMode.FAST, trip_category=TripCategory.CITY,
                passenger_count=1, status=RideStatus.SEARCHING,
                service_area=area, gross_fare=Decimal("25.00"),
                customer_total=Decimal("25.00"), driver_net=Decimal("25.00"),
                pricing_policy="platform_fixed", currency=area.currency_code,
            )
            q = queue.Queue()
            threading.Thread(
                target=_listen,
                args=(f"{ws_url}/ws/rides/{r.id}/?token={customer_token.key}",
                      q, self.errors, self.stop),
                daemon=True,
            ).start()
            time.sleep(0.4)
            self._drain(q, 2)  # connection.established + ride.snapshot
            return r, q

        # =============================================================
        # المرحلة أ — الخريطة ثم القبول
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— أ: الخريطة والقبول —"))

        ride, ride_events = new_ride()
        driver.refresh_from_db()

        nearby = NearbyVehiclesService.for_ride(ride)
        found = next((v for v in nearby if v["driver_id"] == driver.id), None)
        self._check(found is not None, f"2) السائق يظهر في nearby-vehicles ({len(nearby)} سيارة)")

        if found:
            self._check(
                found["available_seats"] == 4 and found["eta_minutes"] >= 1,
                f"3) البيانات كاملة: مقاعد={found['available_seats']} "
                f"eta={found['eta_minutes']}د مسافة={found['approximate_distance_m']}م",
            )
            self._check(
                abs(found["lng"] - JABLEH_LNG) < 0.01 and len(str(found["lng"]).split(".")[-1]) <= 3,
                f"4) الإحداثيات مُقرَّبة للخصوصية: ({found['lng']}, {found['lat']})",
            )

        # مهلة خارج القائمة
        self._expect_error(
            lambda: InvitationService.create(ride.id, driver.id, customer, ttl_seconds=35),
            "5) يرفض مهلة خارج قائمة الأدمن", InvitationError,
        )

        ttl = area.effective_ttl_options[0]
        inv = InvitationService.create(ride.id, driver.id, customer, ttl_seconds=ttl)
        self._check(
            inv.status == InvitationStatus.PENDING and inv.ttl_seconds == ttl,
            f"6) الدعوة أُنشئت بمهلة {inv.ttl_seconds}ث وسعر {inv.quoted_fare}",
        )

        self._expect(driver_events, "invitation.created", "7) وصلت للسائق لحظيًا")
        self._expect(ride_events, "invitation.sent", "8) والزبون يعلم أنها أُرسلت")

        # دعوة موازية ثانية
        self._expect_error(
            lambda: InvitationService.create(ride.id, driver.id, customer, ttl_seconds=ttl),
            f"9) يرفض دعوة موازية (max_parallel={area.invitation_max_parallel})",
            InvitationError,
        )

        # القبول
        driver.refresh_from_db()
        accepted = InvitationService.accept(inv.id, driver)
        time.sleep(0.4)

        ride.refresh_from_db()
        self._check(
            accepted.status == InvitationStatus.ACCEPTED
            and ride.status == RideStatus.DRIVER_SELECTED,
            f"10) القبول قفل الرحلة (ride={ride.status})",
        )

        bridge = RideOffer.objects.filter(
            ride=ride, driver=driver, status=OfferStatus.ACCEPTED
        ).first()
        self._check(
            bridge is not None and bridge.gross_fare == Decimal("25.00"),
            f"11) جسر RideOffer أُنشئ بحالة ACCEPTED وسعر الدعوة "
            f"({bridge.gross_fare if bridge else '—'})",
        )

        self._expect(ride_events, "invitation.accepted", "12) الزبون أُخطر بالقبول")

        # الفحص الحاسم: هل يرى الزبون السيارة تتحرك؟
        driver_ws = websocket.create_connection(
            f"{ws_url}/ws/driver/{driver.id}/?token={driver_token.key}"
        )
        driver_ws.recv()
        driver_ws.send(json.dumps({
            "type": "location.update",
            "lng": JABLEH_LNG + 0.001, "lat": JABLEH_LAT, "heading": 90,
        }))
        self._expect(
            ride_events, "driver.location",
            "13) ★ موقع السائق يصل لغرفة الرحلة — الجسر يعمل فعلًا",
        )

        state = PresenceService.get_state(driver.id)
        self._check(
            state == PresenceState.BUSY,
            f"14) السائق أصبح BUSY فاختفى من الخريطة (state={state})",
        )

        # القبول المزدوج
        again = InvitationService.accept(inv.id, driver)
        self._check(
            again.id == inv.id and again.status == InvitationStatus.ACCEPTED,
            "15) قبول ثانٍ من نفس السائق: عملية واحدة لا خطأ ولا حجز مضاعف",
        )

        # دعوة لسائق مشغول
        ride2, ride2_events = new_ride()
        self._expect_error(
            lambda: InvitationService.create(ride2.id, driver.id, customer),
            "16) يرفض دعوة سائق مرتبط برحلة نشطة",
            InvitationError,
        )

        MatchingService.cancel_ride(ride_id=ride.id, customer=customer)
        time.sleep(0.4)
        self._check(
            PresenceService.get_state(driver.id) == PresenceState.PRESENT,
            "17) إلغاء الرحلة حرّر السائق",
        )

        # =============================================================
        # المرحلة ب — الرفض
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— ب: الرفض —"))

        driver_ws.send(json.dumps({
            "type": "location.update", "lng": JABLEH_LNG, "lat": JABLEH_LAT,
        }))
        time.sleep(0.4)
        driver.refresh_from_db()

        inv2 = InvitationService.create(ride2.id, driver.id, customer)
        self._expect(driver_events, "invitation.created", "18) دعوة ثانية وصلت")

        InvitationService.reject(inv2.id, driver, reason="بعيد عني")
        time.sleep(0.3)

        ride2.refresh_from_db()
        self._check(
            ride2.status in (RideStatus.SEARCHING, RideStatus.OFFERS_RECEIVED),
            f"19) الرفض أبقى الطلب في البحث (status={ride2.status}) — كما تنص الوثيقة",
        )
        self._expect(ride2_events, "invitation.rejected", "20) الزبون أُخطر بالرفض")

        self._expect_error(
            lambda: InvitationService.create(ride2.id, driver.id, customer),
            "21) تهدئة الرفض تمنع إعادة دعوة السائق نفسه فورًا",
            InvitationError,
        )

        # =============================================================
        # المرحلة ج — الانتهاء والإسقاط التلقائي
        # =============================================================
        self.stdout.write(self.style.HTTP_INFO("\n— ج: الانتهاء والإسقاط —"))

        from django.core.cache import cache
        cache.delete(InvitationService._cooldown_key(ride2.id, driver.id))

        inv3 = InvitationService.create(ride2.id, driver.id, customer)
        self._drain(driver_events, 1)

        RideInvitation.objects.filter(id=inv3.id).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        changed = InvitationService.expire(inv3.id)
        time.sleep(0.3)

        self._check(changed, "22) الانتهاء التلقائي غيّر الحالة")
        self._expect(ride2_events, "invitation.expired", "23) والزبون عرف فورًا")

        inv3.refresh_from_db()
        self._check(
            inv3.status == InvitationStatus.EXPIRED,
            f"24) الدعوة EXPIRED في القاعدة ({inv3.status})",
        )

        self._expect_error(
            lambda: InvitationService.accept(inv3.id, driver),
            "25) لا يمكن قبول دعوة منتهية",
            InvitationError,
        )

        # اختيار عرض يُسقط الدعوة المعلّقة
        cache.delete(InvitationService._cooldown_key(ride2.id, driver.id))
        driver_ws.send(json.dumps({
            "type": "location.update", "lng": JABLEH_LNG, "lat": JABLEH_LAT,
        }))
        time.sleep(0.4)
        driver.refresh_from_db()

        inv4 = InvitationService.create(ride2.id, driver.id, customer)
        self._drain(driver_events, 1)

        offer = MatchingService.create_offer(
            ride_id=ride2.id, driver=driver,
            gross_fare=Decimal("30.00"), eta_minutes=5,
        )
        MatchingService.select_offer(
            ride_id=ride2.id, offer_id=offer.id, customer=customer
        )
        time.sleep(0.4)

        inv4.refresh_from_db()
        self._check(
            inv4.status == InvitationStatus.CANCELLED,
            f"26) اختيار عرض أسقط الدعوة المعلّقة ({inv4.status})",
        )
        self._expect(
            driver_events, "invitation.cancelled",
            "27) والسائق عرف فورًا بدل انتظار المهلة",
        )

        # -------------------------------------------------------------
        RideRequest.objects.filter(id__in=[ride.id, ride2.id]).update(
            status=RideStatus.CANCELLED
        )
        self.stop.set()
        driver_ws.close()

        total = self.passed + self.failed
        self.stdout.write("")
        if self.failed == 0:
            self.stdout.write(self.style.SUCCESS(
                f"Direct invitation E2E: {total}/{total} passed."
            ))
        else:
            self.stderr.write(self.style.ERROR(
                f"Direct invitation E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
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
        """يتجاهل الأحداث غير المطلوبة (driver.location يتدفق باستمرار)."""
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
