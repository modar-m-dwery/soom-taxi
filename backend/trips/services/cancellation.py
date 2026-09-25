"""
سياسة الإلغاء بعد تثبيت السائق.

الزبون:
    - مجّانيّ خلال `cancel_free_window_seconds` من التثبيت.
    - مجّانيّ إن تأخّر السائق عن وقته المعلن بأكثر من
      `cancel_driver_late_grace_minutes` — التأخير ذنبه لا ذنب الزبون.
    - بعد وصول السائق وانتظاره `cancel_wait_minutes`: مخالفتان.
    - غير ذلك: مخالفة واحدة.
    بلوغ `late_cancel_strike_limit` خلال `late_cancel_window_days` يوقف
    «الأقرب» و«اختر سيارتك» عن الزبون `late_cancel_penalty_hours`، ويُظهر
    للسائقين شارةً على طلبه — لا غرامة.

السائق:
    إلغاؤه بعد القبول يعيد الطلب إلى البحث للزبون (لا يُترك بلا سيارة)،
    ويُحسب عليه. تجاوز `driver_cancel_daily_limit` في يوم يوقفه عن العروض
    والدعوات `driver_cancel_block_minutes`.

    إلّا «الزبون لم يحضر» (NO_SHOW): بعد وصولٍ تحقّق منه الخادم وانتظار
    `cancel_wait_minutes` كاملة. لا يُحسب على السائق بل على الزبون (مخالفتان
    كالإلغاء بعد الانتظار)، ولا يعود الطلب إلى البحث، ويُعوَّض السائق
    (trips/services/compensation.py).

كلّ الأرقام من منطقة الرحلة، ولكلّ منها افتراضٌ معقول حين لا منطقة.
"""

import math
from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from trips.models import CancellationKind, CancellationRecord, TripStatus

#: سجلّات تُحسب مخالفاتها على الزبون: إلغاؤه هو، و«لم يحضر» التي سجّلها السائق.
CUSTOMER_FAULT = Q(actor="customer") | Q(kind=CancellationKind.NO_SHOW)

DEFAULTS = {
    "cancel_free_window_seconds": 120,
    "cancel_driver_late_grace_minutes": 5,
    "cancel_wait_minutes": 5,
    "late_cancel_strike_limit": 3,
    "late_cancel_window_days": 7,
    "late_cancel_penalty_hours": 24,
    "driver_cancel_daily_limit": 3,
    "driver_cancel_block_minutes": 60,
}


def _setting(area, name):
    value = getattr(area, name, None) if area is not None else None
    return DEFAULTS[name] if value is None else value


class CancellationPolicy:

    # ------------------------------------------------------------------
    # تصنيف إلغاء الزبون
    # ------------------------------------------------------------------

    @classmethod
    def classify_customer(cls, trip, now=None):
        """(kind, strikes) لإلغاء الزبون هذه الرحلة الآن."""
        now = now or timezone.now()
        area = trip.ride.service_area
        assigned_at = trip.arriving_at or trip.created_at

        if now - assigned_at <= timedelta(seconds=_setting(area, "cancel_free_window_seconds")):
            return CancellationKind.FREE, 0

        if trip.arrived_at is None:
            eta = getattr(trip.offer, "eta_minutes", None) or 0
            grace = _setting(area, "cancel_driver_late_grace_minutes")
            if now > assigned_at + timedelta(minutes=eta + grace):
                return CancellationKind.DRIVER_LATE, 0
            return CancellationKind.LATE, 1

        waited = now - trip.arrived_at
        if waited >= timedelta(minutes=_setting(area, "cancel_wait_minutes")):
            return CancellationKind.AFTER_WAIT, 2
        return CancellationKind.LATE, 1

    @classmethod
    def no_show_error(cls, trip, now=None):
        """None إن جاز للسائق تسجيل «الزبون لم يحضر» الآن، وإلّا نصّ السبب."""
        now = now or timezone.now()
        if trip.status != TripStatus.DRIVER_ARRIVED or trip.arrived_at is None:
            return "سجّل وصولك أوّلًا — «الزبون لم يحضر» لا يُقبل قبل الوصول."

        wait = timedelta(minutes=_setting(trip.ride.service_area, "cancel_wait_minutes"))
        waited = now - trip.arrived_at
        if waited < wait:
            left = math.ceil((wait - waited).total_seconds() / 60)
            return f"انتظر الزبون قليلًا بعد — بقي {left} د قبل أن تسجّل عدم حضوره."
        return None

    @classmethod
    def record(cls, trip, actor, kind, strikes, reason="", reason_code=""):
        return CancellationRecord.objects.create(
            ride=trip.ride,
            trip=trip,
            customer=trip.customer,
            driver=trip.driver,
            actor=actor,
            kind=kind,
            strikes=strikes,
            reason=(reason or "")[:255],
            reason_code=reason_code or "",
        )

    # ------------------------------------------------------------------
    # عقوبة الزبون
    # ------------------------------------------------------------------

    @classmethod
    def customer_strikes(cls, customer, area=None, now=None):
        now = now or timezone.now()
        since = now - timedelta(days=_setting(area, "late_cancel_window_days"))
        total = (
            CancellationRecord.objects
            .filter(CUSTOMER_FAULT, customer=customer, created_at__gte=since)
            .aggregate(total=Sum("strikes"))["total"]
        )
        return int(total or 0)

    @classmethod
    def customer_penalty_until(cls, customer, area=None, now=None):
        """نهاية العقوبة إن كان الزبون معاقبًا الآن، وإلّا None."""
        now = now or timezone.now()
        limit = _setting(area, "late_cancel_strike_limit")
        if limit <= 0:
            return None

        since = now - timedelta(days=_setting(area, "late_cancel_window_days"))
        records = list(
            CancellationRecord.objects
            .filter(
                CUSTOMER_FAULT, customer=customer,
                strikes__gt=0, created_at__gte=since,
            )
            .order_by("created_at")
            .values_list("created_at", "strikes")
        )

        # العقوبة تبدأ من المخالفة التي بلغ بها الحدّ، لا من آخر مخالفة.
        running = 0
        for created_at, strikes in records:
            running += strikes
            if running >= limit:
                until = created_at + timedelta(
                    hours=_setting(area, "late_cancel_penalty_hours")
                )
                return until if until > now else None
        return None

    # ------------------------------------------------------------------
    # إيقاف السائق
    # ------------------------------------------------------------------

    @classmethod
    def driver_block_until(cls, driver, area=None, now=None):
        now = now or timezone.now()
        limit = _setting(area, "driver_cancel_daily_limit")
        if limit <= 0 or driver is None:
            return None

        recent = list(
            CancellationRecord.objects
            .filter(
                driver=driver, actor="driver",
                created_at__gte=now - timedelta(days=1),
            )
            # «الزبون لم يحضر» ليس ذنب السائق.
            .exclude(kind=CancellationKind.NO_SHOW)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
        )
        if len(recent) <= limit:
            return None

        until = recent[0] + timedelta(minutes=_setting(area, "driver_cancel_block_minutes"))
        return until if until > now else None
