"""
InvitationService — الدعوة المباشرة لسائق محدد من خريطة السيارات الحيّة.

القرار المعماري الحاكم لهذا الملف:

    قبول الدعوة يُنشئ RideOffer بحالة ACCEPTED.

الدعوة ليست مسارًا موازيًا للعروض، بل *طريقة وصول* أخرى إلى نقطة القفل
نفسها. السبب أن ثلاثة مواضع في المشروع تعرّف "السائق المرتبط بهذه الرحلة"
بوجود عرض مقبول حصرًا:

    MatchingService.get_busy_driver_ids()      -> وإلا أمكن حجزه مرتين
    DriverRoomConsumer._get_active_ride_id()   -> وإلا لم يُبثّ موقعه للزبون
    RideConsumer._user_can_access_ride()       -> وإلا لم يدخل غرفة رحلته

مسار موازٍ كان سيكسر الثلاثة صامتًا. بهذا الجسر يستمر كل ما بُني بلا تعديل.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ops.models import AuditEntity
from ops.services.audit import AuditService

from matching.models import (
    InvitationStatus,
    OfferStatus,
    RideInvitation,
    RideOffer,
)
from matching.services.eta import MatchingETAService
from matching.services.matching import (
    OPEN_RIDE_STATUSES,
    MatchingService,
)
from rides.models import RideRequest, RideStatus
from users.models import DriverProfile
from notifications.services.router import NotificationRouter


class InvitationError(Exception):
    pass


# مهلة تهدئة بعد رفض السائق: يمنع الزبون من إعادة دعوة السائق نفسه فورًا
# فيتحوّل الرفض إلى إزعاج متكرر. ليست في الوثيقة لكنها ضرورية عمليًا.
#
# كانت ثابتًا يُقرأ وقت استيراد الوحدة — وهذا يعني أمرين سيّئين: لا يمكن
# ضبطها لمدينة دون أخرى، ولا يراها override_settings في الاختبارات لأنّ
# القراءة وقعت قبل أن يُطبَّق. صارت دالّة تقرأ عند النداء وتحترم المنطقة.
def _reject_cooldown_seconds(area=None):
    if area is not None:
        return area.effective_invitation_reject_cooldown_seconds
    return getattr(settings, "RIDE_INVITATION_REJECT_COOLDOWN_SECONDS", 60)

# خطط التسعير التي تصلح للدعوة المباشرة: السعر معروف ومعلن قبل الضغط.
FIXED_PRICE_POLICIES = ("regulated_tariff", "platform_fixed")


class InvitationService:

    # =================================================================
    # إنشاء الدعوة
    # =================================================================

    @classmethod
    def create(cls, ride_id, driver_id, customer, ttl_seconds=None, exact_ttl=False):
        # تنظيف كسول قبل القفل، بمعاملة مستقلة تُثبَّت فورًا
        MatchingService._expire_ride_if_stale(ride_id)
        cls._expire_stale_for_ride(ride_id)

        return cls._create_atomic(
            ride_id=ride_id,
            driver_id=driver_id,
            customer=customer,
            ttl_seconds=ttl_seconds,
            exact_ttl=exact_ttl,
        )

    @classmethod
    @transaction.atomic
    def _create_atomic(cls, ride_id, driver_id, customer, ttl_seconds, exact_ttl=False):
        # ترتيب القفل: RideRequest أولًا دائمًا - نفس ترتيب _select_offer_atomic،
        # ولذلك لا يمكن أن يحدث deadlock بين المسارين: كلاهما ينتظر الصف نفسه.
        ride = (
            RideRequest.objects
            .select_for_update()
            .get(id=ride_id, customer=customer)
        )

        if ride.status not in OPEN_RIDE_STATUSES:
            raise InvitationError("الطلب لم يعد مفتوحًا لاستقبال الدعوات.")

        if ride.is_expired:
            raise InvitationError("انتهت صلاحية الطلب.")

        area = getattr(ride, "service_area", None)

        # -------------------------------------------------------------
        # هل الدعوة المباشرة مفعّلة لهذا النمط في هذه المدينة؟
        # -------------------------------------------------------------
        if area is not None and not area.allows_invitation_for_mode(ride.mode):
            raise InvitationError(
                f"الدعوة المباشرة غير مفعّلة لنمط '{ride.mode}' في {area.name}."
            )

        # «اختر سيارتك» موقوفةٌ عن زبونٍ في عقوبة إلغاء — إلّا دعوات «الأقرب»
        # التي أنشأها الخادم نفسه لطلبٍ سبق العقوبة.
        if not exact_ttl:
            from catalog.services import Catalog

            if not Catalog.feature_enabled("pick_car", area):
                raise InvitationError("«اختر سيارتك» متوقّف حاليًّا. اطلب بالعروض.")

            from trips.services.cancellation import CancellationPolicy

            if CancellationPolicy.customer_penalty_until(customer, area):
                raise InvitationError(
                    "بسبب إلغاءات متأخّرة متكرّرة، اختيار سيارة بعينها متوقّف "
                    "مؤقّتًا لحسابك. اطلب بالعروض."
                )

        # -------------------------------------------------------------
        # المهلة: يختارها الزبون، لكن من قائمة يحددها الأدمن
        # -------------------------------------------------------------
        # «الأقرب» يضع مهلته من إعداد المنطقة لا من قائمة الزبون.
        ttl = int(ttl_seconds) if exact_ttl else cls._resolve_ttl(area, ttl_seconds)

        # -------------------------------------------------------------
        # عدد الدعوات المتوازية
        # -------------------------------------------------------------
        max_parallel = getattr(area, "invitation_max_parallel", 1) or 1

        # بلا select_for_update عمدًا: PostgreSQL يرفض FOR UPDATE مع دالة
        # تجميع. والقفل غير لازم أصلًا — نحن نحمل قفل صف الرحلة، وأي إنشاء
        # متزامن لدعوة على الطلب نفسه ينتظر عند ذلك القفل قبل أن يصل هنا.
        pending_count = RideInvitation.objects.filter(
            ride=ride, status=InvitationStatus.PENDING
        ).count()

        if pending_count >= max_parallel:
            raise InvitationError(
                "لديك دعوة معلّقة بالفعل. انتظر ردّ السائق أو ألغِ الدعوة."
            )

        # -------------------------------------------------------------
        # تهدئة الرفض
        # -------------------------------------------------------------
        if cls._is_in_reject_cooldown(ride.id, driver_id, area):
            raise InvitationError(
                "هذا السائق رفض طلبك قبل قليل. اختر سيارة أخرى."
            )

        # -------------------------------------------------------------
        # أهلية السائق - نفس الفحص الموحّد المستخدم في مسار العروض
        # -------------------------------------------------------------
        try:
            driver = (
                DriverProfile.objects
                .select_for_update()
                .select_related("user")
                .get(id=driver_id)
            )
        except DriverProfile.DoesNotExist:
            raise InvitationError("السائق غير موجود.")

        if not MatchingService.can_driver_submit_offer(ride=ride, driver=driver):
            raise InvitationError(
                "هذه السيارة لم تعد متاحة لطلبك. اختر سيارة أخرى."
            )

        # -------------------------------------------------------------
        # السعر: الدعوة المباشرة تعمل بسعر معلن، لا بمزايدة
        # -------------------------------------------------------------
        quoted_fare, policy = cls._resolve_quoted_fare(ride, area)

        # -------------------------------------------------------------
        # لقطة القرار: المسافة والمقاعد وETA وقت الإرسال
        # -------------------------------------------------------------
        distance_m, eta_minutes = cls._distance_and_eta(ride, driver)
        vehicle = cls._active_vehicle(driver)

        now = timezone.now()

        invitation = RideInvitation.objects.create(
            ride=ride,
            driver=driver,
            vehicle=vehicle,
            status=InvitationStatus.PENDING,
            ttl_seconds=ttl,
            expires_at=now + timedelta(seconds=ttl),
            approximate_distance_m=distance_m,
            eta_minutes=eta_minutes,
            available_seats=max(driver.available_seats - driver.current_occupancy, 0),
            quoted_fare=quoted_fare,
            pricing_policy=policy,
        )

        cls._schedule_expiry(invitation)
        cls._publish_created(invitation)

        return invitation

    # =================================================================
    # القبول - أخطر عملية في المرحلة
    # =================================================================

    @classmethod
    def accept(cls, invitation_id, driver):
        cls._expire_if_stale(invitation_id)
        return cls._accept_atomic(invitation_id=invitation_id, driver=driver)

    @classmethod
    @transaction.atomic
    def _accept_atomic(cls, invitation_id, driver):
        # نقرأ رقم الرحلة أولًا بلا قفل، ثم نقفل بالترتيب المعتمد:
        # RideRequest -> RideInvitation -> DriverProfile
        try:
            ride_id = (
                RideInvitation.objects
                .filter(id=invitation_id, driver=driver)
                .values_list("ride_id", flat=True)[0]
            )
        except IndexError:
            raise RideInvitation.DoesNotExist("Invitation not found for this driver.")

        ride = RideRequest.objects.select_for_update().get(id=ride_id)

        invitation = (
            RideInvitation.objects
            .select_for_update()
            .select_related("ride", "driver")
            .get(id=invitation_id, driver=driver)
        )

        # -------------------------------------------------------------
        # Idempotency: نقر مزدوج، أو إعادة اتصال WebSocket تعيد الإرسال.
        # لا خطأ ولا حجز مضاعف - نفس الدعوة تُرجَع كما هي.
        # -------------------------------------------------------------
        if invitation.status == InvitationStatus.ACCEPTED:
            return invitation

        if invitation.status != InvitationStatus.PENDING:
            raise InvitationError("هذه الدعوة لم تعد صالحة.")

        now = timezone.now()

        if invitation.expires_at <= now:
            invitation.status = InvitationStatus.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
            raise InvitationError("انتهت مهلة الدعوة.")

        if ride.status not in OPEN_RIDE_STATUSES:
            invitation.status = InvitationStatus.CANCELLED
            invitation.responded_at = now
            invitation.save(update_fields=["status", "responded_at", "updated_at"])
            raise InvitationError("الطلب لم يعد متاحًا — ثُبِّت سائق آخر.")

        driver_row = DriverProfile.objects.select_for_update().get(id=driver.id)

        # السائق قد يكون انقطع أو انشغل أو فقد مقاعده خلال المهلة
        if not MatchingService.can_driver_submit_offer(ride=ride, driver=driver_row):
            raise InvitationError(
                "لم تعد مؤهلًا لهذا الطلب الآن (اتصال، أو مقاعد، أو ارتباط برحلة أخرى)."
            )

        # -------------------------------------------------------------
        # الجسر: RideOffer مقبول - هو ما يجعل كل ما بُني سابقًا يستمر
        # -------------------------------------------------------------
        offer_expires_at = now + timedelta(
            seconds=getattr(settings, "RIDE_OFFER_TTL_SECONDS", 30)
        )

        offer, _created = RideOffer.objects.update_or_create(
            ride=ride,
            driver=driver_row,
            defaults={
                "gross_fare": invitation.quoted_fare,
                "eta_minutes": invitation.eta_minutes or 1,
                "status": OfferStatus.ACCEPTED,
                "expires_at": offer_expires_at,
                "accepted_at": now,
            },
        )

        # إغلاق كل ما ينافس على هذا الطلب
        competing_offer_ids = list(
            RideOffer.objects
            .select_for_update()
            .filter(ride=ride, status=OfferStatus.PENDING)
            .exclude(id=offer.id)
            .values_list("id", flat=True)
        )

        RideOffer.objects.filter(id__in=competing_offer_ids).update(
            status=OfferStatus.CANCELLED, updated_at=now
        )

        AuditService.record_bulk(
            AuditEntity.OFFER,
            competing_offer_ids,
            from_state=OfferStatus.PENDING,
            to_state=OfferStatus.CANCELLED,
            reason="قُبلت دعوة مباشرة لسائق آخر",
            ride_id=ride.id,
        )

        cancelled_invitations = list(
            RideInvitation.objects
            .select_for_update()
            .filter(ride=ride, status=InvitationStatus.PENDING)
            .exclude(id=invitation.id)
            .values_list("id", "driver_id")
        )

        RideInvitation.objects.filter(
            id__in=[i for i, _ in cancelled_invitations]
        ).update(status=InvitationStatus.CANCELLED, updated_at=now)

        AuditService.record_bulk(
            AuditEntity.INVITATION,
            [i for i, _ in cancelled_invitations],
            from_state=InvitationStatus.PENDING,
            to_state=InvitationStatus.CANCELLED,
            reason="قبل سائق آخر الدعوة أوّلًا",
            ride_id=ride.id,
        )

        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = now
        invitation.save(update_fields=["status", "responded_at", "updated_at"])

        ride.status = RideStatus.DRIVER_SELECTED
        ride.save(update_fields=["status", "updated_at"])
        from trips.services.trip import TripService

        TripService.ensure_trip(ride, offer=offer)

        cls._publish_accepted(invitation, offer, cancelled_invitations)

        return invitation

    # =================================================================
    # الرفض
    # =================================================================

    @classmethod
    @transaction.atomic
    def reject(cls, invitation_id, driver, reason=""):
        invitation = (
            RideInvitation.objects
            .select_for_update()
            # "ride" وحده لا "ride__service_area": منطقة الخدمة تقبل NULL،
            # فضمّها يجعل الوصلة خارجية ويرفض PostgreSQL معها FOR UPDATE.
            # والقفل هنا يجب أن يبقى على الصفّين كما كان — تضييقه تغييرٌ
            # في ضمانات التزامن لا تحسينُ استعلام. المنطقة تُقرأ باستعلام
            # إضافي واحد، ومسار الرفض ليس حارًّا.
            .select_related("ride")
            .get(id=invitation_id, driver=driver)
        )

        if invitation.status == InvitationStatus.REJECTED:
            return invitation  # idempotent

        if invitation.status != InvitationStatus.PENDING:
            raise InvitationError("هذه الدعوة لم تعد صالحة.")

        now = timezone.now()

        invitation.status = InvitationStatus.REJECTED
        invitation.responded_at = now
        invitation.reject_reason = (reason or "")[:255]
        invitation.save(
            update_fields=["status", "responded_at", "reject_reason", "updated_at"]
        )

        # الطلب يبقى في البحث كما تنص الوثيقة صراحةً - لا يُلغى ولا يُعاد إنشاؤه
        cls._publish_rejected(invitation)
        cls._set_reject_cooldown(
            invitation.ride_id, invitation.driver_id, invitation.ride.service_area
        )

        if invitation.ride.auto_dispatch:
            from matching.services.auto_dispatch import AutoDispatchService
            AutoDispatchService.schedule(invitation.ride_id)

        return invitation

    # =================================================================
    # الانتهاء والإلغاء
    # =================================================================

    @classmethod
    def expire(cls, invitation_id):
        """تُستدعى من Celery. ترجّع True إن كانت هي من أنهت الدعوة فعلًا."""
        with transaction.atomic():
            invitation = (
                RideInvitation.objects
                .select_for_update()
                .filter(
                    id=invitation_id,
                    status=InvitationStatus.PENDING,
                    expires_at__lte=timezone.now(),
                )
                .first()
            )

            if invitation is None:
                return False

            invitation.status = InvitationStatus.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])

            cls._publish_expired(invitation)

            if invitation.ride.auto_dispatch:
                from matching.services.auto_dispatch import AutoDispatchService
                AutoDispatchService.schedule(invitation.ride_id)

        return True

    @classmethod
    def cancel_pending_for_ride(cls, ride, reason="ride_locked"):
        """
        تُستدعى من MatchingService عند اختيار عرض أو إلغاء الرحلة.
        السائق المدعوّ يجب أن يعرف فورًا أن دعوته سقطت، لا أن ينتظر المهلة.
        """
        # نجلب الكائنات لا الأرقام فقط: الإشعار يحتاج السائق ومستخدمه.
        pending_invitations = list(
            RideInvitation.objects
            .select_related("driver", "driver__user", "ride")
            .filter(ride=ride, status=InvitationStatus.PENDING)
        )

        if not pending_invitations:
            return 0

        pending = [(inv.id, inv.driver_id) for inv in pending_invitations]

        RideInvitation.objects.filter(
            id__in=[i for i, _ in pending]
        ).update(status=InvitationStatus.CANCELLED, updated_at=timezone.now())

        AuditService.record_bulk(
            AuditEntity.INVITATION,
            [i for i, _ in pending],
            from_state=InvitationStatus.PENDING,
            to_state=InvitationStatus.CANCELLED,
            reason=reason,
            ride_id=ride.id,
        )

        # إشعار صامت لكل سائق سقطت دعوته. بلا هذا تبقى بطاقة الدعوة على
        # شاشته إلى أن يفتح التطبيق ويضغطها فيُرفض.
        for invitation in pending_invitations:
            invitation.status = InvitationStatus.CANCELLED
            NotificationRouter.handle("invitation.cancelled", invitation=invitation)

        transaction.on_commit(
            lambda: cls._publish_cancelled(pending, ride.id, reason)
        )

        return len(pending)

    # =================================================================
    # HELPERS
    # =================================================================

    @staticmethod
    def _resolve_ttl(area, requested):
        if area is None:
            options = [20, 40, 60]
            default = 20
        else:
            options = area.invitation_ttl_options or [20, 40, 60]
            default = area.invitation_ttl_default or options[0]

        if requested is None:
            return default

        try:
            requested = int(requested)
        except (TypeError, ValueError):
            raise InvitationError("قيمة المهلة غير صالحة.")

        if requested not in options:
            raise InvitationError(
                f"المهلة يجب أن تكون إحدى: {options} ثانية."
            )

        return requested

    @staticmethod
    def _resolve_quoted_fare(ride, area):
        """
        الدعوة المباشرة تعمل بسعر معلن مسبقًا - لا مزايدة. المدينة التي لا
        تسمح إلا بالمزايدة لا تصلح لهذا المسار، ونقولها صراحةً بدل أن نمرّر
        سعرًا مخالفًا للخطة المفعّلة.
        """
        from pricing.services import PricingPolicyError, PricingService

        if area is None:
            return ride.gross_fare, "platform_fixed"

        policy = None
        for candidate in FIXED_PRICE_POLICIES:
            if area.allows_policy(candidate):
                policy = candidate
                break

        if policy is None:
            raise InvitationError(
                f"{area.name} لا تسمح بسعر ثابت — الدعوة المباشرة تحتاج "
                "تفعيل 'سعر المنصة الثابت' أو 'تعرفة رسمية'."
            )

        quote = {
            "gross_fare": ride.gross_fare,
            "fare_floor": getattr(ride, "fare_floor", None),
            "fare_cap": getattr(ride, "fare_cap", None),
            "pricing_policy": policy,
            "currency": getattr(ride, "currency", None) or "SYP",
        }

        try:
            fare = PricingService.validate_proposed_fare(
                proposed_fare=ride.gross_fare,
                quote=quote,
                service_area=area,
                policy=policy,
                proposer="customer",
            )
        except PricingPolicyError as exc:
            raise InvitationError(str(exc))

        return fare, policy

    @staticmethod
    def _distance_and_eta(ride, driver):
        from math import radians, sin, cos, sqrt, atan2

        if driver.current_location is None or ride.pickup is None:
            return None, None

        lat1, lon1 = radians(driver.current_location.y), radians(driver.current_location.x)
        lat2, lon2 = radians(ride.pickup.y), radians(ride.pickup.x)
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        km = 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))

        return int(round(km * 1000)), MatchingETAService.calculate_eta_minutes(km)

    @staticmethod
    def _active_vehicle(driver):
        return driver.vehicles.filter(active=True).order_by("-seats").first()

    @classmethod
    def _expire_stale_for_ride(cls, ride_id):
        with transaction.atomic():
            stale_ids = list(
                RideInvitation.objects
                .filter(
                    ride_id=ride_id,
                    status=InvitationStatus.PENDING,
                    expires_at__lte=timezone.now(),
                )
                .values_list("id", flat=True)
            )

            if not stale_ids:
                return

            RideInvitation.objects.filter(id__in=stale_ids).update(
                status=InvitationStatus.EXPIRED
            )

            AuditService.record_bulk(
                AuditEntity.INVITATION,
                stale_ids,
                from_state=InvitationStatus.PENDING,
                to_state=InvitationStatus.EXPIRED,
                reason="انقضت مهلة الدعوة بلا ردّ",
                ride_id=ride_id,
            )

    @classmethod
    def _expire_if_stale(cls, invitation_id):
        with transaction.atomic():
            expired = (
                RideInvitation.objects
                .filter(
                    id=invitation_id,
                    status=InvitationStatus.PENDING,
                    expires_at__lte=timezone.now(),
                )
                .update(status=InvitationStatus.EXPIRED)
            )

            if expired:
                AuditService.record(
                    AuditEntity.INVITATION,
                    invitation_id,
                    from_state=InvitationStatus.PENDING,
                    to_state=InvitationStatus.EXPIRED,
                    reason="انقضت مهلة الدعوة بلا ردّ",
                )

    @staticmethod
    def _schedule_expiry(invitation):
        """
        انتهاء دقيق: مهمة مجدولة لهذه الدعوة تحديدًا بدل استطلاع دوري.
        مهلة 20 ثانية لا تُخدَم بمهمة تعمل كل 30 - كان الزبون سينتظر 50.
        المسح الدوري يبقى شبكة أمان لو كان الـworker متوقفًا.
        """
        def _schedule():
            try:
                from matching.tasks import expire_ride_invitation
                expire_ride_invitation.apply_async(
                    args=[invitation.id],
                    countdown=invitation.ttl_seconds + 1,
                )
            except Exception:
                # لا Celery في بيئة التطوير؟ المسح الدوري والفحص الكسول يغطّيان.
                pass

        transaction.on_commit(_schedule)

    # -----------------------------------------------------------------
    # تهدئة الرفض (Redis - ليست حالة دائمة، فلا داعي لجدول)
    # -----------------------------------------------------------------

    @staticmethod
    def _cooldown_key(ride_id, driver_id):
        return f"invitation:cooldown:{ride_id}:{driver_id}"

    @classmethod
    def _set_reject_cooldown(cls, ride_id, driver_id, area=None):
        seconds = _reject_cooldown_seconds(area)
        if seconds <= 0:
            return
        try:
            from django.core.cache import cache
            cache.set(cls._cooldown_key(ride_id, driver_id), 1, seconds)
        except Exception:
            pass

    @classmethod
    def _is_in_reject_cooldown(cls, ride_id, driver_id, area=None):
        # القراءة لا تحتاج المدّة — وجود المفتاح هو الجواب، وريديس أسقطه
        # وحده عند انتهائها. لكن صفرًا يعني «معطّلة»، وحينها لا نسأل أصلًا.
        if _reject_cooldown_seconds(area) <= 0:
            return False
        try:
            from django.core.cache import cache
            return cache.get(cls._cooldown_key(ride_id, driver_id)) is not None
        except Exception:
            return False

    # -----------------------------------------------------------------
    # الأحداث - كلها بعد الـcommit، بلا استثناء
    # -----------------------------------------------------------------

    @staticmethod
    def _payload(invitation):
        return {
            "invitation_id": invitation.id,
            "ride_id": invitation.ride_id,
            "driver_id": invitation.driver_id,
            "status": invitation.status,
            "ttl_seconds": invitation.ttl_seconds,
            "expires_at": invitation.expires_at.isoformat(),
            "quoted_fare": str(invitation.quoted_fare),
            "pricing_policy": invitation.pricing_policy,
            "eta_minutes": invitation.eta_minutes,
            "approximate_distance_m": invitation.approximate_distance_m,
            "available_seats": invitation.available_seats,
        }

    @classmethod
    def _publish_created(cls, invitation):
        from realtime.events import EventBus

        payload = cls._payload(invitation)
        driver_id = invitation.driver_id
        ride_id = invitation.ride_id

        def _go():
            EventBus.publish(
                group_name=f"driver_{driver_id}",
                event_type="invitation.created",
                entity_type="driver",
                entity_id=driver_id,
                payload=payload,
            )
            EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="invitation.sent",
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
        NotificationRouter.handle("invitation.created", invitation=invitation)
        transaction.on_commit(_go)

    @classmethod
    def _publish_accepted(cls, invitation, offer, cancelled):
        from realtime.events import EventBus
        from matching.serializers import RideOfferSerializer

        payload = cls._payload(invitation)
        offer_payload = RideOfferSerializer(offer).data
        ride_id = invitation.ride_id
        driver_id = invitation.driver_id

        def _go():
            EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="invitation.accepted",
                entity_type="ride",
                entity_id=ride_id,
                payload={**payload, "offer": offer_payload},
            )
            EventBus.publish(
                group_name=f"driver_{driver_id}",
                event_type="invitation.accepted",
                entity_type="driver",
                entity_id=driver_id,
                payload=payload,
            )

            # السائقون الذين سقطت دعواتهم لأن غيرهم أسرع
            for inv_id, other_driver_id in cancelled:
                EventBus.publish(
                    group_name=f"driver_{other_driver_id}",
                    event_type="invitation.cancelled",
                    entity_type="driver",
                    entity_id=other_driver_id,
                    payload={
                        "invitation_id": inv_id,
                        "ride_id": ride_id,
                        "reason": "another_driver_accepted",
                    },
                )

            # لا نكتب الحالة هنا. TripService.ensure_trip سجّل مزامنة
            # الارتباط على on_commit قبل هذه الدالة، وهي تعرف الفرق بين
            # BUSY وSHARING وتُعلم الخريطة بنفسها.
            #
            # هذا هو الثقب نفسه الذي أصلحناه في _select_offer_atomic،
            # وكان ما يزال مفتوحًا هنا: قبول دعوة على رحلة مشتركة كان
            # يكتب SHARING ثم يشطبها بعد سطرين. اختبار المرحلة 8ب لم
            # يمسكه لأنه يمرّ من مسار العروض لا من مسار الدعوة.
            pass

        transaction.on_commit(_go)

    @classmethod
    def _publish_rejected(cls, invitation):
        from realtime.events import EventBus

        payload = cls._payload(invitation)
        payload["reject_reason"] = invitation.reject_reason
        ride_id = invitation.ride_id

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="invitation.rejected",
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
        )

    @classmethod
    def _publish_expired(cls, invitation):
        from realtime.events import EventBus

        payload = cls._payload(invitation)
        ride_id = invitation.ride_id
        driver_id = invitation.driver_id

        def _go():
            EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="invitation.expired",
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
            EventBus.publish_ephemeral(
                group_name=f"driver_{driver_id}",
                event_type="invitation.expired",
                payload=payload,
            )
        NotificationRouter.handle("invitation.expired", invitation=invitation)
        transaction.on_commit(_go)

    @staticmethod
    def _publish_cancelled(pending, ride_id, reason):
        from realtime.events import EventBus

        for inv_id, driver_id in pending:
            EventBus.publish(
                group_name=f"driver_{driver_id}",
                event_type="invitation.cancelled",
                entity_type="driver",
                entity_id=driver_id,
                payload={
                    "invitation_id": inv_id,
                    "ride_id": ride_id,
                    "reason": reason,
                },
            )
