"""
RatingService — تقييم الطرفين.

ثلاثة قرارات تحكم هذا الملف:

1. الحجب المتبادل: لا يرى طرف تقييم الآخر حتى يقيّم هو أيضًا أو تنتهي
   المهلة. بلا هذا يصبح التقييم ردّ فعل لا حكمًا.

2. إعادة الحساب لا الزيادة التدريجية: المتوسط يُحسب من الصفوف في كل مرة.
   نفس مبدأ عدّاد الركّاب في المرحلة 8ب - الحساب التدريجي يحمل خطأه أبدًا.

3. التقييم للرحلات المكتملة فقط. الرحلة الملغاة نزاع لا تجربة، وبابها
   الشكوى لا النجوم.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from feedback.models import (
    Rating,
    RatingDirection,
    RatingSummary,
    RatingTag,
)
from trips.models import Trip, TripStatus


class RatingError(Exception):
    pass


# مهلة التقييم. بعدها يُكشف تقييم الطرف الآخر ويُقفل باب التقييم:
# تقييم يصل بعد شهر لا يقيس تجربة بل مزاجًا.
RATING_WINDOW_DAYS = getattr(settings, "RATING_WINDOW_DAYS", 14)

MIN_SCORE = 1
MAX_SCORE = 5

# تعليق إلزامي مع التقييم المنخفض: نجمة واحدة بلا سبب لا تُصلح شيئًا
# ولا تُستعمل في أي قرار.
COMMENT_REQUIRED_BELOW = getattr(settings, "RATING_COMMENT_REQUIRED_BELOW", 3)


class RatingService:

    # =================================================================
    # الكتابة
    # =================================================================

    @classmethod
    @transaction.atomic
    def submit(cls, ride_id, rater, score, tags=None, comment=""):
        trip = (
            Trip.objects
            .select_for_update()
            .select_related("driver", "driver__user", "customer", "ride")
            .filter(ride_id=ride_id)
            .first()
        )

        if trip is None:
            raise RatingError("لا توجد رحلة بهذا الرقم.")

        direction = cls._direction_for(trip, rater)

        if direction is None:
            raise RatingError("هذه الرحلة ليست لك.")

        if trip.status != TripStatus.COMPLETED:
            raise RatingError(
                "لا يمكن تقييم رحلة لم تكتمل. إن كانت لديك مشكلة فافتح شكوى."
            )

        if cls.window_closed(trip):
            raise RatingError(
                f"انتهت مهلة التقييم ({RATING_WINDOW_DAYS} يومًا)."
            )

        score = cls._validate_score(score)
        tags = cls._validate_tags(trip, direction, score, tags)

        comment = (comment or "").strip()

        if score < COMMENT_REQUIRED_BELOW and not comment and not tags:
            raise RatingError(
                "تقييم منخفض يحتاج سببًا: اختر وسمًا أو اكتب تعليقًا."
            )

        if Rating.objects.filter(trip=trip, direction=direction).exists():
            raise RatingError("قيّمتَ هذه الرحلة من قبل.")

        rating = Rating.objects.create(
            trip=trip,
            direction=direction,
            driver=trip.driver,
            customer=trip.customer,
            rater=rater,
            score=score,
            tags=tags,
            comment=comment[:2000],
        )

        # التجميع بعد الـcommit: فشله لا يجوز أن يُلغي تقييمًا صحيحًا،
        # والمزامنة التالية تصحّحه على أي حال.
        subject_driver_id = trip.driver_id if direction == RatingDirection.CUSTOMER_TO_DRIVER else None
        subject_customer_id = trip.customer_id if direction == RatingDirection.DRIVER_TO_CUSTOMER else None

        transaction.on_commit(
            lambda: cls.recalculate(
                driver_id=subject_driver_id, customer_id=subject_customer_id
            )
        )

        cls._publish(trip, rating)

        return rating

    # =================================================================
    # القراءة
    # =================================================================

    @classmethod
    def for_trip(cls, trip, viewer):
        """
        يرجّع {"mine": ..., "theirs": ..., "theirs_visible": bool}.

        theirs يبقى None حتى ينكشف - وهذا هو الحجب المتبادل عمليًا: لا
        نرسل التقييم ونترك للتطبيق إخفاءه، بل لا نرسله أصلًا.
        """
        direction = cls._direction_for(trip, viewer)

        if direction is None:
            raise RatingError("هذه الرحلة ليست لك.")

        other = cls._opposite(direction)

        ratings = {
            r.direction: r
            for r in Rating.objects.filter(trip=trip)
        }

        mine = ratings.get(direction)
        theirs = ratings.get(other)

        visible = bool(mine) or cls.window_closed(trip)

        return {
            "direction": direction,
            "mine": mine,
            "theirs": theirs if (visible and theirs) else None,
            "theirs_visible": visible,
            "can_rate": (
                mine is None
                and trip.status == TripStatus.COMPLETED
                and not cls.window_closed(trip)
            ),
        }

    @classmethod
    def available_tags(cls, direction, score=None, service_area=None):
        queryset = RatingTag.objects.filter(active=True, direction=direction)

        if service_area is not None:
            queryset = queryset.filter(
                Q(service_area__isnull=True) | Q(service_area=service_area)
            )
        else:
            queryset = queryset.filter(service_area__isnull=True)

        if score is not None:
            queryset = queryset.filter(min_score__lte=score, max_score__gte=score)

        return queryset

    # =================================================================
    # التجميع
    # =================================================================

    @classmethod
    def recalculate(cls, driver_id=None, customer_id=None):
        if driver_id is None and customer_id is None:
            return None

        if driver_id is not None:
            direction = RatingDirection.CUSTOMER_TO_DRIVER
            filters = {"driver_id": driver_id}
            lookup = {"driver_id": driver_id}
        else:
            direction = RatingDirection.DRIVER_TO_CUSTOMER
            filters = {"customer_id": customer_id}
            lookup = {"customer_id": customer_id}

        stats = (
            Rating.objects
            .filter(direction=direction, **filters)
            .aggregate(
                average=Avg("score"),
                count=Count("id"),
                one=Count("id", filter=Q(score=1)),
                two=Count("id", filter=Q(score=2)),
                three=Count("id", filter=Q(score=3)),
                four=Count("id", filter=Q(score=4)),
                five=Count("id", filter=Q(score=5)),
            )
        )

        average = stats["average"]
        average = Decimal(str(round(average, 2))) if average is not None else None

        with transaction.atomic():
            summary, _created = RatingSummary.objects.get_or_create(**lookup)

            summary.average = average
            summary.count = stats["count"] or 0
            summary.one_star = stats["one"] or 0
            summary.two_star = stats["two"] or 0
            summary.three_star = stats["three"] or 0
            summary.four_star = stats["four"] or 0
            summary.five_star = stats["five"] or 0
            summary.save()

            # المرآة: DriverProfile.rating يُقرأ منذ المرحلة 6 في الخريطة
            # الحيّة وnearby-vehicles. كان يعرض قيمة لا مصدر لها؛ الآن له
            # مصدر واحد، ونكتبه هنا حتى لا نضطر لتعديل كل قارئ.
            if driver_id is not None:
                from users.models import DriverProfile

                DriverProfile.objects.filter(id=driver_id).update(rating=average)

        return summary

    @classmethod
    def get_summary(cls, driver_id=None, customer_id=None):
        lookup = (
            {"driver_id": driver_id} if driver_id is not None
            else {"customer_id": customer_id}
        )
        return RatingSummary.objects.filter(**lookup).first()

    # =================================================================
    # HELPERS
    # =================================================================

    @staticmethod
    def window_closed(trip):
        if trip.completed_at is None:
            return False

        deadline = trip.completed_at + timedelta(days=RATING_WINDOW_DAYS)
        return timezone.now() > deadline

    @staticmethod
    def _opposite(direction):
        return (
            RatingDirection.DRIVER_TO_CUSTOMER
            if direction == RatingDirection.CUSTOMER_TO_DRIVER
            else RatingDirection.CUSTOMER_TO_DRIVER
        )

    @staticmethod
    def _direction_for(trip, user):
        """مَن هذا المستخدم بالنسبة لهذه الرحلة؟ None يعني: ليس طرفًا فيها."""
        if user is None:
            return None

        if trip.customer_id == user.id:
            return RatingDirection.CUSTOMER_TO_DRIVER

        driver_profile = getattr(user, "driver_profile", None)

        if driver_profile is not None and trip.driver_id == driver_profile.id:
            return RatingDirection.DRIVER_TO_CUSTOMER

        return None

    @staticmethod
    def _validate_score(score):
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise RatingError("التقييم يجب أن يكون رقمًا.")

        if not (MIN_SCORE <= score <= MAX_SCORE):
            raise RatingError(f"التقييم من {MIN_SCORE} إلى {MAX_SCORE}.")

        return score

    @classmethod
    def _validate_tags(cls, trip, direction, score, tags):
        """
        وسم لا يناسب الدرجة يُرفض لا يُتجاهَل. تمريره صامتًا يعني إحصاءات
        تقول إن سائقًا حصل على "قيادة آمنة" مع نجمة واحدة.
        """
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

        if not tags:
            return []

        area = getattr(trip.ride, "service_area", None)

        allowed = set(
            cls.available_tags(direction, score=score, service_area=area)
            .values_list("code", flat=True)
        )

        unknown = [t for t in tags if t not in allowed]

        if unknown:
            raise RatingError(
                f"وسوم غير صالحة لهذا التقييم: {', '.join(unknown)}"
            )

        return tags

    @staticmethod
    def _publish(trip, rating):
        from realtime.events import EventBus

        ride_id = trip.ride_id
        payload = {
            "ride_id": ride_id,
            "direction": rating.direction,
            "submitted": True,
        }

        # الحمولة لا تحمل الدرجة عمدًا: غرفة الرحلة يدخلها الطرفان، وبثّ
        # الرقم فيها ينقض الحجب المتبادل من الباب الخلفي.
        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="rating.submitted",
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
        )
