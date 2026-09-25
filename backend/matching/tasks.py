from celery import shared_task
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
from rides.models import RideMode, RideRequest, RideStatus


# سقف لكل دورة: يمنع مهمة واحدة من الاستحواذ على الـworker لو تراكمت آلاف
# السجلات بعد انقطاع. الباقي يُلتقط في الدورة التالية.
EXPIRY_BATCH_SIZE = 200


# =====================================================================
# العروض
# =====================================================================

@shared_task
def expire_stale_offers():
    """
    كانت النسخة الأصلية .update() جماعيًا واحدًا. سريع، لكنه صامت تمامًا:
    لا يبثّ offer.expired (وهو حدث إلزامي في §22)، ولا ينظّف SharedRideGroup
    المعلّقة على عرض ميت.
    """
    now = timezone.now()

    offer_ids = list(
        RideOffer.objects
        .filter(status=OfferStatus.PENDING, expires_at__lte=now)
        .values_list("id", flat=True)[:EXPIRY_BATCH_SIZE]
    )

    expired = sum(1 for offer_id in offer_ids if _expire_single_offer(offer_id))

    return f"expired {expired} offers"


def _expire_single_offer(offer_id):
    from matching.services.shared_matching import SharedMatchingService
    from realtime.events import EventBus

    with transaction.atomic():
        offer = (
            RideOffer.objects
            .select_for_update()
            .select_related("ride")
            .filter(
                id=offer_id,
                status=OfferStatus.PENDING,
                expires_at__lte=timezone.now(),
            )
            .first()
        )

        # قُبِل أو أُلغي بين الاستعلام الأول والقفل -> لا نلمسه
        if offer is None:
            return False

        offer.status = OfferStatus.EXPIRED
        offer.save(update_fields=["status", "updated_at"])

        ride = offer.ride

        if ride.mode == RideMode.SHARED and ride.scheduled_at is None:
            SharedMatchingService.cancel_group_for_offer(offer)

        ride_id = ride.id
        offer_id_value = offer.id
        driver_id = offer.driver_id

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="offer.expired",
                entity_type="ride",
                entity_id=ride_id,
                payload={
                    "offer_id": offer_id_value,
                    "driver_id": driver_id,
                    "status": OfferStatus.EXPIRED,
                },
            )
        )

    return True


# =====================================================================
# الرحلات
# =====================================================================

@shared_task
def expire_stale_rides():
    from realtime.events import EventBus

    now = timezone.now()

    ride_ids = list(
        RideRequest.objects
        .filter(
            status__in=[RideStatus.SEARCHING, RideStatus.OFFERS_RECEIVED],
            expires_at__isnull=False,
            expires_at__lte=now,
        )
        .values_list("id", flat=True)[:EXPIRY_BATCH_SIZE]
    )

    if not ride_ids:
        return "expired 0 rides"

    updated = (
        RideRequest.objects
        .filter(
            id__in=ride_ids,
            status__in=[RideStatus.SEARCHING, RideStatus.OFFERS_RECEIVED],
        )
        .update(status=RideStatus.EXPIRED, updated_at=now)
    )

    # الدعوات المعلّقة على طلب منتهٍ لا معنى لها
    cancelled_invitation_ids = list(
        RideInvitation.objects.filter(
            ride_id__in=ride_ids, status=InvitationStatus.PENDING
        ).values_list("id", flat=True)
    )

    RideInvitation.objects.filter(
        id__in=cancelled_invitation_ids
    ).update(status=InvitationStatus.CANCELLED, updated_at=now)

    # الأثر: هذه التحديثات جماعية فلا تراها إشارات post_save.
    AuditService.record_bulk(
        AuditEntity.RIDE,
        ride_ids,
        from_state="searching|offers_received",
        to_state=RideStatus.EXPIRED,
        actor_label="celery:expire_stale_rides",
        reason="انتهت مهلة الطلب بلا اختيار سائق",
    )

    AuditService.record_bulk(
        AuditEntity.INVITATION,
        cancelled_invitation_ids,
        from_state=InvitationStatus.PENDING,
        to_state=InvitationStatus.CANCELLED,
        actor_label="celery:expire_stale_rides",
        reason="أُلغيت لانتهاء الطلب المرتبط",
    )

    for ride_id in ride_ids:
        EventBus.publish(
            group_name=f"ride_{ride_id}",
            event_type="ride.expired",
            entity_type="ride",
            entity_id=ride_id,
            payload={"ride_id": ride_id, "status": RideStatus.EXPIRED},
        )

    return f"expired {updated} rides"


# =====================================================================
# الدعوات المباشرة
# =====================================================================

@shared_task
def expire_ride_invitation(invitation_id):
    """
    مهمة مجدولة لدعوة واحدة بعينها، تُطلَق لحظة إنشائها بـcountdown يساوي
    مهلتها. هذا ما يعطي انتهاءً دقيقًا في الثانية المطلوبة.

    مهمة دورية كل 30 ثانية لا تخدم مهلة 20 ثانية: الزبون كان سينتظر 50.
    """
    from matching.services.invitation import InvitationService

    changed = InvitationService.expire(invitation_id)
    return f"invitation {invitation_id}: {'expired' if changed else 'no-op'}"


@shared_task
def expire_stale_invitations():
    """
    شبكة أمان لا أكثر: تلتقط الدعوات التي فاتتها مهمتها المجدولة لأن الـ
    worker كان متوقفًا لحظة إنشائها. في التشغيل السليم ترجع 0 دائمًا.
    """
    from matching.services.invitation import InvitationService

    stale_ids = list(
        RideInvitation.objects
        .filter(
            status=InvitationStatus.PENDING,
            expires_at__lte=timezone.now(),
        )
        .values_list("id", flat=True)[:EXPIRY_BATCH_SIZE]
    )

    expired = sum(1 for inv_id in stale_ids if InvitationService.expire(inv_id))

    return f"swept {expired} stale invitations"
