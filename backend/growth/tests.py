"""العمولات، العروض الفوريّة، الحوافز، والتقارير."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from config.testkit import (
    auth,
    make_admin,
    make_completed_trip,
    make_customer,
    make_driver,
    make_ride,
)
from growth.models import (
    Campaign,
    CampaignRecipient,
    CommissionRule,
    DriverGroup,
    IncentiveAward,
    IncentiveProgram,
)
from growth.services.campaigns import CampaignService
from growth.services.commission import CommissionService
from growth.services.incentives import IncentiveService
from growth.services.reports import Reports
from locations.models import ServiceArea
from notifications.models import Notification
from payments.models import CustomerCredit
from rides.models import RideStatus


class CommissionTests(TestCase):

    def setUp(self):
        from django.contrib.gis.geos import Point

        self.area = ServiceArea.objects.create(code="JAB", name="جبلة", center=Point(35.92, 35.36, srid=4326))
        self.driver = make_driver()

    def _rule(self, scope, rate, **kwargs):
        return CommissionRule.objects.create(name=scope, scope=scope, rate_pct=Decimal(rate), **kwargs)

    def test_no_rules_means_zero(self):
        self.assertEqual(CommissionService.fee_for(self.driver, self.area, 10000), Decimal("0.00"))

    def test_most_specific_rule_wins(self):
        self._rule("default", "10")
        self._rule("area", "8", area=self.area)
        group = DriverGroup.objects.create(name="ريف")
        group.drivers.add(self.driver)
        self._rule("group", "5", group=group)
        self.assertEqual(CommissionService.fee_for(self.driver, self.area, 10000), Decimal("500.00"))
        self._rule("driver", "2", driver=self.driver)
        self.assertEqual(CommissionService.fee_for(self.driver, self.area, 10000), Decimal("200.00"))
        # سائقٌ آخر بلا مجموعة: قاعدة المدينة.
        self.assertEqual(CommissionService.fee_for(make_driver(), self.area, 10000), Decimal("800.00"))

    def test_founder_always_zero(self):
        self._rule("driver", "10", driver=self.driver)
        self.driver.commission_exempt = True
        self.assertEqual(CommissionService.fee_for(self.driver, self.area, 10000), Decimal("0.00"))

    def test_expired_rule_ignored_and_bounds_apply(self):
        self._rule("default", "10", valid_until=timezone.now() - timedelta(days=1))
        self.assertEqual(CommissionService.fee_for(self.driver, None, 10000), Decimal("0.00"))
        self._rule("default", "1", min_fee=Decimal("300"), max_fee=Decimal("400"))
        self.assertEqual(CommissionService.fee_for(self.driver, None, 10000), Decimal("300.00"))

    def test_area_legal_cap_still_applies(self):
        from pricing.services import PricingService

        self.area.commission_cap_pct = Decimal("5")
        self._rule("default", "20")
        fee = PricingService._platform_fee(self.area, Decimal("10000"), driver=self.driver)
        self.assertEqual(fee, Decimal("500.00"))


class CommissionWindowAndServiceTests(TestCase):
    """«الليل أرخص» و«المشترك بعمولة أقلّ» — بتوقيت دمشق."""

    def setUp(self):
        from zoneinfo import ZoneInfo

        self.tz = ZoneInfo("Asia/Damascus")
        self.driver = make_driver()
        CommissionRule.objects.create(name="عامّة", scope="default", rate_pct=Decimal("10"))

    def _at(self, hour, day=24):
        # 2026-09-24 خميس (weekday 3)
        from datetime import datetime

        return datetime(2026, 9, day, hour, 30, tzinfo=self.tz)

    def _fee(self, when, service=None):
        return CommissionService.fee_for(self.driver, None, 10000, now=when, service=service)

    def test_night_window_crosses_midnight(self):
        CommissionRule.objects.create(
            name="ليل", scope="default", rate_pct=Decimal("5"), hour_from=22, hour_to=5,
        )
        self.assertEqual(self._fee(self._at(23)), Decimal("500.00"))
        self.assertEqual(self._fee(self._at(3)), Decimal("500.00"))
        self.assertEqual(self._fee(self._at(12)), Decimal("1000.00"))
        # حدّ النهاية غير مشمول
        self.assertEqual(self._fee(self._at(5)), Decimal("1000.00"))

    def test_hours_are_damascus_time_not_utc(self):
        CommissionRule.objects.create(
            name="ليل", scope="default", rate_pct=Decimal("5"), hour_from=22, hour_to=5,
        )
        from datetime import timezone as dt_timezone

        utc_20 = self._at(23).astimezone(dt_timezone.utc)   # 20:30 UTC = 23:30 دمشق
        self.assertEqual(utc_20.hour, 20)
        self.assertEqual(self._fee(utc_20), Decimal("500.00"))

    def test_weekday_rule(self):
        CommissionRule.objects.create(
            name="خميس", scope="default", rate_pct=Decimal("7"), weekdays=[3],
        )
        self.assertEqual(self._fee(self._at(12, day=24)), Decimal("700.00"))   # خميس
        self.assertEqual(self._fee(self._at(12, day=25)), Decimal("1000.00"))  # جمعة

    def test_service_rule_only_for_that_service(self):
        CommissionRule.objects.create(
            name="مشترك", scope="default", rate_pct=Decimal("6"), service_code="shared",
        )
        self.assertEqual(self._fee(self._at(12), service="shared"), Decimal("600.00"))
        self.assertEqual(self._fee(self._at(12), service="taxi"), Decimal("1000.00"))
        self.assertEqual(self._fee(self._at(12)), Decimal("1000.00"))

    def test_driver_rule_still_beats_windowed_default(self):
        CommissionRule.objects.create(
            name="ليل", scope="default", rate_pct=Decimal("5"), hour_from=22, hour_to=5,
        )
        CommissionRule.objects.create(
            name="سائق", scope="driver", driver=self.driver, rate_pct=Decimal("2"),
        )
        self.assertEqual(self._fee(self._at(23)), Decimal("200.00"))

    def test_settled_fare_uses_ride_service(self):
        from matching.models import OfferStatus, RideOffer
        from pricing.services import PricingService
        from rides.models import RideMode

        CommissionRule.objects.create(
            name="مشترك", scope="default", rate_pct=Decimal("6"), service_code="shared",
        )
        ride = make_ride(make_customer(), mode=RideMode.SHARED, gross_fare="10000.00")
        offer = RideOffer(
            ride=ride, driver=self.driver, gross_fare=Decimal("10000"), eta_minutes=3,
            status=OfferStatus.ACCEPTED, expires_at=timezone.now(),
        )
        PricingService.settle_from_offer(ride, offer, self.driver)
        self.assertEqual(ride.platform_fee, Decimal("600.00"))

    def test_validation(self):
        from django.core.exceptions import ValidationError

        bad = [
            CommissionRule(name="x", scope="default", hour_from=22),
            CommissionRule(name="x", scope="default", hour_from=5, hour_to=5),
            CommissionRule(name="x", scope="default", weekdays=[7]),
            CommissionRule(name="x", scope="default", service_code="spaceship"),
        ]
        for rule in bad:
            with self.assertRaises(ValidationError):
                rule.clean()


class CampaignTests(TestCase):

    def test_credit_offer_to_idle_customers_is_granted_once(self):
        idle = make_customer()
        make_completed_trip(customer=idle)
        from rides.models import RideRequest
        RideRequest.objects.filter(customer=idle).update(created_at=timezone.now() - timedelta(days=30))
        active = make_customer()
        make_completed_trip(customer=active)

        campaign = Campaign.objects.create(
            title="اشتقنالك", body="رصيد 5000 على رحلتك الجاية",
            audience=Campaign.Audience.IDLE_CUSTOMERS, idle_days=14,
            credit_amount=Decimal("5000"),
        )
        self.assertEqual(CampaignService.send(campaign), 1)
        self.assertEqual(CampaignService.send(campaign), 0)  # لا مرّتين

        credit = CustomerCredit.objects.get(customer=idle)
        self.assertEqual(credit.amount, Decimal("5000.00"))
        self.assertFalse(CustomerCredit.objects.filter(customer=active).exists())
        self.assertTrue(Notification.objects.filter(user=idle, event_type="campaign.offer").exists())
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.recipients_count), (Campaign.Status.SENT, 1))

    def test_driver_group_message(self):
        group = DriverGroup.objects.create(name="المؤسّسون")
        member, outsider = make_driver(), make_driver()
        group.drivers.add(member)
        campaign = Campaign.objects.create(
            title="شكرًا", body="أنتم أساس سووم",
            audience=Campaign.Audience.DRIVER_GROUP, group=group,
        )
        CampaignService.send(campaign)
        self.assertTrue(CampaignRecipient.objects.filter(user=member.user).exists())
        self.assertFalse(CampaignRecipient.objects.filter(user=outsider.user).exists())

    def test_campaign_credit_is_consumed_on_next_payment(self):
        from payments.services.promotions import PromotionService

        customer = make_customer()
        campaign = Campaign.objects.create(
            title="عرض", body="رصيد", audience=Campaign.Audience.ALL_CUSTOMERS,
            credit_amount=Decimal("3000"),
        )
        CampaignService.send(campaign)
        discount, reason = PromotionService.quote(customer, None, Decimal("10000"))
        self.assertEqual(discount, Decimal("3000.00"))


class IncentiveTests(TestCase):

    def setUp(self):
        self.driver = make_driver()
        self.program = IncentiveProgram.objects.create(
            name="30 مشوار", period=IncentiveProgram.Period.WEEK, target_trips=3,
            reward_amount=Decimal("10"), reward_label="10 ليترات بنزين",
        )

    def _complete(self, n):
        for _ in range(n):
            make_completed_trip(driver=self.driver)

    def test_progress_and_single_award(self):
        self._complete(2)
        row = IncentiveService.progress(self.driver)[0]
        self.assertEqual((row["completed_trips"], row["remaining_trips"], row["earned"]), (2, 1, False))
        self.assertEqual(IncentiveService.evaluate(self.driver), [])

        self._complete(2)
        self.assertEqual(len(IncentiveService.evaluate(self.driver)), 1)
        self.assertEqual(IncentiveService.evaluate(self.driver), [])
        self.assertEqual(IncentiveAward.objects.filter(driver=self.driver).count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.driver.user, event_type="incentive.earned").exists())

    def test_group_program_skips_others(self):
        group = DriverGroup.objects.create(name="فان")
        self.program.group = group
        self.program.save()
        self._complete(3)
        self.assertEqual(IncentiveService.evaluate(self.driver), [])

    def test_min_rating(self):
        self.program.min_rating = Decimal("4.5")
        self.program.save()
        self.driver.rating = Decimal("4.0")
        self.driver.save(update_fields=["rating"])
        self._complete(3)
        self.assertEqual(IncentiveService.evaluate(self.driver), [])

    def test_driver_api(self):
        client = APIClient()
        auth(client, self.driver)
        body = client.get("/api/v1/me/incentives/").json()
        self.assertEqual(body[0]["target_trips"], 3)
        client = APIClient()
        auth(client, make_customer())
        self.assertEqual(client.get("/api/v1/me/incentives/").status_code, 403)


class ReportTests(TestCase):

    def test_summary_counts_unmatched(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.EXPIRED)
        make_completed_trip(customer=customer)
        summary = Reports.summary(7)
        self.assertEqual((summary["requests"], summary["completed"], summary["unmatched"]), (2, 1, 1))

    def test_behaviour_score_neutral_for_new_driver(self):
        self.assertGreaterEqual(Reports.behaviour_score(None, None, 0, 0), 80)
        self.assertLess(Reports.behaviour_score(Decimal("3.0"), 0.5, 5, 5), 60)

    def test_dashboard_staff_only(self):
        from django.test import Client

        client = Client()
        self.assertEqual(client.get("/ops/growth/").status_code, 302)
        admin = make_admin()
        client.force_login(admin)
        make_completed_trip()
        response = client.get("/ops/growth/?days=30")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "زبائن خاملون")
