from django.conf import settings


class PresenceState:
    """
    الحالة المركّبة للسائق - ليست Boolean واحد، بل استنتاج من عدة إشارات
    (online flag + heartbeat freshness + location freshness + engagement + seats).
    """
    PRESENT = "present"          # متصل، heartbeat وموقع حديثان، متاح فعليًا
    STALE = "stale"              # متصل لكن heartbeat تجاوز الحد الآمن
    OFFLINE = "offline"          # غير متصل / انتهت صلاحيته
    BUSY = "busy"                # مرتبط برحلة نشطة ولا مقعد فيه لأحد
    UNAVAILABLE = "unavailable"  # حاضر لكن لا مقاعد / لا موقع حديث / غير مؤهل

    # جديد (المرحلة 8ب): على رحلة مشتركة وفيه مقعد فارغ.
    #
    # ليست BUSY وليست PRESENT: هي حالة ثالثة صريحة لأن الجواب على سؤال
    # "هل هذا السائق متاح؟" صار يعتمد على مَن يسأل. متاح لراكب مشترك مسارُه
    # موافق، وغير متاح لراكب يريد سيارة لنفسه. اختزالها في Boolean هو ما
    # كان يجعل المشاركة غير قابلة للعرض على الخريطة أصلًا.
    SHARING = "sharing"


# نمط الرحلة المشتركة كما هو مكتوب في rides.models.RideMode.SHARED.
#
# نكرّره هنا كنص بدل استيراد rides داخل presence: طبقة الحضور يجب أن تبقى
# تحت طبقة الطلبات لا فوقها، وإلا صار الاستيراد دائريًا عند أول توسّع.
# اختبار test_sharing_presence_e2e يتحقق من تطابق القيمتين كفحص أول، فلو
# غُيّر أحدهما يومًا سقط الفحص فورًا بدل أن يصمت النظام.
SHARED_MODE = "shared"


# القيم الافتراضية، تُضبط عبر settings.py وتُعاد معايرتها ميدانيًا
HEARTBEAT_FRESH_SECONDS = getattr(settings, "PRESENCE_HEARTBEAT_FRESH_SECONDS", 30)
HEARTBEAT_STALE_SECONDS = getattr(settings, "PRESENCE_HEARTBEAT_STALE_SECONDS", 60)

# عمر الموقع المقبول. نقطة #9 في خطة المرحلة 6 تنص صراحةً على أن
# "Driver Available" تتطلب location fresh وليس heartbeat fresh فقط. بدون هذا
# الفحص، سائق أرسل نبضات heartbeat فقط (بلا GPS) لعشر دقائق يبقى PRESENT
# بموقع قديم - وهو بالضبط ما يجعل الماركت بليس يكذب على الزبون.
LOCATION_FRESH_SECONDS = getattr(
    settings,
    "PRESENCE_LOCATION_FRESH_SECONDS",
    getattr(settings, "MATCHING_LOCATION_MAX_AGE_SECONDS", 60),
)

# اسم المفاتيح في Redis - منظمة ومحصورة بمكان واحد
PRESENCE_KEY_PREFIX = "presence:driver:"   # Hash لكل سائق (تفاصيل كاملة)
LAST_SEEN_KEY = "drivers:last_seen"        # ZSET (score=timestamp) لمعرفة من حيّ

# فهرس جغرافي واحد لكلّ المدن — وهذا قرار مقصود، لا سهوٌ ينتظر «إصلاحًا».
#
# الاقتراح الطبيعي عند قراءة هذا السطر هو تقسيمه: مفتاح لكلّ منطقة، فيصير
# بحث جبلة لا يمرّ على سائقي اللاذقية. المشكلة أنّ ذلك يكسر سلوكًا صحيحًا.
#
# البحث عن السيارات القريبة يفلتر بالمسافة فقط، بلا شرط منطقة — عمدًا. زبون
# على حافّة جبلة أقرب سيارة إليه قد تكون على بُعد أربعمئة متر خلف الحدّ
# الإداري. تقسيمُ المفتاح يُخفي تلك السيارة عنه، فيخسر الزبون رحلته ويخسر
# السائق أجرته، لأنّ خطًّا على خريطة إدارية قال ذلك.
#
# الحدود الإدارية تحكم القواعد (التعرفة، المهل، من يوثّق) لا الفيزياء. لذلك
# القواعد تُقرأ من ServiceArea، والقرب يُقاس من فهرس واحد.
#
# ومقياس الحجم يطمئن: الفهرس sorted set على geohash، وعشرات الآلاف من
# السائقين فيه تبقى ضمن ميلي ثانية واحدة. حين يصير عنقًا فعليًّا، التقسيم
# الصحيح جغرافيّ (شبكة مربّعات متجاورة) لا إداريّ.
GEO_KEY = "drivers:geo"

# حقول الارتباط برحلة. مجموعة واحدة تُكتب وتُمحى معًا، فلا يبقى منها بقايا
# متناقضة (sharing=1 بلا dest_cell مثلًا).
ENGAGEMENT_FIELDS = ("busy", "sharing", "trip_mode", "dest_cell", "free_seats")
