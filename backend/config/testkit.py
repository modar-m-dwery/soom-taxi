"""
مصانع بيانات الاختبار.

سبب وجود هذا الملفّ: أوامر E2E الأحد عشر تكرّر بينها آلاف الأسطر من
تهيئة البيانات نفسها — مستخدم، سائق، مركبة، منطقة خدمة، طلب. التكرار هو
ما جعل تحويلها إلى اختبارات حقيقية يبدو عملًا ضخمًا، وهو ما يجعل تعديل
حقل واحد في نموذج يكسر أحد عشر ملفًّا.

كل ما هنا نقيّ من منطق الأعمال: يبني بيانات ولا يدّعي شيئًا. الادّعاءات
في ملفّات الاختبار.

الاستخدام:

    from config.testkit import make_customer, make_driver, make_ride

    class MyTests(APITestCase):
        def setUp(self):
            self.customer = make_customer()
            self.driver = make_driver()
"""
import itertools
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.authtoken.models import Token

from rides.models import RideMode, RideRequest, RideStatus, TripCategory
from trips.models import Trip, TripStatus
from users.models import CustomerProfile, DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleType


# عدّادات تضمن تفرّد الهواتف واللوحات بين الاختبارات داخل نفس التشغيل.
_phone_counter = itertools.count(1)
_plate_counter = itertools.count(1)

#: جبلة — تطابق منطقة الخدمة التي ينشئها locations_resolve_test.
JABLEH = (35.90, 35.36)          # (lng, lat)
JABLEH_NEARBY = (35.91, 35.37)
LATTAKIA = (35.7797, 35.5317)


def _next_phone(prefix="+96399"):
    return f"{prefix}{next(_phone_counter):07d}"


def point(lng_lat):
    lng, lat = lng_lat
    return Point(lng, lat, srid=4326)


# =====================================================================
# المستخدمون
# =====================================================================

def make_customer(phone=None, **kwargs):
    user = User.objects.create_user(
        phone=phone or _next_phone(),
        password="test-pass",
        role=UserRole.CUSTOMER,
        is_verified=True,
        **kwargs,
    )
    CustomerProfile.objects.get_or_create(user=user)
    return user


def make_admin(phone=None, is_staff=True, **kwargs):
    """
    الأدمن يُنشأ بـ`is_staff=True` افتراضيًا لأن مسارات `/ops/` تفحص
    العَلَم لا الدور. اختبار يبني أدمن بالدور وحده سيصطدم بـ403 —
    وهو بالضبط الفخّ الذي يجب أن يوثّقه المصنع لا أن يعيد إنتاجه.
    """
    return User.objects.create_user(
        phone=phone or _next_phone(),
        password="test-pass",
        role=UserRole.ADMIN,
        is_verified=True,
        is_staff=is_staff,
        **kwargs,
    )


def make_driver(
    phone=None,
    status=None,
    online=True,
    location=JABLEH,
    seats=4,
    with_vehicle=True,
    fresh_location=True,
):
    """
    يبني سائقًا جاهزًا للمطابقة.

    `fresh_location=True` مهمّ: المطابقة ترفض أي سائق مضى على موقعه أكثر
    من `MATCHING_LOCATION_MAX_AGE_SECONDS`. اختبار ينسى ضبط
    `last_location_at` يفشل بقائمة مرشّحين فارغة بلا رسالة مفيدة.
    """
    user = User.objects.create_user(
        phone=phone or _next_phone(),
        password="test-pass",
        role=UserRole.DRIVER,
        is_verified=True,
    )

    profile = DriverProfile.objects.create(
        user=user,
        status=status or DriverProfile.DriverStatus.ACTIVE,
        online=online,
        current_location=point(location),
        available_seats=seats,
        last_location_at=timezone.now() if fresh_location else None,
    )

    if with_vehicle:
        make_vehicle(profile, seats=seats)

    return profile


def make_vehicle(driver_profile, seats=4, active=True, vehicle_type=None):
    return Vehicle.objects.create(
        driver=driver_profile,
        type_id=vehicle_type or "taxi",
        make="Toyota",
        model="Corolla",
        year=2022,
        color="White",
        plate_number=f"TEST-{next(_plate_counter):05d}",
        seats=seats,
        active=active,
    )


def token_for(user_or_profile):
    """
    يعيد مفتاح التوكن. يقبل مستخدمًا أو ملفّ سائق، فلا يضطر الاختبار
    للتنقّل بين الاثنين.
    """
    user = getattr(user_or_profile, "user", user_or_profile)
    token, _created = Token.objects.get_or_create(user=user)
    return token.key


def auth(client, user_or_profile):
    """يفوّض عميل الاختبار. يعيد المفتاح للاستخدام المباشر إن لزم."""
    key = token_for(user_or_profile)
    client.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return key


# =====================================================================
# الطلبات والرحلات
# =====================================================================

def make_ride(
    customer,
    pickup=JABLEH,
    destination=JABLEH_NEARBY,
    mode=RideMode.FAST,
    status=RideStatus.SEARCHING,
    passenger_count=1,
    gross_fare="25000.00",
    platform_fee="0.00",
    currency="SYP",
    **kwargs,
):
    """
    يُنشئ طلبًا **بلقطة تسعير جاهزة**، متجاوزًا `RideRequestService`.

    التجاوز مقصود: الخدمة تنادي مزوّد المسار عبر الشبكة، واختبار وحدة
    يجب ألّا يعتمد على الإنترنت. الاختبارات التي تفحص التسعير نفسه
    تستدعي الخدمة صراحةً بدل استخدام هذا المصنع.
    """
    gross = Decimal(gross_fare)
    fee = Decimal(platform_fee)

    return RideRequest.objects.create(
        customer=customer,
        pickup=point(pickup),
        destination=point(destination),
        mode=mode,
        trip_category=kwargs.pop("trip_category", TripCategory.CITY),
        passenger_count=passenger_count,
        status=status,
        gross_fare=gross,
        platform_fee=fee,
        customer_total=gross,
        driver_net=gross - fee,
        currency=currency,
        estimated_distance_km=Decimal("3.00"),
        estimated_duration_minutes=8,
        route_distance_km=Decimal("3.20"),
        route_duration_minutes=9,
        **kwargs,
    )


def make_trip(ride, driver, status=TripStatus.IN_PROGRESS, **kwargs):
    vehicle = driver.vehicles.filter(active=True).first()

    return Trip.objects.create(
        ride=ride,
        driver=driver,
        customer=ride.customer,
        vehicle=vehicle,
        status=status,
        final_fare=ride.customer_total,
        currency=ride.currency,
        **kwargs,
    )


def make_completed_trip(customer=None, driver=None, gross_fare="25000.00",
                        platform_fee="0.00", **ride_kwargs):
    """
    الاختصار الأكثر استخدامًا في اختبارات الدفع: رحلة منتهية جاهزة
    لفتح دفعة عليها.
    """
    customer = customer or make_customer()
    driver = driver or make_driver()

    ride = make_ride(
        customer,
        status=RideStatus.COMPLETED,
        gross_fare=gross_fare,
        platform_fee=platform_fee,
        **ride_kwargs,
    )

    trip = make_trip(
        ride,
        driver,
        status=TripStatus.COMPLETED,
        completed_at=timezone.now(),
        started_at=timezone.now(),
        distance_m=3200,
        duration_s=540,
    )

    return trip


def make_accepted_offer(ride, driver, gross_fare=None, eta_minutes=3):
    """
    عرض مقبول — هو ما يربط السائق بالرحلة في كل أنحاء النظام.

    ليس تفصيلًا: `MatchingService.get_busy_driver_ids` و
    `DriverRoomConsumer` و`RideConsumer` و`ResumeService` كلها تعرّف
    "سائق هذه الرحلة" بوجود عرض مقبول حصرًا. اختبار يربط السائق بطريقة
    أخرى يختبر شيئًا لا وجود له في الإنتاج.
    """
    from datetime import timedelta

    from matching.models import OfferStatus, RideOffer

    now = timezone.now()

    return RideOffer.objects.create(
        ride=ride,
        driver=driver,
        gross_fare=Decimal(gross_fare) if gross_fare else ride.gross_fare,
        eta_minutes=eta_minutes,
        status=OfferStatus.ACCEPTED,
        expires_at=now + timedelta(seconds=30),
        accepted_at=now,
    )
