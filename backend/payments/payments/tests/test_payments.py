"""
اختبارات الدفع.

تركّز على ما ينكسر فعلًا في أنظمة المال: التكافؤ، التزامن، توازن الدفتر،
انقلاب إشارة الرصيد، والانتقالات غير المسموحة. الحالة السعيدة مغطّاة
لكنها أقلّ ما يهمّ — لا أحد يخسر مالًا لأن المسار السعيد فشل.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from config.testkit import (
    auth,
    make_admin,
    make_completed_trip,
    make_customer,
    make_driver,
)
from payments.gateways import (
    available_gateways,
    get_gateway,
    reset_registry,
)
from payments.gateways.base import (
    GatewayResult,
    NotConfigured,
    PaymentGateway,
    PaymentGatewayError,
)
from payments.models import (
    DriverBalance,
    LedgerAccount,
    LedgerDirection,
    LedgerEntry,
    Payment,
    PaymentAttempt,
    PaymentStatus,
)
from payments.services.ledger import LedgerError, LedgerService
from payments.services.payment import (
    InvalidTransition,
    PaymentError,
    PaymentService,
    can_transition,
    money,
)


# =====================================================================
# بوابات وهمية للاختبار
# =====================================================================

class OnlineTestGateway(PaymentGateway):
    code = "test_online"
    display_name = "بوابة اختبار إلكترونية"
    is_online = True
    settles_to_platform = True
    supports_refund = True
    supports_webhook = True

    def charge(self, payment, context=None):
        return GatewayResult.success(reference="EXT-1")

    def refund(self, payment, amount, reason="", context=None):
        return GatewayResult.success(reference="REF-1")


class FailingGateway(PaymentGateway):
    code = "test_failing"
    display_name = "بوابة تفشل دائمًا"
    is_online = True
    settles_to_platform = True

    def charge(self, payment, context=None):
        return GatewayResult.permanent("البطاقة مرفوضة.")


class FlakyGateway(PaymentGateway):
    code = "test_flaky"
    display_name = "بوابة تفشل عابرًا"
    is_online = True
    settles_to_platform = True

    def charge(self, payment, context=None):
        return GatewayResult.transient("انقطاع شبكة.")


class ExplodingGateway(PaymentGateway):
    code = "test_exploding"
    display_name = "بوابة ترفع استثناءً"
    is_online = True
    settles_to_platform = True

    def charge(self, payment, context=None):
        raise RuntimeError("انفجار غير متوقّع داخل البوابة")


class MisbehavingGateway(PaymentGateway):
    code = "test_misbehaving"
    display_name = "بوابة تعيد نوعًا خاطئًا"
    is_online = True
    settles_to_platform = True

    def charge(self, payment, context=None):
        return "نجحت"          # ليست GatewayResult


class UnconfiguredGateway(PaymentGateway):
    code = "test_unconfigured"
    display_name = "بوابة غير مهيّأة"
    is_online = True

    def check_ready(self):
        raise NotConfigured("بيانات الاعتماد ناقصة.")

    def charge(self, payment, context=None):
        return GatewayResult.success()


ALL_TEST_GATEWAYS = [
    "payments.gateways.cash.CashGateway",
    "payments.tests.test_payments.OnlineTestGateway",
    "payments.tests.test_payments.FailingGateway",
    "payments.tests.test_payments.FlakyGateway",
    "payments.tests.test_payments.ExplodingGateway",
    "payments.tests.test_payments.MisbehavingGateway",
    "payments.tests.test_payments.UnconfiguredGateway",
]


class GatewayTestMixin:
    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)


# =====================================================================
# سجلّ البوابات
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS)
class GatewayRegistryTests(GatewayTestMixin, TestCase):

    def test_registry_loads_every_configured_gateway(self):
        self.assertEqual(get_gateway("cash").code, "cash")
        self.assertEqual(get_gateway("test_online").code, "test_online")

    def test_unknown_gateway_raises_and_does_not_fall_back(self):
        # السقوط الصامت على النقدي كان سيخفي خطأ إعدادات حقيقيًا.
        with self.assertRaises(PaymentGatewayError):
            get_gateway("nope")

    def test_unconfigured_gateway_hidden_from_available(self):
        codes = {gateway.code for gateway in available_gateways()}
        self.assertIn("cash", codes)
        self.assertNotIn("test_unconfigured", codes)

    @override_settings(PAYMENT_GATEWAYS=[
        "payments.gateways.cash.CashGateway",
        "payments.gateways.cash.CashGateway",
    ])
    def test_duplicate_code_is_rejected_loudly(self):
        from django.core.exceptions import ImproperlyConfigured
        reset_registry()
        with self.assertRaises(ImproperlyConfigured):
            get_gateway("cash")

    def test_cash_gateway_capabilities(self):
        cash = get_gateway("cash")
        self.assertFalse(cash.is_online)
        self.assertFalse(cash.settles_to_platform)
        self.assertFalse(cash.supports_refund)
        self.assertTrue(cash.check_ready())


# =====================================================================
# آلة الحالات
# =====================================================================

class TransitionTableTests(TestCase):

    def test_every_status_has_a_transition_entry(self):
        """
        نقص حالة واحدة من الجدول يعني أن `can_transition` تعيد False
        دائمًا لها — فتعلق الدفعة بلا مخرج ولا رسالة مفهومة.
        """
        from payments.services.payment import ALLOWED_TRANSITIONS

        for value in PaymentStatus.values:
            self.assertIn(value, ALLOWED_TRANSITIONS, f"الحالة {value} غير معرَّفة")

    def test_terminal_statuses_have_no_exit(self):
        for terminal in (
            PaymentStatus.REFUNDED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
        ):
            for target in PaymentStatus.values:
                self.assertFalse(
                    can_transition(terminal, target),
                    f"{terminal} → {target} يجب أن يكون ممنوعًا",
                )

    def test_cannot_go_backwards_from_paid_to_pending(self):
        self.assertFalse(
            can_transition(PaymentStatus.PAID, PaymentStatus.PENDING)
        )


class MoneyHelperTests(TestCase):

    def test_float_is_rejected(self):
        # float في المال هو كيف تختفي القروش. الرفض صريح لا صامت.
        with self.assertRaises(TypeError):
            money(1.15)

    def test_string_and_decimal_normalise_to_two_places(self):
        self.assertEqual(money("10"), Decimal("10.00"))
        self.assertEqual(money(Decimal("10.005")), Decimal("10.01"))
        self.assertEqual(money("10.004"), Decimal("10.00"))


# =====================================================================
# فتح الدفعة
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="cash")
class OpenPaymentTests(GatewayTestMixin, TestCase):

    def test_open_creates_pending_payment_with_snapshot_amounts(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="2500.00")

        payment = PaymentService.open_for_trip(trip)

        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.amount, Decimal("25000.00"))
        self.assertEqual(payment.platform_fee, Decimal("2500.00"))
        self.assertEqual(payment.driver_net, Decimal("22500.00"))
        self.assertEqual(payment.gateway_code, "cash")
        self.assertEqual(payment.currency, "SYP")

    def test_open_is_idempotent(self):
        trip = make_completed_trip()

        first = PaymentService.open_for_trip(trip)
        second = PaymentService.open_for_trip(trip)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.filter(trip=trip).count(), 1)

    def test_idempotency_key_is_derived_not_random(self):
        trip = make_completed_trip()
        key_a = PaymentService.build_idempotency_key(trip.pk)
        key_b = PaymentService.build_idempotency_key(trip.pk)
        self.assertEqual(key_a, key_b)

    def test_fee_greater_than_amount_is_rejected(self):
        trip = make_completed_trip(gross_fare="100.00", platform_fee="500.00")

        with self.assertRaises(PaymentError):
            PaymentService.open_for_trip(trip)

    def test_unknown_gateway_blocks_creation_before_writing(self):
        trip = make_completed_trip()

        with self.assertRaises(PaymentGatewayError):
            PaymentService.open_for_trip(trip, gateway_code="does_not_exist")

        self.assertFalse(Payment.objects.filter(trip=trip).exists())


# =====================================================================
# التحصيل والدفتر
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="cash")
class CashChargeTests(GatewayTestMixin, TestCase):

    def test_cash_charge_marks_paid_and_balances_ledger(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="2500.00")
        payment = PaymentService.open_for_trip(trip)

        payment = PaymentService.charge(payment.pk, system=True)

        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertIsNotNone(payment.paid_at)

        entries = LedgerEntry.objects.filter(payment=payment)
        self.assertEqual(entries.count(), 4)

        debit = sum(
            e.amount for e in entries if e.direction == LedgerDirection.DEBIT
        )
        credit = sum(
            e.amount for e in entries if e.direction == LedgerDirection.CREDIT
        )
        self.assertEqual(debit, credit)

    def test_cash_puts_driver_in_debt_not_credit(self):
        """
        الفخّ الذي كشفته المحاكاة: في النقدي السائق قبض المال بيده،
        فهو **مدين** للمنصّة بالعمولة لا دائن لها بالأجرة.
        """
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="2500.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        balance = DriverBalance.objects.get(driver=trip.driver, currency="SYP")

        self.assertEqual(balance.net_balance, Decimal("-2500.00"))
        self.assertTrue(balance.owes_platform)
        self.assertEqual(balance.amount_owed_to_platform, Decimal("2500.00"))

    def test_cash_fare_lands_in_driver_cash_account_not_driver(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="2500.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        driver_ref = str(trip.driver_id)

        cash_side = LedgerService.account_balance(
            LedgerAccount.DRIVER_CASH, driver_ref, "SYP"
        )
        settlement_side = LedgerService.account_balance(
            LedgerAccount.DRIVER, driver_ref, "SYP"
        )

        self.assertEqual(cash_side, Decimal("25000.00"))
        self.assertEqual(settlement_side, Decimal("-2500.00"))

    def test_recompute_matches_running_balance(self):
        """
        شبكة الأمان يجب أن تعطي النتيجة نفسها — وإلّا أفسدت ما جاءت لتصلحه.
        """
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="2500.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        before = DriverBalance.objects.get(
            driver=trip.driver, currency="SYP"
        ).net_balance

        rebuilt = LedgerService.recompute_driver_balance(trip.driver_id, "SYP")

        self.assertEqual(rebuilt.net_balance, before)

    def test_charge_is_idempotent(self):
        trip = make_completed_trip(gross_fare="10000.00", platform_fee="1000.00")
        payment = PaymentService.open_for_trip(trip)

        PaymentService.charge(payment.pk, system=True)
        PaymentService.charge(payment.pk, system=True)

        # لا قيود مضاعفة ولا رصيد مضاعف.
        self.assertEqual(LedgerEntry.objects.filter(payment=payment).count(), 4)
        balance = DriverBalance.objects.get(driver=trip.driver, currency="SYP")
        self.assertEqual(balance.net_balance, Decimal("-1000.00"))

    def test_zero_fee_writes_only_two_entries(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="0.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        self.assertEqual(LedgerEntry.objects.filter(payment=payment).count(), 2)
        balance = DriverBalance.objects.get(driver=trip.driver, currency="SYP")
        self.assertEqual(balance.net_balance, Decimal("0.00"))

    def test_cash_refund_is_refused(self):
        trip = make_completed_trip()
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        with self.assertRaises(PaymentError):
            PaymentService.refund(payment.pk, reason="اختبار الرفض")


@override_settings(
    PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="test_online"
)
class OnlineChargeTests(GatewayTestMixin, TestCase):

    def test_online_credits_driver_instead_of_debiting(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="3750.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        balance = DriverBalance.objects.get(driver=trip.driver, currency="SYP")

        self.assertEqual(balance.net_balance, Decimal("21250.00"))
        self.assertFalse(balance.owes_platform)

    def test_gateway_reference_is_stored(self):
        trip = make_completed_trip()
        payment = PaymentService.open_for_trip(trip)
        payment = PaymentService.charge(payment.pk, system=True)
        self.assertEqual(payment.gateway_reference, "EXT-1")

    def test_full_refund_marks_refunded_and_writes_reverse_entries(self):
        trip = make_completed_trip(gross_fare="25000.00", platform_fee="3750.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        before = LedgerEntry.objects.filter(payment=payment).count()
        refund = PaymentService.refund(payment.pk, reason="ألغى الزبون")

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(payment.amount_refunded, Decimal("25000.00"))
        self.assertEqual(refund.amount, Decimal("25000.00"))
        self.assertEqual(
            LedgerEntry.objects.filter(payment=payment).count(), before + 2
        )

    def test_partial_refund_then_remainder(self):
        trip = make_completed_trip(gross_fare="25000.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        PaymentService.refund(payment.pk, amount=Decimal("5000.00"), reason="جزئي")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PARTIALLY_REFUNDED)
        self.assertEqual(payment.refundable_amount, Decimal("20000.00"))

        PaymentService.refund(payment.pk, amount=Decimal("20000.00"), reason="الباقي")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)

    def test_refund_beyond_remaining_is_rejected_before_calling_gateway(self):
        trip = make_completed_trip(gross_fare="1000.00")
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        with self.assertRaises(PaymentError):
            PaymentService.refund(payment.pk, amount=Decimal("5000.00"), reason="زائد")

    def test_refund_before_payment_is_rejected(self):
        trip = make_completed_trip()
        payment = PaymentService.open_for_trip(trip)

        with self.assertRaises(InvalidTransition):
            PaymentService.refund(payment.pk, reason="سابق لأوانه")


# =====================================================================
# مقاومة الفشل — أهمّ ما طُلب
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS)
class GatewayFailureTests(GatewayTestMixin, TestCase):

    def _payment_on(self, gateway_code, **kwargs):
        trip = make_completed_trip(**kwargs)
        return PaymentService.open_for_trip(trip, gateway_code=gateway_code)

    def test_permanent_failure_marks_failed_and_writes_no_ledger(self):
        payment = self._payment_on("test_failing")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(LedgerEntry.objects.filter(payment=payment).count(), 0)

    def test_transient_failure_stays_retryable(self):
        payment = self._payment_on("test_flaky")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        payment.refresh_from_db()
        # ليست FAILED: المسار العابر يبقى قابلًا لإعادة المحاولة.
        self.assertEqual(payment.status, PaymentStatus.PROCESSING)
        self.assertFalse(payment.is_terminal)

    def test_gateway_exception_becomes_transient_not_crash(self):
        """
        بوابة تكتبها غدًا قد ترفع استثناءً لم يخطر ببالك. يجب أن يتحوّل
        إلى فشل مسجَّل لا إلى انهيار في وجه راكب واقف في الشارع.
        """
        payment = self._payment_on("test_exploding")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PROCESSING)

        attempt = PaymentAttempt.objects.filter(payment=payment).first()
        self.assertIsNotNone(attempt)
        self.assertFalse(attempt.ok)
        self.assertIn("غير متوقّع", attempt.error)

    def test_gateway_returning_wrong_type_is_treated_as_permanent(self):
        payment = self._payment_on("test_misbehaving")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)

    def test_unconfigured_gateway_raises_business_error_not_crash(self):
        payment = self._payment_on("test_unconfigured")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

    def test_every_attempt_is_recorded_even_on_failure(self):
        payment = self._payment_on("test_failing")

        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        self.assertEqual(PaymentAttempt.objects.filter(payment=payment).count(), 1)

    def test_charging_a_failed_payment_is_refused(self):
        payment = self._payment_on("test_failing")
        with self.assertRaises(PaymentError):
            PaymentService.charge(payment.pk, system=True)

        with self.assertRaises(InvalidTransition):
            PaymentService.charge(payment.pk, system=True)

    def test_attempt_logging_failure_does_not_lose_the_payment(self):
        payment = self._payment_on("cash")

        with patch.object(
            PaymentAttempt.objects, "create", side_effect=RuntimeError("قرص ممتلئ")
        ):
            payment = PaymentService.charge(payment.pk, system=True)

        # سجلّ ناقص أهون من دفعة ضائعة.
        self.assertEqual(payment.status, PaymentStatus.PAID)


# =====================================================================
# الدفتر
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="cash")
class LedgerIntegrityTests(GatewayTestMixin, TestCase):

    def _paid_payment(self):
        trip = make_completed_trip(gross_fare="10000.00", platform_fee="1000.00")
        payment = PaymentService.open_for_trip(trip)
        return PaymentService.charge(payment.pk, system=True)

    def test_unbalanced_lines_are_refused_before_writing(self):
        payment = self._paid_payment()
        before = LedgerEntry.objects.count()

        with self.assertRaises(LedgerError):
            LedgerService.record(
                payment,
                [
                    {
                        "account": LedgerAccount.CUSTOMER,
                        "account_ref": "1",
                        "direction": LedgerDirection.DEBIT,
                        "amount": Decimal("100.00"),
                        "entry_type": "adjustment",
                    },
                    {
                        "account": LedgerAccount.PLATFORM,
                        "account_ref": "",
                        "direction": LedgerDirection.CREDIT,
                        "amount": Decimal("99.00"),
                        "entry_type": "adjustment",
                    },
                ],
            )

        self.assertEqual(LedgerEntry.objects.count(), before)

    def test_float_amount_is_refused(self):
        payment = self._paid_payment()

        with self.assertRaises(LedgerError):
            LedgerService.record(
                payment,
                [{
                    "account": LedgerAccount.PLATFORM,
                    "account_ref": "",
                    "direction": LedgerDirection.DEBIT,
                    "amount": 100.0,
                    "entry_type": "adjustment",
                }],
            )

    def test_entry_cannot_be_modified(self):
        payment = self._paid_payment()
        entry = LedgerEntry.objects.filter(payment=payment).first()

        entry.amount = Decimal("1.00")
        with self.assertRaises(NotImplementedError):
            entry.save()

    def test_entry_cannot_be_deleted(self):
        payment = self._paid_payment()
        entry = LedgerEntry.objects.filter(payment=payment).first()

        with self.assertRaises(NotImplementedError):
            entry.delete()

    def test_queryset_update_and_delete_are_blocked(self):
        self._paid_payment()

        with self.assertRaises(NotImplementedError):
            LedgerEntry.objects.all().update(amount=Decimal("1.00"))

        with self.assertRaises(NotImplementedError):
            LedgerEntry.objects.all().delete()

    def test_audit_reports_no_imbalance_after_normal_flow(self):
        self._paid_payment()
        self.assertEqual(LedgerService.audit_all("SYP"), [])


# =====================================================================
# الواجهات
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="cash")
class PaymentApiTests(GatewayTestMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.driver = make_driver()
        self.trip = make_completed_trip(
            customer=self.customer,
            driver=self.driver,
            gross_fare="25000.00",
            platform_fee="2500.00",
        )
        self.payment = PaymentService.open_for_trip(self.trip)
        self.ride_id = self.trip.ride_id

    # -- القراءة ------------------------------------------------------

    def test_customer_can_read_own_payment(self):
        auth(self.client, self.customer)
        response = self.client.get(f"/api/v1/trips/{self.ride_id}/payment/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["amount"], "25000.00")

    def test_driver_can_read_payment_of_own_trip(self):
        auth(self.client, self.driver)
        response = self.client.get(f"/api/v1/trips/{self.ride_id}/payment/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stranger_gets_404_not_403(self):
        # 403 تؤكّد للغريب أن الرحلة موجودة — وهي معلومة لا يستحقّها.
        auth(self.client, make_customer())
        response = self.client.get(f"/api/v1/trips/{self.ride_id}/payment/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_is_rejected(self):
        self.client.credentials()
        response = self.client.get(f"/api/v1/trips/{self.ride_id}/payment/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- التحصيل ------------------------------------------------------

    def test_driver_confirms_cash_collection(self):
        auth(self.client, self.driver)
        response = self.client.post(
            f"/api/v1/trips/{self.ride_id}/payment/charge/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], PaymentStatus.PAID)

    def test_double_charge_is_safe(self):
        auth(self.client, self.driver)
        url = f"/api/v1/trips/{self.ride_id}/payment/charge/"

        self.client.post(url, {}, format="json")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(LedgerEntry.objects.filter(payment=self.payment).count(), 4)

    def test_switching_gateway_before_charge_is_allowed(self):
        auth(self.client, self.customer)
        response = self.client.post(
            f"/api/v1/trips/{self.ride_id}/payment/charge/",
            {"gateway_code": "test_online"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.gateway_code, "test_online")

    def test_switching_gateway_after_charge_is_conflict(self):
        """
        دوران مقصود: السائق يقبض، ثمّ الزبون يحاول التبديل.

        صار لكلّ فعل صاحبه: قبضُ النقد للسائق (وإلّا أكّد الزبون دفعةً
        لم يدفعها)، وتبديل وسيلة الدفع للزبون (وإلّا حوّل السائق دفعة
        إلكترونية إلى نقد ثمّ أكّدها بنفسه). فيلزم الطرفان لبلوغ
        شرط "مسوّاة" الذي يختبره هذا.
        """
        url = f"/api/v1/trips/{self.ride_id}/payment/charge/"

        auth(self.client, self.driver)
        charged = self.client.post(url, {}, format="json")
        self.assertEqual(charged.status_code, status.HTTP_200_OK)

        auth(self.client, self.customer)
        response = self.client.post(
            url, {"gateway_code": "test_online"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_unknown_gateway_returns_400_not_500(self):
        auth(self.client, self.customer)
        response = self.client.post(
            f"/api/v1/trips/{self.ride_id}/payment/charge/",
            {"gateway_code": "nope"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- البوابات المتاحة ---------------------------------------------

    def test_gateways_endpoint_hides_unconfigured(self):
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/payments/gateways/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {row["code"] for row in response.data}
        self.assertIn("cash", codes)
        self.assertNotIn("test_unconfigured", codes)

    # -- رصيد السائق ---------------------------------------------------

    def test_driver_balance_returns_zeros_when_empty(self):
        auth(self.client, make_driver())
        response = self.client.get("/api/v1/me/driver-balance/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["net_balance"], "0.00")

    def test_customer_cannot_read_driver_balance(self):
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/me/driver-balance/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -- الإعادة -------------------------------------------------------

    def test_refund_requires_staff(self):
        auth(self.client, self.customer)
        response = self.client.post(
            f"/api/v1/payments/{self.payment.pk}/refund/",
            {"reason": "محاولة غير مصرّح بها"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_refund_requires_reason(self):
        auth(self.client, make_admin())
        response = self.client.post(
            f"/api/v1/payments/{self.payment.pk}/refund/", {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================================
# التكامل مع دورة حياة الرحلة
# =====================================================================

@override_settings(PAYMENT_GATEWAYS=ALL_TEST_GATEWAYS, PAYMENT_DEFAULT_GATEWAY="cash")
class TripCompletionHookTests(GatewayTestMixin, TestCase):

    def test_backfill_creates_missing_payment(self):
        from payments.tasks import backfill_missing_payments
        from django.utils import timezone
        from datetime import timedelta

        trip = make_completed_trip()
        Payment.objects.filter(trip=trip).delete()

        # نُقدّم وقت الإتمام لتجاوز مهلة السماح.
        trip.completed_at = timezone.now() - timedelta(minutes=10)
        trip.save(update_fields=["completed_at"])

        result = backfill_missing_payments()

        self.assertEqual(result["created"], 1)
        self.assertTrue(Payment.objects.filter(trip=trip).exists())

    def test_payment_failure_does_not_block_trip_completion(self):
        """
        سائق أنهى رحلة وراكبها نزل يجب ألّا يُحبس بسبب خلل في التسعير.
        """
        from trips.services.trip import TripService

        trip = make_completed_trip()

        with patch.object(
            PaymentService, "open_for_trip", side_effect=RuntimeError("خلل")
        ):
            # لا يرفع استثناءً — يسجّل ويمضي.
            TripService._open_payment(trip)
