"""
أثر التقييد على بقيّة المنصّة: الخصومات، «اختر سيارتك»، «الأقرب»، الحوافز،
ولوحة النزاهة للموظّفين وحدهم.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from config.testkit import make_admin, make_customer, make_driver, make_ride
from growth.models import IncentiveProgram
from growth.services.incentives import IncentiveService
from integrity import registry
from integrity.models import RiskLevel
from integrity.services.scoring import IntegrityService
from payments.models import CustomerCredit
from payments.services.promotions import PromotionService


def _restrict(user):
    IntegrityService.set_manual_level(user, RiskLevel.RESTRICTED)


class PromotionEnforcementTests(TestCase):

    def test_restricted_customer_gets_no_credit(self):
        customer = make_customer()
        CustomerCredit.objects.create(
            customer=customer, amount=Decimal("5000"), currency="SYP", reason="campaign",
        )
        discount, _ = PromotionService.quote(customer, None, Decimal("20000"))
        self.assertEqual(discount, Decimal("5000.00"))

        _restrict(customer)
        discount, reason = PromotionService.quote(customer, None, Decimal("20000"))
        self.assertEqual(discount, Decimal("0"))
        self.assertEqual(reason, "")


class PickCarEnforcementTests(TestCase):

    def test_restricted_customer_cannot_pick_a_car(self):
        from matching.services.invitation import InvitationError, InvitationService

        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer)
        _restrict(customer)
        with self.assertRaisesMessage(InvitationError, "بانتظار مراجعة"):
            InvitationService.create(ride_id=ride.id, driver_id=driver.id, customer=customer)


class NearestEnforcementTests(TestCase):

    def test_restricted_driver_ids_contains_only_restricted_drivers(self):
        clean, flagged = make_driver(), make_driver()
        _restrict(flagged.user)
        ids = IntegrityService.restricted_driver_ids()
        self.assertIn(flagged.id, ids)
        self.assertNotIn(clean.id, ids)

    def test_restricted_customers_are_not_driver_ids(self):
        customer = make_customer()
        _restrict(customer)
        self.assertEqual(IntegrityService.restricted_driver_ids(), set())


class IncentiveEnforcementTests(TestCase):

    def test_restricted_driver_earns_no_award(self):
        from config.testkit import make_completed_trip

        driver = make_driver()
        IncentiveProgram.objects.create(
            name="3 مشاوير", period=IncentiveProgram.Period.DAY, target_trips=3,
            reward_amount=Decimal("10"), reward_label="10 ليترات",
        )
        for _ in range(3):
            make_completed_trip(driver=driver)

        _restrict(driver.user)
        self.assertEqual(IncentiveService.evaluate(driver), [])

        IntegrityService.set_manual_level(driver.user, "")
        self.assertEqual(len(IncentiveService.evaluate(driver)), 1)


class DashboardTests(TestCase):

    def test_staff_sees_dashboard(self):
        IntegrityService.record(make_customer(), registry.MULTI_ACCOUNT_DEVICE.code)
        self.client.force_login(make_admin())
        response = self.client.get(reverse("integrity-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, registry.MULTI_ACCOUNT_DEVICE.label)

    def test_non_staff_is_redirected(self):
        self.client.force_login(make_customer())
        response = self.client.get(reverse("integrity-dashboard"))
        self.assertEqual(response.status_code, 302)
