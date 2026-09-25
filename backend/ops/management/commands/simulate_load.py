"""
محاكاة حمل حيّة — حركة HTTP وWebSocket حقيقية بالتوازي.

ما تفعله بالضبط
---------------
تشغّل عمّالًا متزامنين، كلٌّ منهم يمثّل زبونًا أو سائقًا حقيقيًّا يضرب
الـAPI عبر الشبكة كما يفعل التطبيق. لا استدعاءات داخلية للخدمات — تلك
تختبر المنطق ولا تختبر شيئًا ممّا ينهار فعلًا تحت الحمل: تجمّع الاتصالات،
أقفال الصفوف، مهل المزوّد الخارجي، والسباقات على آخر مقعد.

السيناريوهات
------------
    auction     مزاد كامل: طلب → مرشّحون → عروض من عدّة سائقين → اختيار
                → وصل → بدأ → أنهى → تقييم
    instant     خريطة حيّة → دعوة سائق محدّد → قبول/رفض
    contention  **الأهمّ**: سائقان يتنافسان على العرض نفسه، وزبونان على
                آخر مقعد. هنا وحدها تُختبر `select_for_update`.
    scheduled   رحلة مجدولة مشتركة → انضمام
    published   سائق ينشر سفرية → زبائن يحجزون مقاعد
    browse      حركة قراءة فقط: خريطة، رحلاتي، إشعارات، تقييمي

القياس
------
لكلّ نقطة نهاية: عدد، نجاح، وسيط، p95، p99، وأسوأ زمن. الوسيط وحده
يكذب تحت الحمل — الذيل هو ما يشعر به المستخدم.

وتُفحص **صحّة النتائج** لا سرعتها فقط: قبولان لعرض واحد، حجزان لمقعد
واحد، رحلة بسائقين. سرعةٌ بلا صحّة ليست نجاحًا بل عطلًا أسرع.
"""
from __future__ import annotations

import json
import random
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


# ---------------------------------------------------------------
# القياس
# ---------------------------------------------------------------


class Stats:
    """عدّادات آمنة بين الخيوط."""

    def __init__(self):
        self._lock = threading.Lock()
        self.samples = defaultdict(list)
        self.status = defaultdict(lambda: defaultdict(int))
        self.errors = defaultdict(int)
        self.anomalies = []
        self.scenarios = defaultdict(lambda: {"ok": 0, "fail": 0})

    def record(self, label, ms, code):
        with self._lock:
            self.samples[label].append(ms)
            self.status[label][code] += 1

    def error(self, label, detail=""):
        with self._lock:
            self.errors[f"{label}: {detail}"[:160]] += 1

    def anomaly(self, text):
        with self._lock:
            self.anomalies.append(text)

    def scenario(self, name, ok):
        with self._lock:
            self.scenarios[name]["ok" if ok else "fail"] += 1

    def table(self):
        rows = []
        with self._lock:
            for label, values in sorted(self.samples.items()):
                if not values:
                    continue
                ordered = sorted(values)
                codes = self.status[label]
                good = sum(n for c, n in codes.items() if 200 <= c < 400)
                rows.append(
                    {
                        "endpoint": label,
                        "count": len(ordered),
                        "success_pct": round(100 * good / len(ordered), 1),
                        "p50": round(statistics.median(ordered), 1),
                        "p95": round(ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)], 1),
                        "p99": round(ordered[min(int(len(ordered) * 0.99), len(ordered) - 1)], 1),
                        "max": round(ordered[-1], 1),
                        "codes": dict(sorted(codes.items())),
                    }
                )
        return rows


# ---------------------------------------------------------------
# عميل HTTP
# ---------------------------------------------------------------


class Client:
    def __init__(self, base_url, stats, timeout=30):
        self.base = base_url.rstrip("/")
        self.stats = stats
        self.timeout = timeout

    def call(self, method, path, label, token=None, data=None, expect=None):
        url = f"{self.base}{path}"
        body = json.dumps(data).encode() if data is not None else None

        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Token {token}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)

        started = time.perf_counter()
        code = 0
        payload = None

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                code = response.status
                raw = response.read()
                payload = json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            code = exc.code
            try:
                payload = json.loads(exc.read() or b"null")
            except Exception:  # noqa: BLE001
                payload = None
        except Exception as exc:  # noqa: BLE001
            self.stats.error(label, f"{type(exc).__name__}")
            code = 0

        elapsed_ms = (time.perf_counter() - started) * 1000
        self.stats.record(label, elapsed_ms, code)

        if expect and code not in expect:
            detail = ""
            if isinstance(payload, dict):
                detail = str(payload.get("detail", ""))[:80]
            self.stats.error(label, f"HTTP {code} {detail}")

        return code, payload


# ---------------------------------------------------------------
# الأمر
# ---------------------------------------------------------------


JABLEH = (35.9010, 35.3620)


#: نقاط بدء النوبة — مراكز ثقل جبلة نفسها المستعملة في seed_scale
SHIFT_START_POINTS = [
    (35.9010, 35.3620),
    (35.8935, 35.3585),
    (35.9105, 35.3668),
    (35.9060, 35.3520),
    (35.8990, 35.3710),
]

rng_global = random.Random(20260907)


class DriverLease:
    """
    حجزٌ حصريّ لسائق أثناء سيناريو دورة حياة كاملة.

    لماذا: الخادم يمنع — بحقّ — أن يكون سائق في رحلتين معًا. فلو اختارت
    المحاكاة سائقيها عشوائيًّا لوجد معظمُها سائقًا مشغولًا، وظهرت النتيجة
    كأنّ المطابقة تفشل بينما هي تعمل تمامًا كما يجب. الحجز هنا يجعل
    الرقم المُبلَّغ يقيس المنطق لا التصادم على مورد مشترك.

    وسيناريو `contention` وحده يتجاوز الحجز عمدًا — التصادم هو موضوعه.
    """

    def __init__(self, drivers):
        self._free = list(drivers)
        self._lock = threading.Lock()

    def acquire(self, count=1):
        with self._lock:
            if len(self._free) < count:
                return []
            return [self._free.pop() for _ in range(count)]

    def release(self, drivers):
        with self._lock:
            self._free.extend(drivers)

    def available(self):
        with self._lock:
            return len(self._free)


class Command(BaseCommand):
    help = "محاكاة حمل حيّة عبر HTTP وWebSocket بالتوازي."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--concurrency", type=int, default=60)
        parser.add_argument("--rides", type=int, default=300,
                            help="عدد دورات المزاد الكاملة")
        parser.add_argument("--instant", type=int, default=60)
        parser.add_argument("--contention", type=int, default=40,
                            help="سباقات متعمّدة على العرض والمقعد")
        parser.add_argument("--published", type=int, default=20)
        parser.add_argument("--browse", type=int, default=200)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--skip-ws", action="store_true")
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                "امسح البيانات التشغيلية قبل البدء. مهمّ للتكرار: سيناريو "
                "انقطع في منتصفه يترك سائقه محجوزًا برحلة نشطة لا تنتهي، "
                "فتُحسب التشغيلة التالية على أسطول نصفه مشغول ويبدو الأمر "
                "كأنّ المطابقة تفشل."
            ),
        )

    # -----------------------------------------------------------

    def handle(self, *args, **options):
        from rest_framework.authtoken.models import Token

        from users.models import DriverProfile, User

        rng = random.Random(options["seed"])
        stats = Stats()
        client = Client(options["base_url"], stats)

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 66))
        self.stdout.write(self.style.HTTP_INFO("محاكاة حمل حيّة"))
        self.stdout.write(self.style.HTTP_INFO("=" * 66))

        if options["reset"]:
            from django.core.management import call_command

            self.stdout.write("  مسح البيانات التشغيلية ...")
            call_command("reset_operational_data", yes=True, verbosity=0)

        # ---- تجهيز الهويّات ----
        drivers = self._load_drivers()
        customers = self._load_customers(options)

        if len(drivers) < 10:
            raise CommandError(
                "أقلّ من عشرة سائقين مؤهّلين ومتّصلين. "
                "شغّل: python manage.py seed_scale --fresh"
            )
        if len(customers) < 20:
            raise CommandError("زبائن غير كافين. شغّل seed_scale أوّلًا.")

        self.stdout.write(
            f"  سائقون جاهزون: {len(drivers)}   زبائن: {len(customers)}   "
            f"تزامن: {options['concurrency']}"
        )

        jobs = self._build_jobs(rng, options, drivers, customers, client, stats)
        rng.shuffle(jobs)

        self.stdout.write(f"  مهامّ: {len(jobs)}\n")
        self.stdout.write("  التشغيل ...")

        stop_heartbeats = threading.Event()
        self._start_heartbeats(getattr(self, "_online_driver_ids", []), stop_heartbeats)

        started = time.perf_counter()

        with ThreadPoolExecutor(max_workers=options["concurrency"]) as pool:
            futures = [pool.submit(job) for job in jobs]
            done = 0
            for future in as_completed(futures):
                done += 1
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    stats.error("worker", f"{type(exc).__name__}: {exc}")
                if done % max(len(jobs) // 10, 1) == 0:
                    self.stdout.write(f"    {done}/{len(jobs)}")

        elapsed = time.perf_counter() - started
        stop_heartbeats.set()

        self._verify_integrity(stats)
        self._report(stats, elapsed, len(jobs))

    # -----------------------------------------------------------
    # الهويّات
    # -----------------------------------------------------------

    def _load_drivers(self):
        """
        السائقون المؤهّلون، مُعادون إلى الاتّصال قبل البدء.

        لماذا نُعيد إعلانهم متّصلين: `sweep_stale_driver_presence` يعمل كلّ
        خمس عشرة ثانية ويُخرج من لا نبضة له منذ ستّين ثانية. وهذا سلوك
        صحيح تمامًا — تطبيق السائق الحقيقي ينبض باستمرار. فالمحاكاة تفعل
        ما يفعله التطبيق: تُعلن الاتّصال، ثمّ تنبض في الخلفية طوال التشغيل
        (راجع `_start_heartbeats`). البديل — تعطيل الكانس — كان سيخفي
        العطل الذي بُني الكانس لأجله.
        """
        from rest_framework.authtoken.models import Token

        from drivers.services.eligibility import DriverEligibilityService
        from presence.services import PresenceService
        from users.models import DriverProfile

        profiles = list(
            DriverProfile.objects
            .filter(user__phone__startswith="+96395")
            .exclude(status=DriverProfile.DriverStatus.SUSPENDED)
            .select_related("user")
            .prefetch_related("vehicles")[:400]
        )

        out = []
        online_ids = []

        for profile in profiles:
            if not DriverEligibilityService.is_eligible(profile):
                continue

            if profile.current_location is None:
                # سائق يبدأ نوبته: تطبيقه يرسل أوّل تثبيت GPS. التنظيف
                # التشغيلي يمسح المواقع عمدًا (موقعُ الأمس ليس موقعًا)،
                # فالمحاكاة تفعل ما يفعله التطبيق بدل أن تتوقّع أن تجد
                # موقعًا محفوظًا.
                profile.current_location = self._shift_start_point(rng_global)
                profile.save(update_fields=["current_location"])

            try:
                PresenceService.go_online(profile, engagement={})
                PresenceService.update_location(
                    profile.id,
                    profile.current_location.x,
                    profile.current_location.y,
                )
                PresenceService.heartbeat(profile.id)
                online_ids.append(profile.id)
            except Exception:  # noqa: BLE001
                continue

            token, _ = Token.objects.get_or_create(user=profile.user)
            vehicle = next(
                (v for v in profile.vehicles.all() if v.active), None
            )

            out.append(
                {
                    "profile_id": profile.id,
                    "user_id": profile.user_id,
                    "token": token.key,
                    "vehicle_id": getattr(vehicle, "id", None),
                    "lng": profile.current_location.x if profile.current_location else JABLEH[0],
                    "lat": profile.current_location.y if profile.current_location else JABLEH[1],
                }
            )

        DriverProfile.objects.filter(id__in=online_ids).update(
            online=True, last_location_at=timezone.now()
        )
        self._online_driver_ids = online_ids

        return out

    @staticmethod
    def _shift_start_point(rng):
        from django.contrib.gis.geos import Point

        lng, lat = rng.choice(SHIFT_START_POINTS)
        return Point(
            lng + rng.gauss(0, 0.006), lat + rng.gauss(0, 0.006), srid=4326
        )

    def _start_heartbeats(self, driver_ids, stop_event):
        """
        نبضة كلّ عشر ثوانٍ لكلّ سائق، في خيط خلفي — تمامًا كتطبيق السائق.

        بدونها يُخرج الكانس السائقين في منتصف التشغيل فتنهار المطابقة
        لسبب لا علاقة له بما نقيسه.
        """
        from presence.services import PresenceService

        from users.models import DriverProfile

        def loop():
            while not stop_event.wait(10):
                # نبضة Redis للحضور...
                for driver_id in driver_ids:
                    try:
                        PresenceService.heartbeat(driver_id)
                    except Exception:  # noqa: BLE001
                        pass

                # ...وطابع القاعدة لطزاجة الموقع.
                #
                # مصدران مختلفان لسؤالين مختلفين: Redis يجيب «هل هو
                # متّصل؟» و`last_location_at` في القاعدة تجيب «هل موقعه
                # حديث؟» — وهي ما يفحصه `is_driver_location_fresh` قبل
                # قبول أيّ عرض. تطبيق السائق الحقيقي يحدّث الاثنين معًا
                # عبر `location.update` على الـWebSocket، والمحاكاة تفعل
                # الشيء نفسه. تحديث أحدهما فقط يجعل السائق «متّصلًا
                # ولا يُطابَق» — وهو عطلٌ مربك يبدو كأنّ المطابقة معطّلة.
                try:
                    DriverProfile.objects.filter(id__in=driver_ids).update(
                        last_location_at=timezone.now()
                    )
                except Exception:  # noqa: BLE001
                    pass

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        return thread

    def _load_customers(self, options):
        from rest_framework.authtoken.models import Token

        from users.models import User

        needed = (
            options["rides"]
            + options["instant"]
            + options["contention"] * 2
            + options["published"] * 3
            + options["browse"]
        )

        users = list(
            User.objects.filter(phone__startswith="+96396").order_by("id")[: needed + 50]
        )

        existing = {
            t.user_id: t.key
            for t in Token.objects.filter(user__in=users)
        }

        missing = [u for u in users if u.id not in existing]
        Token.objects.bulk_create(
            [Token(user=u, key=Token.generate_key()) for u in missing],
            batch_size=500,
            ignore_conflicts=True,
        )

        tokens = {
            t.user_id: t.key for t in Token.objects.filter(user__in=users)
        }

        return [
            {"user_id": u.id, "token": tokens[u.id]}
            for u in users
            if u.id in tokens
        ]

    # -----------------------------------------------------------
    # بناء المهامّ
    # -----------------------------------------------------------

    def _build_jobs(self, rng, options, drivers, customers, client, stats):
        jobs = []
        pool = list(customers)
        rng.shuffle(pool)
        cursor = 0

        def take(n=1):
            nonlocal cursor
            picked = pool[cursor:cursor + n]
            cursor += n
            if len(picked) < n:      # التفاف عند النفاد
                cursor = n
                picked = pool[:n]
            return picked

        lease = DriverLease(drivers)

        for _ in range(options["rides"]):
            customer = take()[0]
            jobs.append(
                lambda c=customer: self._auction_leased(client, stats, rng, c, lease)
            )

        for _ in range(options["instant"]):
            customer = take()[0]
            jobs.append(
                lambda c=customer: self._instant_leased(client, stats, rng, c, lease)
            )

        for _ in range(options["contention"]):
            customer = take()[0]
            jobs.append(
                lambda c=customer: self._contention_leased(client, stats, rng, c, lease)
            )

        for _ in range(options["published"]):
            driver = rng.choice(drivers)
            seats = take(3)
            jobs.append(
                lambda d=driver, s=seats: self._published(client, stats, rng, d, s)
            )

        for _ in range(options["browse"]):
            customer = take()[0]
            jobs.append(lambda c=customer: self._browse(client, stats, rng, c, drivers))

        return jobs

    # -----------------------------------------------------------
    # السيناريوهات
    # -----------------------------------------------------------

    @staticmethod
    def _near(rng, lng, lat, spread=0.012):
        return round(lng + rng.gauss(0, spread), 6), round(lat + rng.gauss(0, spread), 6)

    def _create_ride(self, client, rng, customer, mode="fast"):
        plng, plat = self._near(rng, *JABLEH)
        dlng, dlat = self._near(rng, *JABLEH, spread=0.02)

        return client.call(
            "POST", "/api/v1/rides/", "POST /rides/",
            token=customer["token"],
            data={
                "pickup_lat": plat, "pickup_lng": plng,
                "destination_lat": dlat, "destination_lng": dlng,
                "mode": mode,
                "passenger_count": rng.choice([1, 1, 1, 2, 2, 3]),
                "trip_category": "city",
            },
            expect={201, 200, 400},
        )

    def _auction_leased(self, client, stats, rng, customer, lease):
        """يحجز ثلاثة سائقين، يشغّل المزاد، ثمّ يعيدهم إلى البركة."""
        bidders = lease.acquire(3)

        if not bidders:
            stats.scenario("auction (no free driver)", False)
            return

        try:
            self._auction(client, stats, rng, customer, bidders)
        finally:
            lease.release(bidders)

    def _instant_leased(self, client, stats, rng, customer, lease):
        drivers = lease.acquire(1)

        if not drivers:
            stats.scenario("instant (no free driver)", False)
            return

        try:
            self._instant(client, stats, rng, customer, drivers)
        finally:
            lease.release(drivers)

    def _auction(self, client, stats, rng, customer, bidders):
        """المزاد الكامل من الطلب إلى التقييم."""
        code, ride = self._create_ride(client, rng, customer)

        if code not in (200, 201) or not isinstance(ride, dict):
            stats.scenario("auction", False)
            return

        ride_id = ride.get("id")
        if not ride_id:
            stats.scenario("auction", False)
            return

        # عدّة سائقين يزايدون — هذا هو المزاد
        offers = []
        for driver in bidders:
            code, offer = client.call(
                "POST", f"/api/v1/driver/rides/{ride_id}/offers/",
                "POST /driver/rides/{id}/offers/",
                token=driver["token"],
                data={
                    "gross_fare": f"{rng.randint(3000, 12000)}.00",
                    "eta_minutes": rng.randint(2, 15),
                },
                expect={201, 200, 400, 403, 409},
            )
            if code in (200, 201) and isinstance(offer, dict) and offer.get("id"):
                offers.append((offer["id"], driver))

        if not offers:
            stats.scenario("auction", False)
            return

        client.call(
            "GET", f"/api/v1/customer/rides/{ride_id}/offers/",
            "GET /customer/rides/{id}/offers/",
            token=customer["token"], expect={200},
        )

        offer_id, winner = rng.choice(offers)

        code, _ = client.call(
            "POST",
            f"/api/v1/customer/rides/{ride_id}/offers/{offer_id}/select/",
            "POST /offers/{id}/select/",
            token=customer["token"], expect={200, 201, 400, 409},
        )

        if code not in (200, 201):
            stats.scenario("auction", False)
            return

        # دورة الحياة — السائق يتحرّك إلى نقطة الالتقاط أوّلًا
        self._drive_to_pickup(client, winner, ride_id, ride)

        for path, label in (
            (f"/api/v1/driver/rides/{ride_id}/arrived/", "POST /driver/.../arrived/"),
            (f"/api/v1/driver/rides/{ride_id}/start/", "POST /driver/.../start/"),
            (f"/api/v1/driver/rides/{ride_id}/complete/", "POST /driver/.../complete/"),
        ):
            code, _ = client.call(
                "POST", path, label, token=winner["token"],
                expect={200, 201, 400},
            )
            if code not in (200, 201):
                stats.scenario("auction", False)
                return

        client.call(
            "POST", f"/api/v1/trips/{ride_id}/rate/", "POST /trips/{id}/rate/",
            token=customer["token"],
            data={"score": rng.choice([3, 4, 5, 5, 5]), "comment": "محاكاة"},
            expect={200, 201, 400},
        )

        stats.scenario("auction", True)

    def _drive_to_pickup(self, client, driver, ride_id, ride):
        """
        السائق ينتقل إلى نقطة الالتقاط قبل تسجيل الوصول.

        بدون هذا يفشل `arrived` بـ400 لأنّ السائق خارج نصف قطر التحقّق —
        وهو سلوك صحيح للنظام لكنّه يجعل المحاكاة تقيس رفضًا لا رحلة.
        نستعمل نقطة الالتقاط من الاستجابة نفسها لا تخمينًا.
        """
        from django.contrib.gis.geos import Point

        from presence.services import PresenceService
        from users.models import DriverProfile

        lat = ride.get("pickup_lat")
        lng = ride.get("pickup_lng")

        if lat is None or lng is None:
            return

        try:
            DriverProfile.objects.filter(id=driver["profile_id"]).update(
                current_location=Point(float(lng), float(lat), srid=4326),
                last_location_at=timezone.now(),
            )
            PresenceService.update_location(
                driver["profile_id"], float(lng), float(lat)
            )
        except Exception:  # noqa: BLE001
            pass

    def _instant(self, client, stats, rng, customer, drivers):
        """خريطة حيّة → دعوة سائق محدّد."""
        code, ride = self._create_ride(client, rng, customer, mode="express")

        if code not in (200, 201) or not isinstance(ride, dict) or not ride.get("id"):
            stats.scenario("instant", False)
            return

        ride_id = ride["id"]

        code, nearby = client.call(
            "GET", f"/api/v1/customer/rides/{ride_id}/nearby-vehicles/",
            "GET /rides/{id}/nearby-vehicles/",
            token=customer["token"], expect={200, 400},
        )

        vehicles = []
        if isinstance(nearby, dict):
            vehicles = nearby.get("vehicles") or nearby.get("results") or []
        elif isinstance(nearby, list):
            vehicles = nearby

        if not vehicles:
            stats.scenario("instant", False)
            return

        # ندعو السائق المحجوز لنا إن ظهر على الخريطة، وإلّا فأيّ ظاهر.
        leased_ids = {d["profile_id"] for d in drivers}
        mine = [v for v in vehicles if v.get("driver_id") in leased_ids]

        target = mine[0] if mine else rng.choice(vehicles)
        driver_id = target.get("driver_id")

        code, invitation = client.call(
            "POST", f"/api/v1/customer/rides/{ride_id}/invitations/",
            "POST /rides/{id}/invitations/",
            token=customer["token"],
            data={"driver_id": driver_id},
            expect={200, 201, 400, 409},
        )

        if code not in (200, 201) or not isinstance(invitation, dict):
            stats.scenario("instant", False)
            return

        invitation_id = invitation.get("id")
        driver = next((d for d in drivers if d["profile_id"] == driver_id), None)

        if not invitation_id or driver is None:
            stats.scenario("instant", False)
            return

        # ثلثهم يرفضون — الرفض مسار حقيقي لا حالة شاذّة
        if rng.random() < 0.33:
            client.call(
                "POST", f"/api/v1/driver/invitations/{invitation_id}/reject/",
                "POST /driver/invitations/{id}/reject/",
                token=driver["token"], data={"reason": "بعيد"},
                expect={200, 400, 409},
            )
        else:
            client.call(
                "POST", f"/api/v1/driver/invitations/{invitation_id}/accept/",
                "POST /driver/invitations/{id}/accept/",
                token=driver["token"], expect={200, 201, 400, 409},
            )

        stats.scenario("instant", True)

    def _contention_leased(self, client, stats, rng, customer, lease):
        """
        يحجز المتنافسين أيضًا.

        بدون الحجز كانت سيناريوهات التنافس تحرّك سائقين تستعملهم
        سيناريوهات المزاد في اللحظة نفسها، فيفشل تسجيل وصولها لأنّ سائقها
        نُقل إلى نقطة التقاط أخرى — عطلٌ في المحاكاة يبدو عطلًا في الخادم.
        """
        rivals = lease.acquire(4)

        if not rivals:
            stats.scenario("contention (no free driver)", False)
            return

        try:
            self._contention(client, stats, rng, customer, rivals)
        finally:
            lease.release(rivals)

    def _contention(self, client, stats, rng, customer, rivals):
        """
        سباقٌ متعمّد: أربعة سائقين يقدّمون عرضًا، ثمّ يُختار عرضٌ واحد
        **من خيوط متوازية في اللحظة نفسها**.

        الشرط الذي نتحقّق منه: سائق واحد فقط يفوز. قبولان لعرضين على طلب
        واحد يعني أنّ القفل لا يعمل، وهو أخطر عطل يمكن أن يوجد هنا.
        """
        code, ride = self._create_ride(client, rng, customer)

        if code not in (200, 201) or not isinstance(ride, dict) or not ride.get("id"):
            stats.scenario("contention", False)
            return

        ride_id = ride["id"]
        offers = []

        for driver in rivals:
            code, offer = client.call(
                "POST", f"/api/v1/driver/rides/{ride_id}/offers/",
                "POST /driver/rides/{id}/offers/",
                token=driver["token"],
                data={"gross_fare": f"{rng.randint(4000, 9000)}.00",
                      "eta_minutes": rng.randint(2, 10)},
                expect={201, 200, 400, 403, 409},
            )
            if code in (200, 201) and isinstance(offer, dict) and offer.get("id"):
                offers.append(offer["id"])

        if len(offers) < 2:
            stats.scenario("contention", False)
            return

        # الاختيار المتزامن — هنا يقع السباق
        results = []
        lock = threading.Lock()

        def select(offer_id):
            code, _ = client.call(
                "POST",
                f"/api/v1/customer/rides/{ride_id}/offers/{offer_id}/select/",
                "POST /offers/{id}/select/ [race]",
                token=customer["token"], expect={200, 201, 400, 409},
            )
            with lock:
                results.append(code)

        threads = [threading.Thread(target=select, args=(oid,)) for oid in offers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        accepted = sum(1 for c in results if c in (200, 201))

        if accepted > 1:
            stats.anomaly(
                f"سباق العروض: قُبل {accepted} عرضًا على الطلب {ride_id} — "
                f"القفل لم يمنع الازدواج"
            )
            stats.scenario("contention", False)
        else:
            stats.scenario("contention", True)

    def _published(self, client, stats, rng, driver, seat_buyers):
        """سائق ينشر سفرية، وزبائن يحجزون مقاعد بالتوازي."""
        if not driver.get("vehicle_id"):
            stats.scenario("published", False)
            return

        when = timezone.now() + timedelta(hours=rng.randint(3, 72))
        capacity = rng.choice([3, 4])

        code, trip = client.call(
            "POST", "/api/v1/driver/trips/publish/", "POST /driver/trips/publish/",
            token=driver["token"],
            data={
                "vehicle_id": driver["vehicle_id"],
                "trip_category": "intercity",
                "scheduled_at": when.isoformat(),
                "capacity": capacity,
                "pickup_lat": JABLEH[1], "pickup_lng": JABLEH[0],
                "destination_lat": 35.5200, "destination_lng": 35.7900,
                "origin_city": "جبلة", "destination_city": "اللاذقية",
                "price_per_seat": f"{rng.randint(5000, 15000)}.00",
                "title": "سفرية محاكاة",
            },
            expect={200, 201, 400},
        )

        if code not in (200, 201) or not isinstance(trip, dict) or not trip.get("id"):
            stats.scenario("published", False)
            return

        trip_id = trip["id"]

        client.call(
            "GET", "/api/v1/trips/", "GET /trips/ (catalog)",
            token=seat_buyers[0]["token"], expect={200},
        )

        # حجزٌ متزامن يتجاوز السعة عمدًا: مجموع المطلوب أكبر من المتاح،
        # فيجب أن يُرفض الفائض لا أن يُقبل.
        booked = []
        lock = threading.Lock()

        def book(buyer, seats):
            code, _ = client.call(
                "POST", f"/api/v1/trips/{trip_id}/book/", "POST /trips/{id}/book/",
                token=buyer["token"], data={"passenger_count": seats},
                expect={200, 201, 400, 409},
            )
            with lock:
                booked.append((code, seats))

        threads = [
            threading.Thread(target=book, args=(buyer, 2))
            for buyer in seat_buyers
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        seats_sold = sum(s for c, s in booked if c in (200, 201))

        if seats_sold > capacity:
            stats.anomaly(
                f"تجاوز السعة: بيع {seats_sold} مقعدًا من أصل {capacity} "
                f"في السفرية {trip_id}"
            )
            stats.scenario("published", False)
        else:
            stats.scenario("published", True)

    def _browse(self, client, stats, rng, customer, drivers):
        """حركة قراءة فقط — أكثر ما يفعله المستخدمون فعلًا."""
        token = customer["token"]

        client.call("GET", "/api/v1/auth/me/", "GET /auth/me/", token=token, expect={200})
        client.call("GET", "/api/v1/rides/mine/", "GET /rides/mine/", token=token, expect={200})
        client.call("GET", "/api/v1/me/trips/", "GET /me/trips/", token=token, expect={200})
        client.call("GET", "/api/v1/me/notifications/", "GET /me/notifications/", token=token, expect={200})
        client.call("GET", "/api/v1/me/rating/", "GET /me/rating/", token=token, expect={200})
        client.call("GET", "/api/v1/rating-tags/", "GET /rating-tags/", token=token, expect={200})
        client.call("GET", "/api/v1/trips/", "GET /trips/ (catalog)", token=token, expect={200})

        stats.scenario("browse", True)

    # -----------------------------------------------------------
    # فحص الصحّة بعد الحمل
    # -----------------------------------------------------------

    def _verify_integrity(self, stats):
        """
        الأسئلة التي لا يجيب عنها زمن الاستجابة.

        كلّ واحد منها لا يجوز أن يعطي صفًّا واحدًا. صفٌّ هنا يعني خللًا
        في التزامن نجا من الاختبارات الوحدوية لأنّها لا تتنافس فعلًا.
        """
        from django.db.models import Count

        from matching.models import OfferStatus, RideOffer
        from rides.models import RideRequest
        from trips.models import Trip

        # ١. طلبٌ بعرضين مقبولين
        double = (
            RideOffer.objects
            .filter(status=OfferStatus.ACCEPTED)
            .values("ride_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        for row in double[:10]:
            stats.anomaly(
                f"الطلب {row['ride_id']} فيه {row['n']} عرضًا مقبولًا"
            )

        # ٢. طلبٌ برحلتين
        twin_trips = (
            Trip.objects.values("ride_id").annotate(n=Count("id")).filter(n__gt=1)
        )
        for row in twin_trips[:10]:
            stats.anomaly(f"الطلب {row['ride_id']} له {row['n']} رحلة")

        # ٣. سائق في رحلتين نشطتين معًا
        active = (
            Trip.objects
            .filter(status__in=["created", "driver_arriving", "driver_arrived", "in_progress"])
            .values("driver_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        for row in active[:10]:
            stats.anomaly(
                f"السائق {row['driver_id']} في {row['n']} رحلة نشطة معًا"
            )

        # ٤. رحلة مكتملة بلا دفعة
        from payments.models import Payment

        completed_ids = set(
            Trip.objects.filter(status="completed").values_list("id", flat=True)[:5000]
        )
        paid_ids = set(
            Payment.objects.filter(trip_id__in=completed_ids).values_list(
                "trip_id", flat=True
            )
        )
        missing = completed_ids - paid_ids
        if missing:
            stats.anomaly(
                f"{len(missing)} رحلة مكتملة بلا دفعة "
                f"(مهمّة backfill تعالجها كلّ 5 دقائق)"
            )

    # -----------------------------------------------------------
    # التقرير
    # -----------------------------------------------------------

    def _report(self, stats, elapsed, job_count):
        rows = stats.table()
        total_calls = sum(r["count"] for r in rows)

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 96))
        self.stdout.write(self.style.HTTP_INFO("زمن الاستجابة (مللي ثانية)"))
        self.stdout.write(self.style.HTTP_INFO("=" * 96))
        self.stdout.write(
            f"  {'النقطة':<44} {'عدد':>6} {'نجاح%':>7} "
            f"{'p50':>8} {'p95':>8} {'p99':>8} {'أقصى':>8}"
        )
        self.stdout.write("  " + "-" * 92)

        for row in sorted(rows, key=lambda r: -r["p95"]):
            style = self.style.SUCCESS if row["success_pct"] >= 95 else self.style.WARNING
            self.stdout.write(
                style(
                    f"  {row['endpoint']:<44} {row['count']:>6} "
                    f"{row['success_pct']:>7.1f} {row['p50']:>8.1f} "
                    f"{row['p95']:>8.1f} {row['p99']:>8.1f} {row['max']:>8.1f}"
                )
            )

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 96))
        self.stdout.write(self.style.HTTP_INFO("السيناريوهات"))
        self.stdout.write(self.style.HTTP_INFO("=" * 96))

        for name, counts in sorted(stats.scenarios.items()):
            total = counts["ok"] + counts["fail"]
            pct = round(100 * counts["ok"] / total, 1) if total else 0
            style = self.style.SUCCESS if pct >= 90 else self.style.WARNING
            self.stdout.write(
                style(f"  {name:<16} {counts['ok']:>5}/{total:<5} ({pct}%)")
            )

        if stats.errors:
            self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 96))
            self.stdout.write(self.style.HTTP_INFO("الأخطاء (أعلى 15)"))
            self.stdout.write(self.style.HTTP_INFO("=" * 96))
            for key, count in sorted(
                stats.errors.items(), key=lambda kv: -kv[1]
            )[:15]:
                self.stdout.write(self.style.WARNING(f"  {count:>5}x  {key}"))

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 96))
        self.stdout.write(self.style.HTTP_INFO("سلامة البيانات بعد الحمل"))
        self.stdout.write(self.style.HTTP_INFO("=" * 96))

        if stats.anomalies:
            for text in stats.anomalies[:25]:
                self.stdout.write(self.style.ERROR(f"  ✗ {text}"))
            self.stdout.write(
                self.style.ERROR(f"\n  المجموع: {len(stats.anomalies)} خللًا")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "  ✓ لا عرض مقبول مرّتين، ولا طلب برحلتين، ولا سائق في "
                    "رحلتين، ولا تجاوز سعة."
                )
            )

        rps = total_calls / elapsed if elapsed else 0

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 96))
        self.stdout.write(
            f"  {job_count} سيناريو · {total_calls} نداء · "
            f"{elapsed:.1f} ثانية · {rps:.1f} نداء/ثانية"
        )
        self.stdout.write(self.style.HTTP_INFO("=" * 96 + "\n"))
