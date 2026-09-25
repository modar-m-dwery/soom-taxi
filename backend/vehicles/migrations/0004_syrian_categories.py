"""
فئات المركبات كما يسمّيها الناس في سوريا.

«سيدان» و«هاتشباك» و«دفع رباعي» مفردات كتالوجات لا مفردات شارع. الزبون
في جبلة يقول «تكسي» أو «خصوصي» أو «جيب» أو «ميكرو»، والسائق يسجّل سيارته
بالاسم نفسه. ولأنّ التطبيقين وكتالوج واتساب ودفتر الطلبات تقرأ كلّها من
هذا الجدول (عبر /config/)، فتغييره هنا يغيّر المفردات في كلّ مكان دفعةً
واحدة — وهذا هو الترابط المطلوب بين مرحلة واتساب والتطبيق.

القرارات:

١. الفئات القديمة لا تُحذف بل تُطفأ (is_active=False). الرمز مفتاحٌ
   أساسيّ ومركباتٌ قائمة قد تشير إليه، والحذف يسقط بـPROTECT.
٢. المركبات المسجَّلة بالرموز القديمة تُنقل إلى أقرب فئة سورية:
   sedan/hatchback → taxi، suv → jeep. (van يبقى van بالاسم الجديد.)
٣. الرموز الجديدة إنجليزية قصيرة ثابتة — هي ما يخزّنه التطبيق ويكتبه
   موظّف واتساب في عمود category — والأسماء العربية هي ما يراه الناس.
٤. «تكتك» مزروعة لكن مطفأة: المشغّل يفعّلها من لوحة الإدارة حين تظهر في
   مدينته، بلا ترحيل.
٥. fare_multiplier يبقى 1 للجميع: الحقل لا يدخل في حساب الأجرة اليوم
   (يُخزَّن ولا يُقرأ)، ورقمٌ يوحي بتسعير لا يحدث أسوأ من رقم محايد.
"""

from django.db import migrations

SYRIAN = [
    # code, name, name_en, seats, sort_order, is_active
    ("taxi", "تكسي", "Taxi", 4, 10, True),
    ("private", "خصوصي", "Private car", 4, 20, True),
    ("jeep", "جيب", "4x4", 4, 30, True),
    ("van", "فان", "Van", 7, 40, True),
    ("micro", "ميكرو", "Microbus", 12, 50, True),
    ("tuktuk", "تكتك", "Tuk-tuk", 3, 60, False),
]

REMAP = {"sedan": "taxi", "hatchback": "taxi", "suv": "jeep"}


def forwards(apps, schema_editor):
    VehicleCategory = apps.get_model("vehicles", "VehicleCategory")
    Vehicle = apps.get_model("vehicles", "Vehicle")
    RideRequest = apps.get_model("rides", "RideRequest")

    for code, name, name_en, seats, sort_order, is_active in SYRIAN:
        VehicleCategory.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "name_en": name_en,
                "seats": seats,
                "sort_order": sort_order,
                "is_active": is_active,
            },
        )

    for old, new in REMAP.items():
        Vehicle.objects.filter(type_id=old).update(type_id=new)
        RideRequest.objects.filter(requested_vehicle_type=old).update(
            requested_vehicle_type=new
        )

    VehicleCategory.objects.filter(code__in=REMAP).update(is_active=False, sort_order=900)


def backwards(apps, schema_editor):
    VehicleCategory = apps.get_model("vehicles", "VehicleCategory")
    Vehicle = apps.get_model("vehicles", "Vehicle")
    RideRequest = apps.get_model("rides", "RideRequest")

    VehicleCategory.objects.filter(code__in=REMAP).update(is_active=True)
    Vehicle.objects.filter(type_id="taxi").update(type_id="sedan")
    Vehicle.objects.filter(type_id="private").update(type_id="sedan")
    Vehicle.objects.filter(type_id="jeep").update(type_id="suv")
    RideRequest.objects.filter(requested_vehicle_type__in=["taxi", "private"]).update(
        requested_vehicle_type="sedan"
    )
    RideRequest.objects.filter(requested_vehicle_type="jeep").update(
        requested_vehicle_type="suv"
    )
    VehicleCategory.objects.filter(code="van").update(name="فان", seats=8)
    VehicleCategory.objects.filter(
        code__in=["taxi", "private", "jeep", "micro", "tuktuk"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("vehicles", "0003_seed_default_categories"),
        ("rides", "0011_riderequest_route_source_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
