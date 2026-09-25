"""
الكواشف الدوريّة: أنماطٌ لا تُرى من حدثٍ واحد بل من تجميع أيّام.

كلّ كاشف استعلامٌ مجمَّع أو اثنان، ويسجّل عبر `IntegrityService.record`
بمفتاح منعِ تكرارٍ ثابت — فتشغيله كلّ نصف ساعة على نافذة أسبوع لا يحسب
النمط نفسه إلّا مرّة. يرجع كلٌّ منها عدد الإشارات الجديدة.

الجهاز: `OTPChallenge.device_id` الذي يرسله التطبيق مع كلّ طلب رمز دخول.
هاتفٌ واحد دخل منه رقمان = حسابان على جهاز واحد، مهما اختلفت الشرائح.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.utils import timezone

from integrity import registry
from integrity.services.scoring import IntegrityService

logger = logging.getLogger(__name__)

# عتبات افتراضيّة — كلّها قابلة للتجاوز من الإعدادات إن احتاج السوق.
DRIVER_CANCEL_RATE_MIN_ACCEPTED = 8   # عيّنة أصغر تتّهم سائقًا نظاميًّا ألغى مرّتين صدفةً
DRIVER_CANCEL_RATE_THRESHOLD = 0.30
MULTI_ACCOUNT_MIN = 3
REPEAT_PAIR_MIN_TRIPS = 4
REPEAT_PAIR_MAX_AVG_M = 1500
SHORT_TRIP_MAX_M = 700
SHORT_TRIP_MAX_S = 180
SHORT_TRIP_DAILY_MIN = 8
ROUTE_INFLATION_RATIO = 1.5
ROUTE_INFLATION_MIN_EXTRA_M = 2000


def _week(now=None):
    return f"{(now or timezone.now()):%G-W%V}"


class Detectors:

    # ------------------------------------------------------------------
    # الأجهزة
    # ------------------------------------------------------------------

    @staticmethod
    def _devices(days=30):
        """{device_id: {user_id, ...}} للحسابات التي دخلت من كلّ جهاز."""
        from users.models import OTPChallenge

        User = get_user_model()
        since = timezone.now() - timedelta(days=days)
        rows = (
            OTPChallenge.objects
            .filter(created_at__gte=since, consumed_at__isnull=False)
            .exclude(device_id="")
            .values_list("device_id", "phone")
            .distinct()
        )
        phones_by_device = defaultdict(set)
        for device_id, phone in rows:
            phones_by_device[device_id].add(phone)

        all_phones = {p for phones in phones_by_device.values() for p in phones}
        users = dict(User.objects.filter(phone__in=all_phones).values_list("phone", "id"))
        return {
            device: {users[p] for p in phones if p in users}
            for device, phones in phones_by_device.items()
        }

    @classmethod
    def shared_device_pairs(cls, days=30):
        """سائقٌ وزبونٌ دخلا من الجهاز نفسه ولهما رحلة معًا."""
        from trips.models import Trip
        from users.models import UserRole

        User = get_user_model()
        created = 0
        since = timezone.now() - timedelta(days=days)

        for device, user_ids in cls._devices(days).items():
            if len(user_ids) < 2:
                continue
            roles = dict(User.objects.filter(id__in=user_ids).values_list("id", "role"))
            drivers = [u for u, r in roles.items() if r == UserRole.DRIVER]
            customers = [u for u, r in roles.items() if r == UserRole.CUSTOMER]
            for driver_user_id in drivers:
                for customer_id in customers:
                    trips = Trip.objects.filter(
                        driver__user_id=driver_user_id, customer_id=customer_id,
                        created_at__gte=since,
                    )
                    count = trips.count()
                    if not count:
                        continue
                    evidence = {"device_id": device, "trips_together": count}
                    driver_user = User.objects.get(pk=driver_user_id)
                    customer = User.objects.get(pk=customer_id)
                    for user, other in ((driver_user, customer), (customer, driver_user)):
                        if IntegrityService.record(
                            user, registry.SHARED_DEVICE_PAIR.code,
                            evidence=evidence, counterpart=other,
                            dedupe_key=f"shared_dev:{user.pk}:{other.pk}",
                        ):
                            created += 1
        return created

    @classmethod
    def multi_account_devices(cls, days=30):
        """ثلاثة حسابات زبائن فأكثر على جهاز — ومن حصد منها خصم أوّل رحلة."""
        from payments.models import Payment
        from payments.services.promotions import FIRST_RIDE
        from users.models import UserRole

        User = get_user_model()
        created = 0
        for device, user_ids in cls._devices(days).items():
            customers = list(
                User.objects.filter(id__in=user_ids, role=UserRole.CUSTOMER)
                .values_list("id", flat=True)
            )
            if len(customers) < MULTI_ACCOUNT_MIN:
                continue

            promo_users = set(
                Payment.objects.filter(customer_id__in=customers, discount_reason=FIRST_RIDE)
                .values_list("customer_id", flat=True)
            )
            evidence = {
                "device_id": device,
                "accounts_on_device": len(customers),
                "first_ride_discounts": len(promo_users),
            }
            for user in User.objects.filter(id__in=customers):
                if IntegrityService.record(
                    user, registry.MULTI_ACCOUNT_DEVICE.code, evidence=evidence,
                    dedupe_key=f"multi_acc:{device}:{user.pk}",
                ):
                    created += 1
                if len(promo_users) >= 2 and user.pk in promo_users:
                    if IntegrityService.record(
                        user, registry.PROMO_MULTI_ACCOUNT.code, evidence=evidence,
                        dedupe_key=f"promo_multi:{device}:{user.pk}",
                    ):
                        created += 1
        return created

    @classmethod
    def referral_same_device(cls, days=30):
        from users.models import CustomerProfile

        created = 0
        devices = cls._devices(days)
        device_of = defaultdict(set)
        for device, user_ids in devices.items():
            for uid in user_ids:
                device_of[uid].add(device)

        referred = CustomerProfile.objects.filter(
            referred_by__isnull=False,
        ).select_related("user", "referred_by")
        for profile in referred:
            referee = profile.user
            referrer_user = profile.referred_by
            shared = device_of[referee.pk] & device_of[referrer_user.pk]
            if not shared:
                continue
            evidence = {"device_id": sorted(shared)[0]}
            for user, other in ((referee, referrer_user), (referrer_user, referee)):
                if IntegrityService.record(
                    user, registry.REFERRAL_SAME_DEVICE.code, evidence=evidence,
                    counterpart=other,
                    dedupe_key=f"referral_dev:{user.pk}:{other.pk}",
                ):
                    created += 1
        return created

    # ------------------------------------------------------------------
    # الرحلات
    # ------------------------------------------------------------------

    @classmethod
    def repeat_pair_short_trips(cls, days=7):
        from trips.models import Trip, TripStatus

        User = get_user_model()
        since = timezone.now() - timedelta(days=days)
        rows = (
            Trip.objects.filter(status=TripStatus.COMPLETED, completed_at__gte=since)
            .values("driver_id", "driver__user_id", "customer_id")
            .annotate(trips=Count("id"), avg_m=Avg("distance_m"))
            .filter(trips__gte=REPEAT_PAIR_MIN_TRIPS, avg_m__lt=REPEAT_PAIR_MAX_AVG_M)
        )
        created = 0
        week = _week()
        for row in rows:
            driver_user = User.objects.get(pk=row["driver__user_id"])
            customer = User.objects.get(pk=row["customer_id"])
            evidence = {"trips": row["trips"], "avg_distance_m": int(row["avg_m"] or 0), "days": days}
            if IntegrityService.record(
                driver_user, registry.REPEAT_PAIR_SHORT_TRIPS.code,
                evidence=evidence, counterpart=customer,
                dedupe_key=f"pair_short:d:{driver_user.pk}:{customer.pk}:{week}",
            ):
                created += 1
            if IntegrityService.record(
                customer, registry.REPEAT_PAIR_SHORT_TRIPS.code,
                evidence=evidence, counterpart=driver_user,
                weight=registry.REPEAT_PAIR_SHORT_TRIPS.weight // 2,
                dedupe_key=f"pair_short:c:{driver_user.pk}:{customer.pk}:{week}",
            ):
                created += 1
        return created

    @classmethod
    def short_trip_farming(cls, days=2):
        from django.db.models.functions import TruncDate

        from trips.models import Trip, TripStatus

        User = get_user_model()
        since = timezone.now() - timedelta(days=days)
        rows = (
            Trip.objects.filter(status=TripStatus.COMPLETED, completed_at__gte=since)
            .filter(Q(distance_m__lt=SHORT_TRIP_MAX_M) | Q(duration_s__lt=SHORT_TRIP_MAX_S))
            .annotate(day=TruncDate("completed_at"))
            .values("driver__user_id", "day")
            .annotate(short_trips=Count("id"))
            .filter(short_trips__gte=SHORT_TRIP_DAILY_MIN)
        )
        created = 0
        for row in rows:
            user = User.objects.get(pk=row["driver__user_id"])
            if IntegrityService.record(
                user, registry.SHORT_TRIP_FARMING.code,
                evidence={"day": str(row["day"]), "short_trips": row["short_trips"]},
                dedupe_key=f"short_farm:{user.pk}:{row['day']}",
            ):
                created += 1
        return created

    @staticmethod
    def route_inflation_for_trip(trip):
        ride = trip.ride
        # المسار الحقيقيّ من المزوّد أولًا، وإلّا التقدير الداخليّ (المسافة
        # الهوائيّة × معامل الالتفاف) — حين يتعطّل التوجيه يبقى الكشف حيًّا.
        expected_km = ride.route_distance_km or ride.estimated_distance_km
        if not trip.distance_m or not expected_km:
            return None
        expected_m = float(expected_km) * 1000
        extra = trip.distance_m - expected_m
        if trip.distance_m < expected_m * ROUTE_INFLATION_RATIO or extra < ROUTE_INFLATION_MIN_EXTRA_M:
            return None
        return IntegrityService.record(
            trip.driver.user, registry.ROUTE_INFLATION.code,
            evidence={
                "expected_m": int(expected_m),
                "actual_m": trip.distance_m,
                "ratio": round(trip.distance_m / expected_m, 2),
            },
            ride=ride, trip=trip, counterpart=trip.customer,
            dedupe_key=f"route_infl:{trip.pk}",
        )

    @classmethod
    def route_inflation(cls, days=7):
        from trips.models import Trip, TripStatus

        since = timezone.now() - timedelta(days=days)
        trips = (
            Trip.objects.filter(
                status=TripStatus.COMPLETED, completed_at__gte=since,
                distance_m__isnull=False,
            ).select_related("ride", "driver__user", "customer")
        )
        return sum(1 for trip in trips if cls.route_inflation_for_trip(trip))

    @staticmethod
    def driver_cancel_rate(driver=None, days=7):
        """سائقٌ ألغى أكثر من 30٪ ممّا قبله هذا الأسبوع (بثماني رحلات مقبولة فأكثر)."""
        from trips.models import CancellationKind, CancellationRecord, Trip
        from users.models import DriverProfile

        since = timezone.now() - timedelta(days=days)
        drivers = [driver] if driver is not None else DriverProfile.objects.filter(
            trips__created_at__gte=since,
        ).distinct().select_related("user")

        created = 0
        week = _week()
        for d in drivers:
            accepted = Trip.objects.filter(driver=d, created_at__gte=since).count()
            if accepted < DRIVER_CANCEL_RATE_MIN_ACCEPTED:
                continue
            cancelled = CancellationRecord.objects.filter(
                driver=d, actor="driver", created_at__gte=since,
            ).exclude(kind=CancellationKind.NO_SHOW).count()
            rate = cancelled / accepted
            if rate < DRIVER_CANCEL_RATE_THRESHOLD:
                continue
            if IntegrityService.record(
                d.user, registry.DRIVER_CANCEL_RATE.code,
                evidence={"accepted_7d": accepted, "cancelled_7d": cancelled, "rate": round(rate, 2)},
                dedupe_key=f"drv_cancel:{d.pk}:{week}",
            ):
                created += 1
        return created

    # ------------------------------------------------------------------
    # الكلّ
    # ------------------------------------------------------------------

    @classmethod
    def run_all(cls):
        results = {}
        for name in (
            "shared_device_pairs", "multi_account_devices", "referral_same_device",
            "repeat_pair_short_trips", "short_trip_farming", "route_inflation",
            "driver_cancel_rate",
        ):
            try:
                results[name] = getattr(cls, name)()
            except Exception:  # noqa: BLE001 — كاشفٌ معطوب لا يوقف البقيّة
                logger.exception("integrity detector %s failed", name)
                results[name] = "error"
        return results
