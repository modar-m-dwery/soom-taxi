"""
محاكاة مدينة كاملة فوق خدمات المنصّة الحقيقيّة وبساعةٍ مُحاكاة.

لا شيء هنا يختصر المنطق: الطلب يُنشأ بـ`RideRequestService`، والعرض
بـ`MatchingService.create_offer` (بحدود السعر نفسها)، والاختيار
بـ`select_offer`، والرحلة بـ`TripService` (الوصول بنصف القطر الحقيقيّ،
والإنهاء بالمسافة المقيسة من نقاط المسار)، والإلغاء بسياسة الإلغاء،
والشكوى بخدمة الشكاوى. الذي يُحاكى وحده هو **البشر**: متى يطلبون، أين
يذهبون، وكيف يغشّون.

الساعة: `timezone.now` يُستبدل طوال التشغيل بساعةٍ تتقدّم خطوةً (خمس
دقائق افتراضًا)، فتُحاكى أيّام كاملة في دقائق، وكلّ طابعٍ زمنيّ في القاعدة
(إنشاء الطلب، انتهاء العرض، عمر الإشارة) يتبع الساعة المحاكاة.

الحقيقة الأرضيّة: كلّ حساب يعرف «شخصيّته» (نظاميّ، مزيّف GPS، ...)،
فيُقاس الكشف بدقّة لا بانطباع: من انكشف، من فلت، ومن اتُّهم ظلمًا.
"""

import math
import random
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone

from integrity.simulation import demand

# جبلة — مركز المدينة (يطابق ServiceArea «JAB» في أوامر المشروع).
JABLEH_CENTER = (35.9275, 35.3617)

PHONE_PREFIX = "+96300001"          # بادئة لا تطابق رقمًا سوريًّا حقيقيًّا
DEVICE_PREFIX = "sim-device-"
AREA_CODE = "SIM"

# ---------------------------------------------------------------------
# الشخصيّات — الحقيقة الأرضيّة
# ---------------------------------------------------------------------

HONEST = "honest"

DRIVER_CHEATS = {
    "gps_spoofer": "يزيّف موقعه (قفزات + تطبيق Mock)",
    "cherry_picker": "يقبل ثمّ يلغي بعد رؤية الوجهة",
    "off_app": "يلتقي الزبون ثمّ يطلب منه الإلغاء ويكمل نقدًا",
    "farmer": "رحلات قصيرة وهميّة مع حسابٍ له على نفس الجهاز",
    "bait_pricer": "سوم بسعر طُعم ثمّ يطلب أكثر",
    "route_inflater": "يطوّل الطريق",
}

CUSTOMER_CHEATS = {
    "multi_account": "عدّة شرائح على هاتف واحد لحصد خصم أوّل رحلة",
    "referral_ring": "يدعو نفسه من نفس الهاتف",
    "prankster": "يطلب ويُنطِر السائق ثمّ يلغي",
}

# شركاء الغش: حساباتٌ زبائن يديرها سائقٌ غشّاش. تُحسب غشّاشة بشخصيّة سائقها.
ACCOMPLICE = "accomplice"

# ضوضاء نظاميّة يجب ألّا تُتّهم: هاتف عائلة، فقدان GPS مرّة، مشوار يوميّ
# ثابت لمسافة طويلة، وزحمة تطوّل الطريق قليلًا.
HONEST_NOISE = ("family_phone", "gps_glitch", "daily_commute", "traffic_detour")


@dataclass
class SimDriver:
    profile: object
    persona: str
    shift: tuple
    loc: tuple
    device: str
    online: bool = False
    busy: bool = False
    prev_point: tuple | None = None
    accomplices: list = field(default_factory=list)
    noise: str = ""


@dataclass
class SimCustomer:
    user: object
    persona: str
    home: tuple
    device: str
    partner: SimDriver | None = None
    active: bool = False
    noise: str = ""
    commute_to: tuple | None = None


@dataclass
class Journey:
    ride_id: int
    driver: SimDriver
    customer: SimCustomer
    pickup: tuple
    destination: tuple
    phase: str = "to_pickup"            # to_pickup → waiting → in_progress
    board_at: object = None
    plan: dict = field(default_factory=dict)
    path: list = field(default_factory=list)
    path_index: int = 0


# ---------------------------------------------------------------------
# الجغرافيا
# ---------------------------------------------------------------------

def km_to_deg(lat, dx_km, dy_km):
    return dx_km / (111.32 * math.cos(math.radians(lat))), dy_km / 110.57


def offset(point, dx_km, dy_km):
    lng, lat = point
    dlng, dlat = km_to_deg(lat, dx_km, dy_km)
    return (lng + dlng, lat + dlat)


def distance_km(a, b):
    lng1, lat1 = a
    lng2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(min(1, math.sqrt(h)))


def toward(a, b, step_km):
    total = distance_km(a, b)
    if total <= step_km or total == 0:
        return b
    f = step_km / total
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def pt(p):
    return Point(p[0], p[1], srid=4326)


# ---------------------------------------------------------------------
# الساعة المحاكاة
# ---------------------------------------------------------------------

class SimClock:
    def __init__(self, start):
        self.now = start

    def advance(self, minutes):
        self.now = self.now + timedelta(minutes=minutes)

    def __call__(self):
        return self.now


@contextmanager
def simulated_time(clock):
    with mock.patch("django.utils.timezone.now", clock):
        yield


# ---------------------------------------------------------------------
# العالم
# ---------------------------------------------------------------------

class World:

    def __init__(self, *, drivers=60, customers=400, cheat_ratio=0.12, days=2,
                 ramadan=False, seed=7, step_minutes=5, center=JABLEH_CENTER,
                 radius_km=4.0, demand_scale=1.0, log=None):
        self.rng = random.Random(seed)
        self.n_drivers = drivers
        self.n_customers = customers
        self.cheat_ratio = cheat_ratio
        self.days = days
        self.ramadan = ramadan
        self.step = step_minutes
        self.center = center
        self.radius_km = radius_km
        self.demand_scale = demand_scale
        self.log = log or (lambda msg: None)

        self.drivers: list[SimDriver] = []
        self.customers: list[SimCustomer] = []
        self.journeys: dict[int, Journey] = {}
        self.waiting: dict[int, SimCustomer] = {}     # ride_id → customer (بلا سائق بعد)
        self.area = None
        # وسم التشغيل: ستّ خانات تجعل أرقام الهواتف واللوحات فريدةً بين
        # التشغيلات، فتُعاد المحاكاة على القاعدة نفسها بلا تصادم.
        self.run_tag = self._next_run_tag()

        self.hourly = {}          # (day, hour) → counters
        self.errors = {}
        self.counts = {"requests": 0, "completed": 0, "expired": 0,
                       "cust_cancel": 0, "drv_cancel": 0, "complaints": 0,
                       "offers": 0, "gps_rejected": 0, "gps_mock": 0}

    # ------------------------------------------------------------------
    # الإعداد
    # ------------------------------------------------------------------

    def _error(self, where, exc):
        key = f"{where}: {type(exc).__name__}: {str(exc)[:90]}"
        self.errors[key] = self.errors.get(key, 0) + 1

    def random_point(self, around=None, max_km=None):
        around = around or self.center
        max_km = max_km or self.radius_km
        r = max_km * math.sqrt(self.rng.random())
        theta = self.rng.random() * 2 * math.pi
        return offset(around, r * math.cos(theta), r * math.sin(theta))

    def setup_area(self):
        from locations.models import ServiceArea
        from locations.services import LocationService

        existing = LocationService.resolve_area(*self.center)
        if existing is not None:
            self.area = existing
            self.log(f"منطقة الخدمة: {existing.name} (موجودة، بلا تعديل)")
            return

        self.area, _ = ServiceArea.objects.update_or_create(
            code=AREA_CODE,
            defaults=dict(
                name="مدينة المحاكاة",
                center=pt(self.center),
                fallback_radius_km=Decimal(str(self.radius_km + 3)),
                marketplace_cell_precision=5,
                default_matching_radius_km=Decimal("5"),
                first_ride_discount_pct=Decimal("50"),
                first_ride_discount_cap=Decimal("15000"),
                is_active=True,
            ),
        )
        LocationService.invalidate_cache()
        self.log("منطقة الخدمة: أُنشئت «مدينة المحاكاة» (خصم أوّل رحلة 50٪)")

    @staticmethod
    def _next_run_tag():
        """أوّل وسمٍ لم تُستعمل بادئته بعد — يبدأ من ساعة النظام ويتقدّم عند التصادم."""
        import time

        from django.contrib.auth import get_user_model

        User = get_user_model()
        tag = int(time.time()) % 1_000_000
        while User.objects.filter(phone__startswith=f"{PHONE_PREFIX}{tag:06d}").exists():
            tag = (tag + 1) % 1_000_000
        return f"{tag:06d}"

    def _phone(self, n):
        return f"{PHONE_PREFIX}{self.run_tag}{n:05d}"

    def _login(self, user, device):
        from users.models import OTPChallenge

        OTPChallenge.objects.create(
            phone=user.phone, code_salt="sim", code_hash="sim", max_attempts=5,
            expires_at=timezone.now() + timedelta(minutes=5),
            consumed_at=timezone.now(), device_id=device,
        )

    def setup_people(self):
        from users.models import CustomerProfile, DriverProfile, User, UserRole
        from vehicles.models import Vehicle

        rng = self.rng
        seq = iter(range(1, 10 ** 5))

        # ---------------------------------------------------- السائقون
        cheat_names = list(DRIVER_CHEATS)
        n_cheat = max(len(cheat_names), round(self.n_drivers * self.cheat_ratio))
        personas = [cheat_names[i % len(cheat_names)] for i in range(n_cheat)]
        personas += [HONEST] * (self.n_drivers - n_cheat)
        rng.shuffle(personas)

        shift_pool = []
        for shift in demand.SHIFTS:
            shift_pool += [shift] * max(1, round(shift[2] * 100))

        for i, persona in enumerate(personas):
            user = User.objects.create_user(
                phone=self._phone(next(seq)), password=None, role=UserRole.DRIVER,
                is_verified=True, name=f"سائق {i + 1}",
            )
            loc = self.random_point()
            profile = DriverProfile.objects.create(
                user=user, status=DriverProfile.DriverStatus.ACTIVE, online=False,
                current_location=pt(loc), available_seats=4,
                last_location_at=timezone.now(), home_service_area=self.area,
            )
            Vehicle.objects.create(
                driver=profile, type_id="taxi", make="Kia", model="Rio", year=2015,
                color="أبيض", plate_number=f"SIM-{self.run_tag}-{i:04d}", seats=4, active=True,
            )
            device = f"{DEVICE_PREFIX}{self.run_tag}-d{i}"
            self._login(user, device)
            driver = SimDriver(
                profile=profile, persona=persona, shift=rng.choice(shift_pool),
                loc=loc, device=device,
            )
            self.drivers.append(driver)

        # ضوضاء نظاميّة للسائقين
        honest_drivers = [d for d in self.drivers if d.persona == HONEST]
        rng.shuffle(honest_drivers)
        for d in honest_drivers[:3]:
            d.noise = "gps_glitch"
        for d in honest_drivers[3:6]:
            d.noise = "traffic_detour"

        # ---------------------------------------------------- الزبائن
        def make_customer(persona, device=None, noise=""):
            idx = next(seq)
            user = User.objects.create_user(
                phone=self._phone(idx), password=None, role=UserRole.CUSTOMER,
                is_verified=True, name=f"زبون {idx}",
            )
            CustomerProfile.objects.get_or_create(user=user)
            device = device or f"{DEVICE_PREFIX}{self.run_tag}-c{idx}"
            self._login(user, device)
            c = SimCustomer(user=user, persona=persona, home=self.random_point(), device=device, noise=noise)
            self.customers.append(c)
            return c

        # شركاء السائقين الغشّاشين
        for d in self.drivers:
            if d.persona == "farmer":
                # حسابٌ زبون على هاتف السائق نفسه + حسابٌ ثانٍ لصديق
                d.accomplices.append(make_customer(ACCOMPLICE, device=d.device))
                d.accomplices.append(make_customer(ACCOMPLICE))
            elif d.persona == "off_app":
                d.accomplices += [make_customer(ACCOMPLICE) for _ in range(2)]
            for c in d.accomplices:
                c.partner = d

        # الزبائن الغشّاشون
        n_cust_cheat = max(len(CUSTOMER_CHEATS), round(self.n_customers * self.cheat_ratio / 2))
        cust_names = list(CUSTOMER_CHEATS)
        for i in range(n_cust_cheat):
            persona = cust_names[i % len(cust_names)]
            if persona == "multi_account":
                device = f"{DEVICE_PREFIX}{self.run_tag}-sims{i}"
                for _ in range(rng.randint(3, 5)):
                    make_customer(persona, device=device)
            elif persona == "referral_ring":
                device = f"{DEVICE_PREFIX}{self.run_tag}-ring{i}"
                referrer = make_customer(persona, device=device)
                referee = make_customer(persona, device=device)
                profile = referee.user.customer_profile
                profile.referred_by = referrer.user
                profile.save(update_fields=["referred_by"])
            else:
                make_customer(persona)

        # النظاميّون + ضوضاؤهم
        while len(self.customers) < self.n_customers:
            make_customer(HONEST)
        honest = [c for c in self.customers if c.persona == HONEST]
        rng.shuffle(honest)
        # هاتف عائلة: حسابان على جهاز واحد (مسموح)
        for a, b in zip(honest[0:6:2], honest[1:6:2]):
            self._login(b.user, a.device)
            a.noise = b.noise = "family_phone"
        # مشوار يوميّ ثابت لمسافة طويلة مع نفس السائق غالبًا
        for c in honest[6:10]:
            c.noise = "daily_commute"
            c.commute_to = offset(c.home, 5.5, 2.0)

    # ------------------------------------------------------------------
    # الحلقة
    # ------------------------------------------------------------------

    def run(self, clock):
        steps = int(self.days * 24 * 60 / self.step)
        for i in range(steps):
            now = clock.now
            self.tick(now)
            clock.advance(self.step)
            if (i + 1) % int(60 / self.step) == 0:
                self.hourly_housekeeping(clock.now)
            if (i + 1) % int(24 * 60 / self.step) == 0:
                self.log(f"انتهى اليوم {(i + 1) * self.step // (24 * 60)}: {self.counts}")

    def hourly_housekeeping(self, now):
        from integrity.services.detectors import Detectors

        if now.hour % 2 == 0:
            Detectors.run_all()

    def tick(self, now):
        local = timezone.localtime(now)
        key = (local.date().isoformat(), local.hour)
        bucket = self.hourly.setdefault(key, {
            "requests": 0, "matched": 0, "expired": 0, "online": 0,
            "wait_min_total": 0.0, "wait_n": 0,
        })

        self.update_supply(local.hour, bucket)
        self.new_requests(local, bucket)
        self.drivers_bid(now)
        self.customers_choose(now, bucket)
        self.advance_journeys(now)
        self.expire(bucket)

    # ------------------------------------------------------------------
    # العرض: من أونلاين، وأين
    # ------------------------------------------------------------------

    def update_supply(self, hour, bucket):
        from users.models import DriverProfile

        for d in self.drivers:
            should = demand.on_shift(d.shift, hour)
            # الغشّاشون يعملون أكثر — حيث الربح
            if d.persona != HONEST and not should:
                should = self.rng.random() < 0.3
            if should != d.online and not d.busy:
                d.online = should
                DriverProfile.objects.filter(pk=d.profile.pk).update(online=should)
                d.profile.online = should
            if d.online:
                bucket["online"] += 1
                if not d.busy:
                    self.drift(d)

    def drift(self, d):
        """سائقٌ فارغ يتجوّل قليلًا، ويرسل موقعه كما يفعل التطبيق."""
        target = self.random_point(around=d.loc, max_km=0.8)
        # المدينة لا تتسرّب: من ابتعد يعود نحو المركز
        if distance_km(target, self.center) > self.radius_km:
            target = toward(d.loc, self.center, 0.8)
        self.emit_location(d, target)

    def emit_location(self, d, target, mocked=False, after_s=0):
        """
        نسخةٌ من منطق `DriverRoomConsumer._handle_location_update`: الرفض
        بالسرعة المستحيلة، والموقع المُحاكى، ثمّ الكتابة إلى القاعدة.

        `after_s`: كم ثانية بعد بداية الخطوة أُرسلت هذه النبضة. خطوةٌ واحدة
        فيها تجوالٌ ثمّ انطلاقٌ نحو الزبون؛ لو حملتا الطابع نفسه لبدا انتقال
        كيلومترين في صفر ثانية «قفزةً مستحيلة» لسائقٍ نظاميّ.
        """
        from config.security import location_rejection
        from integrity.services import hooks
        from users.models import DriverProfile

        now_epoch = timezone.now().timestamp() + after_s
        if d.prev_point is not None and now_epoch <= d.prev_point[2]:
            now_epoch = d.prev_point[2] + 30

        if d.persona == "gps_spoofer" and self.rng.random() < 0.25:
            # تطبيق Fake GPS شغّال: أندرويد يعلّم الموقع «مُحاكى» ولو بلا قفزة.
            mocked = True
        if d.persona == "gps_spoofer" and self.rng.random() < 0.10:
            # قفزة إلى طلبٍ بعيد: عشرة كيلومترات في ثوانٍ
            target = offset(d.loc, self.rng.uniform(6, 12), self.rng.uniform(-3, 3))
            mocked = self.rng.random() < 0.5
            now_epoch = (d.prev_point[2] + 20) if d.prev_point else now_epoch
        if d.noise == "gps_glitch" and self.rng.random() < 0.002:
            target = offset(d.loc, 8, 0)
            now_epoch = (d.prev_point[2] + 10) if d.prev_point else now_epoch

        reason = location_rejection(target[0], target[1], d.prev_point, now_epoch)
        if reason is None and mocked:
            hooks.on_mock_location(d.profile.id, *target)
            self.counts["gps_mock"] += 1
            if hooks.reject_mock_locations():
                reason = "mock_location"
        if reason is not None:
            if reason == "implausible_speed":
                hooks.on_location_rejected(d.profile.id, reason, target[0], target[1], d.prev_point)
            self.counts["gps_rejected"] += 1
            return False

        d.prev_point = (target[0], target[1], now_epoch)
        d.loc = target
        DriverProfile.objects.filter(pk=d.profile.pk).update(
            current_location=pt(target), last_location_at=timezone.now(),
        )
        return True

    # ------------------------------------------------------------------
    # الطلب
    # ------------------------------------------------------------------

    def new_requests(self, local, bucket):
        weight = demand.demand_weight(local.hour, local.weekday(), self.ramadan)
        # ~3٪ من الزبائن يطلبون في ساعةٍ وزنها 1
        rate = self.n_customers * 0.03 * weight * self.demand_scale * self.step / 60
        n = self._poisson(rate)

        idle = [c for c in self.customers if not c.active and c.persona != ACCOMPLICE]
        self.rng.shuffle(idle)
        for c in idle[:n]:
            self.request(c, bucket)

        # الشركاء يطلبون بإيقاع سائقهم لا بإيقاع المدينة
        for d in self.drivers:
            if d.persona in ("farmer", "off_app") and d.online and not d.busy:
                chance = 0.25 if d.persona == "farmer" else 0.06
                if self.rng.random() < chance:
                    partners = [c for c in d.accomplices if not c.active]
                    if partners:
                        self.request(self.rng.choice(partners), bucket, near=d.loc)

    def _poisson(self, lam):
        # كنوث — يكفي لمعدّلات صغيرة
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def request(self, c, bucket, near=None):
        from rides.models import RideMode
        from rides.services.ride_request import RideRequestService

        pickup = self.random_point(around=near or c.home, max_km=0.6 if near else 1.2)
        if c.partner is not None and c.partner.persona == "farmer":
            destination = self.random_point(around=pickup, max_km=0.5)
        elif c.noise == "daily_commute" and c.commute_to is not None:
            destination = c.commute_to
        else:
            d_km = min(max(self.rng.lognormvariate(math.log(2.8), 0.5), 0.8), 9)
            theta = self.rng.random() * 2 * math.pi
            destination = offset(pickup, d_km * math.cos(theta), d_km * math.sin(theta))
        if distance_km(pickup, destination) < 0.05:
            destination = offset(pickup, 0.2, 0.1)

        try:
            with transaction.atomic():
                ride = RideRequestService.create_ride_request(
                    customer=c.user, pickup=pt(pickup), destination=pt(destination),
                    mode=RideMode.STANDARD, passenger_count=1,
                )
        except Exception as exc:  # noqa: BLE001
            self._error("request", exc)
            return None

        c.active = True
        c.pickup, c.destination, c.ride_id = pickup, destination, ride.id
        c.requested_at = timezone.now()
        self.waiting[ride.id] = c
        self.counts["requests"] += 1
        bucket["requests"] += 1
        return ride

    # ------------------------------------------------------------------
    # السوم: السائقون يقدّمون عروضهم
    # ------------------------------------------------------------------

    def drivers_bid(self, now):
        from matching.services.matching import MatchingService
        from rides.models import RideRequest

        if not self.waiting:
            return
        rides = {r.id: r for r in RideRequest.objects.filter(id__in=list(self.waiting))}
        free = [d for d in self.drivers if d.online and not d.busy]

        for ride_id, c in list(self.waiting.items()):
            ride = rides.get(ride_id)
            if ride is None:
                continue
            if c.partner is not None:
                bidders = [c.partner] if (c.partner.online and not c.partner.busy) else []
            else:
                near = sorted(
                    (d for d in free if distance_km(d.loc, c.pickup) <= 5),
                    key=lambda d: distance_km(d.loc, c.pickup),
                )
                bidders = [d for d in near[:6] if self.rng.random() < 0.6][:3]

            for d in bidders:
                fare = self.offer_fare(ride, d)
                eta = max(1, round(distance_km(d.loc, c.pickup) / 0.5))   # ~30 كم/س
                try:
                    with transaction.atomic():
                        d.profile.refresh_from_db()
                        MatchingService.create_offer(ride.id, d.profile, fare, eta)
                    self.counts["offers"] += 1
                except Exception as exc:  # noqa: BLE001
                    self._error("offer", exc)

    def offer_fare(self, ride, d):
        base = Decimal(ride.gross_fare or 0) or Decimal("10000")
        if d.persona == "bait_pricer":
            factor = Decimal("0.88")
        else:
            factor = Decimal(str(round(self.rng.uniform(1.0, 1.15), 2)))
        fare = (base * factor).quantize(Decimal("1"))
        if ride.fare_floor is not None:
            fare = max(fare, Decimal(ride.fare_floor))
        if ride.fare_cap is not None:
            fare = min(fare, Decimal(ride.fare_cap))
        return fare

    # ------------------------------------------------------------------
    # الزبون يختار
    # ------------------------------------------------------------------

    def customers_choose(self, now, bucket):
        from matching.models import OfferStatus, RideOffer
        from matching.services.matching import MatchingService

        for ride_id, c in list(self.waiting.items()):
            offers = list(
                RideOffer.objects.filter(ride_id=ride_id, status=OfferStatus.PENDING,
                                         expires_at__gt=now)
                .select_related("driver")
            )
            if not offers:
                continue
            by_driver = {d.profile.id: d for d in self.drivers}
            if c.partner is not None:
                chosen = next((o for o in offers if o.driver_id == c.partner.profile.id), None)
            else:
                chosen = min(offers, key=lambda o: (o.gross_fare, o.eta_minutes))
            if chosen is None:
                continue
            driver = by_driver.get(chosen.driver_id)
            if driver is None or driver.busy:
                continue
            try:
                with transaction.atomic():
                    MatchingService.select_offer(ride_id, chosen.id, c.user)
            except Exception as exc:  # noqa: BLE001
                self._error("select", exc)
                continue

            del self.waiting[ride_id]
            driver.busy = True
            bucket["matched"] += 1
            waited = (now - c.requested_at).total_seconds() / 60
            bucket["wait_min_total"] += waited
            bucket["wait_n"] += 1
            self.journeys[ride_id] = Journey(
                ride_id=ride_id, driver=driver, customer=c,
                pickup=c.pickup, destination=c.destination,
                plan=self.plan_for(driver, c),
            )

    def plan_for(self, d, c):
        """ماذا سيحدث في هذه الرحلة — يقرّره البشر لا النظام."""
        rng = self.rng
        plan = {}
        if d.persona == "cherry_picker" and rng.random() < 0.45:
            plan["driver_cancel"] = True
        elif d.persona == HONEST and rng.random() < 0.03:
            plan["driver_cancel"] = True
        if d.persona == "off_app" and c.partner is d:
            plan["customer_cancel_after_arrive"] = "driver_asked" if rng.random() < 0.3 else "found_other"
        elif c.persona == "prankster" and rng.random() < 0.7:
            plan["customer_cancel_after_wait"] = True
        elif c.persona == HONEST and rng.random() < 0.05:
            plan["customer_cancel_early"] = True
        if d.persona == "route_inflater" and rng.random() < 0.7:
            plan["detour"] = 2.2
        elif d.noise == "traffic_detour" and rng.random() < 0.3:
            plan["detour"] = 1.25
        if d.persona == "bait_pricer" and rng.random() < 0.6:
            plan["fare_complaint"] = True
        return plan

    # ------------------------------------------------------------------
    # الرحلات
    # ------------------------------------------------------------------

    def advance_journeys(self, now):
        from trips.services.trip import TripService

        step_km = 30 * self.step / 60      # 30 كم/س
        for ride_id, j in list(self.journeys.items()):
            d, c, plan = j.driver, j.customer, j.plan
            try:
                if plan.get("driver_cancel"):
                    with transaction.atomic():
                        TripService.cancel(ride_id, actor="driver", reason="الوجهة بعيدة", driver=d.profile)
                    self.counts["drv_cancel"] += 1
                    self._requeue(j)
                    continue

                if j.phase == "to_pickup":
                    if plan.get("customer_cancel_early"):
                        with transaction.atomic():
                            TripService.cancel(ride_id, actor="customer", reason_code="changed_mind")
                        self.counts["cust_cancel"] += 1
                        self._finish(j)
                        continue
                    half = self.step * 30
                    self.emit_location(d, toward(d.loc, j.pickup, step_km), after_s=half)
                    if distance_km(d.loc, j.pickup) <= 0.15:
                        self.emit_location(d, j.pickup, after_s=half + 60)
                        with transaction.atomic():
                            d.profile.refresh_from_db()
                            TripService.arrived(ride_id, d.profile)
                        j.phase = "waiting"
                        waits = 6 if plan.get("customer_cancel_after_wait") else self.rng.randint(1, 3)
                        j.board_at = now + timedelta(minutes=waits)

                elif j.phase == "waiting":
                    if now < j.board_at:
                        continue
                    reason = plan.get("customer_cancel_after_arrive")
                    if reason or plan.get("customer_cancel_after_wait"):
                        with transaction.atomic():
                            TripService.cancel(
                                ride_id, actor="customer", reason_code=reason or "other",
                            )
                        self.counts["cust_cancel"] += 1
                        self._finish(j)
                        continue
                    with transaction.atomic():
                        TripService.start(ride_id, d.profile)
                    j.phase = "in_progress"
                    j.path = self.route(j.pickup, j.destination, plan.get("detour"))

                elif j.phase == "in_progress":
                    self.drive_path(j, step_km)
                    if j.path_index >= len(j.path) - 1:
                        with transaction.atomic():
                            d.profile.refresh_from_db()
                            TripService.complete(ride_id, d.profile)
                        self.counts["completed"] += 1
                        if plan.get("fare_complaint"):
                            self.complain(j)
                        self._finish(j)
            except Exception as exc:  # noqa: BLE001
                self._error(f"journey:{j.phase}", exc)
                self._finish(j)

    def route(self, a, b, detour=None):
        """مسارٌ بنقاط كلّ ~150م. الالتفاف يمرّ بنقطة جانبيّة تطوّل الطريق."""
        points = [a]
        waypoints = [b]
        if detour:
            direct = distance_km(a, b)
            extra = direct * (detour - 1) / 2
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            waypoints = [offset(mid, extra, extra * 0.6), b]
        cur = a
        for w in waypoints:
            while distance_km(cur, w) > 0.15:
                cur = toward(cur, w, 0.15)
                points.append(cur)
            cur = w
            points.append(w)
        return points

    def drive_path(self, j, step_km):
        from trips.models import Trip
        from trips.services.trip import TripService

        trip = Trip.objects.get(ride_id=j.ride_id)
        budget = step_km
        base = timezone.now()
        k = 0
        while budget > 0 and j.path_index < len(j.path) - 1:
            nxt = j.path[j.path_index + 1]
            seg = distance_km(j.path[j.path_index], nxt)
            budget -= seg
            j.path_index += 1
            k += 1
            j.driver.loc = nxt
            TripService.record_location(
                trip, nxt[0], nxt[1], speed=8.3, at=base + timedelta(seconds=20 * k),
            )
        from users.models import DriverProfile

        DriverProfile.objects.filter(pk=j.driver.profile.pk).update(
            current_location=pt(j.driver.loc), last_location_at=timezone.now(),
        )
        j.driver.prev_point = (j.driver.loc[0], j.driver.loc[1], timezone.now().timestamp())

    def complain(self, j):
        from feedback.models import ComplaintCategory
        from feedback.services.complaint import ComplaintService

        try:
            with transaction.atomic():
                ComplaintService.open(
                    j.ride_id, j.customer.user, ComplaintCategory.FARE,
                    "اتّفقنا على سعر بالعرض وبعد ما ركبت طلب أكثر.",
                )
            self.counts["complaints"] += 1
        except Exception as exc:  # noqa: BLE001
            self._error("complaint", exc)

    def _finish(self, j):
        j.driver.busy = False
        j.customer.active = False
        self.journeys.pop(j.ride_id, None)

    def _requeue(self, j):
        """إلغاء السائق يعيد الطلب إلى البحث — الزبون لا يُترك."""
        j.driver.busy = False
        self.journeys.pop(j.ride_id, None)
        self.waiting[j.ride_id] = j.customer

    def expire(self, bucket):
        from matching.tasks import expire_stale_offers, expire_stale_rides
        from rides.models import RideRequest, RideStatus

        try:
            expire_stale_offers()
            expire_stale_rides()
        except Exception as exc:  # noqa: BLE001
            self._error("expire", exc)
        if not self.waiting:
            return
        expired = RideRequest.objects.filter(
            id__in=list(self.waiting),
            status__in=[RideStatus.EXPIRED, RideStatus.CANCELLED],
        ).values_list("id", flat=True)
        for ride_id in expired:
            c = self.waiting.pop(ride_id)
            c.active = False
            self.counts["expired"] += 1
            bucket["expired"] += 1

    # ------------------------------------------------------------------
    # الحقيقة الأرضيّة
    # ------------------------------------------------------------------

    def ground_truth(self):
        """{user_id: (role, persona, noise)} لكلّ حساب في المحاكاة."""
        truth = {}
        for d in self.drivers:
            truth[d.profile.user_id] = ("driver", d.persona, d.noise)
        for c in self.customers:
            persona = c.persona
            if persona == ACCOMPLICE and c.partner is not None:
                persona = f"{ACCOMPLICE}:{c.partner.persona}"
            truth[c.user.pk] = ("customer", persona, c.noise)
        return truth
