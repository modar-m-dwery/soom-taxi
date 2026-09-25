"""
تشغيل كل اختبارات E2E دفعة واحدة مع ملخّص واحد.

لماذا هذا الأمر أصلًا؟ لأن تسعة أوامر تُشغَّل يدويًا لا تُشغَّل كلها إلا
نادرًا. ومعنى ذلك عمليًا أن تعديلًا في المطابقة قد يكسر الحضور ولا يظهر
إلا بعد أسبوعين حين يخطر لأحدنا تشغيل ذلك الأمر بالذات.

ليس بديلًا عن CI - الاختبارات ما زالت تعمل على قاعدة التطوير لا على قاعدة
اختبار معزولة - لكنه يجعل "شغّل كل شيء قبل أن تُسلّم" ممكنًا في أمر واحد.

ثلاثة أشياء يفعلها لأن تشغيل تسع مجموعات على سائق واحد ليس كتشغيل كل
واحدة وحدها:

  1. يُعيد ضبط السائق بين المجموعات (--no-reset لتعطيله)
  2. ينتظر قليلًا بينها (--pause)
  3. يطبع لقطة تشخيصية عند أي سقوط، فلا نطارد عطلًا غير موجود
"""
import io
import re
import time

from django.core.management import call_command, get_commands, load_command_class
from django.core.management.base import BaseCommand, CommandError


# (اسم الأمر، وصف، هل يحتاج Daphne)
SUITES = [
    ("test_presence_consistency_e2e", "اتساق الحضور (المرحلة 6)", True),
    ("pricing_policy_test", "سياسات التسعير المنظَّم", False),
    ("test_invitation_e2e", "الدعوة المباشرة (المرحلة 8)", True),
    ("test_trip_lifecycle_e2e", "دورة حياة الرحلة (9أ)", True),
    ("test_sharing_presence_e2e", "المشاركة على الخريطة (8ب)", False),
    ("test_feedback_e2e", "التقييم والشكاوى (9ب)", False),
    ("test_notifications_e2e", "الإشعارات", False),
    ("test_vehicle_presence_e2e", "المركبة والحضور", False),
    ("test_ops_console_e2e", "لوحة التشغيل (12)", False),
]

RESULT_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)\s+passed")


class Command(BaseCommand):
    help = "تشغيل كل اختبارات E2E وطباعة ملخّص واحد"

    def add_arguments(self, parser):
        parser.add_argument("--customer-phone", required=True)
        parser.add_argument("--driver-id", type=int, required=True)
        parser.add_argument(
            "--ws-url",
            default="",
            help=(
                "عنوان Daphne لمجموعات WebSocket، مثل ws://localhost:8000. "
                "بدونه تستخدم كلّ مجموعة قيمتها الافتراضية."
            ),
        )
        parser.add_argument(
            "--skip-ws",
            action="store_true",
            help="تخطّي ما يحتاج Daphne (تشغيل سريع بلا خادم WebSocket)",
        )
        parser.add_argument(
            "--only",
            default="",
            help="أسماء أوامر مفصولة بفواصل، لتشغيل جزء منها فقط",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=3.0,
            help=(
                "ثوانٍ بين المجموعات. المجموعات التي تفتح WebSocket تترك "
                "خيوطًا وسوكيتات تُغلَق متأخرة، وبدء التالية فورًا فوقها "
                "يُسقط اتصالاتها. صفر لتعطيل الانتظار."
            ),
        )
        parser.add_argument(
            "--no-reset",
            action="store_true",
            help=(
                "لا تُعِد ضبط السائق بين المجموعات. الافتراضي أن نُعيده، "
                "لأن مجموعة تترك رحلة نشطة تُسقط التالية بلا ذنب لها."
            ),
        )
        parser.add_argument(
            "--no-diagnose",
            action="store_true",
            help="لا تطبع لقطة حالة السائق بعد المجموعات الساقطة.",
        )

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        only = {
            name.strip()
            for name in (options.get("only") or "").split(",")
            if name.strip()
        }

        results = []
        started = time.time()

        for name, label, needs_ws in SUITES:
            if only and name not in only:
                continue

            if needs_ws and options["skip_ws"]:
                results.append((name, label, "skipped", None, None, 0.0))
                self.stdout.write(self.style.WARNING(
                    f"\n⊘ {label} — تخطّي (يحتاج Daphne)"
                ))
                continue

            if results and options["pause"] > 0:
                time.sleep(options["pause"])

            if not options["no_reset"]:
                self._reset_driver(options["driver_id"])

            result = self._run_suite(name, label, options)
            results.append(result)

            # لقطة فورية عند السقوط: الحالة بعد دقيقة لن تكون هي الحالة
            # لحظة الفشل، وهذا ما جعلنا نطارد عطلًا لا وجود له.
            if result[2] in ("failed", "error") and not options["no_diagnose"]:
                self._diagnose(options["driver_id"])

        self._print_summary(results, time.time() - started)

        failed = [r for r in results if r[2] in ("failed", "error")]

        if failed:
            self.stdout.write(self.style.WARNING(
                "\nقبل أن تعدّ الفشل حقيقيًا: شغّل المجموعة الساقطة وحدها "
                "وراجع نافذة Daphne. تسع مجموعات على سائق واحد في عملية "
                "واحدة ليست كتشغيل كل واحدة على حدة."
            ))
            raise CommandError(f"{len(failed)} من المجموعات لم تنجح.")

    # -----------------------------------------------------------------
    # إعادة الضبط بين المجموعات
    # -----------------------------------------------------------------

    def _reset_driver(self, driver_id):
        """
        كل مجموعة تنظّف قبل أن تبدأ، لكن التنظيف بـ.update() يغيّر القاعدة
        ولا يخبر Redis. فمجموعة تنتهي وقد تركت السائق مرتبطًا تُسقط فحوصًا
        في التالية لا ذنب لها فيها.

        الإصلاح هنا لا في كل مجموعة: مكان واحد يعرف أنه يشغّل تسع مجموعات
        على سائق واحد.
        """
        try:
            from matching.models import OfferStatus, RideOffer
            from rides.models import RideRequest, RideStatus
            from trips.models import Trip, TripStatus
            from trips.services.engagement import EngagementResolver

            active_rides = [
                RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
                RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
            ]
            active_trips = [
                TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
                TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
            ]

            stale_ride_ids = list(
                RideOffer.objects
                .filter(
                    driver_id=driver_id,
                    status=OfferStatus.ACCEPTED,
                    ride__status__in=active_rides,
                )
                .values_list("ride_id", flat=True)
            )

            closed = Trip.objects.filter(
                driver_id=driver_id, status__in=active_trips
            ).update(status=TripStatus.CANCELLED)

            if stale_ride_ids:
                RideRequest.objects.filter(id__in=stale_ride_ids).update(
                    status=RideStatus.CANCELLED
                )
                RideOffer.objects.filter(
                    ride_id__in=stale_ride_ids, status=OfferStatus.ACCEPTED
                ).update(status=OfferStatus.CANCELLED)

            # والأهمّ: أخبِر Redis. .update() لا تُطلق أي إشارة.
            EngagementResolver.sync(driver_id)

            if closed or stale_ride_ids:
                self.stdout.write(self.style.WARNING(
                    f"   ↺ إعادة ضبط: أُغلقت {closed} رحلة و"
                    f"{len(stale_ride_ids)} طلبًا عالقًا من المجموعة السابقة."
                ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"   ↺ تعذّرت إعادة الضبط: {exc!r}"
            ))

    # -----------------------------------------------------------------
    # التشخيص عند السقوط
    # -----------------------------------------------------------------

    def _diagnose(self, driver_id):
        self.stdout.write(self.style.HTTP_INFO(
            "\n--- لقطة حالة السائق لحظة السقوط ---"
        ))

        try:
            call_command("presence_debug", driver_id=driver_id, stdout=self.stdout)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"   (presence_debug غير متاح: {exc!r})"
            ))

    # -----------------------------------------------------------------

    def _run_suite(self, name, label, options):
        self.stdout.write(self.style.HTTP_INFO(f"\n{'=' * 62}"))
        self.stdout.write(self.style.HTTP_INFO(f"▶ {label}  ({name})"))
        self.stdout.write(self.style.HTTP_INFO("=" * 62))

        buffer = io.StringIO()
        started = time.time()

        try:
            call_command(
                name,
                stdout=buffer,
                stderr=buffer,
                **self._accepted_kwargs(name, options),
            )
            output = buffer.getvalue()
            status = "passed"
        except Exception as exc:
            output = buffer.getvalue() + f"\n[EXCEPTION] {exc!r}"
            status = "error"

        elapsed = time.time() - started

        self.stdout.write(output)

        passed, total = self._parse_result(output)

        if status != "error":
            if total is None:
                # لم نجد سطر النتيجة: قد يكون الأمر انتهى بـSETUP FAIL
                status = "error" if "[SETUP FAIL]" in output else "unknown"
            elif passed != total:
                status = "failed"

        return (name, label, status, passed, total, elapsed)

    @staticmethod
    def _accepted_kwargs(name, options):
        """
        نمرّر لكل أمر ما يعرفه فقط. البديل - تمرير كل شيء للجميع - ينهار
        عند أول أمر لا يقبل --driver-id.
        """
        app_name = get_commands().get(name)

        if app_name is None:
            return {}

        command = load_command_class(app_name, name)
        parser = command.create_parser("manage.py", name)

        known = {action.dest for action in parser._actions}

        candidates = {
            "customer_phone": options.get("customer_phone"),
            "driver_id": options.get("driver_id"),
            # بدون هذا السطر لا يصل --ws-url إلى المجموعات إطلاقًا، فتبقى
            # على منفذها الافتراضي مهما مرّرت — وتسقط فحوص الأحداث بصمت
            # بينما بقيّة المجموعة تنجح، فيبدو العطل في Channels لا هنا.
            "ws_url": options.get("ws_url") or None,
        }

        return {
            key: value
            for key, value in candidates.items()
            if key in known and value is not None
        }

    @staticmethod
    def _parse_result(output):
        matches = RESULT_PATTERN.findall(output or "")

        if not matches:
            return None, None

        passed, total = matches[-1]
        return int(passed), int(total)

    # -----------------------------------------------------------------

    def _print_summary(self, results, elapsed):
        self.stdout.write(self.style.HTTP_INFO(f"\n{'=' * 62}"))
        self.stdout.write(self.style.HTTP_INFO("الملخّص"))
        self.stdout.write(self.style.HTTP_INFO("=" * 62))

        total_passed = 0
        total_checks = 0

        marks = {
            "passed": ("✓", self.style.SUCCESS),
            "failed": ("✗", self.style.ERROR),
            "error": ("!", self.style.ERROR),
            "skipped": ("⊘", self.style.WARNING),
            "unknown": ("?", self.style.WARNING),
        }

        for _name, label, status, passed, total, seconds in results:
            mark, style = marks.get(status, ("?", self.style.WARNING))

            if passed is not None and total is not None:
                score = f"{passed}/{total}"
                total_passed += passed
                total_checks += total
            else:
                score = "—"

            self.stdout.write(
                style(f"  {mark} {label:.<44} {score:>8}  {seconds:5.1f}ث")
            )

        line = (
            f"\nالمجموع: {total_passed}/{total_checks} فحصًا "
            f"في {elapsed:.1f} ثانية"
        )

        if total_checks and total_passed == total_checks:
            self.stdout.write(self.style.SUCCESS(line))
        else:
            self.stdout.write(self.style.ERROR(line))
