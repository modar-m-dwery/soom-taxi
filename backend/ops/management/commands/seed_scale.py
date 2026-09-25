"""
زرع بيئة بحجم واقعي — سائقون وزبائن ومركبات ووثائق وتاريخ.

الغرض
-----
حسابان للعرض يثبتان أنّ التدفّق يعمل. خمسمئة سائق وألفا زبون يثبتان
أنّه يعمل **تحت حمل** — وهما شيئان مختلفان تمامًا: استعلام السائقين
القريبين على عشرة صفوف لا يشبهه على خمسمئة، وقفل الصفّ لا يُختبر إلّا
حين يتنافس عليه اثنان فعلًا.

قرارات الواقعية
---------------
**التوزيع الجغرافي ليس منتظمًا.** سائقون موزّعون بانتظام على مربّع يعطي
نتائج مطابقة متفائلة كاذبة. نوزّعهم حول مراكز ثقل (وسط المدينة،
الكورنيش، المشفى، الجامعة) بتوزيع طبيعي — كما هم فعلًا.

**ليس كلّ سائق مؤهّلًا.** في الواقع: بعضهم بوثائق منتهية، بعضهم موقوف،
بعضهم لم يُوثَّق بعد. زرعُ خمسمئة سائق مثاليّ يخفي بالضبط ما بُني
`DriverEligibilityService` لأجله. النسب أدناه مأخوذة من واقع منصّات
مشابهة.

**التاريخ يسبق اليوم.** التقييمات والرحلات المكتملة تُزرع بتواريخ
ماضية، فتُحسب المؤشّرات على شيء، ويرى مبرمج التطبيق قوائم غير فارغة.

الأمان
------
يرفض العمل إن كان `DEPLOYMENT_ENV=production`. وأرقام الهواتف كلّها
تحت بادئة `+9639X` مخصّصة للاختبار حتى لا تشبه رقمًا حقيقيًّا.
"""
from __future__ import annotations

import random
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from drivers.models import (
    REQUIRED_DOCUMENT_TYPES,
    DocumentStatus,
    DriverDocument,
)
from users.models import CustomerProfile, DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleType


# مراكز ثقل جبلة: (خط الطول، العرض، الوزن، الاسم)
JABLEH_HOTSPOTS = [
    (35.9010, 35.3620, 0.30, "وسط المدينة"),
    (35.8935, 35.3585, 0.22, "الكورنيش"),
    (35.9105, 35.3668, 0.18, "المشفى الوطني"),
    (35.9060, 35.3520, 0.15, "الكراج"),
    (35.8990, 35.3710, 0.15, "الحيّ الشرقي"),
]

# الانتشار حول كلّ مركز بالدرجات (~0.004° ≈ 400 م)
HOTSPOT_SPREAD = 0.006

VEHICLE_TYPES = [
    (VehicleType.SEDAN, 0.62),
    (VehicleType.HATCHBACK, 0.20),
    (VehicleType.SUV, 0.12),
    (VehicleType.VAN, 0.06),
]

MAKES = [
    ("Kia", "Rio"), ("Hyundai", "Accent"), ("Toyota", "Corolla"),
    ("Nissan", "Sunny"), ("Chevrolet", "Aveo"), ("Renault", "Symbol"),
    ("Peugeot", "301"), ("Skoda", "Octavia"), ("Hyundai", "Elantra"),
    ("Kia", "Cerato"), ("Toyota", "Yaris"), ("Suzuki", "Swift"),
]

COLORS = ["أبيض", "فضّي", "أسود", "رمادي", "أزرق", "أحمر", "بيج"]

# أسطول تاكسي في سوريا ذكوريّ الغالبية، لكن ليس بالكامل — والرحلات
# المشتركة تُظهر الجنس للمرشّحين، فالتوزيع هنا يغيّر سلوك المطابقة.
GENDERS = [("male", 0.88), ("female", 0.10), ("undisclosed", 0.02)]

FIRST_NAMES = [
    "أحمد", "محمد", "علي", "حسن", "حسين", "عمر", "خالد", "سامر", "باسل",
    "رامي", "زياد", "فادي", "نور", "ليلى", "رنا", "هالة", "سلمى", "مها",
    "دانا", "ريم", "جمانة", "لمى", "يارا", "عبير", "غادة", "وفاء",
]

LAST_NAMES = [
    "الأحمد", "العلي", "الحسن", "درويش", "خضور", "شاهين", "إبراهيم",
    "سليمان", "منصور", "يوسف", "الخطيب", "حمدان", "صالح", "عيسى",
    "الحلبي", "الشامي", "اللاذقاني", "الجبلاوي",
]


def _weighted(pairs, rng):
    total = sum(w for _, w in pairs)
    r = rng.random() * total
    upto = 0.0
    for value, weight in pairs:
        upto += weight
        if r <= upto:
            return value
    return pairs[-1][0]


def _hotspot_point(rng):
    lng, lat, _, _ = _weighted(
        [((h[0], h[1], h[2], h[3]), h[2]) for h in JABLEH_HOTSPOTS], rng
    )
    return Point(
        lng + rng.gauss(0, HOTSPOT_SPREAD),
        lat + rng.gauss(0, HOTSPOT_SPREAD),
        srid=4326,
    )


class Command(BaseCommand):
    help = "زرع بيئة بحجم واقعي: سائقون وزبائن ومركبات ووثائق وتاريخ."

    # نسب واقعية لحالة أسطول حقيقي
    SHARE_ELIGIBLE = 0.72      # مؤهّل بالكامل ويستطيع العمل
    SHARE_PENDING_DOCS = 0.14  # وثائق قيد المراجعة
    SHARE_EXPIRED_DOCS = 0.07  # وثيقة منتهية
    SHARE_SUSPENDED = 0.04     # موقوف
    SHARE_UNVERIFIED = 0.03    # لم يبدأ التوثيق

    SHARE_ONLINE = 0.55        # من المؤهّلين، كم منهم متّصل الآن

    def add_arguments(self, parser):
        parser.add_argument("--drivers", type=int, default=500)
        parser.add_argument("--customers", type=int, default=2000)
        parser.add_argument(
            "--seed", type=int, default=20260907,
            help="بذرة العشوائية — التكرار بالبذرة نفسها يعطي البيانات نفسها",
        )
        parser.add_argument(
            "--fresh", action="store_true",
            help="احذف كيانات الحجم السابقة أولًا (لا يمسّ حسابات العرض)",
        )
        parser.add_argument(
            "--batch", type=int, default=500,
            help="حجم دفعة الإدراج",
        )

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        if getattr(settings, "DEPLOYMENT_ENV", "") == "production":
            raise CommandError(
                "seed_scale لا يعمل في الإنتاج. هذه بيانات اختبار."
            )

        rng = random.Random(options["seed"])
        started = timezone.now()

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 62))
        self.stdout.write(self.style.HTTP_INFO("زرع بيئة بحجم واقعي"))
        self.stdout.write(self.style.HTTP_INFO("=" * 62))

        # مناطق الخدمة وأوسمة التقييم — يعتمد عليها كلّ ما بعدها
        call_command("locations_resolve_test", verbosity=0)
        call_command("seed_rating_tags", verbosity=0)

        if options["fresh"]:
            self._wipe()

        drivers = self._seed_drivers(rng, options["drivers"], options["batch"])
        customers = self._seed_customers(rng, options["customers"], options["batch"])

        elapsed = (timezone.now() - started).total_seconds()

        self._report(drivers, customers, elapsed)

    # -----------------------------------------------------------------
    # الحذف
    # -----------------------------------------------------------------

    def _wipe(self):
        self.stdout.write("حذف كيانات الحجم السابقة ...")

        # البادئة +9639 5/6 مخصّصة لهذا الأمر وحده. حسابات العرض
        # (+96399000010X) خارجها عمدًا فلا تُمسّ.
        qs = User.objects.filter(phone__startswith="+96395") | User.objects.filter(
            phone__startswith="+96396"
        )
        count = qs.count()
        qs.delete()

        self.stdout.write(self.style.WARNING(f"  حُذف {count} حسابًا."))

    # -----------------------------------------------------------------
    # السائقون
    # -----------------------------------------------------------------

    def _seed_drivers(self, rng, count, batch):
        self.stdout.write(f"\nالسائقون ({count}) ...")

        now = timezone.now()
        existing = set(
            User.objects.filter(phone__startswith="+96395").values_list(
                "phone", flat=True
            )
        )

        new_users = []
        for i in range(count):
            phone = f"+96395{i:07d}"
            if phone in existing:
                continue
            new_users.append(
                User(
                    phone=phone,
                    name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                    role=UserRole.DRIVER,
                    is_verified=True,
                    is_active=True,
                    # الجنس يؤثّر فعلًا في المطابقة المشتركة
                    # (MATCHING_SHARED_SHOW_GENDER)، فزرعه واقعيًّا شرطٌ
                    # لاختبار ذلك المسار لا تزيين.
                    gender=_weighted(GENDERS, rng),
                )
            )

        User.objects.bulk_create(new_users, batch_size=batch, ignore_conflicts=True)

        users = list(
            User.objects.filter(phone__startswith="+96395").order_by("id")[:count]
        )

        # الملفّات
        have_profile = set(
            DriverProfile.objects.filter(user__in=users).values_list(
                "user_id", flat=True
            )
        )

        buckets = self._assign_buckets(rng, len(users))

        profiles = []
        for user, bucket in zip(users, buckets):
            if user.id in have_profile:
                continue

            status = (
                DriverProfile.DriverStatus.SUSPENDED
                if bucket == "suspended"
                else DriverProfile.DriverStatus.ACTIVE
            )

            profiles.append(
                DriverProfile(
                    user=user,
                    status=status,
                    available_seats=rng.choice([3, 4, 4, 4, 6]),
                    current_location=_hotspot_point(rng),
                    last_location_at=now - timedelta(seconds=rng.randint(0, 45)),
                )
            )

        DriverProfile.objects.bulk_create(profiles, batch_size=batch)

        by_user = {
            p.user_id: p
            for p in DriverProfile.objects.filter(user__in=users).select_related("user")
        }

        self._seed_vehicles(rng, users, by_user, buckets, batch)
        self._seed_documents(rng, users, by_user, buckets, now, batch)
        self._set_online(rng, users, by_user, buckets)

        return {"users": users, "profiles": by_user, "buckets": buckets}

    def _assign_buckets(self, rng, n):
        """توزيع حالات الأسطول بالنسب المعلنة أعلاه."""
        plan = (
            ["eligible"] * round(n * self.SHARE_ELIGIBLE)
            + ["pending_docs"] * round(n * self.SHARE_PENDING_DOCS)
            + ["expired_docs"] * round(n * self.SHARE_EXPIRED_DOCS)
            + ["suspended"] * round(n * self.SHARE_SUSPENDED)
            + ["unverified"] * round(n * self.SHARE_UNVERIFIED)
        )

        while len(plan) < n:
            plan.append("eligible")

        plan = plan[:n]
        rng.shuffle(plan)
        return plan

    def _seed_vehicles(self, rng, users, profiles, buckets, batch):
        have = set(
            Vehicle.objects.filter(driver__user__in=users).values_list(
                "driver__user_id", flat=True
            )
        )

        vehicles = []
        for index, (user, bucket) in enumerate(zip(users, buckets)):
            if user.id in have or user.id not in profiles:
                continue

            make, model = rng.choice(MAKES)
            vtype = _weighted(VEHICLE_TYPES, rng)

            vehicles.append(
                Vehicle(
                    driver=profiles[user.id],
                    type_id=vtype,
                    make=make,
                    model=model,
                    year=rng.randint(2008, 2024),
                    color=rng.choice(COLORS),
                    plate_number=f"JAB-{index:05d}",
                    seats=6 if vtype == VehicleType.VAN else 4,
                    # المركبة غير فعّالة لغير الموثّق: مصدر أهلية ثانٍ
                    active=bucket != "unverified",
                )
            )

        Vehicle.objects.bulk_create(vehicles, batch_size=batch, ignore_conflicts=True)
        self.stdout.write(f"  مركبات: +{len(vehicles)}")

    def _seed_documents(self, rng, users, profiles, buckets, now, batch):
        have = set(
            DriverDocument.objects.filter(driver__user__in=users).values_list(
                "driver__user_id", flat=True
            )
        )

        docs = []
        for user, bucket in zip(users, buckets):
            if user.id in have or user.id not in profiles:
                continue

            if bucket == "unverified":
                continue  # لم يرفع شيئًا بعد

            if bucket == "pending_docs":
                status, expires = DocumentStatus.PENDING, now + timedelta(days=300)
            elif bucket == "expired_docs":
                status, expires = DocumentStatus.APPROVED, now - timedelta(days=5)
            else:
                status = DocumentStatus.APPROVED
                expires = now + timedelta(days=rng.randint(60, 900))

            for doc_type in REQUIRED_DOCUMENT_TYPES:
                docs.append(
                    DriverDocument(
                        driver=profiles[user.id],
                        type=doc_type,
                        file=f"driver_documents/scale/{user.id}-{doc_type}.txt",
                        status=status,
                        expires_at=expires,
                        reviewed_at=now if status == DocumentStatus.APPROVED else None,
                    )
                )

        DriverDocument.objects.bulk_create(docs, batch_size=batch)
        self.stdout.write(f"  وثائق: +{len(docs)}")

    def _set_online(self, rng, users, profiles, buckets):
        """
        الاتصال يُكتب في القاعدة وفي Redis معًا.

        القاعدة وحدها لا تكفي: `PresenceService` هو مصدر الحقيقة للحضور،
        وسائقٌ `online=True` في القاعدة بلا مفتاح حضور في Redis لا يظهر
        في المطابقة — وهو أكثر ما يربك أوّل تشغيل لبيئة مزروعة.
        """
        from presence.services import PresenceService

        online_ids = []

        for user, bucket in zip(users, buckets):
            if bucket != "eligible" or user.id not in profiles:
                continue
            if rng.random() > self.SHARE_ONLINE:
                continue
            online_ids.append(profiles[user.id].id)

        DriverProfile.objects.filter(id__in=online_ids).update(online=True)
        DriverProfile.objects.filter(user__in=users).exclude(
            id__in=online_ids
        ).update(online=False)

        by_id = {p.id: p for p in profiles.values()}

        marked = 0
        for driver_id in online_ids:
            profile = by_id.get(driver_id)
            if profile is None or profile.current_location is None:
                continue
            try:
                # الترتيب إلزاميّ: go_online ينشئ سجلّ الحضور، وheartbeat
                # يرفض العمل بدونه ("Driver presence not initialized").
                # وupdate_location هو ما يضع السائق في فهرس GEO فعلًا —
                # فبدونه يكون "متّصلًا" ولا تجده المطابقة أبدًا.
                PresenceService.go_online(profile, engagement={})
                PresenceService.update_location(
                    driver_id,
                    profile.current_location.x,
                    profile.current_location.y,
                )
                PresenceService.heartbeat(driver_id)
                marked += 1
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(
                    self.style.WARNING(f"  حضور Redis تعذّر: {exc}")
                )
                break

        self.stdout.write(
            f"  متّصلون: {len(online_ids)} (حضور Redis: {marked})"
        )

    # -----------------------------------------------------------------
    # الزبائن
    # -----------------------------------------------------------------

    def _seed_customers(self, rng, count, batch):
        self.stdout.write(f"\nالزبائن ({count}) ...")

        existing = set(
            User.objects.filter(phone__startswith="+96396").values_list(
                "phone", flat=True
            )
        )

        new_users = []
        for i in range(count):
            phone = f"+96396{i:07d}"
            if phone in existing:
                continue
            new_users.append(
                User(
                    phone=phone,
                    name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                    role=UserRole.CUSTOMER,
                    is_verified=True,
                    is_active=True,
                )
            )

        User.objects.bulk_create(new_users, batch_size=batch, ignore_conflicts=True)

        users = list(
            User.objects.filter(phone__startswith="+96396").order_by("id")[:count]
        )

        have = set(
            CustomerProfile.objects.filter(user__in=users).values_list(
                "user_id", flat=True
            )
        )

        CustomerProfile.objects.bulk_create(
            [CustomerProfile(user=u) for u in users if u.id not in have],
            batch_size=batch,
        )

        self.stdout.write(f"  زبائن: {len(users)}")
        return {"users": users}

    # -----------------------------------------------------------------
    # التقرير
    # -----------------------------------------------------------------

    def _report(self, drivers, customers, elapsed):
        from drivers.services.eligibility import DriverEligibilityService

        buckets = drivers["buckets"]
        counts = {b: buckets.count(b) for b in set(buckets)}

        # عيّنة أهلية حقيقية لا افتراضية
        sample = list(drivers["profiles"].values())[:60]
        eligible = sum(1 for p in sample if DriverEligibilityService.is_eligible(p))

        online = DriverProfile.objects.filter(
            user__phone__startswith="+96395", online=True
        ).count()

        self.stdout.write(self.style.HTTP_INFO("\n" + "=" * 62))
        self.stdout.write(self.style.SUCCESS("اكتمل الزرع"))
        self.stdout.write(self.style.HTTP_INFO("=" * 62))
        self.stdout.write(f"  سائقون:        {len(drivers['users'])}")

        for key, label in (
            ("eligible", "مؤهّل"),
            ("pending_docs", "وثائق قيد المراجعة"),
            ("expired_docs", "وثيقة منتهية"),
            ("suspended", "موقوف"),
            ("unverified", "غير موثّق"),
        ):
            if key in counts:
                self.stdout.write(f"    {label:<22} {counts[key]}")

        self.stdout.write(f"  متّصلون الآن:   {online}")
        self.stdout.write(
            f"  عيّنة أهلية:    {eligible}/{len(sample)} "
            f"({round(100 * eligible / max(len(sample), 1))}%)"
        )
        self.stdout.write(f"  زبائن:         {len(customers['users'])}")
        self.stdout.write(f"  الزمن:         {elapsed:.1f} ثانية\n")

        self.stdout.write(
            "الخطوة التالية: python manage.py simulate_load --help\n"
        )
