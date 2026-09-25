"""
اختبار الإشعارات — الصندوق الصادر ودورته.

لا يحتاج Daphne ولا Celery ولا مفاتيح FCM: يستعمل مزوّدًا وهميًا يمكن
برمجة فشله، فنختبر ما لا يُختبر عادةً إلا في الإنتاج — الرمز الميت،
والانقضاء، والفشل العابر.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.backends.base import BaseBackend, NotConfigured, SendResult
from notifications.models import (
    AppKind,
    Notification,
    NotificationPriority,
    NotificationStatus,
)
from notifications.services.dispatch import DeviceService, NotificationService
from notifications.services.router import NotificationRouter
from users.models import DeviceToken, DriverProfile, User


ANDROID = DeviceToken.Platform.ANDROID


class FakeBackend(BaseBackend):
    """مزوّد قابل للبرمجة: ننصب له الفشل الذي نريد اختباره."""

    name = "fake"

    def __init__(self, mode="ok"):
        self.mode = mode
        self.sent = []

    def check_ready(self):
        if self.mode == "not_configured":
            raise NotConfigured("مفاتيح غير مضبوطة (اختبار)")
        return True

    def send(self, token, notification):
        self.sent.append((token.token, notification.id))

        if self.mode == "permanent":
            return SendResult.permanent("UNREGISTERED")

        if self.mode == "transient":
            return SendResult.transient("TIMEOUT")

        return SendResult.success()


class Command(BaseCommand):
    help = "اختبار صندوق الإشعارات: الانقضاء، الرموز الميتة، منع التكرار"

    def add_arguments(self, parser):
        parser.add_argument("--customer-phone", required=True)
        parser.add_argument("--driver-id", type=int, required=True)

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0

        customer = User.objects.filter(phone=options["customer_phone"]).first()
        if customer is None:
            return self._setup_fail("لا يوجد زبون بهذا الرقم.")

        driver = DriverProfile.objects.filter(id=options["driver_id"]).first()
        if driver is None:
            return self._setup_fail("لا يوجد سائق بهذا المعرّف.")

        self.customer = customer
        self.driver = driver
        self.driver_user = driver.user
        self.prefix = f"test-{timezone.now().timestamp():.0f}"

        try:
            self._run()
        finally:
            self._cleanup()

        total = self.passed + self.failed

        if self.failed:
            self.stdout.write(self.style.ERROR(
                f"\nNotifications E2E: {self.passed}/{total} passed, "
                f"{self.failed} FAILED."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nNotifications E2E: {self.passed}/{total} passed."
            ))

    # =================================================================

    def _run(self):
        self._phase_devices()
        self._phase_outbox()
        self._phase_expiry()
        self._phase_dead_tokens()
        self._phase_router()

    # -----------------------------------------------------------------
    # أ — تسجيل الأجهزة
    # -----------------------------------------------------------------

    def _phase_devices(self):
        self._section("أ: تسجيل الأجهزة")

        token = f"{self.prefix}-A"

        device, created = DeviceService.register(self.customer, token, ANDROID)
        self._check(created and device.is_active, "1) تسجيل جهاز جديد")

        _again, created_again = DeviceService.register(
            self.customer, token, ANDROID
        )
        self._check(
            not created_again and DeviceToken.objects.filter(token=token).count() == 1,
            "2) إعادة التسجيل لا تُنشئ صفًّا ثانيًا",
        )

        # الهاتف ينتقل: نفس الرمز يسجّله مستخدم آخر
        moved, _created = DeviceService.register(self.driver_user, token, ANDROID)
        self._check(
            moved.user_id == self.driver_user.id
            and DeviceToken.objects.filter(token=token).count() == 1,
            "3) ★ رمز انتقل لمستخدم آخر يُنقَل لا يُكرَّر — وإلا وصل "
            "الإشعار للشخص الخطأ",
        )

        DeviceService.unregister(self.driver_user, token)
        moved.refresh_from_db()
        self._check(
            not moved.is_active,
            f"4) تسجيل الخروج يُبطل الرمز (is_active={moved.is_active})",
        )

    # -----------------------------------------------------------------
    # ب — الصندوق
    # -----------------------------------------------------------------

    def _phase_outbox(self):
        self._section("ب: الصندوق الصادر")

        # لا أجهزة فعّالة الآن
        notification = NotificationService.create(
            user=self.customer,
            event_type="test.no_device",
            title="اختبار",
            dedupe_key=f"{self.prefix}-nodev",
            dispatch=False,
        )
        NotificationService.dispatch(notification.id, backend=FakeBackend())
        notification.refresh_from_db()

        self._check(
            notification.status == NotificationStatus.SKIPPED,
            f"5) ★ بلا أجهزة: 'متخطّى' لا 'فاشل' — الفاشل يُعاد أبدًا "
            f"({notification.status})",
        )

        DeviceService.register(self.customer, f"{self.prefix}-B", ANDROID)

        backend = FakeBackend()
        notification = NotificationService.create(
            user=self.customer,
            event_type="test.ok",
            title="وصلك إشعار",
            body="نصّ الاختبار",
            dedupe_key=f"{self.prefix}-ok",
            dispatch=False,
        )
        NotificationService.dispatch(notification.id, backend=backend)
        notification.refresh_from_db()

        self._check(
            notification.status == NotificationStatus.SENT
            and notification.sent_at is not None
            and len(backend.sent) >= 1,
            f"6) الإرسال الناجح يُسجَّل بوقته ({notification.status})",
        )

        duplicate = NotificationService.create(
            user=self.customer,
            event_type="test.ok",
            title="نفس الإشعار",
            dedupe_key=f"{self.prefix}-ok",
            dispatch=False,
        )
        self._check(
            duplicate is None
            and Notification.objects.filter(dedupe_key=f"{self.prefix}-ok").count() == 1,
            "7) ★ منع التكرار على مستوى القاعدة لا بفحص قابل للنسيان",
        )

        # مزوّد غير مهيّأ
        notification = NotificationService.create(
            user=self.customer, event_type="test.unconfigured", title="اختبار",
            dedupe_key=f"{self.prefix}-nocfg", dispatch=False,
        )
        NotificationService.dispatch(
            notification.id, backend=FakeBackend("not_configured")
        )
        notification.refresh_from_db()

        self._check(
            notification.status == NotificationStatus.SKIPPED,
            f"8) ★ مزوّد غير مهيّأ: 'متخطّى' أيضًا — حالة تشغيل لا خطأ "
            f"({notification.status})",
        )

    # -----------------------------------------------------------------
    # ج — الانقضاء
    # -----------------------------------------------------------------

    def _phase_expiry(self):
        self._section("ج: الانقضاء")

        backend = FakeBackend()

        expired = NotificationService.create(
            user=self.customer,
            event_type="test.expired",
            title="دعوة",
            expires_at=timezone.now() - timedelta(seconds=1),
            dedupe_key=f"{self.prefix}-exp",
            dispatch=False,
        )
        NotificationService.dispatch(expired.id, backend=backend)
        expired.refresh_from_db()

        self._check(
            expired.status == NotificationStatus.EXPIRED,
            f"9) ★ المنقضي يُسقَط لا يُرسَل ({expired.status})",
        )
        self._check(
            len(backend.sent) == 0,
            "10) ★ ولم يصل المزوّد أصلًا — لا إشعار يَعِد بعمل انتهى",
        )

        # المكنسة: منقضٍ بقي بالانتظار (العامل كان متوقفًا)
        stale = NotificationService.create(
            user=self.customer, event_type="test.stale", title="قديم",
            expires_at=timezone.now() - timedelta(minutes=5),
            dedupe_key=f"{self.prefix}-stale", dispatch=False,
        )
        swept = NotificationService.expire_stale()
        stale.refresh_from_db()

        self._check(
            swept >= 1 and stale.status == NotificationStatus.EXPIRED,
            f"11) والمكنسة تُعلّم ما بقي بالانتظار بعد انقضائه ({swept})",
        )

        alive = NotificationService.create(
            user=self.customer, event_type="test.alive", title="حيّ",
            expires_at=timezone.now() + timedelta(minutes=10),
            dedupe_key=f"{self.prefix}-alive", dispatch=False,
        )
        NotificationService.dispatch(alive.id, backend=FakeBackend())
        alive.refresh_from_db()

        self._check(
            alive.status == NotificationStatus.SENT,
            "12) وما لم ينقضِ يُرسَل عاديًا",
        )

    # -----------------------------------------------------------------
    # د — الرموز الميتة والفشل العابر
    # -----------------------------------------------------------------

    def _phase_dead_tokens(self):
        self._section("د: الرموز الميتة")

        dead_token = f"{self.prefix}-DEAD"
        DeviceService.register(self.customer, dead_token, ANDROID)

        notification = NotificationService.create(
            user=self.customer, event_type="test.dead", title="اختبار",
            dedupe_key=f"{self.prefix}-dead", dispatch=False,
        )
        NotificationService.dispatch(notification.id, backend=FakeBackend("permanent"))

        device = DeviceToken.objects.get(token=dead_token)
        notification.refresh_from_db()

        self._check(
            not device.is_active,
            "13) ★ الرمز الذي رفضه المزوّد نهائيًا يُبطَل — "
            "وإلا حاولناه إلى الأبد",
        )
        self._check(
            notification.status == NotificationStatus.FAILED
            or notification.attempts >= 1,
            f"14) والإشعار يحمل سبب فشله ({notification.status}, "
            f"محاولات {notification.attempts})",
        )

        # الفشل العابر: لا يُبطل الرمز
        alive_token = f"{self.prefix}-ALIVE"
        DeviceService.register(self.customer, alive_token, ANDROID)

        notification = NotificationService.create(
            user=self.customer, event_type="test.transient", title="اختبار",
            dedupe_key=f"{self.prefix}-transient", dispatch=False,
        )
        NotificationService.dispatch(notification.id, backend=FakeBackend("transient"))

        device = DeviceToken.objects.get(token=alive_token)
        notification.refresh_from_db()

        self._check(
            device.is_active,
            "15) ★ والفشل العابر لا يُبطل الرمز — خلط الحالتين يقتل أجهزة سليمة",
        )
        self._check(
            notification.status == NotificationStatus.PENDING
            and notification.attempts == 1,
            f"16) ويبقى الإشعار بالانتظار لإعادة المحاولة "
            f"({notification.status}, {notification.attempts})",
        )

    # -----------------------------------------------------------------
    # هـ — الموجّه
    # -----------------------------------------------------------------

    def _phase_router(self):
        self._section("هـ: من حدث إلى إشعار")

        DeviceService.register(self.driver_user, f"{self.prefix}-DRV", ANDROID)

        invitation = self._fake_invitation()

        notification = NotificationRouter.handle(
            "invitation.created", invitation=invitation
        )

        self._check(
            notification is not None
            and notification.user_id == self.driver_user.id
            and notification.app == AppKind.DRIVER,
            "17) دعوة جديدة -> إشعار للسائق على تطبيق السائق",
        )

        if notification is None:
            self._check(False, "18) — تخطّي")
            self._check(False, "19) — تخطّي")
            self._check(False, "20) — تخطّي")
            return

        self._check(
            notification.priority == NotificationPriority.URGENT,
            f"18) ★ بأولوية عاجلة — يوقظ الشاشة المقفلة "
            f"({notification.priority})",
        )
        self._check(
            notification.expires_at == invitation.expires_at,
            "19) ★ ومهلته هي مهلة الدعوة نفسها لا رقمًا مستقلًا",
        )
        self._check(
            str(notification.data.get("invitation_id")) == str(invitation.id)
            and notification.data.get("screen") == "invitation",
            f"20) وحمولته تفتح الشاشة الصحيحة ({notification.data.get('screen')})",
        )

        # حدث لا موجّه له: لا ينفجر
        unknown = NotificationRouter.handle("something.unknown", foo=1)
        self._check(unknown is None, "21) حدث بلا موجّه يُتجاهَل بهدوء")

    # =================================================================

    def _fake_invitation(self):
        """
        دعوة في الذاكرة لا في القاعدة: ما نختبره هو الموجّه لا خدمة الدعوات
        (ولها اختبارها الخاص بـ27 فحصًا). بناء دعوة حقيقية هنا يعني تثبيت
        سائق وإنشاء طلب — كلفة بلا مقابل.
        """
        class _Ride:
            id = 999_000
            currency = "SYP"

        class _Invitation:
            id = 999_001
            ride_id = _Ride.id
            ride = _Ride()
            driver = self.driver
            quoted_fare = "25.00"
            ttl_seconds = 20
            eta_minutes = 4
            expires_at = timezone.now() + timedelta(seconds=20)

        return _Invitation()

    def _cleanup(self):
        DeviceToken.objects.filter(token__startswith=self.prefix).delete()
        Notification.objects.filter(dedupe_key__startswith=self.prefix).delete()
        Notification.objects.filter(
            dedupe_key="invitation.created:999001"
        ).delete()

    # -----------------------------------------------------------------

    def _section(self, title):
        self.stdout.write(self.style.HTTP_INFO(f"\n— {title} —"))

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(f"[OK]   {label}")
        else:
            self.failed += 1
            self.stdout.write(self.style.ERROR(f"[FAIL] {label}"))

    def _setup_fail(self, message):
        self.stderr.write(self.style.ERROR(f"[SETUP FAIL] {message}"))
