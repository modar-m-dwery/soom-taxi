"""
نقاط الدخول الآنيّة: تُستدعى من مسارات المنصّة الساخنة (موقع السائق،
الإلغاء، الشكوى، إتمام الرحلة).

قاعدة واحدة تحكم هذا الملفّ: **لا شيء هنا يُسقط المسار الذي استدعاه.**
كشف الغش مهمّ، لكنّ سائقًا لا يُحدَّث موقعه لأنّ جدول الإشارات مقفول
أسوأ من غشّاشٍ فات مرّة. كلّ دالة تبتلع أخطاءها وتسجّلها.
"""

import functools
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from integrity import registry
from integrity.services.scoring import IntegrityService

logger = logging.getLogger(__name__)

# نبضة موقع كلّ ثلاث ثوانٍ؛ غشّاشٌ مستمرّ يولّد ألف رفض في الساعة. إشارةٌ
# واحدة لكلّ نافذة كهذه — التكرار عبر نوافذ وأيّام هو ما يرفع النقاط.
GPS_SIGNAL_BUCKET_SECONDS = 15 * 60

# «السائق طلب منّي الإلغاء» — رمز سبب الإلغاء الذي يرسله التطبيق.
REASON_DRIVER_ASKED = "driver_asked"

NO_SHOW_MIN = 2
NO_SHOW_WINDOW_DAYS = 7


def _never_raise(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 — الكشف لا يُسقط المسار الساخن
            logger.exception("integrity hook %s failed", fn.__name__)
            return None

    return wrapper


def _bucket(epoch=None):
    # من ساعة المنصّة لا من ساعة النظام: المحاكاة تستبدلها، والإنتاج سيّان.
    epoch = epoch if epoch is not None else timezone.now().timestamp()
    return int(epoch // GPS_SIGNAL_BUCKET_SECONDS)


def _driver_user(driver_id):
    from users.models import DriverProfile

    return DriverProfile.objects.filter(id=driver_id).values_list("user_id", flat=True).first()


def _user(user_id):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=user_id).first() if user_id else None


# ---------------------------------------------------------------------
# الموقع
# ---------------------------------------------------------------------

def reject_mock_locations():
    return bool(getattr(settings, "INTEGRITY_REJECT_MOCK_LOCATIONS", True))


def _first_in_window(kind, driver_id):
    """
    مرّةً واحدة لكلّ نافذة عبر كلّ العمّال: `cache.add` ذرّيّ في Redis.
    بدونه يطرق كلّ نبضة مزيَّفة (كلّ ثلاث ثوانٍ) القاعدةَ ليكتشف أنّ
    الإشارة مسجّلة أصلًا.
    """
    from django.core.cache import cache

    key = f"integrity:{kind}:{driver_id}:{_bucket()}"
    return cache.add(key, 1, GPS_SIGNAL_BUCKET_SECONDS)


@_never_raise
def on_location_rejected(driver_id, reason, lng, lat, previous=None):
    if reason != "implausible_speed":
        return None
    if not _first_in_window("gps_speed", driver_id):
        return None
    user = _user(_driver_user(driver_id))
    evidence = {"lng": lng, "lat": lat}
    if previous is not None:
        evidence["previous"] = {"lng": previous[0], "lat": previous[1], "at": previous[2]}
    return IntegrityService.record(
        user,
        registry.GPS_IMPLAUSIBLE_SPEED.code,
        evidence=evidence,
        dedupe_key=f"gps_speed:{driver_id}:{_bucket()}",
    )


@_never_raise
def on_mock_location(driver_id, lng, lat):
    if not _first_in_window("gps_mock", driver_id):
        return None
    user = _user(_driver_user(driver_id))
    return IntegrityService.record(
        user,
        registry.GPS_MOCK_LOCATION.code,
        evidence={"lng": lng, "lat": lat},
        dedupe_key=f"gps_mock:{driver_id}:{_bucket()}",
    )


# ---------------------------------------------------------------------
# الإلغاء
# ---------------------------------------------------------------------

@_never_raise
def on_cancellation(record):
    """يُستدعى بعد إنشاء CancellationRecord (trips.models)."""
    from trips.models import CancellationKind, CancellationRecord

    trip = record.trip
    driver_user = record.driver.user if record.driver_id else None
    customer = record.customer

    if record.actor == "customer":
        if (record.reason_code or "") == REASON_DRIVER_ASKED and driver_user is not None:
            IntegrityService.record(
                driver_user,
                registry.DRIVER_ASKED_TO_CANCEL.code,
                evidence={"ride_id": record.ride_id, "reason": record.reason},
                ride=record.ride,
                trip=trip,
                counterpart=customer,
                dedupe_key=f"asked_cancel:{record.ride_id}",
            )

        if trip is not None and trip.arrived_at is not None and driver_user is not None:
            _check_off_app_pair(record)

        if record.kind == CancellationKind.AFTER_WAIT:
            _check_repeated_no_show(customer)

    elif record.kind == CancellationKind.NO_SHOW and driver_user is not None:
        # «لم يحضر» يسجّلها السائق، والذنب على الزبون — لكنّها أيضًا أسهل
        # طريق لثنائيٍّ متواطئ: تعويضٌ للسائق ومشوارٌ خارج التطبيق معًا.
        _check_repeated_no_show(customer)
        _check_no_show_pair(record)

    elif record.actor == "driver" and driver_user is not None:
        from integrity.services.detectors import Detectors

        Detectors.driver_cancel_rate(driver=record.driver)
    return None


def _check_repeated_no_show(customer):
    """
    مرّتان بأسبوع: السائق وصل ونطر، ثمّ ألغى الزبون أو لم يحضر. الزبون
    النظاميّ يفعلها نادرًا جدًّا — وحتّى هنا الأثر «مراقبة» لا تقييد.
    """
    from trips.models import CancellationKind, CancellationRecord

    since = timezone.now() - timedelta(days=NO_SHOW_WINDOW_DAYS)
    waits = CancellationRecord.objects.filter(
        Q(actor="customer", kind=CancellationKind.AFTER_WAIT)
        | Q(kind=CancellationKind.NO_SHOW),
        customer=customer, created_at__gte=since,
    ).count()
    if waits >= NO_SHOW_MIN:
        IntegrityService.record(
            customer,
            registry.REPEATED_NO_SHOW.code,
            evidence={f"no_shows_{NO_SHOW_WINDOW_DAYS}d": waits},
            dedupe_key=f"no_show:{customer.pk}:{timezone.now():%G-W%V}",
        )


def _check_no_show_pair(record):
    """
    الثنائي نفسه مرّتين في أسبوعين: «لم يحضر» ثمّ «لم يحضر». زبونٌ لا يحضر
    لسائقين مختلفين مزعجٌ فقط؛ لا يحضر للسائق نفسه مرّةً بعد مرّة فهو غالبًا
    يركب معه — خارج التطبيق، والسائق يقبض التعويض فوق ذلك.
    """
    from trips.models import CancellationKind, CancellationRecord

    since = timezone.now() - timedelta(days=14)
    count = CancellationRecord.objects.filter(
        customer=record.customer, driver=record.driver,
        kind=CancellationKind.NO_SHOW, created_at__gte=since,
    ).count()
    if count < 2:
        return

    week = f"{timezone.now():%G-W%V}"
    evidence = {"no_show_same_pair_14d": count}
    IntegrityService.record(
        record.driver.user, registry.OFF_APP_SUSPECTED.code,
        evidence=evidence, ride=record.ride, trip=record.trip,
        counterpart=record.customer,
        dedupe_key=f"off_app_ns:d:{record.driver_id}:{record.customer_id}:{week}",
    )
    IntegrityService.record(
        record.customer, registry.OFF_APP_SUSPECTED.code,
        evidence=evidence, ride=record.ride, trip=record.trip,
        counterpart=record.driver.user,
        weight=registry.OFF_APP_SUSPECTED.weight // 2,
        dedupe_key=f"off_app_ns:c:{record.driver_id}:{record.customer_id}:{week}",
    )


def _check_off_app_pair(record):
    """
    الثنائي نفسه: السائق وصل، والزبون ألغى **قبل أن ينتهي الانتظار** —
    مرّتان في أسبوعين تكفيان للشكّ.

    الإلغاء بعد انتظارٍ كامل (AFTER_WAIT) مستثنى عمدًا: ذاك نمط زبونٍ يلعب
    والسائق ضحيّته، لا اتّفاقٌ بينهما. وجدته المحاكاة: سائقٌ نظاميّ صادف
    الزبونَ المزعج نفسه مرّتين ليلًا فاتُّهم بالعمل خارج التطبيق.
    """
    from trips.models import CancellationKind, CancellationRecord

    if record.kind == CancellationKind.AFTER_WAIT:
        return
    since = timezone.now() - timedelta(days=14)
    count = (
        CancellationRecord.objects.filter(
            customer=record.customer, driver=record.driver, actor="customer",
            trip__arrived_at__isnull=False, created_at__gte=since,
        )
        .exclude(kind=CancellationKind.AFTER_WAIT)
        .count()
    )
    if count < 2:
        return

    week = f"{timezone.now():%G-W%V}"
    evidence = {"arrived_then_cancelled_14d": count}
    driver_user = record.driver.user
    IntegrityService.record(
        driver_user, registry.OFF_APP_SUSPECTED.code,
        evidence=evidence, ride=record.ride, trip=record.trip,
        counterpart=record.customer,
        dedupe_key=f"off_app:d:{record.driver_id}:{record.customer_id}:{week}",
    )
    # الزبون شريكٌ في النمط لكنّه أقلّ مسؤوليّة: نصف الوزن.
    IntegrityService.record(
        record.customer, registry.OFF_APP_SUSPECTED.code,
        evidence=evidence, ride=record.ride, trip=record.trip,
        counterpart=driver_user,
        weight=registry.OFF_APP_SUSPECTED.weight // 2,
        dedupe_key=f"off_app:c:{record.driver_id}:{record.customer_id}:{week}",
    )


# ---------------------------------------------------------------------
# الشكاوى
# ---------------------------------------------------------------------

@_never_raise
def on_complaint(complaint):
    """شكوى أجرة من الزبون على رحلةٍ سعرُها من عرض سوم = سعر طُعم محتمل."""
    from feedback.models import ComplaintCategory

    if complaint.category != ComplaintCategory.FARE:
        return None
    trip = complaint.trip
    if trip is None or trip.offer_id is None or complaint.complainant_id != trip.customer_id:
        return None
    driver_user = trip.driver.user
    return IntegrityService.record(
        driver_user,
        registry.FARE_ABOVE_AGREED.code,
        evidence={
            "complaint_id": complaint.pk,
            "agreed_fare": str(trip.offer.gross_fare),
            "final_fare": str(trip.final_fare),
        },
        ride=trip.ride,
        trip=trip,
        counterpart=complaint.complainant,
        dedupe_key=f"fare_bait:{trip.pk}",
    )


# ---------------------------------------------------------------------
# إتمام الرحلة
# ---------------------------------------------------------------------

@_never_raise
def on_trip_completed(trip):
    from integrity.services.detectors import Detectors

    Detectors.route_inflation_for_trip(trip)
    return None
