from django.db import transaction

from drivers.services.eligibility import (
    DriverEligibilityService,
)
from users.models import DriverProfile
from config.observability.safety import swallow

class DriverAvailabilityService:
    """
    مسار REST للحضور. كان يغيّر DriverProfile.online في PostgreSQL فقط، بينما
    DriverRoomConsumer (WebSocket) يغيّر PostgreSQL *و* Redis Presence. النتيجة
    كانت سائقًا يستخدم REST فيصبح online=True في القاعدة و OFFLINE في Presence:
    Matching يراه متاحًا والماركت بليس لا يراه إطلاقًا - وهو التناقض الذي تمنعه
    نقطة #9 في خطة المرحلة 6 ("نفس التعريف لكل المستهلكين").

    الآن القناتان تمرّان على نفس الخدمات بنفس الترتيب.
    """

    @classmethod
    @transaction.atomic
    def go_online(cls, driver_profile):

        driver_profile = (
            DriverProfile.objects
            .select_for_update()
            .get(id=driver_profile.id)
        )

        if (
            driver_profile.status
            != DriverProfile.DriverStatus.ACTIVE
        ):
            raise ValueError(
                "Driver is not active."
            )

        if not DriverEligibilityService.is_eligible(
            driver_profile
        ):
            raise ValueError(
                "Driver is not eligible to go online."
            )

        driver_profile.online = True

        updated_fields = ["online"]

        # منطقة السائق الأمّ تُملأ من أوّل اتّصال بموقع معروف، ولا تُلمس
        # بعدها. الاشتقاق هنا لا في كلّ تحديث موقع: نريد «تحت أيّ مدينة
        # يُدار» لا «أين هو الآن» — والثاني يتغيّر كلّ ثلاث ثوانٍ.
        if (
            driver_profile.home_service_area_id is None
            and driver_profile.current_location is not None
        ):
            area = cls._resolve_home_area(driver_profile)
            if area is not None:
                driver_profile.home_service_area = area
                updated_fields.append("home_service_area")

        driver_profile.save(update_fields=updated_fields)

        # بعد الـcommit فقط: لو فشلت المعاملة لاحقًا لا نريد سائقًا "حاضرًا"
        # في Redis وغير متصل في القاعدة.
        transaction.on_commit(
            lambda: cls._sync_presence_online(driver_profile)
        )

        return driver_profile

    @classmethod
    @transaction.atomic
    def go_offline(cls, driver_profile):

        driver_profile = (
            DriverProfile.objects
            .select_for_update()
            .get(id=driver_profile.id)
        )

        driver_profile.online = False

        driver_profile.save(
            update_fields=[
                "online",
            ]
        )

        driver_id = driver_profile.id

        transaction.on_commit(
            lambda: cls._sync_presence_offline(driver_id)
        )

        return driver_profile

    # -----------------------------------------------------------
    # PRESENCE SYNC
    #
    # نستوردها داخل الدالة عمدًا: drivers لا يجب أن يعتمد على presence/realtime
    # وقت تحميل التطبيقات (app loading)، ولأن فشل Redis يجب ألا يمنع تغيير
    # الحالة في PostgreSQL - المصدر الدائم يبقى هو الحَكَم.
    # -----------------------------------------------------------

    @staticmethod
    def _sync_presence_online(driver_profile):
        from presence.services import PresenceService

        with swallow("presence", event="driver.go_online"):
            PresenceService.go_online(driver_profile)

    @staticmethod
    def _resolve_home_area(driver_profile):
        """
        فشل الاشتقاق ليس فشل اتّصال. سائق خارج كلّ منطقة معروفة — أو خلل في
        طبقة المواقع — يجب أن يبقى قادرًا على العمل بالافتراضات العامّة، لا
        أن يُمنع من الاتّصال لأنّ حقلًا إداريًّا تعذّر ملؤه.
        """
        with swallow("locations", event="driver.resolve_home_area"):
            from locations.services import LocationService

            point = driver_profile.current_location
            return LocationService.resolve_area(point.x, point.y)
        return None

    @staticmethod
    def _sync_presence_offline(driver_id):
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService

        with swallow("presence", event="driver.go_offline"):
            PresenceService.go_offline(driver_id)
            MarketplaceService.handle_offline(driver_id)