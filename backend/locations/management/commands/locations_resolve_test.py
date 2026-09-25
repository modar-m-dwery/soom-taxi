"""
تحقق سريع من ServiceArea + LocationService دون فتح لوحة الإدارة.

الاستخدام:
    python manage.py locations_resolve_test
"""
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from locations.models import ServiceArea
from locations.services import LocationService


class Command(BaseCommand):
    help = "Create/refresh sample ServiceAreas (Jableh, Lattakia) and test area resolution."

    def handle(self, *args, **options):
        jableh, _ = ServiceArea.objects.update_or_create(
            code="JAB",
            defaults=dict(
                name="جبلة",
                # مركز المدينة نفسها. القيمة السابقة (35.9, 35.36) تقع في
                # البحر على بعد ~2.5 كم غرب الساحل: كلّ محاكٍ ضُبط عليها
                # عرض خريطةً زرقاء بلا شارع واحد، وبدا ذلك عطلًا في الرسم.
                center=Point(35.9275, 35.3617, srid=4326),
                fallback_radius_km=Decimal("8"),
                marketplace_cell_precision=5,  # ~4.9كم — يوافق نصف قطر المطابقة؛ 7 أخفى سائقًا على بُعد كيلومتر
                default_matching_radius_km=Decimal("5"),
                is_active=True,
            ),
        )

        lattakia, _ = ServiceArea.objects.update_or_create(
            code="LAT",
            defaults=dict(
                name="اللاذقية",
                center=Point(35.7797, 35.5317, srid=4326),
                fallback_radius_km=Decimal("15"),
                marketplace_cell_precision=5,  # نفس الدقّة في كلّ المدن حتّى يثبت غير ذلك
                default_matching_radius_km=Decimal("7"),
                is_active=True,
            ),
        )

        LocationService.invalidate_cache()  # تأكيد أننا لا نعتمد على TTL في هذا الاختبار

        self.stdout.write(self.style.SUCCESS(f"ServiceArea ready: {jableh}, {lattakia}"))

        test_points = [
            ("داخل جبلة", 35.9275, 35.3617),
            ("داخل اللاذقية", 35.78, 35.53),
            ("خارج كل المناطق (بعيد في البحر)", 34.5, 35.0),
        ]

        for label, lng, lat in test_points:
            area = LocationService.resolve_area(lng, lat)
            cell_id = LocationService.compute_marketplace_cell_id(lng, lat)

            if area:
                self.stdout.write(
                    f"[{label}] -> area={area.code} precision={area.marketplace_cell_precision} "
                    f"cell_id={cell_id}"
                )
            else:
                self.stdout.write(f"[{label}] -> لا توجد منطقة خدمة تغطي هذه النقطة (cell_id={cell_id})")

        # تأكيد أن دقة المدينتين مختلفة فعليًا تنتج معرفات خلايا مختلفة الطول المنطقي
        jab_cell = LocationService.compute_marketplace_cell_id(35.9, 35.36)
        lat_cell = LocationService.compute_marketplace_cell_id(35.78, 35.53)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nJableh cell (precision={jableh.marketplace_cell_precision}): {jab_cell}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Lattakia cell (precision={lattakia.marketplace_cell_precision}): {lat_cell}"
            )
        )