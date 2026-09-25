"""
ComplaintService — الشكاوى وتجميد أدلّتها.

الفكرة الحاكمة: الشكوى تُنشئ نسخة مجمّدة من الوقائع لحظة فتحها.

السبب اصطدام مباشر بين شيئين بنيناهما بأنفسنا: cleanup_old_trip_locations
تحذف نقاط المسار بعد ثلاثين يومًا (وهذا صحيح - لا يجوز أن يبقى تتبّع
الناس إلى الأبد)، بينما الشكوى قد تُفتح في اليوم التاسع والعشرين وتُراجَع
بعد أسبوع. بلا التجميد نكون بنينا نظام أدلّة يحذف أدلّته.

ما يُجمَّد ليس المسار كاملًا - ذلك يعيد المشكلة نفسها - بل خلاصته:
الأرقام والأختام الزمنية ونتائج التحقق الجغرافي. وهي ما يُحسم به النزاع
عمليًا: هل بدأت الرحلة؟ كم استغرقت؟ هل كان السائق عند نقطة الالتقاء فعلًا؟
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from feedback.models import (
    Complaint,
    ComplaintCategory,
    ComplaintSeverity,
    ComplaintStatus,
)
from trips.models import Trip


class ComplaintError(Exception):
    pass


# فئات ترفع الخطورة تلقائيًا. السلامة لا تنتظر دورها في الطابور.
CRITICAL_CATEGORIES = {ComplaintCategory.SAFETY}
HIGH_CATEGORIES = {ComplaintCategory.BEHAVIOR, ComplaintCategory.NO_SHOW}

# مهلة فتح شكوى بعد الرحلة
COMPLAINT_WINDOW_DAYS = getattr(settings, "COMPLAINT_WINDOW_DAYS", 30)

# شكوى مفتوحة أطول من هذا تُصعَّد
COMPLAINT_ESCALATE_AFTER_HOURS = getattr(
    settings, "COMPLAINT_ESCALATE_AFTER_HOURS", 48
)


class ComplaintService:

    # =================================================================

    @classmethod
    @transaction.atomic
    def open(cls, ride_id, complainant, category, description):
        trip = (
            Trip.objects
            .select_related("ride", "driver", "customer", "completion_record")
            .filter(ride_id=ride_id)
            .first()
        )

        if trip is None:
            raise ComplaintError("لا توجد رحلة بهذا الرقم.")

        role = cls._role_of(trip, complainant)

        if role is None:
            raise ComplaintError("هذه الرحلة ليست لك.")

        if category not in ComplaintCategory.values:
            raise ComplaintError("فئة الشكوى غير معروفة.")

        description = (description or "").strip()

        if len(description) < 10:
            raise ComplaintError("اشرح المشكلة في عشرة أحرف على الأقل.")

        cls._check_window(trip)
        cls._check_duplicate(trip, complainant, category)

        # الرحلة الملغاة يجوز الاشتكاء منها - بل هي من أكثر ما يُشتكى منه.
        # لذلك لا فحص على الحالة هنا، بخلاف التقييم.

        if role == "customer":
            against_driver, against_customer = trip.driver, None
        else:
            against_driver, against_customer = None, trip.customer

        complaint = Complaint.objects.create(
            trip=trip,
            complainant=complainant,
            against_driver=against_driver,
            against_customer=against_customer,
            category=category,
            severity=cls._severity_for(trip, category),
            status=ComplaintStatus.OPEN,
            description=description[:5000],
            evidence=cls.freeze_evidence(trip),
        )

        cls._publish(complaint)

        return complaint

    # =================================================================
    # تجميد الأدلّة
    # =================================================================

    @classmethod
    def freeze_evidence(cls, trip):
        record = getattr(trip, "completion_record", None)
        ride = trip.ride

        evidence = {
            "frozen_at": timezone.now().isoformat(),
            "trip_id": trip.id,
            "ride_id": trip.ride_id,
            "trip_status": trip.status,
            "mode": getattr(ride, "mode", None),
            "timeline": {
                "created_at": cls._stamp(trip.created_at),
                "arriving_at": cls._stamp(trip.arriving_at),
                "arrived_at": cls._stamp(trip.arrived_at),
                "started_at": cls._stamp(trip.started_at),
                "completed_at": cls._stamp(trip.completed_at),
                "cancelled_at": cls._stamp(trip.cancelled_at),
            },
            "measurements": {
                "distance_m": trip.distance_m,
                "duration_s": trip.duration_s,
                "gps_points_count": trip.gps_points_count,
            },
            "verification": {
                "pickup_verified": trip.pickup_verified,
                "dropoff_verified": trip.dropoff_verified,
                "needs_review": trip.needs_review,
                "review_reason": trip.review_reason,
            },
            "money": {
                "final_fare": str(trip.final_fare),
                "currency": trip.currency,
                "quoted_gross_fare": str(getattr(ride, "gross_fare", "") or ""),
                "pricing_policy": getattr(ride, "pricing_policy", None),
            },
            "cancellation": {
                "cancelled_by": trip.cancelled_by or None,
                "reason": trip.cancel_reason or None,
            },
            "completion_record_id": record.id if record else None,
        }

        # حدود المسار فقط لا نقاطه: تكفي للتحقق من أن الرحلة جرت حيث تقول،
        # ولا تُنشئ نسخة ثانية من سجلّ التتبّع تُفلت من سياسة الاحتفاظ.
        first = trip.locations.order_by("timestamp").first()
        last = trip.locations.order_by("-timestamp").first()

        if first is not None and last is not None:
            evidence["path_bounds"] = {
                "first": cls._point(first),
                "last": cls._point(last),
            }

        return evidence

    # =================================================================
    # المعالجة الإدارية
    # =================================================================

    @classmethod
    @transaction.atomic
    def set_status(cls, complaint_id, status, actor, note=""):
        if status not in ComplaintStatus.values:
            raise ComplaintError("حالة غير معروفة.")

        complaint = (
            Complaint.objects
            .select_for_update()
            .filter(id=complaint_id)
            .first()
        )

        if complaint is None:
            raise ComplaintError("الشكوى غير موجودة.")

        if complaint.status in (ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED):
            raise ComplaintError("الشكوى مغلقة بالفعل.")

        complaint.status = status
        complaint.resolution_note = (note or "")[:5000]

        if status in (ComplaintStatus.RESOLVED, ComplaintStatus.REJECTED):
            if not complaint.resolution_note:
                raise ComplaintError(
                    "الإغلاق يحتاج سببًا مكتوبًا - الشكوى تُغلَق بقرار لا بصمت."
                )
            complaint.resolved_by = actor
            complaint.resolved_at = timezone.now()

        complaint.save(
            update_fields=[
                "status", "resolution_note", "resolved_by",
                "resolved_at", "updated_at",
            ]
        )

        cls._publish(complaint, event_type="complaint.updated")

        return complaint

    @classmethod
    def escalate_stale(cls):
        """
        يُستدعى من Celery beat. شكوى مفتوحة بلا حراك ليست شكوى مُدارة.
        """
        cutoff = timezone.now() - timedelta(hours=COMPLAINT_ESCALATE_AFTER_HOURS)

        stale = Complaint.objects.filter(
            status=ComplaintStatus.OPEN,
            created_at__lte=cutoff,
            escalated_at__isnull=True,
        ).exclude(severity=ComplaintSeverity.CRITICAL)

        escalated = []

        for complaint in stale:
            complaint.severity = (
                ComplaintSeverity.CRITICAL
                if complaint.severity == ComplaintSeverity.HIGH
                else ComplaintSeverity.HIGH
            )
            complaint.escalated_at = timezone.now()
            complaint.save(update_fields=["severity", "escalated_at", "updated_at"])
            escalated.append(complaint.id)

        return escalated

    # =================================================================
    # HELPERS
    # =================================================================

    @staticmethod
    def _stamp(value):
        return value.isoformat() if value else None

    @staticmethod
    def _point(location):
        return {
            "lng": location.location.x,
            "lat": location.location.y,
            "at": location.timestamp.isoformat(),
        }

    @staticmethod
    def _role_of(trip, user):
        if user is None:
            return None

        if trip.customer_id == user.id:
            return "customer"

        driver_profile = getattr(user, "driver_profile", None)

        if driver_profile is not None and trip.driver_id == driver_profile.id:
            return "driver"

        return None

    @staticmethod
    def _severity_for(trip, category):
        if category in CRITICAL_CATEGORIES:
            return ComplaintSeverity.CRITICAL

        # الرحلة المعلَّمة للمراجعة أصلًا تبدأ شكواها درجة أعلى: النظام
        # كان قد شكّ فيها قبل أن يشتكي أحد.
        if trip.needs_review:
            return ComplaintSeverity.HIGH

        if category in HIGH_CATEGORIES:
            return ComplaintSeverity.HIGH

        return ComplaintSeverity.NORMAL

    @staticmethod
    def _check_window(trip):
        reference = trip.completed_at or trip.cancelled_at or trip.created_at

        if reference is None:
            return

        if timezone.now() > reference + timedelta(days=COMPLAINT_WINDOW_DAYS):
            raise ComplaintError(
                f"انتهت مهلة الشكوى ({COMPLAINT_WINDOW_DAYS} يومًا)."
            )

    @staticmethod
    def _check_duplicate(trip, complainant, category):
        exists = Complaint.objects.filter(
            trip=trip,
            complainant=complainant,
            category=category,
            status__in=[ComplaintStatus.OPEN, ComplaintStatus.IN_REVIEW],
        ).exists()

        if exists:
            raise ComplaintError(
                "لديك شكوى مفتوحة من الفئة نفسها على هذه الرحلة."
            )

    @staticmethod
    def _publish(complaint, event_type="complaint.opened"):
        from realtime.events import EventBus

        complaint_id = complaint.id
        ride_id = complaint.trip.ride_id if complaint.trip_id else None
        payload = {
            "complaint_id": complaint_id,
            "ride_id": ride_id,
            "category": complaint.category,
            "severity": complaint.severity,
            "status": complaint.status,
        }

        if ride_id is None:
            return

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type=event_type,
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
        )
