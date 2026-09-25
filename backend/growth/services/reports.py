"""
تقارير المشغّل: أين يطلب الناس، وأين لا يجدون سيارة، ومن الأنشط، ومن خمل.

كلّ تقرير استعلامٌ مجمَّع واحد أو اثنان — لا حلقات على الصفوف. والفترة
بالأيّام من المشغّل.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone

from rides.models import RideRequest, RideStatus
from trips.models import CancellationKind, CancellationRecord, Trip, TripStatus
from users.models import DriverProfile, UserRole

UNMATCHED = [RideStatus.EXPIRED, RideStatus.CANCELLED]


def _since(days):
    return timezone.now() - timedelta(days=days)


class Reports:

    # ------------------------------------------------------------------
    # الطلب
    # ------------------------------------------------------------------

    @staticmethod
    def summary(days=7, area=None):
        rides = RideRequest.objects.filter(created_at__gte=_since(days))
        if area is not None:
            rides = rides.filter(service_area=area)
        total = rides.count()
        completed = rides.filter(status=RideStatus.COMPLETED).count()
        # «لم يجد سيارة»: انتهى أو أُلغي دون أن يُثبَّت سائق قطّ.
        unmatched = rides.filter(status__in=UNMATCHED, trip__isnull=True).count()
        return {
            "days": days,
            "requests": total,
            "completed": completed,
            "unmatched": unmatched,
            "completion_rate": round(completed * 100 / total, 1) if total else 0.0,
            "unmatched_rate": round(unmatched * 100 / total, 1) if total else 0.0,
        }

    @staticmethod
    def demand_by_hour(days=7, area=None):
        rides = RideRequest.objects.filter(created_at__gte=_since(days))
        if area is not None:
            rides = rides.filter(service_area=area)
        rows = (
            rides.annotate(hour=ExtractHour("created_at"))
            .values("hour")
            .annotate(
                requests=Count("id"),
                unmatched=Count("id", filter=Q(status__in=UNMATCHED, trip__isnull=True)),
            )
            .order_by("hour")
        )
        by_hour = {row["hour"]: row for row in rows}
        return [
            {
                "hour": hour,
                "requests": by_hour.get(hour, {}).get("requests", 0),
                "unmatched": by_hour.get(hour, {}).get("unmatched", 0),
            }
            for hour in range(24)
        ]

    @staticmethod
    def hotspots(days=7, area=None, limit=15):
        """
        خلايا ~1 كم مرتّبة بالطلب. خليّةٌ عالية «بلا سيارة» تقول للمشغّل أين
        يوجّه السائقين أو يطلق حافزًا.
        """
        from django.db.models import DecimalField, F, Func

        # العمود geography: ST_X يريد geometry، وROUND يريد numeric لا float.
        def _cell(field, axis):
            return Func(
                F(field),
                template=f"ROUND(ST_{axis}(%(expressions)s::geometry)::numeric, 2)",
                output_field=DecimalField(max_digits=8, decimal_places=2),
            )

        rides = RideRequest.objects.filter(created_at__gte=_since(days))
        if area is not None:
            rides = rides.filter(service_area=area)
        rows = (
            rides.annotate(
                lng=_cell("pickup", "X"),
                lat=_cell("pickup", "Y"),
            )
            .values("lat", "lng")
            .annotate(
                requests=Count("id"),
                unmatched=Count("id", filter=Q(status__in=UNMATCHED, trip__isnull=True)),
            )
            .order_by("-requests")[:limit]
        )
        return [
            {
                "lat": float(row["lat"]),
                "lng": float(row["lng"]),
                "requests": row["requests"],
                "unmatched": row["unmatched"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # الأشخاص
    # ------------------------------------------------------------------

    @staticmethod
    def top_customers(days=30, limit=20):
        User = get_user_model()
        since = _since(days)
        rows = (
            User.objects.filter(role=UserRole.CUSTOMER)
            .annotate(
                rides=Count(
                    "ride_requests",
                    filter=Q(
                        ride_requests__status=RideStatus.COMPLETED,
                        ride_requests__created_at__gte=since,
                    ),
                ),
                spent=Sum(
                    "ride_requests__customer_total",
                    filter=Q(
                        ride_requests__status=RideStatus.COMPLETED,
                        ride_requests__created_at__gte=since,
                    ),
                ),
                last_ride=Max("ride_requests__created_at"),
            )
            .filter(rides__gt=0)
            .order_by("-rides", "-spent")[:limit]
        )
        return [
            {
                "id": u.id, "name": u.name or "", "phone": u.phone,
                "rides": u.rides, "spent": u.spent or Decimal("0"),
                "last_ride": u.last_ride,
            }
            for u in rows
        ]

    @classmethod
    def top_drivers(cls, days=30, limit=20):
        since = _since(days)
        drivers = (
            DriverProfile.objects.select_related("user")
            .annotate(
                completed_trips=Count("trips", filter=Q(trips__status=TripStatus.COMPLETED, trips__completed_at__gte=since)),
                earned=Sum("trips__final_fare", filter=Q(trips__status=TripStatus.COMPLETED, trips__completed_at__gte=since)),
            )
            .filter(completed_trips__gt=0)
            .order_by("-completed_trips")[:limit]
        )
        return [cls._driver_row(d, since) for d in drivers]

    @staticmethod
    def _driver_row(driver, since):
        from matching.models import InvitationStatus, RideInvitation

        cancels = CancellationRecord.objects.filter(
            driver=driver, actor="driver", created_at__gte=since,
        ).exclude(kind=CancellationKind.NO_SHOW).count()
        invitations = RideInvitation.objects.filter(driver=driver, sent_at__gte=since)
        answered = invitations.exclude(status=InvitationStatus.PENDING).count()
        accepted = invitations.filter(status=InvitationStatus.ACCEPTED).count()
        acceptance = accepted / answered if answered else None
        trips = getattr(driver, "completed_trips", 0) or 0

        return {
            "id": driver.id,
            "name": driver.user.name or "",
            "phone": driver.user.phone,
            "trips": trips,
            "earned": getattr(driver, "earned", None) or Decimal("0"),
            "rating": float(driver.rating) if driver.rating is not None else None,
            "cancellations": cancels,
            "acceptance_pct": round(acceptance * 100) if acceptance is not None else None,
            "score": Reports.behaviour_score(driver.rating, acceptance, cancels, trips),
        }

    @staticmethod
    def behaviour_score(rating, acceptance, cancellations, trips):
        """
        درجة سلوك 0–100: التقييم 50٪، قبول الدعوات 25٪، الالتزام (قلّة
        الإلغاء بعد القبول) 25٪. معلومةٌ ناقصة تُحسب محايدة لا صفرًا —
        سائقٌ جديد لا يُعاقَب لأنّه جديد.
        """
        rating_part = (float(rating) / 5.0) if rating else 0.8
        acceptance_part = acceptance if acceptance is not None else 0.8
        denominator = trips + cancellations
        commitment = 1 - (cancellations / denominator) if denominator else 1.0
        return round(50 * rating_part + 25 * acceptance_part + 25 * commitment)

    @staticmethod
    def idle_customers(days=14, limit=200):
        """ركبوا من قبل ولم يركبوا منذ `days` يومًا — أوّل من يستحقّ عرضًا."""
        User = get_user_model()
        since = _since(days)
        return list(
            User.objects.filter(role=UserRole.CUSTOMER, is_active=True)
            .annotate(
                last_ride=Max("ride_requests__created_at"),
                completed=Count("ride_requests", filter=Q(ride_requests__status=RideStatus.COMPLETED)),
            )
            .filter(completed__gt=0, last_ride__lt=since)
            .order_by("last_ride")
            .values("id", "name", "phone", "last_ride", "completed")[:limit]
        )

    @staticmethod
    def new_customers_without_ride(min_age_days=3, limit=200):
        User = get_user_model()
        return list(
            User.objects.filter(
                role=UserRole.CUSTOMER, is_active=True,
                created_at__lt=_since(min_age_days),
            )
            .annotate(requests=Count("ride_requests"))
            .filter(requests=0)
            .order_by("-created_at")
            .values("id", "name", "phone", "created_at")[:limit]
        )

    @staticmethod
    def idle_drivers(days=7, limit=200):
        """موثَّقون ولم يُنجزوا رحلة منذ `days` يومًا — يستحقّون تذكيرًا أو حافزًا."""
        since = _since(days)
        return list(
            DriverProfile.objects.filter(status=DriverProfile.DriverStatus.ACTIVE)
            .annotate(
                recent=Count("trips", filter=Q(trips__status=TripStatus.COMPLETED, trips__completed_at__gte=since)),
                last_trip=Max("trips__completed_at"),
            )
            .filter(recent=0)
            .order_by("last_trip")
            .values("id", "user__name", "user__phone", "last_trip", "last_location_at")[:limit]
        )

    # ------------------------------------------------------------------
    # للجمهور في الحملات
    # ------------------------------------------------------------------

    @classmethod
    def audience_user_ids(cls, campaign):
        from growth.models import Campaign

        A = Campaign.Audience
        User = get_user_model()
        area = campaign.area

        if campaign.audience == A.ALL_CUSTOMERS:
            qs = User.objects.filter(role=UserRole.CUSTOMER, is_active=True)
            if area is not None:
                qs = qs.filter(ride_requests__service_area=area).distinct()
            return list(qs.values_list("id", flat=True))
        if campaign.audience == A.IDLE_CUSTOMERS:
            return [row["id"] for row in cls.idle_customers(campaign.idle_days, limit=100000)]
        if campaign.audience == A.NEW_CUSTOMERS:
            return [row["id"] for row in cls.new_customers_without_ride(limit=100000)]
        if campaign.audience == A.TOP_CUSTOMERS:
            return [row["id"] for row in cls.top_customers(30, limit=campaign.top_count)]

        drivers = DriverProfile.objects.filter(status=DriverProfile.DriverStatus.ACTIVE)
        if area is not None:
            drivers = drivers.filter(home_service_area=area)
        if campaign.audience == A.ALL_DRIVERS:
            return list(drivers.values_list("user_id", flat=True))
        if campaign.audience == A.IDLE_DRIVERS:
            ids = {row["id"] for row in cls.idle_drivers(campaign.idle_days, limit=100000)}
            return list(drivers.filter(id__in=ids).values_list("user_id", flat=True))
        if campaign.audience == A.TOP_DRIVERS:
            ids = [row["id"] for row in cls.top_drivers(30, limit=campaign.top_count)]
            return list(DriverProfile.objects.filter(id__in=ids).values_list("user_id", flat=True))
        if campaign.audience == A.DRIVER_GROUP and campaign.group_id:
            return list(campaign.group.drivers.values_list("user_id", flat=True))
        return []
