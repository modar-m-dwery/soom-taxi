# -*- coding: utf-8 -*-
"""
استيراد دفتر واتساب — الجسر بين مرحلة التسعين يومًا والتطبيق.

الأعمدة والقيم هنا هي نفسها في وثيقة «بوّابة واتساب» (صفحات زبائن/سوّاق/
رحلات). إن غيّر أحدٌ اسم عمود في الجدول أو في الأمر، يسقط هذا الاختبار
قبل يوم الإطلاق لا فيه.
"""

import io
import tempfile
from decimal import Decimal
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase

from locations.models import ServiceArea
from ops.models import LegacyRide
from users.models import CustomerProfile, DriverProfile, User, UserRole
from vehicles.models import Vehicle

CUSTOMERS = """phone,name,area,usual_pickup,first_seen,rides,last_ride,source,saved_us,channel
+963991000001,أبو أحمد,JAB,دوّار الساعة,2026-06-02,7,2026-08-30,ملصق,نعم,نعم
0992000002,أم سامر,LAT,,2026-07-15,1,2026-07-15,إحالة,لا,لا
12345,معطوب,OUT,,,,,,,
"""

DRIVERS = """phone,name,category,color,plate,area,founder_no,joined,rides,complaints,status
+963993000001,أبو محمد,تكسي,أصفر,123456 جبلة,JAB,3,2026-06-01,40,0,نشط
+963993000002,سامر,micro,أبيض,555111,LAT,,2026-07-01,12,2,نائم
+963993000003,خطأ,سيدان,,999,JAB,,,,,
"""

RIDES = """datetime,customer_phone,driver_phone,from,to,area,offers,price,minutes_to_offer,status,fail_reason,rating
2026-08-30 18:20,+963991000001,+963993000001,دوّار الساعة,المشفى الوطني,JAB,3,25000,2,تمّ,,5
2026-08-31 09:05,+963991000001,,الكورنيش,الجامعة,JAB,0,,,لم تُخدَم,ما في سوّاق,
2026-09-01 21:40,0992000002,+963993000002,الميناء,الشيخ ضاهر,LAT,2,30000,4,ألغيت,الزبون ما طلع,
"""


class ImportWhatsappLedgerTests(TestCase):
    def setUp(self):
        for code, name, lng, lat in (("JAB", "جبلة", 35.9275, 35.3617),
                                     ("LAT", "اللاذقية", 35.7797, 35.5317)):
            ServiceArea.objects.update_or_create(
                code=code,
                defaults=dict(name=name, center=Point(lng, lat, srid=4326),
                              fallback_radius_km=Decimal("8"), is_active=True),
            )
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = {}
        for name, body in (("customers", CUSTOMERS), ("drivers", DRIVERS), ("rides", RIDES)):
            path = root / f"{name}.csv"
            path.write_text(body, encoding="utf-8")
            self.paths[name] = str(path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **extra):
        out = io.StringIO()
        call_command("import_whatsapp_ledger", customers=self.paths["customers"],
                     drivers=self.paths["drivers"], rides=self.paths["rides"],
                     stdout=out, **extra)
        return out.getvalue()

    def test_customers_become_users_with_their_history(self):
        self._run()

        user = User.objects.get(phone="+963991000001")
        self.assertEqual(user.role, UserRole.CUSTOMER)
        self.assertTrue(user.is_verified)
        prefs = CustomerProfile.objects.get(user=user).preferences["whatsapp"]
        self.assertEqual(prefs["rides"], 7)
        self.assertTrue(prefs["saved_us"])
        self.assertEqual(prefs["usual_pickup"], "دوّار الساعة")

        # 09XX تُطبَّع إلى +9639XX — المفصل الأوّل في الوثيقة.
        self.assertTrue(User.objects.filter(phone="+963992000002").exists())

    def test_drivers_get_profile_vehicle_and_founder_note(self):
        self._run()

        driver = DriverProfile.objects.get(user__phone="+963993000001")
        self.assertEqual(driver.status, DriverProfile.DriverStatus.PENDING)
        self.assertEqual(driver.home_service_area.code, "JAB")
        self.assertIn("سائق مؤسّس #3", driver.verification_note)

        vehicle = Vehicle.objects.get(plate_number="123456 جبلة")
        self.assertEqual(vehicle.type_id, "taxi")      # «تكسي» بالعربية → taxi
        self.assertEqual(vehicle.color, "أصفر")

        micro = Vehicle.objects.get(plate_number="555111")
        self.assertEqual(micro.type_id, "micro")       # بالرمز مباشرةً
        self.assertEqual(micro.seats, 12)

    def test_rides_are_kept_as_legacy_rows_linked_by_phone(self):
        self._run()

        self.assertEqual(LegacyRide.objects.count(), 3)
        done = LegacyRide.objects.get(status=LegacyRide.Status.DONE)
        self.assertEqual(done.price, 25000)
        self.assertEqual(done.minutes_to_offer, 2)
        self.assertEqual(done.customer.phone, "+963991000001")
        self.assertEqual(done.driver.phone, "+963993000001")

        unserved = LegacyRide.objects.get(status=LegacyRide.Status.UNSERVED)
        self.assertEqual(unserved.fail_reason, "ما في سوّاق")
        self.assertIsNone(unserved.driver)

    def test_bad_rows_are_reported_not_fatal(self):
        out = self._run()

        self.assertIn("زبائن سطر 4", out)           # رقم 12345
        self.assertIn("سوّاق سطر 4", out)            # فئة «سيدان» لم تعد اسمًا مقبولًا
        self.assertFalse(User.objects.filter(phone="+963993000003").exists())
        self.assertEqual(User.objects.filter(role=UserRole.CUSTOMER).count(), 2)

    def test_rerun_is_idempotent(self):
        self._run()
        before = (User.objects.count(), Vehicle.objects.count(), LegacyRide.objects.count())
        self._run()
        after = (User.objects.count(), Vehicle.objects.count(), LegacyRide.objects.count())
        self.assertEqual(before, after)

    def test_dry_run_writes_nothing(self):
        out = self._run(dry_run=True)
        self.assertIn("dry-run", out)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(LegacyRide.objects.count(), 0)
