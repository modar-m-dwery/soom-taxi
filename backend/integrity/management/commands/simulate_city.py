"""
محاكاة مدينة بالذروة، فيها غشّاشون، فوق خدمات المنصّة الحقيقيّة.

    python manage.py simulate_city --days 2 --drivers 60 --customers 400
    python manage.py simulate_city --ramadan --report sim.md --json sim.json

يُنشئ منطقة «مدينة المحاكاة» (إن لم تغطِّ منطقةٌ قائمة المركز) وسائقين
وزبائن بأرقام تبدأ بـ+96300001 — لا تطابق رقمًا حقيقيًّا — ثمّ يشغّل أيّامًا
كاملة بساعةٍ مُحاكاة، ويشغّل كواشف الغش كما يفعل Celery، ويطبع تقريرًا:
الذروة ساعةً بساعة، ودقّة الكشف (من انكشف، من فلت، من اتُّهم ظلمًا)،
والملاحظات والتعيينات على كلّ حساب غشّاش.

البيانات تبقى بعد التشغيل عمدًا: افتح /ops/integrity/ لترى القضايا كما
سيراها المشرف. ولا تُحذف لاحقًا — دفتر المدفوعات لا يقبل الحذف بتصميمه —
فشغّلها على قاعدة تطوير أو تجربة. كلّ تشغيل يأخذ أرقامًا جديدة فلا يتصادم
مع ما قبله، والتقرير يقيس حسابات التشغيل الحاليّ وحدها.

لا يعمل في الإنتاج.
"""

import json
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from integrity.simulation import report as report_mod
from integrity.simulation.world import LOCAL_TZ, SimClock, World, simulated_time


class Command(BaseCommand):
    help = "Peak-hour city simulation with cheating drivers/customers; measures fraud detection."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=float, default=2)
        parser.add_argument("--drivers", type=int, default=60)
        parser.add_argument("--customers", type=int, default=400)
        parser.add_argument("--cheat-ratio", type=float, default=0.12)
        parser.add_argument("--ramadan", action="store_true")
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--step-minutes", type=int, default=5)
        parser.add_argument("--demand-scale", type=float, default=1.0)
        parser.add_argument("--start", default="", help="YYYY-MM-DD (افتراضًا: قبل الأيّام المحاكاة)")
        parser.add_argument("--report", default="", help="مسار ملف Markdown للتقرير")
        parser.add_argument("--json", dest="json_path", default="", help="مسار ملف JSON للتقرير")

    def handle(self, *args, **opts):
        if getattr(settings, "DEPLOYMENT_ENV", "") == "production":
            raise CommandError("المحاكاة لا تعمل على قاعدة الإنتاج.")
        if 60 % opts["step_minutes"]:
            raise CommandError("--step-minutes يجب أن يقسم 60.")

        # منتصف الليل بتوقيت دمشق، لا UTC.
        if opts["start"]:
            day = datetime.strptime(opts["start"], "%Y-%m-%d").date()
        else:
            day = timezone.now().astimezone(LOCAL_TZ).date() - timedelta(days=int(opts["days"]) + 1)
        start = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ)

        world = World(
            drivers=opts["drivers"], customers=opts["customers"],
            cheat_ratio=opts["cheat_ratio"], days=opts["days"], ramadan=opts["ramadan"],
            seed=opts["seed"], step_minutes=opts["step_minutes"],
            demand_scale=opts["demand_scale"], log=lambda m: self.stdout.write(m),
        )

        clock = SimClock(start)
        with simulated_time(clock):
            world.setup_area()
            world.setup_people()
            self.stdout.write(
                f"بدء المحاكاة من {start:%Y-%m-%d} لـ{opts['days']} يوم: "
                f"{len(world.drivers)} سائق، {len(world.customers)} زبون."
            )
            world.run(clock)

            from integrity.services.detectors import Detectors

            Detectors.run_all()
            data = report_mod.build(world)

        markdown = report_mod.to_markdown(data)
        if opts["report"]:
            with open(opts["report"], "w", encoding="utf-8") as fh:
                fh.write(markdown)
            self.stdout.write(self.style.SUCCESS(f"التقرير: {opts['report']}"))
        if opts["json_path"]:
            with open(opts["json_path"], "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        if not opts["report"]:
            self.stdout.write(markdown)

        m = data["metrics"].get("watch", {})
        self.stdout.write(self.style.SUCCESS(
            f"الكشف: دقّة {int(m.get('precision', 0) * 100)}٪، "
            f"استدعاء {int(m.get('recall', 0) * 100)}٪ — التفاصيل في التقرير."
        ))

