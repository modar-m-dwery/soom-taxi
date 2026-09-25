"""
السوم بنمط inDrive: الزبون يعرض سعره، والسائقون يقبلونه أو يعرضون أعلى.

القواعد التي يثبّتها هذا الملفّ:
  - أرضيّة الزبون نسبةٌ من تسعيرة المنصّة (70٪ افتراضًا) — لا سباق للأرخص.
  - السعر يُرفع ولا يُخفض بعد عرضه.
  - عرض السائق ≥ سعر الزبون، وسقفه نسبةٌ من سعر الزبون.
  - «الأقرب» بسعر المنصّة، فلا اقتراح فيه.
  - منطقةٌ لم تفعّل «الزبون يقترح السعر» ترفض الاقتراح.
"""
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APIClient

from config.testkit import auth, make_customer, make_driver, make_ride
from locations.models import PricingPolicy, ServiceArea
from locations.services import LocationService
from matching.services.matching import MatchingError, MatchingService

QUOTE = "10000.00"


def make_area(**overrides):
    defaults = dict(
        name="جبلة", center=Point(35.9275, 35.3617, srid=4326),
        fallback_radius_km=Decimal("8"), is_active=True,
        allowed_pricing_policies=[
            PricingPolicy.PLATFORM_FIXED, PricingPolicy.DRIVER_BIDDING,
            PricingPolicy.CUSTOMER_BIDDING,
        ],
    )
    defaults.update(overrides)
    area, _ = ServiceArea.objects.update_or_create(code="JAB", defaults=defaults)
    LocationService.invalidate_cache()
    return area


class ProposalBoundsTests(TestCase):

    def setUp(self):
        self.area = make_area()
        self.customer = make_customer()
        self.ride = make_ride(self.customer, gross_fare=QUOTE, service_area=self.area)

    def _propose(self, fare):
        return MatchingService.propose_fare(self.ride.id, self.customer, Decimal(fare))

    def test_proposal_is_stored(self):
        ride = self._propose("8000")
        self.assertEqual(ride.customer_proposed_fare, Decimal("8000.00"))

    def test_below_seventy_percent_is_rejected(self):
        with self.assertRaises(MatchingError):
            self._propose("6999")
        self._propose("7000")

    def test_area_ratio_is_respected(self):
        self.area.customer_proposal_min_ratio = Decimal("0.90")
        self.area.save(update_fields=["customer_proposal_min_ratio"])
        with self.assertRaises(MatchingError):
            self._propose("8500")

    def test_can_raise_but_not_lower(self):
        self._propose("8000")
        with self.assertRaisesMessage(MatchingError, "رفعه فقط"):
            self._propose("7500")
        with self.assertRaisesMessage(MatchingError, "رفعه فقط"):
            self._propose("8000")
        ride = self._propose("9000")
        self.assertEqual(ride.customer_proposed_fare, Decimal("9000.00"))

    def test_typo_cap_without_area_cap(self):
        with self.assertRaises(MatchingError):
            self._propose("300001")

    def test_not_for_nearest(self):
        self.ride.auto_dispatch = True
        self.ride.save(update_fields=["auto_dispatch"])
        with self.assertRaisesMessage(MatchingError, "الأقرب"):
            self._propose("9000")

    def test_area_without_customer_bidding_rejects(self):
        make_area(allowed_pricing_policies=[PricingPolicy.PLATFORM_FIXED, PricingPolicy.DRIVER_BIDDING])
        with self.assertRaisesMessage(MatchingError, "غير مفعّل"):
            self._propose("9000")

    def test_only_owner_can_propose(self):
        from rides.models import RideRequest

        with self.assertRaises(RideRequest.DoesNotExist):
            MatchingService.propose_fare(self.ride.id, make_customer(), Decimal("9000"))


class DriverOffersOnProposalTests(TestCase):

    def setUp(self):
        self.area = make_area()
        self.customer = make_customer()
        self.driver = make_driver()
        self.ride = make_ride(self.customer, gross_fare=QUOTE, service_area=self.area)
        MatchingService.propose_fare(self.ride.id, self.customer, Decimal("8000"))

    def _offer(self, fare, driver=None):
        return MatchingService.create_offer(
            ride_id=self.ride.id, driver=driver or self.driver,
            gross_fare=Decimal(fare), eta_minutes=4,
        )

    def test_driver_accepts_customer_price(self):
        offer = self._offer("8000")
        self.assertEqual(offer.gross_fare, Decimal("8000.00"))

    def test_driver_cannot_undercut_customer(self):
        with self.assertRaises(MatchingError):
            self._offer("7900")

    def test_counter_offer_capped_by_ratio(self):
        self._offer("12000")  # 150٪ من 8000
        with self.assertRaises(MatchingError):
            self._offer("12001", driver=make_driver())

    def test_customer_pays_the_offer_they_pick(self):
        offer = self._offer("9000")
        MatchingService.select_offer(ride_id=self.ride.id, offer_id=offer.id, customer=self.customer)
        self.ride.refresh_from_db()
        self.assertEqual(self.ride.customer_total, Decimal("9000.00"))

    def test_proposal_works_where_only_customer_bidding_is_allowed(self):
        make_area(allowed_pricing_policies=[PricingPolicy.PLATFORM_FIXED, PricingPolicy.CUSTOMER_BIDDING])
        offer = self._offer("8000")
        self.assertEqual(offer.gross_fare, Decimal("8000.00"))


class ProposeFareEndpointTests(TestCase):

    def setUp(self):
        self.area = make_area()
        self.customer = make_customer()
        self.ride = make_ride(self.customer, gross_fare=QUOTE, service_area=self.area)
        self.client = APIClient()
        auth(self.client, self.customer)

    def test_propose_returns_ride_with_price(self):
        response = self.client.post(
            f"/api/v1/rides/{self.ride.id}/propose-fare/", {"proposed_fare": "8500.00"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["customer_proposed_fare"], "8500.00")

    def test_too_low_explains(self):
        response = self.client.post(
            f"/api/v1/rides/{self.ride.id}/propose-fare/", {"proposed_fare": "100.00"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("أقل من الحد", response.json()["detail"])

    def test_other_customer_gets_404(self):
        other = APIClient()
        auth(other, make_customer())
        response = other.post(
            f"/api/v1/rides/{self.ride.id}/propose-fare/", {"proposed_fare": "8500.00"}, format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_config_exposes_proposal_settings(self):
        response = self.client.get("/api/v1/config/", {"lat": 35.3617, "lng": 35.9275})
        pricing = response.json()["pricing"]
        self.assertTrue(pricing["customer_can_propose"])
        self.assertEqual(pricing["customer_proposal_min_ratio"], "0.70")
        self.assertEqual(pricing["customer_proposal_step"], "500.00")


class CustomerBiddingMigrationTests(TestCase):

    def test_new_areas_allow_customer_bidding_by_default(self):
        self.assertIn(PricingPolicy.CUSTOMER_BIDDING, ServiceArea.default_pricing_policies())
