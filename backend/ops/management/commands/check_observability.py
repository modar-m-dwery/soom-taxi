"""
اختبار اتصال لطبقة الرصد.

طبقة سجلّات لا تُختبَر هي أسوأ من عدمها: تظنّ أنك ترى وأنت لا ترى. هذا
الأمر يتحقّق من كل حلقة في السلسلة ويقول لك أيّها انقطعت.

    python manage.py check_observability

ولفحص السلسلة كاملة حتى Celery (يحتاج عاملًا يعمل):

    python manage.py check_observability --with-celery
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "فحص طبقة الرصد: المعرّف، السجلّات، الملفّات، ورموز الأخطاء"

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-celery",
            action="store_true",
            help="افحص انتقال المعرّف إلى مهمّة Celery (يحتاج عاملًا يعمل).",
        )

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0

        self.stdout.write(self.style.HTTP_INFO("\n— فحص طبقة الرصد —\n"))

        self._check_settings()
        self._check_context()
        self._check_files()
        self._check_error_codes()
        self._check_swallow()

        if options["with_celery"]:
            self._check_celery()

        total = self.passed + self.failed
        line = f"\nالنتيجة: {self.passed}/{total}"

        if self.failed:
            self.stdout.write(self.style.ERROR(line))
        else:
            self.stdout.write(self.style.SUCCESS(line))
            self.stdout.write(
                "\nافتح الآن logs/ وستجد ملفّين على الأقل. ابحث في "
                "errors.log عن المعرّف المطبوع أعلاه."
            )

    # -----------------------------------------------------------------

    def _ok(self, label, detail=""):
        self.passed += 1
        suffix = f"  ({detail})" if detail else ""
        self.stdout.write(self.style.SUCCESS(f"  [OK]   {label}{suffix}"))

    def _fail(self, label, detail=""):
        self.failed += 1
        suffix = f"  ← {detail}" if detail else ""
        self.stdout.write(self.style.ERROR(f"  [FAIL] {label}{suffix}"))

    # -----------------------------------------------------------------

    def _check_settings(self):
        self.stdout.write(self.style.HTTP_INFO("١) الإعدادات"))

        mw = "config.observability.middleware.RequestContextMiddleware"

        if mw in settings.MIDDLEWARE:
            self._ok("الوسيط مركَّب في MIDDLEWARE")
        else:
            self._fail("الوسيط غير مركَّب", "أضِفه إلى MIDDLEWARE في settings.py")

        handler = settings.REST_FRAMEWORK.get("EXCEPTION_HANDLER", "")

        if handler.endswith("api_exception_handler"):
            self._ok("معالج استثناءات DRF مضبوط")
        else:
            self._fail(
                "EXCEPTION_HANDLER غير مضبوط",
                "كل خطأ سيعود بلا code وبلا request_id",
            )

        root = settings.LOGGING.get("root", {})

        if root.get("handlers"):
            self._ok("مُسجِّل root موجود", f"معالجات: {', '.join(root['handlers'])}")
        else:
            self._fail(
                "لا مُسجِّل root",
                "كل logger غير مسمّى صراحةً سيختفي",
            )

    def _check_context(self):
        self.stdout.write(self.style.HTTP_INFO("\n٢) معرّف الحادثة"))

        from config.observability.context import bind, get_request_id

        unbind = bind(actor="check")
        rid = get_request_id()

        if rid and len(rid) >= 8:
            self._ok("المعرّف يُولَّد", rid)
        else:
            self._fail("لا معرّف")

        logger = logging.getLogger("check.observability")
        logger.info("سطر فحص عادي")
        logger.warning("سطر فحص تحذيري — يجب أن يظهر في errors.log")

        try:
            raise ValueError("استثناء مُتعمَّد للفحص — تجاهله")
        except ValueError:
            logger.exception("سطر فحص باستثناء")

        self._ok("كُتبت ثلاثة أسطر بالمعرّف", rid)

        self.stdout.write(
            self.style.WARNING(f"\n     ← معرّف هذا الفحص: {rid}\n")
        )

        unbind()

    def _check_files(self):
        self.stdout.write(self.style.HTTP_INFO("٣) الملفّات"))

        log_dir = Path(settings.BASE_DIR) / "logs"

        if not log_dir.exists():
            self._fail("مجلّد logs/ غير موجود")
            return

        self._ok("مجلّد logs/ موجود", str(log_dir))

        files = sorted(log_dir.glob("*.log"))

        if not files:
            self._fail(
                "لا ملفّات سجلّ",
                "المعالجات delay=True فلا تُنشأ إلا عند أول كتابة",
            )
            return

        self._ok(f"وُجد {len(files)} ملفًّا", ", ".join(f.name for f in files))

        # التحقّق الحقيقي: هل السطر المكتوب JSON صالح ويحمل المعرّف؟
        errors = [f for f in files if f.name.endswith(".errors.log")]

        if not errors:
            self._fail("لا ملفّ أخطاء", "التحذير أعلاه لم يُكتب")
            return

        try:
            last = errors[0].read_text(encoding="utf-8").strip().splitlines()[-1]
            row = json.loads(last)
        except Exception as exc:
            self._fail("سطر الأخطاء ليس JSON صالحًا", repr(exc))
            return

        if "request_id" in row and row["request_id"] != "-":
            self._ok("سطر الأخطاء JSON ويحمل المعرّف", row["request_id"])
        else:
            self._fail(
                "السطر بلا معرّف",
                "الفلتر request_context غير مركَّب على المعالج",
            )

    def _check_error_codes(self):
        self.stdout.write(self.style.HTTP_INFO("\n٤) رموز الأخطاء"))

        from config.observability.errors import AppError, resolve

        code, status = resolve(AppError("x", code="test.code", status_code=409))

        if code == "test.code" and status == 409:
            self._ok("AppError يحمل رمزه وحالته")
        else:
            self._fail("AppError لا يُقرأ", f"{code}/{status}")

        # استثناء من خدماتك القائمة، بلا أي تعديل عليها
        try:
            from trips.services.trip import TripError

            code, status = resolve(TripError("هذه الرحلة ليست لك."))

            if code == "trip.forbidden":
                self._ok("استثناء قائم تُرجم إلى رمز", code)
            else:
                self._fail("لم يُترجم", code)
        except ImportError:
            self._fail("تعذّر استيراد TripError")

        try:
            from matching.services.matching import MatchingError

            code, _ = resolve(MatchingError("Offer has expired."))

            if code == "offer.expired":
                self._ok("والنصّ المعروف يعطي رمزًا دقيقًا", code)
            else:
                self._fail("النصّ لم يُترجم", code)
        except ImportError:
            self._fail("تعذّر استيراد MatchingError")

    def _check_swallow(self):
        self.stdout.write(self.style.HTTP_INFO("\n٥) أدوات منع الابتلاع"))

        from config.observability.safety import run_all, swallow

        with swallow("check.observability", event="check.swallow"):
            raise RuntimeError("ابتلاع مُتعمَّد — يجب أن يُسجَّل لا أن يختفي")

        self._ok("swallow ابتلع ولم يُسقط العملية")

        calls = []

        failures = run_all(
            lambda: calls.append(1),
            lambda: (_ for _ in ()).throw(RuntimeError("خطوة ساقطة متعمَّدة")),
            lambda: calls.append(3),
            event="check.run_all",
        )

        if calls == [1, 3] and failures == 1:
            self._ok("run_all أكمل بعد سقوط خطوة", "الخطوة الثالثة نُفّذت")
        else:
            self._fail("run_all لم يُكمل", f"calls={calls} failures={failures}")

    def _check_celery(self):
        self.stdout.write(self.style.HTTP_INFO("\n٦) Celery"))

        from config.observability.context import bind, get_request_id

        unbind = bind(actor="check")
        rid = get_request_id()

        try:
            from notifications.tasks import dispatch_notification

            result = dispatch_notification.delay(-1)
            self._ok(
                "أُرسلت مهمّة بالمعرّف",
                f"{rid} → task {result.id}",
            )
            self.stdout.write(
                self.style.WARNING(
                    f"     ← افتح نافذة Celery وابحث عن {rid}\n"
                    "       إن ظهر، فالسلسلة كاملة من REST إلى المهمّة."
                )
            )
        except Exception as exc:
            self._fail("تعذّر إرسال المهمّة", repr(exc))

        unbind()
