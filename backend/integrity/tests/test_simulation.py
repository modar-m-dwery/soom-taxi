"""
دخانُ المحاكاة: بضع ساعات مدينةٍ صغيرة تمرّ عبر خدمات المنصّة الحقيقيّة
بلا خطأ، وتُنتج تقريرًا بمقاييس الكشف.
"""
from datetime import datetime, timedelta

from django.test import TransactionTestCase
from django.utils import timezone

from integrity.simulation import report
from integrity.simulation.world import LOCAL_TZ, SimClock, World, simulated_time


class SimulationSmokeTests(TransactionTestCase):

    def test_few_hours_of_city_life(self):
        day = timezone.now().astimezone(LOCAL_TZ).date() - timedelta(days=2)
        start = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ) + timedelta(hours=7)
        world = World(drivers=14, customers=70, cheat_ratio=0.5, days=0.25, seed=3)
        clock = SimClock(start)
        with simulated_time(clock):
            world.setup_area()
            world.setup_people()
            world.run(clock)
            data = report.build(world)

        self.assertGreater(data["counts"]["requests"], 0)
        self.assertGreater(data["counts"]["completed"], 0)
        self.assertIn("watch", data["metrics"])
        # الحسابات المتعدّدة على هاتف واحد تُكشف من الساعة الأولى.
        self.assertGreater(data["metrics"]["watch"]["tp"], 0)
        # لا اتّهام لنظاميّ في هذه الضوضاء الصغيرة.
        self.assertEqual(data["metrics"]["watch"]["fp"], 0)
        self.assertIn("# تقرير محاكاة المدينة", report.to_markdown(data))
