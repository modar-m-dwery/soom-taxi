"""
العمولة: أيّ قاعدة تنطبق على هذا السائق في هذه المدينة الآن؟

الأدقّ يغلب (سائق ← مجموعة ← مدينة ← عامّة)، وعند التساوي الأحدث. بلا
قاعدة: صفر — وهو سلوك المنصّة قبل هذه الأداة، فلا يتغيّر شيء لم يقرّره
المشغّل.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone

ZERO = Decimal("0.00")


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CommissionService:

    @staticmethod
    def rule_for(driver, area, now=None):
        from growth.models import CommissionRule

        now = now or timezone.now()
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

        # مدينةٌ محدَّدة داخل النطاق نفسه أدقّ من غيابها.
        return max(
            candidates,
            key=lambda r: (
                CommissionRule.SPECIFICITY[r.scope],
                r.area_id is not None,
                r.created_at,
            ),
        )

    @classmethod
    def fee_for(cls, driver, area, gross, now=None):
        if driver is not None and getattr(driver, "commission_exempt", False):
            return ZERO

        rule = cls.rule_for(driver, area, now)
        if rule is None:
            return ZERO

        gross = Decimal(gross)
        fee = gross * rule.rate_pct / Decimal("100") + rule.fixed_fee
        if rule.min_fee is not None:
            fee = max(fee, rule.min_fee)
        if rule.max_fee is not None:
            fee = min(fee, rule.max_fee)
        return _money(min(max(fee, ZERO), gross))
