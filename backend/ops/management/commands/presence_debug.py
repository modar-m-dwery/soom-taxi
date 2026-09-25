"""
لقطة كاملة لحالة سائق واحد، من كل مصدر يدّعي معرفتها.

بُنيت لأننا اصطدمنا أربع مرات بالسؤال نفسه: "لماذا يقول النظام إن هذا
السائق مشغول؟" — وفي كل مرة كان الجواب في حقل واحد لم نكن نراه.

    python manage.py presence_debug --driver-id 5

تطبع الحقائق الأربع جنبًا إلى جنب: القاعدة، والرحلات النشطة، والعروض
المقبولة، وحزمة Redis الخام. حين تتناقض، السطر المتناقض هو الجواب.
"""
import json
import time

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "لقطة تشخيصية كاملة لحالة سائق"

    def add_arguments(self, parser):
        parser.add_argument("--driver-id", type=int, required=True)
        parser.add_argument(
            "--watch",
            type=int,
            default=0,
            help="أعد الطباعة كل N ثانية (0 = مرة واحدة). يكشف مَن يكتب متأخرًا.",
        )

    def handle(self, *args, **options):
        driver_id = options["driver_id"]

        if options["watch"] <= 0:
            self._dump(driver_id)
            return

        self.stdout.write(self.style.WARNING(
            f"مراقبة كل {options['watch']}ث — Ctrl+C للإيقاف.\n"
        ))

        previous = None

        while True:
            snapshot = self._collect(driver_id)

            if snapshot != previous:
                self.stdout.write(self.style.HTTP_INFO(
                    f"\n=== {timezone.now().strftime('%H:%M:%S')} — تغيّر ==="
                ))
                self._render(snapshot)
                previous = snapshot

            time.sleep(options["watch"])

    # -----------------------------------------------------------------

    def _dump(self, driver_id):
        self._render(self._collect(driver_id))

    def _collect(self, driver_id):
        from matching.models import OfferStatus, RideOffer
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService
        from rides.models import RideStatus
        from trips.models import Trip, TripStatus
        from users.models import DriverProfile

        active_ride_statuses = [
            RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
        ]
        active_trip_statuses = [
            TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
            TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
        ]

        driver = DriverProfile.objects.filter(id=driver_id).select_related("user").first()

        if driver is None:
            return {"error": f"لا سائق بالمعرّف {driver_id}"}

        snapshot = PresenceService.get_snapshot(driver_id)
        state = PresenceService._resolve_state_from_snapshot(snapshot)
        cell = PresenceService.get_current_cell(driver_id)

        return {
            "db": {
                "phone": driver.user.phone,
                "status": driver.status,
                "online": driver.online,
                "occupancy": driver.current_occupancy,
                "available_seats": driver.available_seats,
                "last_location_at": (
                    driver.last_location_at.isoformat()
                    if driver.last_location_at else None
                ),
                "location": (
                    [round(driver.current_location.x, 5),
                     round(driver.current_location.y, 5)]
                    if driver.current_location else None
                ),
            },
            "active_trips": [
                {"trip": t.id, "ride": t.ride_id, "status": t.status,
                 "mode": getattr(t.ride, "mode", None),
                 "passengers": getattr(t.ride, "passenger_count", None),
                 "updated": t.updated_at.strftime("%H:%M:%S")}
                for t in Trip.objects
                .filter(driver_id=driver_id, status__in=active_trip_statuses)
                .select_related("ride")
            ],
            "accepted_offers_on_active_rides": list(
                RideOffer.objects
                .filter(
                    driver_id=driver_id,
                    status=OfferStatus.ACCEPTED,
                    ride__status__in=active_ride_statuses,
                )
                .values_list("ride_id", "ride__status")
            ),
            "redis": dict(snapshot),
            "resolved_state": state,
            "marketplace_cell": cell,
            "cell_members": (
                MarketplaceService.get_cell_member_ids(cell) if cell else []
            ),
        }

    # -----------------------------------------------------------------

    def _render(self, data):
        if "error" in data:
            self.stderr.write(self.style.ERROR(data["error"]))
            return

        w = self.stdout.write

        w(self.style.HTTP_INFO("\n— PostgreSQL —"))
        for key, value in data["db"].items():
            w(f"  {key:.<22} {value}")

        w(self.style.HTTP_INFO("\n— الرحلات النشطة —"))
        if data["active_trips"]:
            for trip in data["active_trips"]:
                w(f"  {trip}")
        else:
            w("  (لا شيء)")

        w(self.style.HTTP_INFO("\n— العروض المقبولة على طلبات نشطة —"))
        w(f"  {data['accepted_offers_on_active_rides'] or '(لا شيء)'}")

        w(self.style.HTTP_INFO("\n— Redis (حزمة الحضور الخام) —"))
        redis_data = data["redis"]

        if not redis_data:
            w("  (المفتاح غير موجود)")
        else:
            now = time.time()
            for key in sorted(redis_data):
                value = redis_data[key]
                suffix = ""

                # الأختام الزمنية بلا أعمار لا تُقرأ. هذه هي الحقول التي
                # تحسم دائمًا: هل النبضة قديمة؟ هل الموقع قديم؟
                if key in ("last_heartbeat", "last_location_at"):
                    try:
                        suffix = f"   ← عمره {int(now - float(value))}ث"
                    except (TypeError, ValueError):
                        pass

                marker = "  ★" if key in (
                    "busy", "sharing", "free_seats", "online"
                ) else "   "

                w(f"{marker} {key:.<22} {value}{suffix}")

        w(self.style.HTTP_INFO("\n— الخلاصة —"))
        w(f"  الحالة المستنتجة....... {data['resolved_state']}")
        w(f"  خليّة الخريطة.......... {data['marketplace_cell']}")
        w(f"  أعضاء الخليّة.......... {data['cell_members']}")

        # التناقض الذي يفسّر أغلب الأعطال التي مرّت بنا
        busy_in_redis = data["redis"].get("busy") == "1"
        has_active_trip = bool(data["active_trips"])

        if busy_in_redis and not has_active_trip:
            w(self.style.ERROR(
                "\n  ⚠ متناقض: Redis يقول مشغول ولا رحلة نشطة في القاعدة.\n"
                "     هذا هو 'السائق الشبح'. الإصلاح:\n"
                "     ops/drivers/{id}/release/  أو  EngagementResolver.sync(id)"
            ))

        if has_active_trip and not (busy_in_redis or data["redis"].get("sharing") == "1"):
            w(self.style.ERROR(
                "\n  ⚠ متناقض: رحلة نشطة في القاعدة وRedis يقول متاح.\n"
                "     السائق قابل للحجز مرتين. الإصلاح نفسه."
            ))

        w("")