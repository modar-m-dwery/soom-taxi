"""
«الأقرب» — الخادم يدعو السائق بدل الزبون.

الزبون الذي يختار «الأقرب» لا يريد أن يقارن عروضًا ولا أن يختار سيارة:
يريد أوّل سيارة تصل. فيدعو الخادم أقرب سائق متاح بمهلة قصيرة، وإن رفض
أو صمت دعا التالي — حتّى عددٍ يضعه المشغّل. بعدها يُترك الطلب للعروض
العاديّة ويُخبَر الزبون، بدل أن يبقى معلّقًا بلا شيء.

المبنى كلّه فوق الدعوة المباشرة القائمة، لا بجانبها: القبول والإغلاق
والإشعار والتدقيق هي نفسها، فلا مسار ثانٍ يتباعد عن الأوّل.

`advance` آمنة التكرار: قد تُنادى من الرفض ومن الانتهاء ومن المسح الدوري
للدعوة نفسها. قفل صفّ الطلب ووجود دعوة معلّقة يجعلان النداء الثاني بلا أثر.
"""

import logging

from django.db import transaction

from matching.models import InvitationStatus, RideInvitation
from rides.models import RideMode, RideRequest

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 15
DEFAULT_MAX_ATTEMPTS = 5


class AutoDispatchService:

    @staticmethod
    def settings_for(area):
        if area is None:
            return DEFAULT_TTL_SECONDS, DEFAULT_MAX_ATTEMPTS
        return (
            area.auto_dispatch_ttl_seconds or DEFAULT_TTL_SECONDS,
            area.auto_dispatch_max_attempts or DEFAULT_MAX_ATTEMPTS,
        )

    @classmethod
    def schedule(cls, ride_id):
        """بعد تثبيت المعاملة الحاليّة — الدعوة تحتاج صفّ الطلب مثبَّتًا."""
        transaction.on_commit(lambda: cls.advance(ride_id))

    @classmethod
    def advance(cls, ride_id):
        """ادعُ السائق التالي الأقرب. ترجع الدعوة أو None."""
        from matching.services.invitation import InvitationError, InvitationService
        from matching.services.matching import OPEN_RIDE_STATUSES
        from matching.services.nearby import NearbyVehiclesService

        ride = (
            RideRequest.objects
            .select_related("service_area", "customer")
            .filter(id=ride_id)
            .first()
        )

        if ride is None or not ride.auto_dispatch:
            return None

        if ride.status not in OPEN_RIDE_STATUSES or ride.is_expired:
            return None

        # دعوة معلّقة = دورٌ جارٍ. النداء المكرَّر يقف هنا.
        if RideInvitation.objects.filter(
            ride=ride, status=InvitationStatus.PENDING
        ).exists():
            return None

        ttl, max_attempts = cls.settings_for(ride.service_area)

        tried = set(
            RideInvitation.objects
            .filter(ride=ride)
            .values_list("driver_id", flat=True)
        )

        if len(tried) >= max_attempts:
            cls._exhaust(ride, reason="max_attempts")
            return None

        # مرتّبة بالأقرب — نفس القائمة التي يراها الزبون على خريطته.
        for vehicle in NearbyVehiclesService.for_ride(ride):
            driver_id = vehicle["driver_id"]
            # سيارةٌ فيها ركّاب تصلح لطلب مشترك وحده — والقائمة نفسها لا
            # تُرجعها لغيره أصلًا؛ الفحص هنا حزامُ أمان.
            if driver_id in tried or (
                vehicle.get("is_sharing") and ride.mode != RideMode.SHARED
            ):
                continue
            try:
                return InvitationService.create(
                    ride_id=ride.id,
                    driver_id=driver_id,
                    customer=ride.customer,
                    ttl_seconds=ttl,
                    exact_ttl=True,
                )
            except InvitationError as exc:
                # سائقٌ انشغل بين القائمة والدعوة: التالي، لا توقّف.
                logger.info(
                    "auto-dispatch ride=%s skipped driver=%s: %s",
                    ride.id, driver_id, exc,
                )
                continue

        cls._exhaust(ride, reason="no_drivers")
        return None

    @classmethod
    def _exhaust(cls, ride, reason):
        """لا سائق قَبِل: الطلب يعود مزادًا عاديًّا، والزبون يعرف ذلك."""
        from realtime.events import EventBus

        updated = RideRequest.objects.filter(
            id=ride.id, auto_dispatch=True
        ).update(auto_dispatch=False)

        # سباقان على الإنهاك نفسه: واحدٌ فقط يُعلن.
        if not updated:
            return

        ride_id = ride.id

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="auto_dispatch.exhausted",
                entity_type="ride",
                entity_id=ride_id,
                payload={"ride_id": ride_id, "reason": reason},
            )
        )
