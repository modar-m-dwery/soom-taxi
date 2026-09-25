from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ads.models import Ad, Placement
from catalog.models import FeatureFlag
from catalog.services import invalidate
from config.testkit import auth, make_customer

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class AdsTests(TestCase):

    def setUp(self):
        invalidate()
        self.addCleanup(invalidate)
        self.client = APIClient()
        auth(self.client, make_customer())

    def _enable(self, on=True):
        flag = FeatureFlag.objects.get(key="ads")
        flag.enabled = on
        flag.save()

    def _ad(self, **kwargs):
        defaults = dict(
            title="عرض", placement=Placement.CUSTOMER_HOME,
            image=SimpleUploadedFile("a.png", PNG, content_type="image/png"),
        )
        defaults.update(kwargs)
        return Ad.objects.create(**defaults)

    def test_off_by_default(self):
        self._ad()
        self.assertEqual(self.client.get("/api/v1/ads/?placement=customer_home").status_code, 403)

    def test_live_ads_only(self):
        self._enable()
        live = self._ad()
        self._ad(title="انتهى", ends_at=timezone.now() - timedelta(hours=1))
        self._ad(title="مطفأ", is_active=False)
        body = self.client.get("/api/v1/ads/?placement=customer_home").json()
        self.assertEqual([a["id"] for a in body], [live.id])

    def test_events_count(self):
        self._enable()
        ad = self._ad()
        self.client.post(f"/api/v1/ads/{ad.id}/event/", {"kind": "impression"})
        self.client.post(f"/api/v1/ads/{ad.id}/event/", {"kind": "click"})
        ad.refresh_from_db()
        self.assertEqual((ad.impressions, ad.clicks), (1, 1))

    def test_only_https_links_and_images(self):
        with self.assertRaises(ValidationError):
            Ad(title="x", placement=Placement.CUSTOMER_HOME, link_url="http://evil.example").clean()
        from ads.models import validate_ad_image

        with self.assertRaises(ValidationError):
            validate_ad_image(SimpleUploadedFile("a.svg", b"<svg/>"))

    def test_image_served(self):
        ad = self._ad()
        response = APIClient().get(f"/api/v1/ads/{ad.id}/image/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
