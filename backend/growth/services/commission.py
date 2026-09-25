"""
العمولة: أيّ قاعدة تنطبق على هذا السائق في هذه المدينة، لهذه الخدمة، الآن؟

الأدقّ يغلب (سائق ← مجموعة ← مدينة ← عامّة). داخل النطاق نفسه: المحصورة
بمدينة، ثمّ بخدمة، ثمّ بنافذة وقت، أدقّ من العامّة — وعند التساوي الأحدث.
بلا قاعدة: صفر — وهو سلوك المنصّة قبل هذه الأداة، فلا يتغيّر شيء لم يقرّره
المشغّل.

الساعات بتوقيت دمشق لا UTC: المشغّل يكتب «من 22 إلى 5» ويعني ليل المدينة.
"""

from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

ZERO = Decimal("0.00")
LOCAL_TZ = ZoneInfo("Asia/Damascus")


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CommissionService:

    @staticmethod
    def service_for_ride(ride):
        """رمز الخدمة في الكتالوج لطلبٍ: من نمطه (المشترك) أو فئته (بين المدن…)، وإلّا التكسي."""
        from catalog.services import Catalog

        if ride is None:
            return None
        return (
            Catalog.service_for_mode(getattr(ride, "mode", None))
            or Catalog.service_for_category(getattr(ride, "trip_category", None))
            or "taxi"
        )

    @staticmethod
    def rule_for(driver, area, now=None, service=None):
        from growth.models import CommissionRule

        now = now or timezone.now()
        local_now = now.astimezone(LOCAL_TZ)
        rules = (
            CommissionRule.objects
            .filter(is_active=True)
            .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now))
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        )

        area_id = getattr(area, "id", None)
        driver_id = getattr(driver, "id", None)
        group_ids = (
            list(driver.growth_groups.values_list("id", flat=True))
            if driver is not None else []
        )

        candidates = []
        for rule in rules:
            if rule.service_code and rule.service_code != service:
                continue
            if not rule.applies_at(local_now):
                continue
            if rule.area_id is not None and rule.area_id != area_id:
                continue
            if rule.scope == CommissionRule.Scope.DRIVER and rule.driver_id != driver_id:
                continue
            if rule.scope == CommissionRule.Scope.GROUP and rule.group_id not in group_ids:
                continue
            if rule.scope == CommissionRule.Scope.AREA and rule.area_id is None:
                continue
            candidates.append(rule)

        if not candidates:
            return None

        # مدينةٌ/خدمةٌ/نافذةٌ محدَّدة داخل النطاق نفسه أدقّ من غيابها.
        return max(
            candidates,
            key=lambda r: (
                CommissionRule.SPECIFICITY[r.scope],
                r.area_id is not None,
                bool(r.service_code),
                r.is_windowed,
                r.created_at,
            ),
        )

    @classmethod
    def fee_for(cls, driver, area, gross, now=None, service=None):
        if driver is not None and getattr(driver, "commission_exempt", False):
            return ZERO

        rule = cls.rule_for(driver, area, now, service=service)
        if rule is None:
            return ZERO

        gross = Decimal(gross)
        fee = gross * rule.rate_pct / Decimal("100") + rule.fixed_fee
        if rule.min_fee is not None:
            fee = max(fee, rule.min_fee)
        if rule.max_fee is not None:
            fee = min(fee, rule.max_fee)
        return _money(min(max(fee, ZERO), gross))
