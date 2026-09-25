import itertools
import traceback
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.utils import timezone

from users.models import User, DriverProfile, UserRole
from vehicles.models import Vehicle, VehicleType
from rides.models import RideRequest, RideMode, RideStatus
from rides.services.ride_request import RideRequestService
from matching.models import RideOffer, OfferStatus
from matching.services.matching import MatchingService, MatchingError

results = []

_plate_counter = itertools.count(1)
def check(label, condition):
    status_str = "PASS" if condition else "FAIL"
    results.append((label, status_str))
    print(f"[{status_str}] {label}")


def cleanup():
    RideOffer.objects.filter(ride__customer__phone__startswith="+TEST").delete()
    RideRequest.objects.filter(customer__phone__startswith="+TEST").delete()
    Vehicle.objects.filter(driver__user__phone__startswith="+TEST").delete()
    DriverProfile.objects.filter(user__phone__startswith="+TEST").delete()
    User.objects.filter(phone__startswith="+TEST").delete()


cleanup()  # تنظيف أي بقايا من تشغيل سابق فشل

try:
    # ------------------------------------------------------------
    # إعداد البيانات
    # ------------------------------------------------------------

    customer_user = User.objects.create_user(
        phone="+TEST_CUSTOMER",
        password="x",
        role=UserRole.CUSTOMER,
        is_verified=True,
    )

    near_driver_user = User.objects.create_user(
        phone="+TEST_DRIVER_NEAR", password="x", role=UserRole.DRIVER
    )
    far_driver_user = User.objects.create_user(
        phone="+TEST_DRIVER_FAR", password="x", role=UserRole.DRIVER
    )
    offline_driver_user = User.objects.create_user(
        phone="+TEST_DRIVER_OFFLINE", password="x", role=UserRole.DRIVER
    )
    stale_driver_user = User.objects.create_user(
        phone="+TEST_DRIVER_STALE", password="x", role=UserRole.DRIVER
    )

    pickup = Point(31.2357, 30.0444, srid=4326)      # القاهرة (وسط)
    destination = Point(31.3200, 30.0700, srid=4326)  # نقطة قريبة مختلفة

    near_point = Point(31.2400, 30.0450, srid=4326)   # قريب جدًا من pickup
    far_point = Point(35.9106, 31.9539, srid=4326)    # عمّان - بعيد جدًا

    now = timezone.now()

    def make_driver(user, location, online=True, fresh=True, seats=4):
        d = DriverProfile.objects.create(
            user=user,
            status=DriverProfile.DriverStatus.ACTIVE,
            online=online,
            current_location=location,
            current_occupancy=0,
            available_seats=seats,
            last_location_at=now if fresh else now - timedelta(minutes=30),
        )
        Vehicle.objects.create(
            driver=d,
            type_id=VehicleType.SEDAN,
            make="Toyota",
            model="Corolla",
            year=2020,
            color="White",
            plate_number=f"TST-{next(_plate_counter):04d}",
            seats=seats,
            active=True,
        )
        return d

    near_driver = make_driver(near_driver_user, near_point)
    far_driver = make_driver(far_driver_user, far_point)
    offline_driver = make_driver(offline_driver_user, near_point, online=False)
    stale_driver = make_driver(stale_driver_user, near_point, fresh=False)

    # ------------------------------------------------------------
    # 1) إنشاء طلب رحلة
    # ------------------------------------------------------------

    ride = RideRequestService.create_ride_request(
        customer=customer_user,
        pickup=pickup,
        destination=destination,
        mode=RideMode.STANDARD,
        passenger_count=1,
    )

    check("الرحلة أُنشئت بحالة SEARCHING", ride.status == RideStatus.SEARCHING)

    # ------------------------------------------------------------
    # 2) فلترة السائقين المؤهلين (اتجاه رحلة -> سائقين)
    # ------------------------------------------------------------

    eligible = list(MatchingService.get_eligible_drivers(ride))
    eligible_ids = {d.id for d in eligible}

    check("السائق القريب مؤهل", near_driver.id in eligible_ids)
    check("السائق البعيد غير مؤهل", far_driver.id not in eligible_ids)
    check("السائق غير المتصل (offline) غير مؤهل", offline_driver.id not in eligible_ids)
    check("السائق بموقع قديم (stale) غير مؤهل", stale_driver.id not in eligible_ids)

    # ------------------------------------------------------------
    # 3) فلترة الرحلات المؤهلة (اتجاه سائق -> رحلات) - الدالة الجديدة
    # ------------------------------------------------------------

    near_driver_rides = set(
        MatchingService.get_eligible_rides_for_driver(near_driver)
        .values_list("id", flat=True)
    )
    far_driver_rides = set(
        MatchingService.get_eligible_rides_for_driver(far_driver)
        .values_list("id", flat=True)
    )

    check("get_eligible_rides_for_driver: الرحلة تظهر للسائق القريب", ride.id in near_driver_rides)
    check("get_eligible_rides_for_driver: الرحلة لا تظهر للسائق البعيد", ride.id not in far_driver_rides)

    # ------------------------------------------------------------
    # 4) تقديم عرض من سائق غير مؤهل -> يجب أن يفشل
    # ------------------------------------------------------------

    try:
        MatchingService.create_offer(
            ride_id=ride.id, driver=far_driver, gross_fare=50, eta_minutes=10
        )
        check("رفض عرض من سائق بعيد", False)
    except MatchingError:
        check("رفض عرض من سائق بعيد", True)

    # ------------------------------------------------------------
    # 5) تقديم عرض صحيح -> الرحلة تنتقل إلى OFFERS_RECEIVED
    # ------------------------------------------------------------

    offer1 = MatchingService.create_offer(
        ride_id=ride.id, driver=near_driver, gross_fare=45, eta_minutes=8
    )
    ride.refresh_from_db()

    check("العرض أُنشئ بحالة PENDING", offer1.status == OfferStatus.PENDING)
    check("الرحلة انتقلت إلى OFFERS_RECEIVED بعد أول عرض", ride.status == RideStatus.OFFERS_RECEIVED)

    # ------------------------------------------------------------
    # 6) تقديم عرض ثانٍ من نفس السائق وهو PENDING -> يجب أن يُرفض
    # ------------------------------------------------------------

    try:
        MatchingService.create_offer(
            ride_id=ride.id, driver=near_driver, gross_fare=40, eta_minutes=7
        )
        check("رفض عرض مكرر من نفس السائق أثناء PENDING", False)
    except MatchingError:
        check("رفض عرض مكرر من نفس السائق أثناء PENDING", True)

    # ------------------------------------------------------------
    # 7) بعد انتهاء صلاحية العرض -> نفس السائق يقدر يعيد التقديم
    #    (هذا هو الإصلاح الأهم: لا يصطدم بـ unique_ride_driver_offer)
    # ------------------------------------------------------------

    offer1.expires_at = now - timedelta(seconds=1)
    offer1.save(update_fields=["expires_at"])

    offer_retry = MatchingService.create_offer(
        ride_id=ride.id, driver=near_driver, gross_fare=42, eta_minutes=9
    )

    check(
        "إعادة التقديم بعد انتهاء الصلاحية تنجح (نفس الصف يُحدَّث)",
        offer_retry.id == offer1.id and offer_retry.status == OfferStatus.PENDING,
    )
    check("السعر تحدّث في العرض المعاد", float(offer_retry.gross_fare) == 42.0)

    # ------------------------------------------------------------
    # 8) سائق ثانٍ (نضيفه قريبًا) يقدّم عرضًا أفضل
    # ------------------------------------------------------------

    second_driver_user = User.objects.create_user(
        phone="+TEST_DRIVER_2", password="x", role=UserRole.DRIVER
    )
    second_driver = make_driver(second_driver_user, near_point)

    offer2 = MatchingService.create_offer(
        ride_id=ride.id, driver=second_driver, gross_fare=35, eta_minutes=6
    )

    active_offers = list(
        RideOffer.objects.filter(ride=ride).exclude(status=OfferStatus.CANCELLED)
        .order_by("gross_fare")
    )
    check("يوجد عرضان PENDING نشطان قبل الاختيار", len(active_offers) == 2)

    # ------------------------------------------------------------
    # 9) الزبون يختار العرض الأرخص -> ACCEPTED + إلغاء الباقي + DRIVER_ASSIGNED
    # ------------------------------------------------------------

    selected = MatchingService.select_offer(
        ride_id=ride.id, offer_id=offer2.id, customer=customer_user
    )
    ride.refresh_from_db()
    offer_retry.refresh_from_db()

    check("العرض المختار أصبح ACCEPTED", selected.status == OfferStatus.ACCEPTED)
    check("العرض الآخر أصبح CANCELLED تلقائيًا", offer_retry.status == OfferStatus.CANCELLED)
    check("الرحلة أصبحت DRIVER_SELECTED", ride.status == RideStatus.DRIVER_SELECTED)

    # ------------------------------------------------------------
    # 10) محاولة اختيار عرض آخر بعد أن الرحلة أُغلقت -> يجب أن تُرفض
    # ------------------------------------------------------------

    try:
        MatchingService.select_offer(
            ride_id=ride.id, offer_id=offer_retry.id, customer=customer_user
        )
        check("رفض اختيار عرض بعد إغلاق الرحلة", False)
    except MatchingError:
        check("رفض اختيار عرض بعد إغلاق الرحلة", True)

    # ------------------------------------------------------------
    # 11) السائق الفائز أصبح "مشغولاً" في get_busy_driver_ids
    # ------------------------------------------------------------

    busy_ids = set(MatchingService.get_busy_driver_ids())
    check("السائق الفائز يظهر في قائمة المشغولين الآن", second_driver.id in busy_ids)

except Exception:
    print("=== استثناء غير متوقع أثناء الاختبار ===")
    traceback.print_exc()

finally:
    cleanup()

    print("\n===== الملخص =====")
    passed = sum(1 for _, s in results if s == "PASS")
    failed = sum(1 for _, s in results if s == "FAIL")
    print(f"PASS: {passed} | FAIL: {failed} | TOTAL: {len(results)}")
    if failed:
        print("\nالبنود الفاشلة:")
        for label, s in results:
            if s == "FAIL":
                print(f"  - {label}")