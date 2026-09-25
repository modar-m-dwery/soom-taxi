"""
اختبار حمل مباشر على Redis presence، بدون الحاجة لسائقين حقيقيين في DB.
يحاكي N سائق منتشرين عشوائيًا حول نقطة مركزية (جبلة افتراضيًا)، يقيس:
    - زمن كتابة N سائق (go_online + update_location)
    - زمن GEOSEARCH + بناء snapshot الكامل (get_available_nearby_with_snapshots)
    - زمن sweep_stale_drivers

الاستخدام:
    python manage.py presence_load_test --count 1000
    python manage.py presence_load_test --count 500 --radius 5
"""
import random
import time

from django.core.management.base import BaseCommand

from presence.redis_client import get_redis
from presence.services import PresenceService
from presence.constants import GEO_KEY, LAST_SEEN_KEY, PRESENCE_KEY_PREFIX


class FakeDriver:
    """كائن بسيط يحاكي DriverProfile بالحقول التي تحتاجها go_online فقط."""

    def __init__(self, driver_id, lng, lat):
        from django.utils import timezone
        self.last_location_at = timezone.now()
        self.id = driver_id
        self.current_occupancy = 0
        self.available_seats = 4
        self.status = "active"

        class _Point:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        self.current_location = _Point(lng, lat)


class Command(BaseCommand):
    help = "Load test presence engine with N synthetic drivers."

    # نطاق تقريبي حول جبلة (يمكن تغييره)
    CENTER_LNG = 35.9
    CENTER_LAT = 35.36
    SPREAD_DEG = 0.15  # ~15 كم تقريبًا

    ID_OFFSET = 900_000_000  # لتفادي أي تعارض مع IDs حقيقية

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=500)
        parser.add_argument("--radius", type=float, default=5.0)
        parser.add_argument("--cleanup", action="store_true", help="Remove synthetic drivers after the test.")

    def handle(self, *args, **options):
        count = options["count"]
        radius_km = options["radius"]

        driver_ids = [self.ID_OFFSET + i for i in range(count)]

        self.stdout.write(f"== Load test: {count} synthetic drivers ==")

        # -----------------------------------------------------------
        # 1) الكتابة: go_online لكل سائق
        # -----------------------------------------------------------
        t0 = time.perf_counter()

        for driver_id in driver_ids:
            lng = self.CENTER_LNG + random.uniform(-self.SPREAD_DEG, self.SPREAD_DEG)
            lat = self.CENTER_LAT + random.uniform(-self.SPREAD_DEG, self.SPREAD_DEG)
            PresenceService.go_online(FakeDriver(driver_id, lng, lat))

        write_seconds = time.perf_counter() - t0
        self.stdout.write(
            self.style.SUCCESS(
                f"[WRITE] {count} drivers online in {write_seconds:.3f}s "
                f"({(count / write_seconds):.1f} writes/sec)"
            )
        )

        # -----------------------------------------------------------
        # 2) القراءة: nearby + snapshots دفعة واحدة (المسار الموصى به)
        # -----------------------------------------------------------
        t0 = time.perf_counter()
        nearby = PresenceService.get_available_nearby_with_snapshots(
            self.CENTER_LNG, self.CENTER_LAT, radius_km=radius_km, limit=count
        )
        read_seconds = time.perf_counter() - t0

        self.stdout.write(
            self.style.SUCCESS(
                f"[READ]  found {len(nearby)} available drivers within {radius_km}km "
                f"in {read_seconds * 1000:.1f}ms"
            )
        )

        # -----------------------------------------------------------
        # 3) القراءة (الطريقة القديمة N+1) للمقارنة، على عيّنة أصغر فقط
        #    (لتفادي إبطاء الاختبار بشكل غير ضروري مع أعداد كبيرة)
        # -----------------------------------------------------------
        sample_size = min(count, 100)
        t0 = time.perf_counter()
        PresenceService.get_available_nearby_driver_ids(
            self.CENTER_LNG, self.CENTER_LAT, radius_km=radius_km, limit=sample_size
        )
        naive_seconds = time.perf_counter() - t0

        self.stdout.write(
            f"[READ, naive N+1, sample={sample_size}] {naive_seconds * 1000:.1f}ms "
            f"(للمقارنة فقط - هذا ما كنا سنحصل عليه بدون bulk snapshots)"
        )

        # -----------------------------------------------------------
        # 4) Sweep
        # -----------------------------------------------------------
        t0 = time.perf_counter()
        stale = PresenceService.sweep_stale_drivers()
        sweep_seconds = time.perf_counter() - t0

        self.stdout.write(
            f"[SWEEP] {sweep_seconds * 1000:.1f}ms, removed {len(stale)} stale drivers "
            f"(متوقع 0 لأن كل السائقين طازجين للتو)"
        )

        # -----------------------------------------------------------
        # تنظيف
        # -----------------------------------------------------------
        if options["cleanup"]:
            self._cleanup(driver_ids)
            self.stdout.write(self.style.WARNING("Synthetic drivers cleaned up."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "لم يتم التنظيف. أعد التشغيل بـ --cleanup لإزالة بيانات الاختبار، "
                    "أو استخدم presence_load_test --count 0 --cleanup لاحقًا لتنظيف يدوي."
                )
            )

    def _cleanup(self, driver_ids):
        r = get_redis()
        pipe = r.pipeline()
        for driver_id in driver_ids:
            pipe.delete(f"{PRESENCE_KEY_PREFIX}{driver_id}")
            pipe.zrem(GEO_KEY, str(driver_id))
            pipe.zrem(LAST_SEEN_KEY, str(driver_id))
        pipe.execute()