"""
السوم الكامل في المناطق القائمة: حيث يعرض السائق سعره (driver_bidding)
صار الزبون يقترح سعره أيضًا (customer_bidding) — كما تصفه وثيقة المنتج.

لا يلمس منطقةً بتعرفة إلزامية: الجمع بينهما مرفوض في `ServiceArea.clean`.
والعكس (reverse) يزيل الخطّة التي أضافها وحدها.
"""
from django.db import migrations

DRIVER = "driver_bidding"
CUSTOMER = "customer_bidding"
REGULATED = "regulated_tariff"


def enable(apps, schema_editor):
    ServiceArea = apps.get_model("locations", "ServiceArea")
    for area in ServiceArea.objects.all():
        policies = list(area.allowed_pricing_policies or [])
        if DRIVER in policies and CUSTOMER not in policies and REGULATED not in policies:
            policies.append(CUSTOMER)
            area.allowed_pricing_policies = policies
            area.save(update_fields=["allowed_pricing_policies"])


def disable(apps, schema_editor):
    ServiceArea = apps.get_model("locations", "ServiceArea")
    for area in ServiceArea.objects.all():
        policies = list(area.allowed_pricing_policies or [])
        if CUSTOMER in policies and area.default_pricing_policy != CUSTOMER:
            policies.remove(CUSTOMER)
            area.allowed_pricing_policies = policies
            area.save(update_fields=["allowed_pricing_policies"])


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0009_customer_proposal"),
    ]

    operations = [
        migrations.RunPython(enable, disable),
    ]
