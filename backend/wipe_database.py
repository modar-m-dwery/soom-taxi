# سكريبت حذف البيانات عدا السوبر يوزر 
# تعليمة التنفيذ:
# python manage.py shell -c "exec(open('wipe_database.py', encoding='utf-8').read())"
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authtoken.models import Token

SUPERUSER_PHONE = "963938124411"

User = get_user_model()


@transaction.atomic
def wipe_all_except_superuser():

    try:
        keep_user = User.objects.get(phone=SUPERUSER_PHONE)
    except User.DoesNotExist:
        raise RuntimeError(
            f"السوبر يوزر صاحب الرقم {SUPERUSER_PHONE} غير موجود. "
            "تم إيقاف العملية لمنع حذف كل شيء بالخطأ."
        )

    keep_user_id = keep_user.id

    from matching.models import (
        SharedJoinRequest,
        SharedRideGroupMember,
        SharedRideGroup,
        ScheduledSharedTripMember,
        ScheduledSharedTrip,
        RideOffer,
    )

    SharedJoinRequest.objects.all().delete()
    SharedRideGroupMember.objects.all().delete()
    SharedRideGroup.objects.all().delete()
    ScheduledSharedTripMember.objects.all().delete()
    ScheduledSharedTrip.objects.all().delete()
    RideOffer.objects.all().delete()

    from rides.models import RideRequest

    RideRequest.objects.all().delete()

    # ==========================================================
    # 2) وثائق السائقين والمركبات
    # ==========================================================

    try:
        from drivers.models import DriverDocument
        DriverDocument.objects.all().delete()
    except ImportError:
        pass

    try:
        from vehicles.models import Vehicle
        Vehicle.objects.all().delete()
    except ImportError:
        pass

    # ==========================================================
    # 3) بروفايلات السائقين/العملاء (كل شيء غير مرتبط بالسوبر يوزر)
    # ==========================================================

    try:
        from users.models import DriverProfile
        DriverProfile.objects.exclude(user_id=keep_user_id).delete()
    except ImportError:
        pass

    try:
        from users.models import CustomerProfile
        CustomerProfile.objects.exclude(user_id=keep_user_id).delete()
    except ImportError:
        pass

    # ==========================================================
    # 4) OTP Challenges (باستثناء ما يخص السوبر يوزر إن وجد)
    # ==========================================================

    try:
        from users.models import OTPChallenge
        OTPChallenge.objects.exclude(phone=SUPERUSER_PHONE).delete()
    except ImportError:
        pass

    # ==========================================================
    # 5) Tokens (نحتفظ فقط بتوكن السوبر يوزر)
    # ==========================================================

    Token.objects.exclude(user_id=keep_user_id).delete()

    # ==========================================================
    # 6) المستخدمون (نحتفظ فقط بالسوبر يوزر)
    # ==========================================================

    User.objects.exclude(id=keep_user_id).delete()

    print(
        f"تم تنظيف قاعدة البيانات بالكامل. "
        f"تم الاحتفاظ فقط بالمستخدم: {keep_user.phone} (id={keep_user_id})"
    )


wipe_all_except_superuser()