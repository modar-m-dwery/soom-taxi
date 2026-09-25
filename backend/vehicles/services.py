from django.db import transaction

from vehicles.models import Vehicle


class VehicleError(Exception):
    pass


def _sync_after_vehicle_change(driver_profile, went_dark=False):
    """
    مزامنة ما بعد تغيير المركبة.

    كانت تنادي sync_from_driver وحدها، وهي تكتب المقاعد والسعة والحالة -
    وكان ذلك كافيًا قبل المرحلة 8ب. لم يعد كذلك: السائق المشارك تُقرأ
    مقاعده الفارغة من حقل free_seats في حزمة الارتباط لا من الطرح، فتبديل
    مركبة بأصغر منها كان يترك رقمًا قديمًا يَعِد بمقعد لم يعد موجودًا.

    EngagementResolver.sync يعيد حساب الاثنين معًا ويُعلم الخريطة.
    """
    from presence.services import PresenceService

    try:
        driver_profile.refresh_from_db()
        PresenceService.sync_from_driver(driver_profile)
    except Exception:
        pass

    try:
        from trips.services.engagement import EngagementResolver

        EngagementResolver.sync(driver_profile.id)
    except Exception:
        pass

    if not went_dark:
        return

    # لم تبقَ مركبة فعّالة: القاعدة تقول online=False، ويجب أن يقول Redis
    # الشيء نفسه. بدون هذا يبقى السائق مرسومًا على خرائط مَن يشاهد الآن
    # إلى أن يرسل نبضة موقع تالية - وهو لن يرسلها، فقد أُطفئ.
    try:
        from realtime.marketplace import MarketplaceService

        PresenceService.go_offline(driver_profile.id)
        MarketplaceService.handle_offline(driver_profile.id)
    except Exception:
        pass


def _assert_no_active_trip(driver_profile):
    """
    تبديل المركبة أثناء رحلة جارية ممنوع.

    الراكب ينتظر سيارة بلونها ورقمها، والرحلة تحمل مرجعًا إلى مركبة بعينها
    في سجلّها الدائم. تبديلها تحت الرحلة يجعل ما يراه الراكب في التطبيق
    مخالفًا لما يقف أمامه، ويجعل سجلّ الرحلة يشير إلى مركبة لم تنفّذها.
    """
    from trips.models import Trip, TripStatus

    active = Trip.objects.filter(
        driver=driver_profile,
        status__in=[
            TripStatus.CREATED,
            TripStatus.DRIVER_ARRIVING,
            TripStatus.DRIVER_ARRIVED,
            TripStatus.IN_PROGRESS,
        ],
    ).exists()

    if active:
        raise VehicleError(
            "لا يمكن تغيير المركبة أثناء رحلة جارية. أنهِ رحلتك أولًا."
        )


class VehicleService:

    @staticmethod
    @transaction.atomic
    def register_vehicle(driver_profile, validated_data):
        """
        تسجيل مركبة جديدة.

        المركبة تبدأ inactive.
        """
        vehicle = Vehicle.objects.create(
            driver=driver_profile,
            active=False,
            **validated_data,
        )

        return vehicle

    @staticmethod
    @transaction.atomic
    def set_active_vehicle(driver_profile, vehicle_id):
        """
        جعل مركبة واحدة فقط فعالة لهذا السائق.
        """
        _assert_no_active_trip(driver_profile)

        vehicle = (
            Vehicle.objects
            .select_for_update()
            .get(id=vehicle_id, driver=driver_profile)
        )

        Vehicle.objects.filter(
            driver=driver_profile,
            active=True,
        ).exclude(id=vehicle.id).update(active=False)

        vehicle.active = True
        vehicle.save(update_fields=["active"])

        driver_profile.available_seats = vehicle.seats
        driver_profile.save(update_fields=["available_seats"])

        transaction.on_commit(
            lambda: _sync_after_vehicle_change(driver_profile)
        )

        return vehicle

    @staticmethod
    @transaction.atomic
    def deactivate_vehicle(driver_profile, vehicle_id):
        """
        إلغاء تفعيل مركبة.
        """
        _assert_no_active_trip(driver_profile)

        vehicle = (
            Vehicle.objects
            .select_for_update()
            .get(id=vehicle_id, driver=driver_profile)
        )

        vehicle.active = False
        vehicle.save(update_fields=["active"])

        active_vehicle = (
            Vehicle.objects
            .filter(driver=driver_profile, active=True)
            .order_by("-created_at")
            .first()
        )

        went_dark = active_vehicle is None

        if active_vehicle:
            driver_profile.available_seats = active_vehicle.seats
        else:
            driver_profile.available_seats = 0
            driver_profile.online = False

        driver_profile.save(update_fields=["available_seats", "online"])

        transaction.on_commit(
            lambda: _sync_after_vehicle_change(driver_profile, went_dark=went_dark)
        )

        return vehicle
