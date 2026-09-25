"""بلاطات الخريطة تأتي من الخادم — تبديل المزوّد لا يحتاج تحديثًا للتطبيق."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class MapTilesConfigTests(TestCase):

    def test_defaults_to_openstreetmap(self):
        body = APIClient().get("/api/v1/config/").json()
        tiles = body["map_tiles"]
        self.assertIn("tile.openstreetmap.org", tiles["url_template"])
        self.assertIsNone(tiles["dark_url_template"])
        self.assertEqual(tiles["max_zoom"], 19)

    @override_settings(
        MAP_TILES_URL="https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=abc",
        MAP_TILES_DARK_URL="https://api.maptiler.com/maps/dataviz-dark/256/{z}/{x}/{y}.png?key=abc",
        MAP_TILES_ATTRIBUTION="© MapTiler © OpenStreetMap contributors",
    )
    def test_provider_from_settings(self):
        tiles = APIClient().get("/api/v1/config/").json()["map_tiles"]
        self.assertTrue(tiles["url_template"].startswith("https://api.maptiler.com"))
        self.assertIn("dataviz-dark", tiles["dark_url_template"])
        self.assertIn("MapTiler", tiles["attribution"])
