"""
كنس الحضور بمهلة كلّ مدينة.

الرقم الذي كان مكتوبًا في الشيفرة: `PRESENCE_HEARTBEAT_STALE_SECONDS = 60`
— ولا حتّى متغيّر بيئة. ما تحرسه هذه الاختبارات أنّه صار قابلًا للضبط لكلّ
مدينة **وأنّ الضبط يسري فعلًا على الكنس**، لا أنّه ظهر في الأدمن فحسب.

والفرق يهمّ عمليًّا: حيٌّ بشبكة ضعيفة يحتاج تسامحًا أوسع، وإلّا اختفى سائقوه
من الخريطة كلّ دقيقة وعادوا. ومدينة بتغطية جيّدة تريد العكس: خريطة نظيفة
لا تعرض سائقًا انقطع.
"""
import time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TestCase

from config.testkit import make_driver
from locations.models import ServiceArea
from locations.services import LocationService
from presence.tasks import _area_stale_map, _sweep_by_area


JABLEH = (35.90, 35.36)
LATTAKIA = (35.7797, 35.5317)


def make_area(code, lng_lat, **overrides):
    lng, lat = lng_lat
    defaults = dict(
        name=code,
        center=Point(lng, lat, srid=4326),
        fallback_radius_km=Decimal("8"),
        default_matching_radius_km=Decimal("5"),
        is_active=True,
    )
    defaults.update(overrides)
    area, _ = ServiceArea.objects.update_or_create(code=code, defaults=defaults)
    LocationService.invalidate_cache()
    return area


class AreaStaleMapTests(TestCase):

    def tearDown(self):
        LocationService.invalidate_cache()

    def test_map_carries_the_global_default_under_none(self):
        make_area("JAB", JABLEH)

        stale = _area_stale_map()

        from django.conf import settings

        self.assertEqual(stale[None], settings.PRESENCE_HEARTBEAT_STALE_SECONDS)

    def test_each_area_contributes_its_own_value(self):
        jableh = make_area("JAB", JABLEH, presence_stale_seconds=45)
        lattakia = make_area("LAT", LATTAKIA, presence_stale_seconds=120)

        stale = _area_stale_map()

        self.assertEqual(stale[jableh.id], 45)
        self.assertEqual(stale[lattakia.id], 120)

    def test_unset_area_inherits_the_global_default(self):
        area = make_area("JAB", JABLEH, presence_stale_seconds=None)

        stale = _area_stale_map()

        self.assertEqual(stale[area.id], stale[None])


class SweepByAreaTests(TestCase):
    """
    نمنع ريديس عن هذه الاختبارات ونحقن المرشّحين: ما نختبره هو **قرار** من
    يُكنَس، لا نقل البايتات. حقن المرشّحين يجعل الاختبار حتميًّا بلا انتظار
    ستّين ثانية حقيقية.
    """

    def setUp(self):
        self.jableh = make_area("JAB", JABLEH, presence_stale_seconds=45)
        self.lattakia = make_area("LAT", LATTAKIA, presence_stale_seconds=120)

        self.fast = make_driver(location=JABLEH)
        self.fast.home_service_area = self.jableh
        self.fast.save(update_fields=["home_service_area"])

        self.slow = make_driver(location=LATTAKIA)
        self.slow.home_service_area = self.lattakia
        self.slow.save(update_fields=["home_service_area"])

    def tearDown(self):
        LocationService.invalidate_cache()

    def _sweep(self, silence_seconds):
        """كلا السائقين صامتان المدّة نفسها. من يُكنَس؟"""
        now = time.time()
        candidates = [
            (self.fast.id, now - silence_seconds),
            (self.slow.id, now - silence_seconds),
        ]

        with patch(
            "presence.services.PresenceService.stale_candidates",
            return_value=candidates,
        ), patch(
            "presence.services.PresenceService.mark_offline",
            side_effect=lambda ids: list(ids),
        ) as mark:
            _sweep_by_area()

        return set(mark.call_args[0][0])

    def test_the_strictest_city_sweeps_first(self):
        # ستّون ثانية: تجاوزت مهلة جبلة (45) ولم تبلغ مهلة اللاذقية (120).
        swept = self._sweep(60)

        self.assertIn(self.fast.id, swept)
        self.assertNotIn(
            self.slow.id, swept,
            "سائق اللاذقية كُنس بمهلة جبلة — المهلة صارت عامّة من جديد",
        )

    def test_long_silence_sweeps_both(self):
        swept = self._sweep(200)

        self.assertEqual(swept, {self.fast.id, self.slow.id})

    def test_short_silence_sweeps_nobody(self):
        swept = self._sweep(30)

        self.assertEqual(swept, set())

    def test_driver_without_a_home_area_uses_the_global_default(self):
        # حقلٌ إداريّ فارغ يجب ألّا يعني «معلّق إلى الأبد».
        orphan = make_driver(location=JABLEH)
        self.assertIsNone(orphan.home_service_area_id)

        now = time.time()

        with patch(
            "presence.services.PresenceService.stale_candidates",
            return_value=[(orphan.id, now - 300)],
        ), patch(
            "presence.services.PresenceService.mark_offline",
            side_effect=lambda ids: list(ids),
        ) as mark:
            _sweep_by_area()

        self.assertIn(orphan.id, mark.call_args[0][0])

    def test_one_redis_scan_regardless_of_city_count(self):
        # لو مسحنا لكلّ منطقة لصارت الكلفة خطّية بعدد المدن، وهي مهمّة
        # تعمل كلّ خمس عشرة ثانية.
        make_area("HOM", (36.72, 34.73), presence_stale_seconds=30)
        make_area("ALP", (37.16, 36.20), presence_stale_seconds=90)

        with patch(
            "presence.services.PresenceService.stale_candidates",
            return_value=[],
        ) as scan:
            _sweep_by_area()

        self.assertEqual(scan.call_count, 1)

    def test_the_scan_uses_the_strictest_cutoff(self):
        # لو استعمل الأوسع لفاته من تجاوز مهلة مدينته الأقسى.
        make_area("HOM", (36.72, 34.73), presence_stale_seconds=20)

        with patch(
            "presence.services.PresenceService.stale_candidates",
            return_value=[],
        ) as scan:
            _sweep_by_area()

        self.assertEqual(scan.call_args[0][0], 20)


class DriverHomeAreaTests(TestCase):
    """المنطقة الأمّ تُملأ من أوّل اتّصال ولا تُلمس بعده."""

    def setUp(self):
        self.jableh = make_area("JAB", JABLEH)
        self.lattakia = make_area("LAT", LATTAKIA)

    def tearDown(self):
        LocationService.invalidate_cache()

    def _go_online(self, driver):
        from drivers.services.availability import DriverAvailabilityService

        with patch(
            "drivers.services.eligibility.DriverEligibilityService.is_eligible",
            return_value=True,
        ):
            return DriverAvailabilityService.go_online(driver)

    def test_first_go_online_resolves_the_home_area(self):
        driver = make_driver(location=JABLEH, status="active")
        self.assertIsNone(driver.home_service_area_id)

        driver = self._go_online(driver)

        self.assertEqual(driver.home_service_area_id, self.jableh.id)

    def test_a_trip_to_another_city_does_not_move_the_home_area(self):
        # «أين هو الآن» سؤال الموقع، و«تحت أيّ مدينة يُدار» سؤال آخر.
        driver = make_driver(location=JABLEH, status="active")
        driver = self._go_online(driver)

        driver.current_location = Point(*LATTAKIA, srid=4326)
        driver.save(update_fields=["current_location"])

        driver = self._go_online(driver)

        self.assertEqual(driver.home_service_area_id, self.jableh.id)

    def test_going_online_outside_every_area_still_works(self):
        # فشل اشتقاق حقل إداريّ يجب ألّا يمنع سائقًا من العمل.
        driver = make_driver(location=(33.0, 33.0), status="active")

        driver = self._go_online(driver)

        self.assertTrue(driver.online)
        self.assertIsNone(driver.home_service_area_id)
