"""
تعويض المشوار الفاضي.

السائق قاد إلى الزبون، ووصل (والخادم تحقّق من وصوله بنصف قطر الالتقاط)،
وانتظر `cancel_wait_minutes` كاملة، ثمّ ألغى الزبون أو لم يحضر. خسر وقودًا
ووقتًا ومشوارًا كان سيأخذه غيره.

من يدفع: المنصّة. يُقيَّد على حسابها ويُضاف لرصيد السائق — أي يُخصم فورًا
من العمولة المستحقّة عليه، فيستفيد منه بلا انتظار ولا نقد. لا شيء يُطلب
من الزبون: سياسة الإلغاء كلّها بلا غرامات نقديّة (سوقٌ فقير)، والزبون ينال
مخالفتين بدلها.

الحماية من التواطؤ (سائق وزبون يتّفقان على «لم يحضر» ليأخذا التعويض ويكملا
المشوار خارج التطبيق):
  - سقفٌ يوميّ لكلّ سائق (`wasted_trip_compensation_daily_cap`).
  - الثنائي نفسه لا يُعوَّض أكثر من مرّة كلّ PAIR_WINDOW_DAYS يومًا.
  - لا تعويض إن كان أحدهما مقيّدًا في نظام النزاهة.
  - وتكرار «لم يحضر» للثنائي نفسه إشارةٌ في نظام النزاهة (integrity.hooks).
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from trips.models import CancellationKind, CancellationRecord

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

COMPENSATED_KINDS = frozenset({CancellationKind.AFTER_WAIT, CancellationKind.NO_SHOW})
PAIR_WINDOW_DAYS = 14
DEFAULT_DAILY_CAP = 3


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


class WastedTripCompensation:

    @staticmethod
    def amount_for(trip):
        """المبلغ من إعداد المنطقة، وإلّا أجرة فتح العدّاد للطلب نفسه."""
        ride = trip.ride
        area = ride.service_area
        configured = getattr(area, "wasted_trip_compensation", None) if area else None
        if configured is not None:
            return _money(configured)
        return _money(ride.base_fare)

    @classmethod
    def skip_reason(cls, record, amount, now=None):
        """لماذا لا يُعوَّض هذا الإلغاء — None إن كان يستحقّ."""
        now = now or timezone.now()
        trip = record.trip

        if record.kind not in COMPENSATED_KINDS:
            return "kind"
        if record.driver_id is None or trip is None or trip.arrived_at is None:
            return "not_arrived"
        if amount <= ZERO:
            return "disabled"

        area = trip.ride.service_area
        cap = area.wasted_trip_compensation_daily_cap if area is not None else DEFAULT_DAILY_CAP
        paid_today = CancellationRecord.objects.filter(
            driver_id=record.driver_id,
            driver_compensation__gt=0,
            created_at__gte=now - timedelta(days=1),
        ).count()
        if paid_today >= cap:
            return "daily_cap"

        if CancellationRecord.objects.filter(
            driver_id=record.driver_id,
            customer_id=record.customer_id,
            driver_compensation__gt=0,
            created_at__gte=now - timedelta(days=PAIR_WINDOW_DAYS),
        ).exists():
            return "pair_window"

        from integrity.services.scoring import IntegrityService

        if IntegrityService.is_restricted(record.driver.user) or IntegrityService.is_restricted(
            record.customer
        ):
            return "restricted"
        return None

    @classmethod
    @transaction.atomic
    def apply(cls, record):
        """يعوّض السائق إن استحقّ، ويعيد المبلغ (صفر إن لم يستحقّ)."""
        from payments.models import LedgerAccount, LedgerDirection, LedgerEntryType
        from payments.services.ledger import LedgerService

        trip = record.trip
        if trip is None:
            return ZERO

        amount = cls.amount_for(trip)
        reason = cls.skip_reason(record, amount)
        if reason is not None:
            logger.info(
                "compensation: لا تعويض لإلغاء الرحلة %s (%s)", trip.pk, reason,
            )
            return ZERO

        currency = trip.ride.currency or "SYP"
        memo = f"تعويض مشوار فاضي — الرحلة {trip.pk}"
        LedgerService.record(
            None,
            [
                {
                    "account": LedgerAccount.PLATFORM,
                    "account_ref": "",
                    "direction": LedgerDirection.DEBIT,
                    "amount": amount,
                    "entry_type": LedgerEntryType.COMPENSATION,
                },
                {
                    "account": LedgerAccount.DRIVER,
                    "account_ref": str(record.driver_id),
                    "direction": LedgerDirection.CREDIT,
                    "amount": amount,
                    "entry_type": LedgerEntryType.COMPENSATION,
                },
            ],
            memo=memo,
            currency=currency,
        )
        LedgerService.apply_to_driver_balance(
            record.driver_id, currency, amount, earned=amount,
        )

        record.driver_compensation = amount
        record.save(update_fields=["driver_compensation"])
        return amount
