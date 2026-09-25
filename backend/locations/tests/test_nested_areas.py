"""
مناطق متداخلة: ضيعةٌ بإعداداتها (نصف قطر أوسع مثلًا) داخل نطاق مدينة —
النقطة داخل الضيعة تتبع الضيعة، وخارجها تتبع المدينة، مهما كان ترتيب
الصفوف في القاعدة.
"""
from decimal import Decimal

from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase

from locations.models import ServiceArea
from locations.services import LocationService


def _square(lng, lat, half_deg):
    return Polygon.from_bbox((lng - half_deg, lat - half_deg, lng + half_deg, lat + half_deg))


class NestedAreaTests(TestCase):

    def setUp(self):
        LocationService.invalidate_cache()

    def tearDown(self):
        LocationService.invalidate_cache()

    def test_smaller_polygon_wins_regardless_of_order(self):
        # المدينة أوّلًا في القاعدة — كانت تغلب دائمًا قبل الإصلاح.
        city = ServiceArea.objects.create(
            code="CTY", name="مدينة", boundary=_square(35.92, 35.36, 0.10),
            center=Point(35.92, 35.36, srid=4326),
        )
        village = ServiceArea.objects.create(
            code="VIL", name="ضيعة", boundary=_square(35.95, 35.38, 0.01),
            center=Point(35.95, 35.38, srid=4326),
            default_matching_radius_km=Decimal("12"),
        )
        LocationService.invalidate_cache()
        self.assertEqual(LocationService.resolve_area(35.95, 35.38), village)
        self.assertEqual(LocationService.resolve_area(35.90, 35.34), city)

    def test_polygon_inside_radius_area(self):
        city = ServiceArea.objects.create(
            code="RAD", name="مدينة بنصف قطر", center=Point(35.92, 35.36, srid=4326),
            fallback_radius_km=Decimal("15"),
        )
        village = ServiceArea.objects.create(
            code="VL2", name="ضيعة", boundary=_square(35.95, 35.38, 0.01),
        )
        LocationService.invalidate_cache()
        self.assertEqual(LocationService.resolve_area(35.95, 35.38), village)
        self.assertEqual(LocationService.resolve_area(35.92, 35.36), city)

    def test_single_match_and_outside(self):
        area = ServiceArea.objects.create(
            code="ONE", name="وحيدة", center=Point(35.92, 35.36, srid=4326),
            fallback_radius_km=Decimal("5"),
        )
        LocationService.invalidate_cache()
        self.assertEqual(LocationService.resolve_area(35.92, 35.36), area)
        self.assertIsNone(LocationService.resolve_area(36.50, 35.36))
