"""
إكمال فئات المركبات الأربع.

الترحيل 0002 كما هو في هذا المستودع ينشئ جدول VehicleCategory، ويزرع
**فئة واحدة** (sedan) قبل تحويل Vehicle.type إلى مفتاح أجنبي — وهو ما
يكفي لمنع خرق التكامل المرجعي، ولا يكفي للتطبيق.

فنقطة /config/ تُرجع `vehicle_categories` وعليها يبني الزبون قائمة
الاختيار. بصفٍّ واحد يرى المستخدم خيارًا واحدًا لا أربعة، وشاشة اختيار
بخيار وحيد تبدو عطلًا لا تصميمًا.

القيم هي أعضاء VehicleType الأربعة الأصلية، وهو ما يذكره تعليق النموذج
صراحةً: الـenum بقي «لزرع الافتراضات في أوّل ترحيل».

الزرع بـupdate_or_create لا create: يمرّ فوق sedan المزروعة في 0002 بلا
خطأ، ويُعاد تشغيله بلا أثر جانبيّ.
"""
from django.db import migrations


DEFAULTS = [
    ("sedan", "سيدان", "Sedan", 4, 10),
    ("hatchback", "هاتشباك", "Hatchback", 4, 20),
    ("suv", "دفع رباعي", "SUV", 6, 30),
    ("van", "فان", "Van", 8, 40),
]


def seed(apps, schema_editor):
    VehicleCategory = apps.get_model("vehicles", "VehicleCategory")
    for code, name, name_en, seats, sort_order in DEFAULTS:
        VehicleCategory.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "name_en": name_en,
                "seats": seats,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    # sedan لا تُحذف: 0002 يزرعها ومركباتٌ قائمة قد تشير إليها،
    # والحذف يسقط بـPROTECT على Vehicle.type.
    VehicleCategory = apps.get_model("vehicles", "VehicleCategory")
    VehicleCategory.objects.filter(
        code__in=[row[0] for row in DEFAULTS if row[0] != "sedan"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0002_vehiclecategory_alter_vehicle_type"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]