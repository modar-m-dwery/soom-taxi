"""
دفتر القيود المزدوج.

قاعدة واحدة تحكم هذا الملفّ كلّه:

    كل حركة مال تُكتب كمجموعة قيود مجموع مدينها = مجموع دائنها.

ليست شكليّة محاسبية. هي الفرق بين أن تقول لسائق "رصيدك ٤٠ ألفًا" وأن
تستطيع أن **تُثبت** له من أين جاءت، رحلةً رحلة. ولأنها كذلك، فالقيود
لا تُعدَّل ولا تُحذف — التصحيح بقيد معاكس، تمامًا كدفتر ورقي.

كل الكتابة تمرّ من `LedgerService.record` وحدها. لا يُنشأ `LedgerEntry`
مباشرةً في أي مكان آخر في المشروع، وإلّا سقط ضمان التوازن.
"""
import logging
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from payments.models import (
    DriverBalance,
    LedgerAccount,
    LedgerDirection,
    LedgerEntry,
    ZERO,
)


logger = logging.getLogger(__name__)


class LedgerError(Exception):
    """خلل في الدفتر. لا يُلتقط ويُتجاهل أبدًا — يعني أن المال لا يتوازن."""


def new_transaction_ref():
    return uuid.uuid4().hex


class LedgerService:

    # =================================================================
    # الكتابة
    # =================================================================

    @staticmethod
    @transaction.atomic
    def record(payment, lines, transaction_ref=None, memo="", currency=None):
        """
        يكتب مجموعة قيود متوازنة دفعةً واحدة.

        `payment` قد يكون None لحركةٍ لا دفعة لها (تعويض مشوار فاضي)،
        وحينها تُمرَّر `currency` صراحةً.

        `lines` قائمة من قواميس:

            {
                "account": LedgerAccount.DRIVER,
                "account_ref": "12",
                "direction": LedgerDirection.CREDIT,
                "amount": Decimal("25000.00"),
                "entry_type": LedgerEntryType.DRIVER_EARNING,
            }

        يرفع `LedgerError` إن لم تتوازن — قبل الكتابة لا بعدها. قيد غير
        متوازن لا يُكتب أصلًا، فلا يوجد في هذا النظام دفتر يحتاج إصلاحًا.
        """
        if not lines:
            raise LedgerError("لا قيود لكتابتها.")

        debit = ZERO
        credit = ZERO

        for line in lines:
            amount = line["amount"]

            if not isinstance(amount, Decimal):
                raise LedgerError(
                    f"مبلغ القيد يجب أن يكون Decimal لا {type(amount).__name__}."
                )

            if amount <= ZERO:
                raise LedgerError("مبلغ القيد يجب أن يكون موجبًا.")

            if line["direction"] == LedgerDirection.DEBIT:
                debit += amount
            elif line["direction"] == LedgerDirection.CREDIT:
                credit += amount
            else:
                raise LedgerError(f"اتجاه قيد غير معروف: {line['direction']}")

        if debit != credit:
            raise LedgerError(
                f"القيود غير متوازنة: مدين {debit} ≠ دائن {credit}."
            )

        ref = transaction_ref or new_transaction_ref()
        if payment is not None:
            currency = payment.currency
        elif not currency:
            raise LedgerError("حركةٌ بلا دفعة تحتاج عملةً صريحة.")

        entries = [
            LedgerEntry(
                payment=payment,
                account=line["account"],
                account_ref=str(line.get("account_ref") or ""),
                direction=line["direction"],
                amount=line["amount"],
                currency=currency,
                entry_type=line["entry_type"],
                transaction_ref=ref,
                memo=(line.get("memo") or memo or "")[:255],
            )
            for line in lines
        ]

        # bulk_create يتجاوز save() المخصّص، وهذا مقبول هنا وحده: الحماية
        # التي يوفّرها save() هي منع التعديل، والإدراج الأوّل مسموح أصلًا.
        LedgerEntry.objects.bulk_create(entries)

        logger.info(
            "ledger: كُتب %d قيدًا للدفعة %s بمرجع %s",
            len(entries),
            payment.pk if payment is not None else "—",
            ref,
        )

        return ref

    # =================================================================
    # رصيد السائق
    # =================================================================

    @staticmethod
    @transaction.atomic
    def apply_to_driver_balance(driver_id, currency, delta, earned=ZERO, commission=ZERO):
        """
        يحرّك رصيد السائق بمقدار `delta`.

        `select_for_update` ليس زينة: سائق ينهي رحلتين في اللحظة نفسها
        (رحلة مشتركة براكبين) يولّد تحديثين متوازيين على الصفّ نفسه —
        وبلا قفل يضيع أحدهما صامتًا.
        """
        balance, _created = DriverBalance.objects.select_for_update().get_or_create(
            driver_id=driver_id,
            currency=currency,
            defaults={
                "net_balance": ZERO,
                "lifetime_earned": ZERO,
                "lifetime_commission": ZERO,
            },
        )

        balance.net_balance = balance.net_balance + delta
        balance.lifetime_earned = balance.lifetime_earned + earned
        balance.lifetime_commission = balance.lifetime_commission + commission
        balance.save(
            update_fields=[
                "net_balance",
                "lifetime_earned",
                "lifetime_commission",
                "updated_at",
            ]
        )

        return balance

    # =================================================================
    # القراءة والتدقيق
    # =================================================================

    @staticmethod
    def account_balance(account, account_ref="", currency="SYP"):
        """
        الرصيد المحسوب من الدفتر مباشرة — مصدر الحقيقة.

        بطيء بطبيعته (يجمع كل القيود)، ولذلك `DriverBalance` موجود
        كتجميعة سريعة. تُستخدم هذه عند التدقيق أو الشكّ لا في المسار الحارّ.
        """
        rows = LedgerEntry.objects.filter(
            account=account,
            account_ref=str(account_ref or ""),
            currency=currency,
        )

        credit = rows.filter(direction=LedgerDirection.CREDIT).aggregate(
            total=Sum("amount")
        )["total"] or ZERO

        debit = rows.filter(direction=LedgerDirection.DEBIT).aggregate(
            total=Sum("amount")
        )["total"] or ZERO

        return credit - debit

    @staticmethod
    def assert_balanced(transaction_ref):
        """
        يتحقّق أن حركة بعينها متوازنة. للاختبارات وأوامر التدقيق.
        """
        rows = LedgerEntry.objects.filter(transaction_ref=transaction_ref)

        debit = rows.filter(direction=LedgerDirection.DEBIT).aggregate(
            total=Sum("amount")
        )["total"] or ZERO

        credit = rows.filter(direction=LedgerDirection.CREDIT).aggregate(
            total=Sum("amount")
        )["total"] or ZERO

        if debit != credit:
            raise LedgerError(
                f"الحركة {transaction_ref} غير متوازنة: "
                f"مدين {debit} ≠ دائن {credit}."
            )

        return True

    @staticmethod
    def audit_all(currency="SYP"):
        """
        يفحص توازن الدفتر كلّه ويعيد قائمة الحركات المختلّة.

        يجب أن يعيد قائمة فارغة دائمًا. أي عنصر فيها حادثة تُحقَّق، لا
        رقم يُعرض في تقرير.
        """
        broken = []

        refs = (
            LedgerEntry.objects.filter(currency=currency)
            .values_list("transaction_ref", flat=True)
            .distinct()
        )

        for ref in refs:
            try:
                LedgerService.assert_balanced(ref)
            except LedgerError as exc:
                broken.append({"transaction_ref": ref, "error": str(exc)})

        return broken

    @staticmethod
    def recompute_driver_balance(driver_id, currency="SYP"):
        """
        يعيد بناء `DriverBalance` من الدفتر.

        شبكة أمان لا مسار أساسي: تُستدعى عند الشكّ أو بعد تسوية يدوية،
        لا بعد كل رحلة.
        """
        net = LedgerService.account_balance(
            LedgerAccount.DRIVER, str(driver_id), currency
        )

        with transaction.atomic():
            balance, _created = DriverBalance.objects.select_for_update().get_or_create(
                driver_id=driver_id,
                currency=currency,
                defaults={"net_balance": ZERO},
            )
            balance.net_balance = net
            balance.save(update_fields=["net_balance", "updated_at"])

        return balance
