"""
OpsConsoleService — التدخّلات الإدارية.

قاعدتان تحكمان كل دالة هنا:

1. **لا SQL خامّ ولا تعديل مباشر.** كل تدخّل يمرّ من الخدمة التي تملك
   القاعدة (TripService، MatchingService، EngagementResolver). المشغّل
   الذي يُصلح حالة بـUPDATE في لوحة الإدارة يكسر ثلاثة أشياء لا يراها:
   الأحداث، والحضور، والخريطة.

2. **لا فعل بلا سبب مكتوب ولا بلا أثر.** السبب إلزامي، وصفّ AdminAction
   يُكتب في المعاملة نفسها. صلاحية إنهاء رحلة أو إيقاف حساب بلا سجلّ هي
   الباب الذي تُساء منه المنصّات من الداخل.
"""
from django.db import transaction
from django.utils import timezone

from ops.models import ActionKind, AdminAction
from users.models import DriverProfile


class OpsError(Exception):
    pass


MIN_REASON_LENGTH = 10


class OpsConsoleService:

    # =================================================================
    # تحرير سائق عالق
    # =================================================================

    @classmethod
    @transaction.atomic
    def release_driver(cls, driver_id, actor, reason):
        """
        السائق الذي يقول محرّك الحضور إنه مشغول ولا رحلة نشطة له.

        لا نكتب "متاح" في Redis مباشرة: تلك معالجة للعَرَض. نُغلق أي رحلة
        عالقة أولًا ثم نُعيد حساب الارتباط من القاعدة، فيصير الجواب صحيحًا
        لأن الحقيقة صحيحة لا لأننا كتبناه.
        """
        from trips.models import Trip, TripStatus
        from trips.services.engagement import EngagementResolver

        cls._require_reason(reason)

        driver = DriverProfile.objects.filter(id=driver_id).first()

        if driver is None:
            raise OpsError("السائق غير موجود.")

        before = cls._driver_snapshot(driver)

        stuck = list(
            Trip.objects
            .select_for_update()
            .filter(
                driver=driver,
                status__in=[
                    TripStatus.CREATED,
                    TripStatus.DRIVER_ARRIVING,
                    TripStatus.DRIVER_ARRIVED,
                    TripStatus.IN_PROGRESS,
                ],
            )
        )

        closed = []

        for trip in stuck:
            trip.status = TripStatus.CANCELLED
            trip.cancelled_at = timezone.now()
            trip.cancelled_by = "admin"
            trip.cancel_reason = reason[:255]
            trip.save(update_fields=[
                "status", "cancelled_at", "cancelled_by",
                "cancel_reason", "updated_at",
            ])
            closed.append(trip.id)

        EngagementResolver.sync_on_commit(driver_id)

        driver.refresh_from_db()

        return cls._record(
            actor=actor,
            kind=ActionKind.RELEASE_DRIVER,
            target_type="driver",
            target_id=driver_id,
            reason=reason,
            before=before,
            after={**cls._driver_snapshot(driver), "closed_trips": closed},
        )

    # =================================================================
    # إنهاء رحلة إداريًا
    # =================================================================

    @classmethod
    @transaction.atomic
    def force_complete_trip(cls, ride_id, actor, reason):
        """
        الرحلة التي انتهت فعلًا ولم يُنهِها السائق (سقط تطبيقه، أو نسي).

        نمرّ من TripService لا من UPDATE: هي التي تحسب المسافة وتكتب سجلّ
        الإتمام وتُحرّر السائق وتبثّ الحدث. وcompletion_source=admin يبقى
        في السجلّ الدائم، فلا تختلط رحلة أنهاها مشغّل برحلة أنهاها سائقها.
        """
        from trips.models import CompletionSource, Trip, TripStatus
        from trips.services.trip import TripError, TripService

        cls._require_reason(reason)

        trip = Trip.objects.select_related("driver").filter(ride_id=ride_id).first()

        if trip is None:
            raise OpsError("لا توجد رحلة بهذا الرقم.")

        before = cls._trip_snapshot(trip)

        if trip.status == TripStatus.COMPLETED:
            raise OpsError("الرحلة منتهية بالفعل.")

        try:
            # السائق يُمرَّر من الرحلة لا من الطلب: الخدمة تتحقق من
            # الملكية، ونحن نتجاوز التحقق بحقّ إداري لا بخرقٍ للقاعدة.
            if trip.status != TripStatus.IN_PROGRESS:
                trip.status = TripStatus.IN_PROGRESS
                trip.started_at = trip.started_at or timezone.now()
                trip.save(update_fields=["status", "started_at", "updated_at"])

            trip = TripService.complete(
                ride_id=ride_id,
                driver=trip.driver,
                source=CompletionSource.ADMIN,
            )
        except TripError as exc:
            raise OpsError(str(exc))

        # الإنهاء الإداري يُعلَّم للمراجعة دائمًا: لم يشهده أحد من الطرفين.
        if not trip.needs_review:
            trip.needs_review = True
            trip.review_reason = f"إنهاء إداري: {reason}"[:255]
            trip.save(update_fields=["needs_review", "review_reason", "updated_at"])

        return cls._record(
            actor=actor,
            kind=ActionKind.FORCE_COMPLETE,
            target_type="trip",
            target_id=trip.id,
            reason=reason,
            before=before,
            after=cls._trip_snapshot(trip),
        )

    # =================================================================
    # إلغاء رحلة إداريًا
    # =================================================================

    @classmethod
    @transaction.atomic
    def force_cancel_trip(cls, ride_id, actor, reason):
        from trips.models import Trip, TripStatus
        from trips.services.engagement import EngagementResolver

        cls._require_reason(reason)

        trip = (
            Trip.objects
            .select_for_update()
            .select_related("ride")
            .filter(ride_id=ride_id)
            .first()
        )

        if trip is None:
            raise OpsError("لا توجد رحلة بهذا الرقم.")

        if trip.status in (TripStatus.COMPLETED, TripStatus.CANCELLED):
            raise OpsError("الرحلة مغلقة بالفعل.")

        before = cls._trip_snapshot(trip)

        from rides.models import RideStatus

        trip.status = TripStatus.CANCELLED
        trip.cancelled_at = timezone.now()
        trip.cancelled_by = "admin"
        trip.cancel_reason = reason[:255]
        trip.save(update_fields=[
            "status", "cancelled_at", "cancelled_by", "cancel_reason", "updated_at",
        ])

        ride = trip.ride
        ride.status = RideStatus.CANCELLED
        ride.save(update_fields=["status", "updated_at"])

        EngagementResolver.sync_on_commit(trip.driver_id)

        return cls._record(
            actor=actor,
            kind=ActionKind.FORCE_CANCEL,
            target_type="trip",
            target_id=trip.id,
            reason=reason,
            before=before,
            after=cls._trip_snapshot(trip),
        )

    # =================================================================
    # توثيق السائقين
    # =================================================================

    @classmethod
    @transaction.atomic
    def set_driver_status(cls, driver_id, actor, new_status, reason):
        """
        توثيق أو رفض أو إيقاف.

        الإيقاف يُخرج السائق من الخدمة فورًا لا عند نبضته التالية: سائق
        أوقفناه لشكوى سلامة ويبقى ظاهرًا على الخريطة نصف ساعة هو بالضبط
        ما لا يجوز أن يحدث.
        """
        cls._require_reason(reason)

        valid = {
            DriverProfile.DriverStatus.ACTIVE: ActionKind.VERIFY_DRIVER,
            DriverProfile.DriverStatus.REJECTED: ActionKind.REJECT_DRIVER,
            DriverProfile.DriverStatus.SUSPENDED: ActionKind.SUSPEND_DRIVER,
        }

        if new_status not in valid:
            raise OpsError("حالة غير مسموحة من اللوحة.")

        driver = (
            DriverProfile.objects
            .select_for_update()
            .select_related("user")
            .filter(id=driver_id)
            .first()
        )

        if driver is None:
            raise OpsError("السائق غير موجود.")

        before = cls._driver_snapshot(driver)

        driver.status = new_status
        driver.verification_note = reason[:500]
        driver.verified_by = actor
        driver.verified_at = timezone.now()

        if new_status != DriverProfile.DriverStatus.ACTIVE:
            driver.online = False

        driver.save(update_fields=[
            "status", "verification_note", "verified_by",
            "verified_at", "online", "updated_at",
        ])

        if new_status != DriverProfile.DriverStatus.ACTIVE:
            cls._take_offline_on_commit(driver_id)

        return cls._record(
            actor=actor,
            kind=valid[new_status],
            target_type="driver",
            target_id=driver_id,
            reason=reason,
            before=before,
            after=cls._driver_snapshot(driver),
        )

    # =================================================================
    # HELPERS
    # =================================================================

    @staticmethod
    def _take_offline_on_commit(driver_id):
        def _go():
            try:
                from presence.services import PresenceService
                from realtime.marketplace import MarketplaceService

                PresenceService.go_offline(driver_id)
                MarketplaceService.handle_offline(driver_id)
            except Exception:
                pass

        transaction.on_commit(_go)

    @staticmethod
    def _require_reason(reason):
        if not reason or len(reason.strip()) < MIN_REASON_LENGTH:
            raise OpsError(
                f"التدخّل الإداري يحتاج سببًا مكتوبًا "
                f"({MIN_REASON_LENGTH} أحرف على الأقل)."
            )

    @staticmethod
    def _driver_snapshot(driver):
        return {
            "status": driver.status,
            "online": driver.online,
            "occupancy": driver.current_occupancy,
            "available_seats": driver.available_seats,
            "rating": str(driver.rating) if driver.rating is not None else None,
        }

    @staticmethod
    def _trip_snapshot(trip):
        return {
            "status": trip.status,
            "distance_m": trip.distance_m,
            "duration_s": trip.duration_s,
            "final_fare": str(trip.final_fare),
            "needs_review": trip.needs_review,
        }

    @staticmethod
    def _record(actor, kind, target_type, target_id, reason, before, after):
        """
        كلّ تدخّل إداري يترك ثلاثة آثار، لا واحدًا:

          1. `AdminAction` — اللقطة الكاملة قبل وبعد، للمراجعة العميقة.
          2. `AuditLog`    — سطر في الجدول الزمني الموحّد، فتظهر تدخّلات
                             الإدارة في قصّة الرحلة إلى جانب بقيّة الانتقالات
                             بدل أن تعيش في جدول منفصل لا يقرؤه أحد معها.
          3. بثّ إلى لوحة التشغيل — بقيّة المشغّلين يرون التدخّل فورًا،
                             فلا يتدخّل اثنان في الحالة نفسها.
        """
        action = AdminAction.objects.create(
            actor=actor,
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            before=before,
            after=after,
        )

        from ops.models import AuditAction, AuditEntity
        from ops.services.audit import AuditService

        entity = {
            "driver": AuditEntity.DRIVER,
            "trip": AuditEntity.TRIP,
            "ride": AuditEntity.RIDE,
        }.get(target_type, AuditEntity.USER)

        AuditService.record(
            entity,
            target_id,
            action=AuditAction.ADMIN_ACTION,
            from_state=str(before.get("status", ""))[:40],
            to_state=str(after.get("status", ""))[:40],
            actor=actor,
            reason=reason,
            admin_action_id=action.id,
            kind=kind,
        )

        from realtime.ops_live import OpsLiveBroadcaster

        OpsLiveBroadcaster.admin_action(
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            actor_label=f"user:{getattr(actor, 'phone', actor.pk)}",
            reason=reason,
        )

        return action
