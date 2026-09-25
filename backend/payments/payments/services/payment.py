"""
خدمة الدفع — كل قانون المال في المشروع هنا.

ثلاثة مبادئ تحكم الملفّ:

**١. آلة حالات صريحة.** `ALLOWED_TRANSITIONS` جدول مكتوب لا سلسلة شروط
متناثرة. الانتقال غير المسموح يرفع استثناءً بجملة مفهومة، ولا يمرّ صامتًا
أبدًا. هذه هي النقطة التي تنهار عندها أنظمة الدفع عادةً: حالة وصلت من
طريق لم يتوقّعه أحد.

**٢. القفل قبل القراءة.** كل انتقال يبدأ بـ`select_for_update` على صفّ
الدفعة. إشعار وارد من المزوّد وضغطة زرّ من السائق قد يصلان في المللي
ثانية نفسها — وبلا قفل يفوز آخرهما كتابةً لا آخرهما منطقًا.

**٣. الفشل نتيجة لا انهيار.** أي استثناء غير متوقّع من بوابة يُلتقط
ويُصنَّف ويُسجَّل. لا يخرج من هذه الطبقة استثناء يصل المستخدم كـ500.
"""
import hashlib
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from payments.gateways import (
    NotConfigured,
    default_gateway_code,
    get_gateway,
)
from payments.gateways.base import GatewayResult, PaymentGatewayError
from payments.models import (
    AttemptAction,
    LedgerAccount,
    LedgerDirection,
    LedgerEntryType,
    Payment,
    PaymentAttempt,
    PaymentStatus,
    Refund,
    RefundStatus,
    TERMINAL_STATUSES,
    ZERO,
)
from payments.services.ledger import LedgerService, new_transaction_ref


logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


class PaymentError(Exception):
    """خطأ عمل في الدفع. يُترجَم إلى 400 لا 500."""


class PaymentAuthorizationError(PaymentError):
    """المؤكِّد ليس صاحب الصلاحية. يُترجَم إلى 403 لا 400."""


class InvalidTransition(PaymentError):
    """انتقال حالة غير مسموح."""


def money(value):
    """تطبيع أي مبلغ إلى Decimal بخانتين. لا float إطلاقًا."""
    if isinstance(value, float):
        raise TypeError("لا تمرّر float للمبالغ المالية.")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# =====================================================================
# آلة الحالات
# =====================================================================

ALLOWED_TRANSITIONS = {
    PaymentStatus.PENDING: {
        PaymentStatus.PROCESSING,
        PaymentStatus.AUTHORIZED,
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.AUTHORIZED,
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.AUTHORIZED: {
        PaymentStatus.PAID,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.PAID: {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.REFUNDED,
    },
    # الحالات النهائية: لا مخرج منها.
    PaymentStatus.REFUNDED: set(),
    PaymentStatus.FAILED: set(),
    PaymentStatus.CANCELLED: set(),
}


def can_transition(current, target):
    return target in ALLOWED_TRANSITIONS.get(current, set())


class PaymentService:

    # =================================================================
    # الإنشاء
    # =================================================================

    @staticmethod
    def build_idempotency_key(trip_id):
        """
        مفتاح ثابت مشتقّ من الرحلة.

        اشتقاقه بدل توليده عشوائيًا مقصود: نداءان متزامنان لـ
        `open_for_trip` لنفس الرحلة يولّدان المفتاح نفسه، فيصطدم ثانيهما
        بقيد التفرّد في قاعدة البيانات بدل أن يُنشئ دفعة ثانية. التكافؤ
        مضمون من قاعدة البيانات لا من ترتيب التنفيذ.
        """
        digest = hashlib.sha256(f"trip:{trip_id}".encode("utf-8")).hexdigest()
        return f"trip-{trip_id}-{digest[:24]}"

    @classmethod
    @transaction.atomic
    def open_for_trip(cls, trip, gateway_code=None):
        """
        يُنشئ دفعة معلّقة لرحلة مكتملة. **متكافئ**: استدعاؤه مرّتين يعيد
        الدفعة نفسها بلا تغيير.

        يُستدعى من `TripService.complete` بعد كتابة سجلّ الإتمام.
        """
        existing = Payment.objects.filter(trip=trip).first()
        if existing is not None:
            return existing

        ride = trip.ride

        amount = money(ride.customer_total or trip.final_fare or ZERO)
        platform_fee = money(ride.platform_fee or ZERO)

        if platform_fee > amount:
            # لا نصحّح صامتًا: عمولة تتجاوز الأجرة خلل تسعير يجب أن يُرى.
            raise PaymentError(
                f"العمولة {platform_fee} تتجاوز إجمالي المبلغ {amount}."
            )

        driver_net = money(amount - platform_fee)
        code = gateway_code or default_gateway_code()

        # نتحقّق أن البوابة موجودة قبل الكتابة، لا بعدها.
        get_gateway(code)

        payment = Payment(
            trip=trip,
            customer=trip.customer,
            driver=trip.driver,
            amount=amount,
            platform_fee=platform_fee,
            driver_net=driver_net,
            currency=(ride.currency or trip.currency or "SYP"),
            gateway_code=code,
            status=PaymentStatus.PENDING,
            idempotency_key=cls.build_idempotency_key(trip.pk),
        )
        payment.full_clean(exclude=["trip", "customer", "driver"])
        payment.save()

        logger.info(
            "payments: فُتحت دفعة %s للرحلة %s بمبلغ %s %s عبر %s",
            payment.pk, trip.pk, amount, payment.currency, code,
        )

        return payment

    # =================================================================
    # التحصيل
    # =================================================================

    @classmethod
    def charge(cls, payment_id, actor=None, context=None, system=False):
        """
        ينفّذ التحصيل عبر البوابة ثم يثبّت النتيجة.

        النداء الخارجي يقع **خارج** المعاملة عمدًا: إبقاء معاملة قاعدة
        بيانات مفتوحة طوال انتظار مزوّد بطيء يستنزف مجمّع الاتصالات
        ويقفل صفوفًا لعشر ثوانٍ. نقرأ، ثم نُنادي، ثم نفتح معاملة قصيرة
        للتثبيت — ونعيد فحص الحالة داخلها لأنها قد تكون تغيّرت.

        `actor` إلزاميّ لبوّابات التأكيد اليدوي — راجع `_authorize_charge`.
        `system=True` للمستدعي الداخلي الموثوق (مهمّة Celery للتعويض).
        """
        payment = Payment.objects.select_related("trip", "driver", "customer").get(
            pk=payment_id
        )

        cls._authorize_charge(payment, actor, system=system)

        if payment.status in TERMINAL_STATUSES:
            raise InvalidTransition(
                f"الدفعة في حالة نهائية ({payment.get_status_display()})."
            )

        if payment.status in (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED):
            # متكافئ: محصَّلة أصلًا.
            return payment

        gateway = get_gateway(payment.gateway_code)

        try:
            gateway.check_ready()
        except NotConfigured as exc:
            cls._log_attempt(
                payment, AttemptAction.CHARGE, GatewayResult.transient(str(exc))
            )
            raise PaymentError(
                f"بوابة الدفع غير مهيّأة حاليًا: {exc}"
            ) from exc

        result = cls._call_gateway(
            gateway, "charge", payment, AttemptAction.CHARGE, context=context
        )

        return cls._settle_charge_result(payment.pk, result, gateway)

    @classmethod
    def _authorize_charge(cls, payment, actor, system=False):
        """
        مَن يحقّ له تأكيد التحصيل.

        الثغرة التي يسدّها هذا
        ----------------------
        كان `actor` يُمرَّر إلى `charge` ولا يُقرأ في أيّ سطر. والواجهة
        (`ChargeTripPaymentView`) تقبل الزبون **أو** السائق. النتيجة أنّ
        زبونًا ينهي رحلة نقدية يستطيع أن يؤكّد بنفسه أنّه دفع: تنتقل
        الدفعة إلى PAID، ويُقيَّد على السائق قيدُ عمولة على مالٍ لم
        يقبضه — ولا يبقى للسائق طريقٌ لتصحيحها.

        تعليق `payments/gateways/cash.py` يذكر هذا الشرط صراحةً ويقول
        إنّ `PaymentService` هو من يفرضه. هنا يُفرَض فعلًا.

        القاعدة
        -------
        بوّابة يؤكّدها إنسان (نقد) → السائق صاحب الرحلة وحده، أو مشغّل.
        بوّابة يؤكّدها مزوّد خارجي → لا تأكيد يدويًّا أصلًا؛ المزوّد
        يُبلّغ عبر webhook موقَّع.
        """
        # مستدعٍ داخلي موثوق (مهمّة Celery). صريحٌ لا ضمنيّ: لو كان
        # `actor is None` وحده يعني "النظام" لصار كلّ نداء نسي تمرير
        # الفاعل ثغرةً صامتة — وهي بالضبط الطريقة التي وُلدت بها هذه
        # الثغرة أوّل مرّة.
        if system:
            return

        gateway = get_gateway(payment.gateway_code)

        if not getattr(gateway, "requires_manual_confirmation", False):
            return

        if actor is None:
            raise PaymentAuthorizationError(
                "تأكيد التحصيل يحتاج هوية المؤكِّد."
            )

        # المشغّل يستطيع التصحيح — وفعله مسجَّل في AdminAction وAuditLog.
        if getattr(actor, "is_staff", False):
            return

        driver_profile = getattr(actor, "driver_profile", None)

        if driver_profile is not None and driver_profile.pk == payment.driver_id:
            return

        raise PaymentAuthorizationError(
            "سائق الرحلة وحده يؤكّد قبض النقد."
        )

    @classmethod
    def _settle_charge_result(cls, payment_id, result, gateway):
        """
        يثبّت نتيجة التحصيل داخل معاملة قصيرة مع قفل الصفّ.

        ————
        الدرس الأغلى في هذا الملفّ، وقد كشفته الاختبارات لا المراجعة:

            **لا تَرفع استثناءً داخل `transaction.atomic` بعد كتابة أردتَ
            بقاءها.**

        الاستثناء يُلغي المعاملة كلّها — بما فيها حفظ الحالة الفاشلة
        نفسها. كانت النتيجة أن دفعة رُفضت بطاقتها تبقى `pending` إلى
        الأبد، ومهمّة `retry_stuck_payments` تطرق مزوّدًا رفض العملية
        رفضًا نهائيًا، بلا توقّف وبلا أثر يشرح السبب.

        ولذلك: الكتابة داخل الكتلة، والرفع **بعد** خروجها وتثبيتها.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)

            # قد تكون الحالة تغيّرت أثناء نداء البوابة (إشعار وارد سبقنا).
            if payment.status in (
                PaymentStatus.PAID,
                PaymentStatus.PARTIALLY_REFUNDED,
            ):
                return payment

            payment.attempts = payment.attempts + 1

            if result.reference:
                payment.gateway_reference = result.reference

            if result.payload:
                merged = dict(payment.gateway_payload or {})
                merged.update(result.payload)
                payment.gateway_payload = merged

            if result.ok:
                target = (
                    PaymentStatus.AUTHORIZED
                    if gateway.supports_authorize_capture
                    and not getattr(gateway, "captures_immediately", True)
                    else PaymentStatus.PAID
                )
                cls._transition(payment, target)

                if target == PaymentStatus.PAID:
                    payment.paid_at = timezone.now()
                    payment.failure_reason = ""

                payment.save()

                if target == PaymentStatus.PAID:
                    cls._post_ledger_for_payment(payment, gateway)

                return payment

            # فشل: العابر يُبقيها قابلة لإعادة المحاولة، والدائم ينهيها.
            payment.failure_reason = result.error

            if result.permanent_failure:
                cls._transition(payment, PaymentStatus.FAILED)
            elif can_transition(payment.status, PaymentStatus.PROCESSING):
                # الحارس ضروري: دفعة عالقة في PROCESSING تفشل عابرًا مرّة
                # أخرى لا يوجد لها انتقال، ورفع InvalidTransition هنا كان
                # سيحجب سبب الفشل الحقيقي خلف خطأ آلة حالات مضلِّل.
                cls._transition(payment, PaymentStatus.PROCESSING)

            payment.save()

        # خارج المعاملة: الحالة الفاشلة ثُبِّتت، والآن نُشير إلى الفشل.
        raise PaymentError(result.error or "فشل التحصيل لدى المزوّد.")

    # =================================================================
    # القيود المحاسبية
    # =================================================================

    @classmethod
    def _post_ledger_for_payment(cls, payment, gateway):
        """
        يكتب قيود الرحلة المدفوعة.

        الفرع الوحيد في هذا الملفّ الذي يعتمد على البوابة، وهو يعتمد على
        **قدرتها** لا على اسمها:

          settles_to_platform = False (نقدي):
              الزبون يدفع للسائق مباشرة، فيصير السائق مدينًا للمنصّة
              بالعمولة. رصيده ينقص.

          settles_to_platform = True (إلكتروني):
              المال يصل المنصّة، فتصير مدينة للسائق بصافيه. رصيده يزيد.

        بوابة جديدة غدًا تُصنَّف بأحد الوضعين فتعمل محاسبتها بلا سطر جديد.
        """
        amount = payment.amount
        fee = payment.platform_fee
        net = payment.driver_net

        driver_ref = str(payment.driver_id)
        customer_ref = str(payment.customer_id)
        ref = new_transaction_ref()

        lines = []

        if gateway.settles_to_platform:
            # الزبون → المنصّة
            lines.append({
                "account": LedgerAccount.CUSTOMER,
                "account_ref": customer_ref,
                "direction": LedgerDirection.DEBIT,
                "amount": amount,
                "entry_type": LedgerEntryType.TRIP_FARE,
            })
            lines.append({
                "account": LedgerAccount.PLATFORM,
                "account_ref": "",
                "direction": LedgerDirection.CREDIT,
                "amount": amount,
                "entry_type": LedgerEntryType.TRIP_FARE,
            })

            # المنصّة → السائق (صافيه)
            if net > ZERO:
                lines.append({
                    "account": LedgerAccount.PLATFORM,
                    "account_ref": "",
                    "direction": LedgerDirection.DEBIT,
                    "amount": net,
                    "entry_type": LedgerEntryType.DRIVER_EARNING,
                })
                lines.append({
                    "account": LedgerAccount.DRIVER,
                    "account_ref": driver_ref,
                    "direction": LedgerDirection.CREDIT,
                    "amount": net,
                    "entry_type": LedgerEntryType.DRIVER_EARNING,
                })

            delta = net
            earned = net
            commission = fee

        else:
            # الزبون → نقد بيد السائق.
            #
            # الطرف المقابل DRIVER_CASH لا DRIVER عمدًا: النقد المقبوض
            # ليس دَينًا بين السائق والمنصّة، والخلط بينهما يقلب إشارة
            # الرصيد. راجع تعليق LedgerAccount.
            lines.append({
                "account": LedgerAccount.CUSTOMER,
                "account_ref": customer_ref,
                "direction": LedgerDirection.DEBIT,
                "amount": amount,
                "entry_type": LedgerEntryType.TRIP_FARE,
            })
            lines.append({
                "account": LedgerAccount.DRIVER_CASH,
                "account_ref": driver_ref,
                "direction": LedgerDirection.CREDIT,
                "amount": amount,
                "entry_type": LedgerEntryType.TRIP_FARE,
            })

            # السائق → المنصّة (العمولة)
            if fee > ZERO:
                lines.append({
                    "account": LedgerAccount.DRIVER,
                    "account_ref": driver_ref,
                    "direction": LedgerDirection.DEBIT,
                    "amount": fee,
                    "entry_type": LedgerEntryType.PLATFORM_COMMISSION,
                })
                lines.append({
                    "account": LedgerAccount.PLATFORM,
                    "account_ref": "",
                    "direction": LedgerDirection.CREDIT,
                    "amount": fee,
                    "entry_type": LedgerEntryType.PLATFORM_COMMISSION,
                })

            delta = -fee
            # ما يبقى للسائق فعلًا بعد العمولة — لا ما قبضه بيده.
            # التعريف نفسه في الفرعين، فمقارنة دخل سائقين إحداهما نقدية
            # والأخرى إلكترونية تبقى ذات معنى.
            earned = net
            commission = fee

        LedgerService.record(
            payment,
            lines,
            transaction_ref=ref,
            memo=f"رحلة #{payment.trip_id}",
        )

        LedgerService.apply_to_driver_balance(
            driver_id=payment.driver_id,
            currency=payment.currency,
            delta=delta,
            earned=earned,
            commission=commission,
        )

        return ref

    # =================================================================
    # الإعادة
    # =================================================================

    @classmethod
    def refund(cls, payment_id, amount=None, reason="", requested_by=None):
        """
        يعيد مبلغًا كليًا أو جزئيًا.

        التحقّق من المبلغ يقع قبل نداء البوابة: طلب إعادة يتجاوز المتبقّي
        خطأ عمل لا خطأ مزوّد، ولا داعي لإزعاج المزوّد به.
        """
        payment = Payment.objects.get(pk=payment_id)

        if not payment.is_settled:
            raise InvalidTransition("لا يمكن إعادة مبلغ لم يُحصَّل.")

        remaining = payment.refundable_amount
        amount = money(amount) if amount is not None else remaining

        if amount <= ZERO:
            raise PaymentError("مبلغ الإعادة يجب أن يكون موجبًا.")

        if amount > remaining:
            raise PaymentError(
                f"مبلغ الإعادة {amount} يتجاوز المتبقّي {remaining}."
            )

        gateway = get_gateway(payment.gateway_code)

        if not gateway.supports_refund:
            raise PaymentError(
                f"بوابة {gateway.display_name} لا تدعم الإعادة البرمجية."
            )

        key = hashlib.sha256(
            f"refund:{payment.pk}:{amount}:{payment.amount_refunded}".encode("utf-8")
        ).hexdigest()[:40]

        existing = Refund.objects.filter(idempotency_key=key).first()
        if existing is not None:
            return existing

        result = cls._call_gateway(
            gateway,
            "refund",
            payment,
            AttemptAction.REFUND,
            amount=amount,
            reason=reason,
        )

        return cls._settle_refund_result(
            payment.pk, amount, reason, key, result, requested_by
        )

    @classmethod
    def _settle_refund_result(cls, payment_id, amount, reason, key, result, requested_by):
        """
        يثبّت نتيجة الإعادة. الرفع خارج المعاملة للسبب نفسه المشروح في
        `_settle_charge_result`: سجلّ إعادة فاشلة يجب أن يبقى، وإلّا
        تكرّر النظام المحاولة بلا ذاكرة أنها فشلت.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_id)

            refund = Refund(
                payment=payment,
                amount=amount,
                currency=payment.currency,
                reason=(reason or "")[:300],
                idempotency_key=key,
                requested_by=requested_by,
                gateway_reference=result.reference,
            )

            if not result.ok:
                refund.status = RefundStatus.FAILED
                refund.save()
            else:
                refund = cls._complete_refund(payment, refund, amount)

        if not result.ok:
            raise PaymentError(result.error or "فشلت الإعادة لدى المزوّد.")

        return refund

    @classmethod
    def _complete_refund(cls, payment, refund, amount):
        """الجزء الناجح من الإعادة — يعمل داخل معاملة المُنادي."""
        refund.status = RefundStatus.COMPLETED
        refund.completed_at = timezone.now()
        refund.save()

        payment.amount_refunded = money(payment.amount_refunded + amount)

        target = (
            PaymentStatus.REFUNDED
            if payment.amount_refunded >= payment.amount
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        cls._transition(payment, target)
        payment.save()

        # قيد معاكس — لا تعديل على القيد الأصلي.
        LedgerService.record(
            payment,
            [
                {
                    "account": LedgerAccount.CUSTOMER,
                    "account_ref": str(payment.customer_id),
                    "direction": LedgerDirection.CREDIT,
                    "amount": amount,
                    "entry_type": LedgerEntryType.REFUND,
                },
                {
                    "account": LedgerAccount.PLATFORM,
                    "account_ref": "",
                    "direction": LedgerDirection.DEBIT,
                    "amount": amount,
                    "entry_type": LedgerEntryType.REFUND,
                },
            ],
            memo=f"إعادة رحلة #{payment.trip_id}",
        )

        return refund

    # =================================================================
    # الإلغاء
    # =================================================================

    @classmethod
    @transaction.atomic
    def cancel(cls, payment_id, reason=""):
        """يلغي دفعة لم تُحصَّل. الملغاة أصلًا تُعاد كما هي."""
        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if payment.status == PaymentStatus.CANCELLED:
            return payment

        if payment.is_settled:
            raise InvalidTransition(
                "الدفعة محصَّلة — استخدم الإعادة لا الإلغاء."
            )

        cls._transition(payment, PaymentStatus.CANCELLED)
        payment.failure_reason = (reason or "")[:300]
        payment.save()

        return payment

    # =================================================================
    # الإشعارات الواردة
    # =================================================================

    @classmethod
    @transaction.atomic
    def apply_webhook(cls, gateway_code, event):
        """
        يطبّق حدثًا **تم التحقّق من توقيعه** على الدفعة المعنيّة.

        التحقّق يقع في الواجهة قبل الوصول إلى هنا. هذه الدالة تفترض
        الحدث موثوقًا — ولذلك لا تُستدعى من أي مكان آخر.
        """
        gateway = get_gateway(gateway_code)
        reference = gateway.extract_webhook_reference(event)

        if not reference:
            logger.warning("إشعار %s بلا معرّف عملية — أُهمل.", gateway_code)
            return None

        payment = (
            Payment.objects.select_for_update()
            .filter(gateway_code=gateway_code, gateway_reference=reference)
            .first()
        )

        if payment is None:
            logger.warning(
                "إشعار %s لمعرّف غير معروف: %s — أُهمل.", gateway_code, reference
            )
            return None

        cls._log_attempt(
            payment,
            AttemptAction.WEBHOOK,
            GatewayResult.success(reference=reference, payload=event),
        )

        target = gateway.extract_webhook_status(event)

        if target is None:
            return payment

        if payment.status == target:
            return payment

        if not can_transition(payment.status, target):
            # ليس خطأ: إشعارات المزوّدين تصل متأخّرة وخارج الترتيب كثيرًا.
            logger.info(
                "إشعار %s: انتقال مُهمَل %s → %s للدفعة %s",
                gateway_code, payment.status, target, payment.pk,
            )
            return payment

        cls._transition(payment, target)

        if target == PaymentStatus.PAID:
            payment.paid_at = payment.paid_at or timezone.now()
            payment.save()
            cls._post_ledger_for_payment(payment, gateway)
        else:
            payment.save()

        return payment

    # =================================================================
    # أدوات داخلية
    # =================================================================

    @staticmethod
    def _transition(payment, target):
        """
        ينقل الحالة أو يرفض. لا يحفظ — الحفظ مسؤولية المُنادي، حتى يجمع
        كل تغييراته في كتابة واحدة.
        """
        if payment.status == target:
            return payment

        if not can_transition(payment.status, target):
            raise InvalidTransition(
                f"انتقال غير مسموح: {payment.status} → {target}."
            )

        payment.status = target
        return payment

    @classmethod
    def _call_gateway(cls, gateway, method, payment, action, **kwargs):
        """
        ينادي البوابة ويسجّل المحاولة، ولا يسمح لاستثناء بالخروج.

        بوابة تكتبها أنت غدًا قد ترفع استثناءً لم يخطر ببالك. أن يتحوّل
        ذلك إلى فشل عابر مسجَّل — لا إلى 500 في وجه راكب واقف في الشارع —
        هو الفرق بين نظام يحتمل المفاجأة ونظام ينهار عندها.
        """
        try:
            result = getattr(gateway, method)(payment, **kwargs)
        except PaymentGatewayError as exc:
            result = GatewayResult.permanent(str(exc))
        except Exception as exc:  # noqa: BLE001 — مقصود: لا شيء يمرّ
            logger.exception(
                "استثناء غير متوقّع من بوابة %s في %s", gateway.code, method
            )
            result = GatewayResult.transient(f"خطأ غير متوقّع: {exc}")

        if not isinstance(result, GatewayResult):
            logger.error(
                "بوابة %s أعادت نوعًا غير متوقّع من %s: %r",
                gateway.code, method, type(result),
            )
            result = GatewayResult.permanent(
                "البوابة أعادت نتيجة غير صالحة."
            )

        cls._log_attempt(payment, action, result)
        return result

    @staticmethod
    def _log_attempt(payment, action, result):
        """
        يسجّل المحاولة. الفشل في التسجيل لا يُسقط العملية — سجلّ ناقص
        أهون من دفعة ضائعة.
        """
        try:
            PaymentAttempt.objects.create(
                payment=payment,
                gateway_code=payment.gateway_code,
                action=action,
                ok=result.ok,
                permanent_failure=result.permanent_failure,
                error=result.error,
                response_payload=result.payload or {},
            )
        except Exception:
            logger.exception("تعذّر تسجيل محاولة الدفع للدفعة %s", payment.pk)
