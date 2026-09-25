"""
حقل فئة المركبة — تحقّق من القاعدة لا من enum مجمَّد.

المشكلة التي يحلّها: `ChoiceField(choices=VehicleType.choices)` يُقرأ مرّة
واحدة عند استيراد الوحدة. الفئات صارت صفوفًا يضيفها المشغّل وقت التشغيل،
فحقلٌ يحمل نسخته من القائمة يرفض فئةً أُضيفت بعد آخر إقلاع — وهو بالضبط
العطل الذي يجعل «ديناميكي» كلمةً لا وصفًا.

ولماذا لا `SlugRelatedField` مباشرةً: لأنّه يقبل أيّ فئة موجودة، ولو كانت
معطّلة أو غير متاحة في مدينة المستخدم. الفرق بين «موجودة» و«متاحة لك الآن»
هو ما يمنع سائقًا من تسجيل مركبة بفئة أُخفيت الأسبوع الماضي.
"""
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from vehicles.models import VehicleCategory


@extend_schema_field({
    "type": "string",
    "description": (
        "Vehicle category code. The valid set is dynamic — operators add and "
        "retire categories from the admin panel — so it is deliberately not "
        "published as an enum here. Read the current list from "
        "GET /api/v1/config/ (`vehicle_categories[].code`)."
    ),
    "example": "taxi",
})
class VehicleCategoryField(serializers.Field):
    """
    يقبل الرمز النصّي، ويرجّع الرمز النصّي، ويتحقّق من القاعدة بينهما.

    في المخطّط يظهر نصًّا لا enum — وهذا صادق: القيم المسموحة تتغيّر بلا
    إصدار جديد من الخادم، ونشرها في المخطّط يعِد العميل بثباتٍ لا وجود له.
    مصدرها الصحيح هو /api/v1/config/.
    """

    default_error_messages = {
        "unknown": "فئة المركبة '{value}' غير معروفة أو غير متاحة الآن.",
        "invalid": "فئة المركبة يجب أن تكون رمزًا نصّيًّا.",
    }

    def __init__(self, *args, **kwargs):
        self.area_getter = kwargs.pop("area_getter", None)
        kwargs.setdefault(
            "help_text",
            "رمز فئة المركبة. القيم المتاحة تأتي من GET /api/v1/config/.",
        )
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        # القيمة قد تكون الكائن (من ModelSerializer) أو الرمز (من dict).
        return getattr(value, "code", value)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")

        code = data.strip().lower()
        area = self.area_getter(self.context) if self.area_getter else None

        if code not in VehicleCategory.active_codes(area):
            self.fail("unknown", value=data)

        return code

    def get_attribute(self, instance):
        # نلتقط الرمز مباشرةً من عمود المفتاح الأجنبي: `instance.type` يجلب
        # الصفّ من القاعدة، و`instance.type_id` هو الرمز نفسه بلا استعلام.
        if hasattr(instance, "type_id"):
            return instance.type_id
        return super().get_attribute(instance)


class VehicleCategoryCodeField(VehicleCategoryField):
    """نفسه لكن بلا ربط بعمود type — لحقول مثل requested_vehicle_type."""

    def get_attribute(self, instance):
        return serializers.Field.get_attribute(self, instance)
