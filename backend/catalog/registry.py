"""
سجلّ الخدمات والميزات — ما تعرفه الشيفرة، لا ما قرّره المشغّل.

القسمة مقصودة:

- **التعريف** هنا، في الشيفرة: رمزٌ ثابت، اسمٌ افتراضيّ، وأين يُفرض.
  خدمةٌ جديدة (تأجير سيارات، نقل عفش) تُسجِّل نفسها من تطبيقها في
  `AppConfig.ready` — لا تعديل في هذا الملفّ ولا في غيره.
- **الحالة** في القاعدة (`catalog.models`): مفعّلة أم لا، لكلّ المنصّة أو
  لمدينة بعينها. يغيّرها المشغّل من الأدمن فيسري الأثر فورًا بلا إصدار.

`sync_definitions` بعد كلّ ترحيل ينشئ الصفوف الناقصة ولا يمسّ الموجودة:
ما أطفأه المشغّل يبقى مطفأً.
"""

from dataclasses import dataclass, field


class ServiceStatus:
    ACTIVE = "active"
    COMING_SOON = "coming_soon"   # تظهر للزبون بشارة «قريبًا» — تسويقٌ قبل الإطلاق
    HIDDEN = "hidden"

    CHOICES = [
        (ACTIVE, "مفعّلة"),
        (COMING_SOON, "قريبًا"),
        (HIDDEN, "مخفيّة"),
    ]


@dataclass(frozen=True)
class ServiceDefinition:
    code: str
    name: str
    name_en: str
    icon: str
    description: str = ""
    sort_order: int = 100
    default_status: str = ServiceStatus.ACTIVE
    # الربط بمحرّك الرحلات حين تكون الخدمة شكلًا من أشكال الطلب:
    ride_mode: str | None = None
    trip_category: str | None = None


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    description: str
    default: bool = True


SERVICES: dict[str, ServiceDefinition] = {}
FEATURES: dict[str, FeatureDefinition] = {}


def register_service(definition: ServiceDefinition):
    SERVICES[definition.code] = definition
    return definition


def register_feature(definition: FeatureDefinition):
    FEATURES[definition.key] = definition
    return definition


# ---------------------------------------------------------------------
# المبنيّ اليوم
# ---------------------------------------------------------------------

register_service(ServiceDefinition(
    "taxi", "تكسي", "Taxi", "local_taxi",
    "المشوار داخل المدينة: عروض، الأقرب، أو اختر سيارتك.", 10,
))
register_service(ServiceDefinition(
    "shared", "مشترك", "Shared", "groups",
    "تقاسم السيارة مع ركّاب بطريقك بسعرٍ أقلّ.", 20, ride_mode="shared",
))
register_service(ServiceDefinition(
    "intercity", "بين المدن", "Intercity", "route",
    "مشوار من مدينة إلى أخرى.", 30, trip_category="intercity",
))
register_service(ServiceDefinition(
    "service_line", "سرفيس", "Service line", "directions_bus",
    "خطّ سرفيس بمقعد.", 40, trip_category="service_line",
))
register_service(ServiceDefinition(
    "published_trips", "السفريات", "Trips", "event_seat",
    "رحلات ينشرها السائقون بين المدن وللنزهات — احجز مقعدًا.", 50,
))
register_service(ServiceDefinition(
    "morning_subscription", "اشتراك الصباح", "Morning ride", "wb_twilight",
    "مشوار يوميّ ثابت يُطلب تلقائيًّا قبل موعده.", 60,
))

# ---------------------------------------------------------------------
# خدماتٌ قادمة — تظهر «قريبًا» حتّى تُبنى، ويطفئها المشغّل إن شاء
# ---------------------------------------------------------------------

register_service(ServiceDefinition(
    "car_rental", "تأجير سيارات", "Car rental", "car_rental",
    "سيارة مع سائق أو بدونه، باليوم.", 110, ServiceStatus.COMING_SOON,
))
register_service(ServiceDefinition(
    "cargo", "نقل خضرة ودواجن", "Produce & poultry", "local_shipping",
    "سوزوكي وبيك آب لنقل البضائع.", 120, ServiceStatus.COMING_SOON,
))
register_service(ServiceDefinition(
    "furniture", "نقل عفش", "Furniture moving", "chair",
    "نقل فرش البيت مع عمّال.", 130, ServiceStatus.COMING_SOON,
))
register_service(ServiceDefinition(
    "wedding_convoy", "عراضة وأعراس", "Weddings", "celebration",
    "مواكب الأعراس والحفلات.", 140, ServiceStatus.COMING_SOON,
))

# ---------------------------------------------------------------------
# الميزات
# ---------------------------------------------------------------------

register_feature(FeatureDefinition("nearest", "«الأقرب»: الخادم يرسل أقرب سائق تلقائيًّا."))
register_feature(FeatureDefinition("pick_car", "«اختر سيارتك»: الزبون يختار سيارة من الخريطة."))
register_feature(FeatureDefinition("search_radius", "الزبون يختار نطاق البحث."))
register_feature(FeatureDefinition("scheduled_rides", "الحجز في موعد لاحق."))
register_feature(FeatureDefinition("referral", "زبونٌ يجلب زبونًا — رمز الدعوة ومكافأتها."))
register_feature(FeatureDefinition("first_ride_discount", "خصم أوّل مشوار."))
register_feature(FeatureDefinition("telegram_channel", "ربط تليغرام قناةً للإشعارات."))
register_feature(FeatureDefinition("ads", "أماكن الإعلانات في التطبيق.", default=False))
