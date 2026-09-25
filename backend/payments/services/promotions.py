# -*- coding: utf-8 -*-
"""
الترويج: أوّل مشوار بنصف السعر، وزبون يجلب زبونًا.

من خطّة التسعين يومًا (§6 جذب الزبائن):
  • «أوّل مشوار بنصف السعر — مرّة واحدة لكلّ رقم، بسقفٍ محدَّد لا نسبة.»
  • «زبون يجلب زبونًا — مشوار مخفَّض للاثنين بعد أن يُتمّ الجديد رحلته
    الأولى. وتُدفع بعد الإنجاز لا قبله.»

القواعد التي تحكم هذا الملفّ:
  ١. الأرقام إعدادات لكلّ مدينة (ServiceArea) لا ثوابت: الصفر يطفئها.
  ٢. الخصم يُقرَّر عند فتح الدفعة ويُثبَّت عند التحصيل — لا عند الطلب: زبونٌ
     ألغى لا يستهلك خصمه.
  ٣. الخصم تتحمّله المنصّة لا السائق: صافي السائق ثابت، والفرق قيدٌ
     متوازن على حساب المنصّة (LedgerEntryType.PROMOTION).
  ٤. مكافأة الإحالة تُمنح مرّةً واحدة، حين تصير أوّل دفعة للمدعوّ «محصَّلة».
"""

import logging
from decimal import Decimal

from django.db import transaction

from payments.models import CustomerCredit, Payment, PaymentStatus, ZERO

logger = logging.getLogger(__name__)

FIRST_RIDE = "first_ride"
CREDIT = "credit"


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"))


class PromotionService:

    # ------------------------------------------------------------ تقدير
    @classmethod
    def quote(cls, customer, service_area, total, currency="SYP"):
        """
        يعيد (discount, reason) لدفعةٍ تُفتح الآن لهذا الزبون.

        الترتيب: خصم أوّل مشوار أوّلًا (لا يتراكم مع رصيد الإحالة في الرحلة
        نفسها — المدعوّ لا يملك رصيدًا قبل رحلته الأولى أصلًا)، ثمّ الأرصدة.
        """
        total = _money(total)
        if total <= ZERO:
            return ZERO, ""

        profile = getattr(customer, "customer_profile", None)

        discount = cls._first_ride_discount(customer, profile, service_area, total)
        if discount > ZERO:
            return discount, FIRST_RIDE

        available = cls.credit_balance(customer, currency)
        if available > ZERO:
            return min(available, total), CREDIT

        return ZERO, ""

    @classmethod
    def _first_ride_discount(cls, customer, profile, service_area, total):
        from catalog.services import Catalog

        if not Catalog.feature_enabled("first_ride_discount", service_area):
            return ZERO
        pct = Decimal(getattr(service_area, "first_ride_discount_pct", 0) or 0)
        if pct <= ZERO or profile is None or profile.first_ride_discount_used:
            return ZERO
        if cls.has_paid_before(customer):
            return ZERO
        discount = _money(total * pct / Decimal("100"))
        cap = getattr(service_area, "first_ride_discount_cap", None)
        if cap is not None:
            discount = min(discount, _money(cap))
        return min(discount, total)

    @staticmethod
    def has_paid_before(customer):
        return Payment.objects.filter(
            customer=customer,
            status__in=(PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED,
                        PaymentStatus.REFUNDED),
        ).exists()

    @staticmethod
    def credit_balance(customer, currency="SYP"):
        total = ZERO
        for credit in CustomerCredit.objects.filter(customer=customer, currency=currency):
            total += credit.remaining
        return _money(total)

    # ------------------------------------------------------------ تثبيت
    @classmethod
    @transaction.atomic
    def consume(cls, payment):
        """يُستدعى حين تصير الدفعة محصَّلة: يثبّت ما قُرِّر عند الفتح."""
        if payment.discount_amount <= ZERO:
            return

        if payment.discount_reason == FIRST_RIDE:
            profile = getattr(payment.customer, "customer_profile", None)
            if profile is not None and not profile.first_ride_discount_used:
                profile.first_ride_discount_used = True
                profile.save(update_fields=["first_ride_discount_used"])
            return

        if payment.discount_reason == CREDIT:
            remaining = payment.discount_amount
            credits = (
                CustomerCredit.objects
                .select_for_update()
                .filter(customer=payment.customer, currency=payment.currency)
                .order_by("created_at")
            )
            for credit in credits:
                if remaining <= ZERO:
                    break
                free = credit.remaining
                if free <= ZERO:
                    continue
                take = min(free, remaining)
                credit.consumed_amount = credit.consumed_amount + take
                if credit.consumed_by_id is None:
                    credit.consumed_by = payment
                credit.save(update_fields=["consumed_amount", "consumed_by"])
                remaining -= take

    # ------------------------------------------------------------ الإحالة
    @classmethod
    @transaction.atomic
    def reward_referral(cls, payment, service_area):
        """
        بعد أوّل دفعة محصَّلة للمدعوّ: رصيدٌ للداعي والمدعوّ معًا.

        «بعد الإنجاز لا قبله»: نداءٌ من `_post_ledger_for_payment` لا من
        إدخال الرمز. والمكافأة مرّةً واحدة — `source_payment` يحرس التكرار.
        """
        from catalog.services import Catalog

        if not Catalog.feature_enabled("referral", service_area):
            return None
        reward = _money(getattr(service_area, "referral_reward", 0) or 0)
        if reward <= ZERO:
            return []

        profile = getattr(payment.customer, "customer_profile", None)
        if profile is None or profile.referred_by_id is None:
            return []

        if CustomerCredit.objects.filter(source_payment=payment).exists():
            return []

        earlier = Payment.objects.filter(
            customer=payment.customer,
            status__in=(PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED,
                        PaymentStatus.REFUNDED),
        ).exclude(pk=payment.pk).exists()
        if earlier:
            return []

        currency = payment.currency
        credits = [
            CustomerCredit(customer=profile.referred_by, amount=reward, currency=currency,
                           reason=CustomerCredit.Reason.REFERRER, source_payment=payment),
            CustomerCredit(customer=payment.customer, amount=reward, currency=currency,
                           reason=CustomerCredit.Reason.REFEREE, source_payment=payment),
        ]
        CustomerCredit.objects.bulk_create(credits)
        logger.info("promotions: مكافأة إحالة %s %s للطرفين — دفعة %s",
                    reward, currency, payment.pk)
        return credits

    # ------------------------------------------------------------ الرمز
    @staticmethod
    @transaction.atomic
    def apply_referral_code(customer, code):
        """يربط المدعوّ بالداعي. يرفع ValueError بنصّ عربيّ جاهز للعرض."""
        from users.models import CustomerProfile

        code = (code or "").strip().upper()
        if not code:
            raise ValueError("أدخل رمز الدعوة.")

        profile, _ = CustomerProfile.objects.select_for_update().get_or_create(user=customer)
        if profile.referred_by_id is not None:
            raise ValueError("سبق أن سجّلت رمز دعوة.")
        if PromotionService.has_paid_before(customer):
            raise ValueError("رمز الدعوة يُدخل قبل رحلتك الأولى.")

        referrer = CustomerProfile.objects.filter(referral_code=code).select_related("user").first()
        if referrer is None:
            raise ValueError("رمز الدعوة غير صحيح.")
        if referrer.user_id == customer.pk:
            raise ValueError("لا يمكنك دعوة نفسك.")

        profile.referred_by = referrer.user
        profile.save(update_fields=["referred_by"])
        return referrer.user
