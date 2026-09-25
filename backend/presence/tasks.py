import time

from celery import shared_task
from django.utils import timezone

from presence.constants import HEARTBEAT_STALE_SECONDS
from presence.services import PresenceService


def _area_stale_map():
    """
    {area_id: مهلة الانقطاع} لكلّ منطقة، ومعها الافتراضي العامّ تحت None.

    المناطق قليلة (وحدات لا آلاف) ومخزّنة مؤقّتًا مع إبطال عند الحفظ، فهذه
    قراءة من الذاكرة لا استعلام في كلّ دورة كنس.
    """
    from locations.services import LocationService

    stale = {None: HEARTBEAT_STALE_SECONDS}

    for area in LocationService.get_active_service_areas():
        stale[area.id] = area.effective_presence_stale_seconds

    return stale


def _sweep_by_area():
    """
    الكنس بمهلة كلّ مدينة بدل مهلة واحدة للمنصّة.

    الترتيب مقصود: نقرأ المرشّحين بأقسى مهلة موجودة — فمن لم يتجاوزها لم
    يتجاوز أيّ مهلة أخرى وليس مرشّحًا أصلًا — ثمّ نُسقط من لم يتجاوز مهلة
    مدينته هو. لولا ذلك لاحتجنا مسحًا لكلّ منطقة، والمسح واحد هنا مهما بلغ
    عدد المدن.

    وسائق بلا منطقة أمّ يخضع للافتراضي العامّ: أن يبقى معلّقًا إلى الأبد
    لأنّ حقلًا إداريًّا فارغ هو أسوأ الاحتمالات.
    """
    stale_map = _area_stale_map()
    strictest = min(stale_map.values())

    candidates = PresenceService.stale_candidates(strictest)

    if not candidates:
        return []

    from users.models import DriverProfile

    driver_ids = [driver_id for driver_id, _ in candidates]

    areas = dict(
        DriverProfile.objects
        .filter(id__in=driver_ids)
        .values_list("id", "home_service_area_id")
    )

    now = time.time()
    default = stale_map[None]

    confirmed = [
        driver_id
        for driver_id, last_heartbeat in candidates
        if (now - last_heartbeat) >= stale_map.get(
            areas.get(driver_id), default
        )
    ]

    return PresenceService.mark_offline(confirmed)


@shared_task
def sweep_stale_driver_presence():
    """
    Celery beat: كل 15-20 ثانية (اضبطها في CELERY_BEAT_SCHEDULE).
    يزيل السائقين الذين توقف نبضهم في Redis، ويعيد مزامنة
    DriverProfile.online في PostgreSQL (المصدر الدائم).

    الجزء F: لو أحد هؤلاء السائقين مرتبط فعليًا برحلة نشطة (عرض مقبول
    وحالة رحلة DRIVER_SELECTED/ARRIVING/ARRIVED/IN_PROGRESS)، هذا انقطاع
    خطير أثناء رحلة فعلية - يجب أن يعرف العميل فورًا وليس فقط لوحة
    الإدارة لاحقًا. لذلك نبثّ driver.offline كحدث أعمال حقيقي (عبر
    EventBus.publish، وليس ephemeral) لغرفة تلك الرحلة تحديدًا.
    """
    from users.models import DriverProfile  # local import لتفادي app-loading issues

    stale_ids = _sweep_by_area()

    if not stale_ids:
        return "no stale drivers"

    updated = (
        DriverProfile.objects
        .filter(id__in=stale_ids, online=True)
        .update(online=False, updated_at=timezone.now())
    )

    from matching.models import RideOffer, OfferStatus
    from rides.models import RideStatus
    from realtime.events import EventBus
    from realtime.marketplace import MarketplaceService

    # الجزء G: إخراج كل سائق منقطع من خليته في الماركت بليس، بغض النظر
    # عن كونه مرتبطًا برحلة نشطة أم لا - هو غير متاح الآن على أي حال.
    for driver_id in stale_ids:
        MarketplaceService.handle_offline(driver_id)

    active_statuses = [
        RideStatus.DRIVER_SELECTED,
        RideStatus.DRIVER_ARRIVING,
        RideStatus.DRIVER_ARRIVED,
        RideStatus.IN_PROGRESS,
    ]

    affected = (
        RideOffer.objects
        .filter(
            driver_id__in=stale_ids,
            status=OfferStatus.ACCEPTED,
            ride__status__in=active_statuses,
        )
        .values("driver_id", "ride_id")
    )

    for row in affected:
        # حدث أعمال حقيقي - قابل للّحاق عبر resync لأنه حرج لسلامة الرحلة
        EventBus.publish(
            group_name=f"ride_{row['ride_id']}",
            event_type="driver.offline",
            entity_type="ride",
            entity_id=row["ride_id"],
            payload={"driver_id": row["driver_id"]},
        )
        # إشعار قناة السائق نفسه أيضًا (مفيد للوحة إدارة متصلة عليها)
        EventBus.publish_ephemeral(
            group_name=f"driver_{row['driver_id']}",
            event_type="presence.offline",
            payload={"driver_id": row["driver_id"]},
        )

    return f"marked {updated} drivers offline: {stale_ids}"