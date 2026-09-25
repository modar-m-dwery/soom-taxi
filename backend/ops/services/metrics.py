"""
مؤشّرات الأداء التي تشترطها الوثيقة (§11).

المؤشّرات السبعة المسمّاة هناك:

    first_offer_time            كم يمرّ قبل أوّل عرض
    rate_success_match          نسبة الطلبات التي وجدت سائقًا
    driver_cancel_rate          نسبة إلغاء السائقين
    customer_cancel_rate        نسبة إلغاء الزبائن
    rate_accept_invitation      نسبة قبول الدعوات المباشرة
    time_response_invitation    كم يستغرق ردّ السائق على دعوة
    conversion_trip_to_map      نسبة تحوّل الخريطة الحيّة إلى رحلة فعلية

ومعها ثلاثة أضفناها لأنّ غيابها يخفي أعطالًا حقيقية:

    routing_fallback_rate       نسبة الرحلات المسعَّرة على تقدير لا مسار
    completion_rate             نسبة الرحلات التي اكتملت فعلًا
    review_flag_rate            نسبة الرحلات المعلَّمة للمراجعة

لماذا من جداول المجال لا من سجلّ التدقيق
-----------------------------------------
سجلّ التدقيق يحوي كلّ شيء، لكنّه جدول واحد ينمو بلا حدّ وحقوله نصّية.
حساب وسيط زمني منه يعني مسحًا كاملًا. جداول المجال تحمل الطوابع الزمنية
في أعمدة مفهرسة (`sent_at`, `responded_at`, `created_at`)، فالحساب
عليها استعلامٌ واحد يستعمل الفهرس.

الوسيط لا المتوسّط
------------------
`first_offer_time` بالمتوسّط يكذب: طلبٌ واحد انتظر ساعة يرفع متوسّط مئة
طلب انتظرت ثانيتين. نُخرج الوسيط (p50) والمئين التسعين (p90) معًا —
الأوّل يصف التجربة المعتادة والثاني يصف أسوأ ما يحتمله الناس.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Min,
    Q,
)
from django.db.models.functions import TruncHour
from django.utils import timezone


# ---------------------------------------------------------------
# أدوات
# ---------------------------------------------------------------


def _pct(numerator, denominator, digits=2):
    """نسبة مئوية، وNone لا صفر حين لا يوجد مقام."""
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, digits)


def _seconds(delta):
    return round(delta.total_seconds(), 1) if delta else None


def _percentiles(values, points=(50, 90)):
    """
    مئينات من قائمة مرتّبة — في بايثون لا في SQL.

    `PERCENTILE_CONT` متاح في PostgreSQL، لكنّه يحتاج `WITHIN GROUP` وهو
    خارج ما يعبّر عنه ORM بلا SQL خام. والقوائم هنا محدودة بنافذة زمنية،
    فالكلفة مقبولة والشيفرة تبقى قابلة للقراءة.
    """
    if not values:
        return {f"p{p}": None for p in points}

    ordered = sorted(values)
    out = {}

    for p in points:
        index = min(int(round((p / 100.0) * (len(ordered) - 1))), len(ordered) - 1)
        out[f"p{p}"] = round(ordered[index], 1)

    return out


class MetricsService:

    DEFAULT_WINDOW_HOURS = 24

    # -----------------------------------------------------------
    # الواجهة
    # -----------------------------------------------------------

    @classmethod
    def compute(cls, since=None, until=None, service_area=None):
        """
        كلّ المؤشّرات لنافذة زمنية واحدة.

        `service_area` كائن أو None لكلّ المناطق. التقسيم بالمنطقة مهمّ:
        نسبة مطابقة ممتازة في جبلة قد تخفي انهيارًا في اللاذقية.
        """
        until = until or timezone.now()
        since = since or (until - timedelta(hours=cls.DEFAULT_WINDOW_HOURS))

        window = {"created_at__gte": since, "created_at__lt": until}

        return {
            "window": {
                "since": since.isoformat(),
                "until": until.isoformat(),
                "hours": round((until - since).total_seconds() / 3600, 2),
            },
            "service_area": getattr(service_area, "code", None),
            "matching": cls._matching(window, service_area),
            "invitations": cls._invitations(since, until, service_area),
            "trips": cls._trips(window, service_area),
            "pricing": cls._pricing(window, service_area),
        }

    # -----------------------------------------------------------
    # المطابقة
    # -----------------------------------------------------------

    @classmethod
    def _matching(cls, window, service_area):
        from matching.models import RideOffer
        from rides.models import RideRequest, RideStatus

        rides = RideRequest.objects.filter(**window)
        rides = cls._scope_rides(rides, service_area)

        total = rides.count()

        # وصلت إلى سائق: أيّ حالة بعد الاختيار
        matched_states = [
            RideStatus.DRIVER_SELECTED,
            RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED,
            RideStatus.IN_PROGRESS,
            RideStatus.COMPLETED,
        ]

        matched = rides.filter(status__in=matched_states).count()
        expired = rides.filter(status=RideStatus.EXPIRED).count()
        cancelled = rides.filter(status=RideStatus.CANCELLED).count()

        # زمن أوّل عرض: فرق بين إنشاء الطلب وأوّل عرض عليه
        first_offer_rows = (
            rides
            .annotate(first_offer_at=Min("offers__created_at"))
            .filter(first_offer_at__isnull=False)
            .values_list("created_at", "first_offer_at")
        )

        deltas = [
            (first - created).total_seconds()
            for created, first in first_offer_rows
            if first and created and first >= created
        ]

        offers = RideOffer.objects.filter(**window)
        if service_area is not None:
            offers = offers.filter(ride__service_area=service_area)

        return {
            "rides_created": total,
            "rides_matched": matched,
            "rides_expired": expired,
            "rides_cancelled": cancelled,
            # الوثيقة: rate_success_match
            "rate_success_match_pct": _pct(matched, total),
            "rides_with_offer": len(deltas),
            "offer_coverage_pct": _pct(len(deltas), total),
            # الوثيقة: first_offer_time
            "first_offer_seconds": {
                "count": len(deltas),
                "avg": round(sum(deltas) / len(deltas), 1) if deltas else None,
                **_percentiles(deltas),
            },
            "offers_submitted": offers.count(),
            "offers_per_ride": (
                round(offers.count() / total, 2) if total else None
            ),
        }

    # -----------------------------------------------------------
    # الدعوات المباشرة
    # -----------------------------------------------------------

    @classmethod
    def _invitations(cls, since, until, service_area):
        from matching.models import InvitationStatus, RideInvitation

        # الدعوة تستعمل sent_at لا created_at
        invitations = RideInvitation.objects.filter(
            sent_at__gte=since, sent_at__lt=until
        )

        if service_area is not None:
            invitations = invitations.filter(ride__service_area=service_area)

        total = invitations.count()

        accepted = invitations.filter(status=InvitationStatus.ACCEPTED).count()
        rejected = invitations.filter(status=InvitationStatus.REJECTED).count()
        expired = invitations.filter(status=InvitationStatus.EXPIRED).count()
        cancelled = invitations.filter(status=InvitationStatus.CANCELLED).count()

        # زمن الردّ — للمجاب عليها فقط، فالمنتهية بلا ردّ ليست بطيئة بل صامتة
        responded = invitations.filter(responded_at__isnull=False).annotate(
            response_time=ExpressionWrapper(
                F("responded_at") - F("sent_at"), output_field=DurationField()
            )
        )

        response_seconds = [
            row.total_seconds()
            for row in responded.values_list("response_time", flat=True)
            if row is not None
        ]

        # conversion_trip_to_map: من رأى الخريطة ودعا سائقًا، كم منهم ركب؟
        rides_with_invitation = (
            invitations.values("ride_id").distinct().count()
        )
        rides_converted = (
            invitations.filter(status=InvitationStatus.ACCEPTED)
            .values("ride_id")
            .distinct()
            .count()
        )

        return {
            "invitations_sent": total,
            "accepted": accepted,
            "rejected": rejected,
            "expired": expired,
            "cancelled": cancelled,
            # الوثيقة: rate_accept_invitation
            "rate_accept_invitation_pct": _pct(accepted, total),
            "reject_rate_pct": _pct(rejected, total),
            "no_response_rate_pct": _pct(expired, total),
            # الوثيقة: time_response_invitation
            "response_seconds": {
                "count": len(response_seconds),
                "avg": (
                    round(sum(response_seconds) / len(response_seconds), 1)
                    if response_seconds
                    else None
                ),
                **_percentiles(response_seconds),
            },
            # الوثيقة: conversion_trip_to_map
            "rides_using_map": rides_with_invitation,
            "conversion_trip_to_map_pct": _pct(
                rides_converted, rides_with_invitation
            ),
        }

    # -----------------------------------------------------------
    # الرحلات
    # -----------------------------------------------------------

    @classmethod
    def _trips(cls, window, service_area):
        from trips.models import Trip, TripStatus

        trips = Trip.objects.filter(**window)
        if service_area is not None:
            trips = trips.filter(ride__service_area=service_area)

        total = trips.count()

        completed = trips.filter(status=TripStatus.COMPLETED).count()
        cancelled_qs = trips.filter(status=TripStatus.CANCELLED)
        cancelled = cancelled_qs.count()

        by_driver = cancelled_qs.filter(cancelled_by="driver").count()
        by_customer = cancelled_qs.filter(cancelled_by="customer").count()
        by_admin = cancelled_qs.filter(cancelled_by="admin").count()

        needs_review = trips.filter(needs_review=True).count()

        durations = [
            (end - start).total_seconds() / 60
            for start, end in trips.filter(
                started_at__isnull=False, completed_at__isnull=False
            ).values_list("started_at", "completed_at")
            if end and start and end >= start
        ]

        return {
            "trips_created": total,
            "completed": completed,
            "cancelled": cancelled,
            "completion_rate_pct": _pct(completed, total),
            # الوثيقة: driver_cancel_rate / customer_cancel_rate
            # المقام كلّ الرحلات لا الملغاة فقط: «كم رحلة من مئة يلغيها
            # سائق» سؤالٌ مختلف عن «كم من الإلغاءات سببها سائق».
            "driver_cancel_rate_pct": _pct(by_driver, total),
            "customer_cancel_rate_pct": _pct(by_customer, total),
            "admin_cancel_rate_pct": _pct(by_admin, total),
            "needs_review": needs_review,
            "review_flag_rate_pct": _pct(needs_review, total),
            "duration_minutes": {
                "count": len(durations),
                "avg": round(sum(durations) / len(durations), 1) if durations else None,
                **_percentiles(durations),
            },
        }

    # -----------------------------------------------------------
    # التسعير والتوجيه
    # -----------------------------------------------------------

    @classmethod
    def _pricing(cls, window, service_area):
        from maps.services.routing import RoutingService
        from rides.models import RideRequest

        rides = cls._scope_rides(RideRequest.objects.filter(**window), service_area)

        priced = rides.filter(route_source__in=["provider", "estimated"])
        total_priced = priced.count()
        estimated = priced.filter(route_source="estimated").count()

        fares = rides.filter(gross_fare__isnull=False).aggregate(
            avg=Avg("gross_fare"), n=Count("id")
        )

        return {
            "rides_priced": total_priced,
            "priced_on_estimate": estimated,
            # مؤشّر أضفناه: ارتفاعه يعني أنّ مزوّد الخرائط يتعثّر،
            # وأنّ أسعارًا تُبنى على تقدير لا على مسار حقيقي.
            "routing_fallback_rate_pct": _pct(estimated, total_priced),
            "avg_gross_fare": (
                round(float(fares["avg"]), 2) if fares["avg"] is not None else None
            ),
            "routing_provider": RoutingService.health(),
        }

    # -----------------------------------------------------------
    # سلاسل زمنية
    # -----------------------------------------------------------

    @classmethod
    def hourly_series(cls, hours=24, service_area=None):
        """
        عدّاد لكلّ ساعة — لرسم منحنى في لوحة التشغيل.

        استعلامان لا `hours` استعلامًا: التجميع في القاعدة بـTruncHour.
        """
        from rides.models import RideRequest, RideStatus
        from trips.models import Trip, TripStatus

        until = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        since = until - timedelta(hours=hours)

        rides = cls._scope_rides(
            RideRequest.objects.filter(created_at__gte=since, created_at__lt=until),
            service_area,
        )

        ride_rows = (
            rides
            .annotate(hour=TruncHour("created_at"))
            .values("hour")
            .annotate(
                created=Count("id"),
                matched=Count("id", filter=~Q(status__in=[
                    RideStatus.SEARCHING,
                    RideStatus.OFFERS_RECEIVED,
                    RideStatus.EXPIRED,
                    RideStatus.CANCELLED,
                    RideStatus.DRAFT,
                ])),
            )
            .order_by("hour")
        )

        trips = Trip.objects.filter(created_at__gte=since, created_at__lt=until)
        if service_area is not None:
            trips = trips.filter(ride__service_area=service_area)

        trip_rows = (
            trips
            .annotate(hour=TruncHour("created_at"))
            .values("hour")
            .annotate(
                started=Count("id"),
                completed=Count("id", filter=Q(status=TripStatus.COMPLETED)),
            )
            .order_by("hour")
        )

        merged = {}

        for row in ride_rows:
            key = row["hour"].isoformat()
            merged.setdefault(key, {"hour": key})
            merged[key]["rides_created"] = row["created"]
            merged[key]["rides_matched"] = row["matched"]

        for row in trip_rows:
            key = row["hour"].isoformat()
            merged.setdefault(key, {"hour": key})
            merged[key]["trips_started"] = row["started"]
            merged[key]["trips_completed"] = row["completed"]

        return sorted(merged.values(), key=lambda r: r["hour"])

    # -----------------------------------------------------------
    # داخلي
    # -----------------------------------------------------------

    @staticmethod
    def _scope_rides(queryset, service_area):
        if service_area is None:
            return queryset

        # RideRequest قد لا يحمل مفتاح المنطقة مباشرةً في كلّ إصدار،
        # فنحاول الحقل وإن غاب نعيد الاستعلام كما هو بدل أن ننهار.
        try:
            queryset.model._meta.get_field("service_area")
        except Exception:  # noqa: BLE001
            return queryset

        return queryset.filter(service_area=service_area)
