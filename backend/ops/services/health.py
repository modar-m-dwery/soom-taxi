"""
OpsHealthService — ما الذي يجري الآن، وما الذي يحتاج إنسانًا.

الفرق بين السؤالين هو الفرق بين لوحة معلومات ولوحة تشغيل.

لوحة المعلومات تعرض كل شيء وتترك للمشغّل أن يبحث. ولوحة التشغيل تعرض
**ما هو خطأ**: رحلة عالقة، سائق مشغول بلا رحلة، شكوى حرجة لم يلمسها أحد،
إشعار فشل. المشغّل لا يملك وقتًا ليقرأ الأرقام السليمة.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from presence.constants import PresenceState
from presence.services import PresenceService
from users.models import DriverProfile


# رحلة لم تتحرك منذ هذا الوقت وهي في حالة انتقالية = شيء علق
STUCK_TRIP_MINUTES = 45

# طلب يبحث منذ هذا الوقت بلا نتيجة = المنطقة بلا سائقين أو المطابقة معطوبة
STALE_SEARCH_MINUTES = 10

ACTIVE_TRIP_STATUSES = None  # يُملأ كسولًا من trips.models


def _active_trip_statuses():
    from trips.models import TripStatus

    return [
        TripStatus.CREATED,
        TripStatus.DRIVER_ARRIVING,
        TripStatus.DRIVER_ARRIVED,
        TripStatus.IN_PROGRESS,
    ]


class OpsHealthService:

    # =================================================================
    # نظرة عامة
    # =================================================================

    @classmethod
    def overview(cls):
        from feedback.models import Complaint, ComplaintStatus
        from matching.models import InvitationStatus, OfferStatus, RideInvitation, RideOffer
        from rides.models import RideRequest, RideStatus
        from trips.models import Trip, TripStatus

        now = timezone.now()
        today = now - timedelta(hours=24)

        presence = cls.presence_breakdown()

        trips = Trip.objects.aggregate(
            active=Count("id", filter=Q(status__in=_active_trip_statuses())),
            completed_today=Count(
                "id",
                filter=Q(status=TripStatus.COMPLETED, completed_at__gte=today),
            ),
            cancelled_today=Count(
                "id",
                filter=Q(status=TripStatus.CANCELLED, cancelled_at__gte=today),
            ),
            needs_review=Count("id", filter=Q(needs_review=True)),
        )

        rides = RideRequest.objects.aggregate(
            searching=Count(
                "id",
                filter=Q(
                    status__in=[RideStatus.SEARCHING, RideStatus.OFFERS_RECEIVED]
                ),
            ),
            created_today=Count("id", filter=Q(created_at__gte=today)),
        )

        complaints = Complaint.objects.aggregate(
            open=Count(
                "id",
                filter=Q(
                    status__in=[ComplaintStatus.OPEN, ComplaintStatus.IN_REVIEW]
                ),
            ),
            critical=Count(
                "id",
                filter=Q(
                    severity="critical",
                    status__in=[ComplaintStatus.OPEN, ComplaintStatus.IN_REVIEW],
                ),
            ),
        )

        return {
            "at": now.isoformat(),
            "drivers": presence,
            "trips": trips,
            "rides": rides,
            "complaints": complaints,
            "pending_offers": RideOffer.objects.filter(
                status=OfferStatus.PENDING, expires_at__gt=now
            ).count(),
            "pending_invitations": RideInvitation.objects.filter(
                status=InvitationStatus.PENDING, expires_at__gt=now
            ).count(),
        }

    @classmethod
    def presence_breakdown(cls):
        """
        توزيع حالات السائقين كما يراها محرّك الحضور لا كما تقول القاعدة.

        الفرق مقصود: القاعدة تقول `online=True` لسائق أغلق التطبيق قبل
        دقيقتين، ومحرّك الحضور يعرف أن نبضته انقطعت. الرقم الذي يهمّ
        المشغّل هو الثاني.
        """
        driver_ids = list(
            DriverProfile.objects
            .filter(status=DriverProfile.DriverStatus.ACTIVE)
            .values_list("id", flat=True)
        )

        counts = {
            PresenceState.PRESENT: 0,
            PresenceState.SHARING: 0,
            PresenceState.BUSY: 0,
            PresenceState.STALE: 0,
            PresenceState.UNAVAILABLE: 0,
            PresenceState.OFFLINE: 0,
        }

        if not driver_ids:
            return {**counts, "total_active_accounts": 0}

        snapshots = PresenceService.get_snapshots_bulk(driver_ids)
        now_ts = timezone.now().timestamp()

        for driver_id in driver_ids:
            state = PresenceService._resolve_state_from_snapshot(
                snapshots.get(driver_id) or {}, now=now_ts
            )
            counts[state] = counts.get(state, 0) + 1

        return {**counts, "total_active_accounts": len(driver_ids)}

    # =================================================================
    # ما يحتاج إنسانًا
    # =================================================================

    @classmethod
    def attention(cls):
        return {
            "stuck_trips": cls.stuck_trips(),
            "ghost_busy_drivers": cls.ghost_busy_drivers(),
            "trips_needing_review": cls.trips_needing_review(),
            "urgent_complaints": cls.urgent_complaints(),
            "stale_searches": cls.stale_searches(),
            "failed_notifications": cls.failed_notifications(),
            "pending_driver_verifications": cls.pending_verifications(),
        }

    @classmethod
    def stuck_trips(cls, limit=50):
        """رحلة في حالة انتقالية منذ ٤٥ دقيقة: السائق نسي، أو التطبيق سقط."""
        from trips.models import Trip

        cutoff = timezone.now() - timedelta(minutes=STUCK_TRIP_MINUTES)

        trips = (
            Trip.objects
            .filter(status__in=_active_trip_statuses(), updated_at__lt=cutoff)
            .select_related("driver", "driver__user", "customer", "ride")
            .order_by("updated_at")[:limit]
        )

        return [
            {
                "trip_id": trip.id,
                "ride_id": trip.ride_id,
                "status": trip.status,
                "driver_id": trip.driver_id,
                "driver_phone": trip.driver.user.phone,
                "customer_phone": trip.customer.phone,
                "stuck_minutes": int(
                    (timezone.now() - trip.updated_at).total_seconds() / 60
                ),
            }
            for trip in trips
        ]

    @classmethod
    def ghost_busy_drivers(cls, limit=50):
        """
        سائق يقول محرّك الحضور إنه BUSY ولا رحلة نشطة له في القاعدة.

        هذه أهمّ فحوص اللوحة كلها: هي الحالة التي تُخفي سائقًا عن الخريطة
        إلى الأبد بلا أن يشتكي أحد — الزبون لا يعرف أنه موجود، والسائق
        يظنّ أن الطلبات قليلة اليوم. كانت مستحيلة الاكتشاف قبل هذه اللوحة.
        """
        from trips.models import Trip

        active_driver_ids = set(
            Trip.objects
            .filter(status__in=_active_trip_statuses())
            .values_list("driver_id", flat=True)
        )

        driver_ids = list(
            DriverProfile.objects
            .filter(status=DriverProfile.DriverStatus.ACTIVE)
            .values_list("id", flat=True)
        )

        if not driver_ids:
            return []

        snapshots = PresenceService.get_snapshots_bulk(driver_ids)
        now_ts = timezone.now().timestamp()

        ghosts = []

        for driver_id in driver_ids:
            if driver_id in active_driver_ids:
                continue

            state = PresenceService._resolve_state_from_snapshot(
                snapshots.get(driver_id) or {}, now=now_ts
            )

            if state in (PresenceState.BUSY, PresenceState.SHARING):
                ghosts.append({
                    "driver_id": driver_id,
                    "presence_state": state,
                    "reason": "لا رحلة نشطة في القاعدة",
                })

            if len(ghosts) >= limit:
                break

        return ghosts

    @classmethod
    def trips_needing_review(cls, limit=50):
        from trips.models import Trip

        trips = (
            Trip.objects
            .filter(needs_review=True)
            .select_related("driver", "customer")
            .order_by("-completed_at")[:limit]
        )

        return [
            {
                "trip_id": trip.id,
                "ride_id": trip.ride_id,
                "reason": trip.review_reason,
                "final_fare": str(trip.final_fare),
                "completed_at": (
                    trip.completed_at.isoformat() if trip.completed_at else None
                ),
            }
            for trip in trips
        ]

    @classmethod
    def urgent_complaints(cls, limit=50):
        from feedback.models import Complaint, ComplaintSeverity, ComplaintStatus

        complaints = (
            Complaint.objects
            .filter(
                status__in=[ComplaintStatus.OPEN, ComplaintStatus.IN_REVIEW],
                severity__in=[ComplaintSeverity.HIGH, ComplaintSeverity.CRITICAL],
            )
            .select_related("complainant")
            .order_by("-severity", "created_at")[:limit]
        )

        return [
            {
                "complaint_id": c.id,
                "category": c.category,
                "severity": c.severity,
                "status": c.status,
                "age_hours": int(
                    (timezone.now() - c.created_at).total_seconds() / 3600
                ),
                "complainant_phone": c.complainant.phone,
                "ride_id": c.trip.ride_id if c.trip_id else None,
            }
            for c in complaints
        ]

    @classmethod
    def stale_searches(cls, limit=50):
        from rides.models import RideRequest, RideStatus

        cutoff = timezone.now() - timedelta(minutes=STALE_SEARCH_MINUTES)

        rides = (
            RideRequest.objects
            .filter(
                status__in=[RideStatus.SEARCHING, RideStatus.OFFERS_RECEIVED],
                created_at__lt=cutoff,
            )
            .select_related("customer", "service_area")
            .order_by("created_at")[:limit]
        )

        return [
            {
                "ride_id": ride.id,
                "status": ride.status,
                "mode": ride.mode,
                "area": getattr(ride.service_area, "name", None),
                "waiting_minutes": int(
                    (timezone.now() - ride.created_at).total_seconds() / 60
                ),
                "customer_phone": ride.customer.phone,
            }
            for ride in rides
        ]

    @classmethod
    def failed_notifications(cls, limit=20):
        try:
            from notifications.models import Notification, NotificationStatus
        except Exception:
            return []

        cutoff = timezone.now() - timedelta(days=1)

        rows = (
            Notification.objects
            .filter(status=NotificationStatus.FAILED, created_at__gte=cutoff)
            .order_by("-created_at")[:limit]
        )

        return [
            {
                "notification_id": n.id,
                "event_type": n.event_type,
                "user_id": n.user_id,
                "error": n.last_error,
                "attempts": n.attempts,
            }
            for n in rows
        ]

    @classmethod
    def pending_verifications(cls, limit=50):
        drivers = (
            DriverProfile.objects
            .filter(status=DriverProfile.DriverStatus.PENDING)
            .select_related("user")
            .prefetch_related("vehicles")
            .order_by("id")[:limit]
        )

        return [
            {
                "driver_id": d.id,
                "phone": d.user.phone,
                "name": d.user.name,
                "vehicles": [
                    {"id": v.id, "type": v.type_id, "plate": getattr(v, "plate_number", ""),
                     "seats": v.seats, "active": v.active}
                    for v in d.vehicles.all()
                ],
            }
            for d in drivers
        ]

    # =================================================================
    # الخريطة الحيّة للإدارة
    # =================================================================

    @classmethod
    def live_drivers(cls, limit=200):
        """
        كل السائقين الظاهرين الآن، بإحداثيات **دقيقة**.

        هنا وحدها لا نُقرّب: تقريب الـ110م بُني ليمنع الزبون من تتبّع
        سائق قبل القبول، ولا معنى له أمام مشغّل يحتاج أن يعرف أين السيارة
        فعلًا حين يتصل به سائق تائه. الفرق أن هذا المسار محميّ بصلاحية
        إدارية وكل دخول إليه معروف صاحبه.
        """
        driver_ids = list(
            DriverProfile.objects
            .filter(status=DriverProfile.DriverStatus.ACTIVE)
            .values_list("id", flat=True)[:limit]
        )

        if not driver_ids:
            return []

        snapshots = PresenceService.get_snapshots_bulk(driver_ids)
        drivers = {
            d.id: d
            for d in DriverProfile.objects.filter(id__in=driver_ids).select_related("user")
        }
        now_ts = timezone.now().timestamp()

        rows = []

        for driver_id in driver_ids:
            data = snapshots.get(driver_id) or {}
            state = PresenceService._resolve_state_from_snapshot(data, now=now_ts)

            if state == PresenceState.OFFLINE:
                continue

            driver = drivers.get(driver_id)

            rows.append({
                "driver_id": driver_id,
                "phone": driver.user.phone if driver else None,
                "name": driver.user.name if driver else None,
                "state": state,
                "lng": float(data["lng"]) if data.get("lng") else None,
                "lat": float(data["lat"]) if data.get("lat") else None,
                "heading": data.get("heading") or None,
                "free_seats": PresenceService.get_remaining_seats(
                    driver_id, snapshot=data
                ),
                "trip_mode": data.get("trip_mode") or None,
                "cell": data.get("cell_id") or None,
            })

        return rows
