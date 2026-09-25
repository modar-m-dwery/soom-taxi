"""
تحقق من طبقة التسعير: يبني أربع مناطق تمثّل الأنماط التنظيمية الأربعة التي
رصدها المسح، ثم يثبت أن كل قاعدة تُطبَّق فعلًا وأن المخالفات تُرفض.

لا يحتاج Daphne ولا Redis ولا سائقين — قاعدة البيانات فقط.

الاستخدام:
    python manage.py pricing_policy_test
    python manage.py pricing_policy_test --cleanup     # حذف مناطق الاختبار بعدها
"""
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from locations.models import (
    PriceChangeWorkflow,
    PricingPolicy,
    ServiceArea,
    SharedDestinationPrecision,
    SurgeMode,
)
from locations.services import LocationService
from pricing.services import PricingPolicyError, PricingService


TEST_CODES = ["TSY", "TJO", "TAE", "TIN"]


class Command(BaseCommand):
    help = "Verify the pricing policy layer across four regulatory patterns."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup", action="store_true")

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0

        areas = self._build_areas()
        LocationService.invalidate_cache()

        self._test_backward_compatibility()
        self._test_free_market(areas["TSY"])
        self._test_regulated_tariff(areas["TJO"])
        self._test_regulator_tiers(areas["TAE"])
        self._test_corridor(areas["TIN"])
        self._test_model_validation()
        self._test_privacy_guardrail(areas["TSY"])

        if options["cleanup"]:
            ServiceArea.objects.filter(code__in=TEST_CODES).delete()
            LocationService.invalidate_cache()
            self.stdout.write(self.style.WARNING("\nمناطق الاختبار حُذفت."))
        else:
            self.stdout.write(self.style.WARNING(
                "\nمناطق الاختبار باقية في لوحة الإدارة لتفحص التشيك بوكس. "
                "أعد التشغيل بـ--cleanup لحذفها."
            ))

        total = self.passed + self.failed
        self.stdout.write("")
        if self.failed == 0:
            self.stdout.write(self.style.SUCCESS(f"Pricing layer: {total}/{total} passed."))
        else:
            self.stderr.write(self.style.ERROR(
                f"Pricing layer: {self.passed}/{total} passed, {self.failed} FAILED."
            ))

    # =================================================================
    # SETUP
    # =================================================================

    def _build_areas(self):
        specs = [
            # --- سوق حرّ: لا نص ينظّم التسعير (سوريا/العراق/الجزائر/تونس)
            dict(
                code="TSY", name="[اختبار] سوق حرّ", country_code="SY",
                currency_code="SYP", center=Point(36.30, 33.51, srid=4326),
                allowed_pricing_policies=[
                    PricingPolicy.PLATFORM_FIXED,
                    PricingPolicy.DRIVER_BIDDING,
                    PricingPolicy.CUSTOMER_BIDDING,
                ],
                default_pricing_policy=PricingPolicy.DRIVER_BIDDING,
                surge_mode=SurgeMode.DISABLED,
                price_change_workflow=PriceChangeWorkflow.NOTIFY,
                regulator_name="الهيئة الناظمة للاتصالات والبريد",
                compliance_note="لم أجد تعرفة ملزمة للتطبيقات — يتطلب تحققًا محليًا.",
            ),
            # --- تعرفة رسمية إلزامية (الأردن)
            dict(
                code="TJO", name="[اختبار] تعرفة إلزامية", country_code="JO",
                currency_code="JOD", center=Point(35.93, 31.95, srid=4326),
                allowed_pricing_policies=[PricingPolicy.REGULATED_TARIFF],
                default_pricing_policy=PricingPolicy.REGULATED_TARIFF,
                surge_mode=SurgeMode.DISABLED,
                regulator_name="هيئة تنظيم قطاع النقل البري (LTRC)",
                legal_reference="نظام تنظيم نقل الركاب عبر التطبيقات الذكية",
            ),
            # --- نوافذ ورسوم تحددها الهيئة + حد أدنى مطلق (دبي)
            dict(
                code="TAE", name="[اختبار] نوافذ الهيئة", country_code="AE",
                currency_code="AED", center=Point(55.27, 25.20, srid=4326),
                allowed_pricing_policies=[PricingPolicy.REGULATED_TARIFF],
                default_pricing_policy=PricingPolicy.REGULATED_TARIFF,
                surge_mode=SurgeMode.REGULATOR_TIERS,
                min_fare_absolute=Decimal("13.00"),
                regulator_name="هيئة الطرق والمواصلات (RTA)",
            ),
            # --- ممر تعرفة + حصة سائق دنيا (الهند)
            dict(
                code="TIN", name="[اختبار] ممر تعرفة", country_code="IN",
                currency_code="INR", center=Point(77.59, 12.97, srid=4326),
                allowed_pricing_policies=[
                    PricingPolicy.TARIFF_CORRIDOR,
                    PricingPolicy.DRIVER_BIDDING,
                ],
                default_pricing_policy=PricingPolicy.TARIFF_CORRIDOR,
                surge_mode=SurgeMode.CAPPED,
                surge_max_multiplier=Decimal("2.00"),
                fare_floor_multiplier=Decimal("0.50"),
                fare_cap_multiplier=Decimal("2.00"),
                driver_min_share_pct=Decimal("80.00"),
                regulator_name="MoRTH — MV Aggregators Guidelines 2025",
            ),
        ]

        areas = {}
        for spec in specs:
            code = spec.pop("code")
            spec.setdefault("fallback_radius_km", Decimal("25"))
            spec.setdefault("is_active", True)
            area, _ = ServiceArea.objects.update_or_create(code=code, defaults=spec)
            areas[code] = area

        self.stdout.write(self.style.SUCCESS(
            f"جاهز: {', '.join(f'{c}' for c in areas)}\n"
        ))
        return areas

    # =================================================================
    # TESTS
    # =================================================================

    def _test_backward_compatibility(self):
        """أهم اختبار: الكود القائم يجب أن يعطي نفس الأرقام بالضبط."""
        q = PricingService.calculate_base_fare(
            mode="standard", distance_km=10, duration_minutes=20
        )

        self._check(q["base_fare"] == Decimal("4000.00"), f"1) base_fare = {q['base_fare']}")
        self._check(q["distance_fare"] == Decimal("8000.00"), f"2) distance_fare = {q['distance_fare']}")
        self._check(q["time_fare"] == Decimal("1600.00"), f"3) time_fare = {q['time_fare']}")
        self._check(q["gross_fare"] == Decimal("13600.00"), f"4) gross_fare = {q['gross_fare']}")
        self._check(q["platform_fee"] == Decimal("0.00"), "5) platform_fee = 0 (قرار MVP)")
        self._check(
            q["driver_net"] == q["customer_total"] == Decimal("13600.00"),
            "6) driver_net = customer_total = gross (بلا عمولة)",
        )

    def _test_free_market(self, area):
        q = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area,
        )
        self._check(
            q["pricing_policy"] == PricingPolicy.DRIVER_BIDDING,
            f"7) السوق الحرّ يطبّق الخطة الافتراضية (مزايدة سائقين): {q['pricing_policy']}",
        )
        self._check(q["currency"] == "SYP", f"8) العملة تتبع المنطقة: {q['currency']}")

        # بلا أرضية ولا سقف -> أي سعر موجب مقبول
        ok = self._expect_ok(
            lambda: PricingService.validate_proposed_fare(
                Decimal("9000"), q, service_area=area, proposer="driver"
            ),
            "9) سوق حرّ يقبل سعر سائق أقل من تسعيرة المنصة",
        )

        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                Decimal("0"), q, service_area=area, proposer="driver"
            ),
            "10) يرفض سعرًا صفريًا",
        )

        # خطة غير مفعّلة في هذه المنطقة
        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                Decimal("9000"), q, service_area=area,
                policy=PricingPolicy.TARIFF_CORRIDOR, proposer="driver",
            ),
            "11) يرفض خطة غير مفعّلة في المنطقة",
        )

    def _test_regulated_tariff(self, area):
        q = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area,
        )

        self._expect_ok(
            lambda: PricingService.validate_proposed_fare(
                q["gross_fare"], q, service_area=area, proposer="driver"
            ),
            "12) التعرفة الإلزامية تقبل السعر الرسمي بالضبط",
        )

        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                q["gross_fare"] - Decimal("1"), q, service_area=area, proposer="driver"
            ),
            "13) وترفض أي خصم عنه ولو بوحدة واحدة",
        )

        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                q["gross_fare"] + Decimal("500"), q, service_area=area, proposer="customer"
            ),
            "14) وترفض أي اقتراح من الزبون (لا مساومة على تعرفة رسمية)",
        )

    def _test_regulator_tiers(self, area):
        # رحلة قصيرة جدًا: الأجرة المحسوبة أقل من الحد الأدنى المطلق
        q = PricingService.quote(
            mode="standard", distance_km=0.1, duration_minutes=1,
            service_area=area,
        )
        # base 4000 يتجاوز 13 أصلًا، فنختبر الحد الأدنى بقيمة صغيرة مصطنعة:
        self._check(
            q["min_fare_applied"] is False,
            "15) الحد الأدنى لا يُطبَّق حين تتجاوزه الأجرة المحسوبة",
        )

        # المنصة لا تحسب مضاعِفًا في نمط نوافذ الهيئة
        q2 = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area, surge_multiplier=Decimal("3.0"),
        )
        self._check(
            q2["surge_multiplier"] == Decimal("1") and q2["surge_source"] == "regulator",
            f"16) نوافذ الهيئة تتجاهل أي مضاعِف من المنصة "
            f"(multiplier={q2['surge_multiplier']}, source={q2['surge_source']})",
        )

        # الرسم الثابت الذي تفرضه الهيئة يُضاف
        q3 = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area, regulator_surcharge=Decimal("7.50"),
        )
        self._check(
            q3["gross_fare"] == q2["gross_fare"] + Decimal("7.50"),
            f"17) رسم الذروة الرسمي يُضاف كمبلغ ثابت: {q3['gross_fare']}",
        )

    def _test_corridor(self, area):
        q = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area,
        )

        self._check(
            q["fare_floor"] == Decimal("6800.00") and q["fare_cap"] == Decimal("27200.00"),
            f"18) الممر محسوب من التسعيرة: [{q['fare_floor']} — {q['fare_cap']}]",
        )

        self._expect_ok(
            lambda: PricingService.validate_proposed_fare(
                Decimal("10000"), q, service_area=area,
                policy=PricingPolicy.DRIVER_BIDDING, proposer="driver",
            ),
            "19) يقبل مزايدة داخل الممر",
        )

        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                Decimal("5000"), q, service_area=area,
                policy=PricingPolicy.DRIVER_BIDDING, proposer="driver",
            ),
            "20) يرفض ما دون الأرضية (حماية دخل السائق)",
        )

        self._expect_error(
            lambda: PricingService.validate_proposed_fare(
                Decimal("30000"), q, service_area=area,
                policy=PricingPolicy.DRIVER_BIDDING, proposer="driver",
            ),
            "21) يرفض ما فوق السقف (حماية الزبون)",
        )

        # السقف الأقصى للتسعير الديناميكي
        q2 = PricingService.quote(
            mode="standard", distance_km=10, duration_minutes=20,
            service_area=area, surge_multiplier=Decimal("5.0"),
        )
        self._check(
            q2["surge_multiplier"] == Decimal("2.00"),
            f"22) مضاعِف 5.0 يُقصّ إلى السقف القانوني 2.0 "
            f"(الناتج {q2['surge_multiplier']})",
        )

    def _test_model_validation(self):
        base = dict(
            name="[اختبار] تحقق", center=Point(10.0, 10.0, srid=4326),
            fallback_radius_km=Decimal("10"),
        )

        # تناقض منطقي: تعرفة إلزامية + مزايدة
        a = ServiceArea(
            code="TVAL", **base,
            allowed_pricing_policies=[
                PricingPolicy.REGULATED_TARIFF, PricingPolicy.DRIVER_BIDDING
            ],
            default_pricing_policy=PricingPolicy.REGULATED_TARIFF,
        )
        self._expect_error(
            a.full_clean,
            "23) يرفض الجمع بين تعرفة إلزامية ومزايدة",
            exc=ValidationError,
        )

        # الخطة الافتراضية خارج المسموح
        b = ServiceArea(
            code="TVAL", **base,
            allowed_pricing_policies=[PricingPolicy.PLATFORM_FIXED],
            default_pricing_policy=PricingPolicy.CUSTOMER_BIDDING,
        )
        self._expect_error(
            b.full_clean,
            "24) يرفض خطة افتراضية غير مفعّلة",
            exc=ValidationError,
        )

        # ممر بلا حدود
        c = ServiceArea(
            code="TVAL", **base,
            allowed_pricing_policies=[PricingPolicy.TARIFF_CORRIDOR],
            default_pricing_policy=PricingPolicy.TARIFF_CORRIDOR,
        )
        self._expect_error(
            c.full_clean,
            "25) يرفض ممر تعرفة بلا أرضية وسقف",
            exc=ValidationError,
        )

        # مهلة افتراضية خارج الخيارات
        d = ServiceArea(
            code="TVAL", **base,
            allowed_pricing_policies=[PricingPolicy.PLATFORM_FIXED],
            default_pricing_policy=PricingPolicy.PLATFORM_FIXED,
            invitation_ttl_options=[20, 40, 60],
            invitation_ttl_default=35,
        )
        self._expect_error(
            d.full_clean,
            "26) يرفض مهلة افتراضية خارج قائمة الخيارات",
            exc=ValidationError,
        )

        # بلا حدود ولا مركز
        e = ServiceArea(
            code="TVAL", name="x",
            allowed_pricing_policies=[PricingPolicy.PLATFORM_FIXED],
            default_pricing_policy=PricingPolicy.PLATFORM_FIXED,
        )
        self._expect_error(
            e.full_clean,
            "27) يرفض منطقة بلا حدود ولا مركز",
            exc=ValidationError,
        )

    def _test_privacy_guardrail(self, area):
        """الحاجز الذي طلبتَ أن يقرره الأدمن — لكن ضمن حدود."""
        area.shared_destination_precision = 7  # ~150م = حيّ بعينه
        self._expect_error(
            area.full_clean,
            "28) يرفض دقّة وجهة أدقّ من ~1.2كم (منع كشف الحيّ)",
            exc=ValidationError,
        )

        area.shared_destination_precision = SharedDestinationPrecision.FINE
        cell = LocationService.coarse_destination_cell(36.30, 33.51, area=area)
        self._check(
            len(cell) == 6,
            f"29) الوجهة المُقرَّبة بدقّة الأدمن: {cell} (طول {len(cell)})",
        )

        area.shared_destination_precision = SharedDestinationPrecision.COARSE
        cell = LocationService.coarse_destination_cell(36.30, 33.51, area=area)
        self._check(len(cell) == 4, f"30) وبحماية قصوى: {cell} (طول {len(cell)})")

        area.shared_destination_precision = SharedDestinationPrecision.BALANCED
        area.save(update_fields=["shared_destination_precision"])

    # =================================================================
    # HELPERS
    # =================================================================

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
        else:
            self.failed += 1
            self.stderr.write(self.style.ERROR(f"[FAIL] {label}"))
        return condition

    def _expect_ok(self, fn, label):
        try:
            fn()
        except Exception as exc:
            self.failed += 1
            self.stderr.write(self.style.ERROR(
                f"[FAIL] {label}: رُفض بينما كان يجب أن يُقبل -> {exc}"
            ))
            return False
        self.passed += 1
        self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
        return True

    def _expect_error(self, fn, label, exc=PricingPolicyError):
        try:
            fn()
        except exc:
            self.passed += 1
            self.stdout.write(self.style.SUCCESS(f"[OK]   {label}"))
            return True
        except Exception as other:
            self.failed += 1
            self.stderr.write(self.style.ERROR(
                f"[FAIL] {label}: استثناء من نوع غير متوقع -> "
                f"{type(other).__name__}: {other}"
            ))
            return False
        self.failed += 1
        self.stderr.write(self.style.ERROR(
            f"[FAIL] {label}: قُبل بينما كان يجب أن يُرفض"
        ))
        return False
