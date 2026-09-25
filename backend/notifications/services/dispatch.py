"""
NotificationService — الصندوق الصادر ودورته.

الترتيب المعتمد: اكتب أولًا، أرسل ثانيًا.

الكتابة تجري داخل معاملة الحدث نفسه، فلا يمكن أن يصل إشعار عن دعوة
تراجعت معاملتها. والإرسال يجري بعد الـcommit، فلا تُحبس معاملة قاعدة
البيانات على نداء شبكة خارجي.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from notifications.backends.base import NotConfigured
from notifications.models import (
    AppKind,
    Notification,
    NotificationPriority,
    NotificationStatus,
)
# رموز الأجهزة تعيش في users لا هنا: جدول واحد لسؤال واحد.
from users.models import DeviceToken

logger = logging.getLogger("notifications")


DEFAULT_BACKEND = "notifications.backends.console.ConsoleBackend"

MAX_ATTEMPTS = getattr(settings, "NOTIFICATION_MAX_ATTEMPTS", 3)


def get_backend():
    """
    يُقرأ من settings.NOTIFICATION_BACKEND. الافتراضي هو الطابعة، لا FCM:
    بيئة تطوير تُرسل إشعارات حقيقية إلى هواتف الناس خطأٌ يُكتشف متأخرًا.
    """
    from django.utils.module_loading import import_string

    path = getattr(settings, "NOTIFICATION_BACKEND", DEFAULT_BACKEND)

    return import_string(path)()


class NotificationService:

    # =================================================================
    # الإنشاء
    # =================================================================

    @classmethod
    def create(cls, user, event_type, title, body="", data=None, app=AppKind.CUSTOMER,
               priority=NotificationPriority.NORMAL, expires_at=None,
               dedupe_key="", dispatch=True):
        """
        يرجّع الإشعار، أو None إن كان مكررًا (dedupe_key موجود من قبل).

        التكرار ليس خطأً يُرفَع: نقر مزدوج أو مهمة أُعيدت حالتان طبيعيتان،
        والصحيح تجاهلهما بهدوء لا إسقاط العملية التي أطلقتهما.
        """
        if user is None:
            return None

        notification = Notification(
            user=user,
            event_type=event_type,
            title=title[:120],
            body=(body or "")[:300],
            data=data or {},
            app=app,
            priority=priority,
            expires_at=expires_at,
            dedupe_key=(dedupe_key or "")[:120],
        )

        try:
            with transaction.atomic():
                notification.save()
        except IntegrityError:
            logger.debug("notification deduped: %s", dedupe_key)
            return None

        if dispatch:
            notification_id = notification.id
            transaction.on_commit(lambda: cls.dispatch_async(notification_id))

        return notification

    @staticmethod
    def dispatch_async(notification_id):
        """
        يحاول عبر Celery، ويرجع إلى الإرسال المباشر إن لم يكن العامل يعمل.

        الارتداد مقصود: إشعار الدعوة عمره عشرون ثانية، وتأجيله إلى أن
        يُشغَّل العامل يعني ضياعه. أما الإشعارات العادية فلا يضرّها ذلك.
        """
        try:
            from notifications.tasks import dispatch_notification

            dispatch_notification.delay(notification_id)
        except Exception as exc:
            logger.warning("celery unavailable (%s); sending inline", exc)
            NotificationService.dispatch(notification_id)

    # =================================================================
    # الإرسال
    # =================================================================

    @classmethod
    def dispatch(cls, notification_id, backend=None):
        notification = Notification.objects.filter(id=notification_id).first()

        if notification is None:
            return None

        if notification.status != NotificationStatus.PENDING:
            return notification

        # -------------------------------------------------------------
        # الانقضاء أولًا، قبل أي عمل آخر.
        #
        # دعوة مهلتها عشرون ثانية وصل إشعارها بعد ثلاث دقائق: السائق يضغط
        # فيجد "انتهت". هذا أسوأ من ألّا يصله شيء، لأنه يُفقد الثقة بكل
        # إشعار بعده. فنُسقطه ونسجّل إسقاطه.
        # -------------------------------------------------------------
        if notification.is_expired:
            return cls._finish(
                notification, NotificationStatus.EXPIRED, "انقضى قبل الإرسال"
            )

        # -------------------------------------------------------------
        # سلسلة القنوات.
        #
        # كان هنا منطق الدفع كاملًا ثمّ نداء صريح للقناة الاحتياطية — أي
        # أنّ «كيف يصل الإشعار» كان مكتوبًا داخل «متى يُرسَل». إضافة
        # تليغرام كانت تعني تعديل هذه الدالّة، وإضافة واتساب بعدها تعديلها
        # ثانيةً، وكلّ تعديل يمرّ على منطق الانقضاء وسقف المحاولات.
        #
        # الآن: هذه الدالّة تقرّر *متى*، والسلسلة تقرّر *كيف*. وما كان
        # يفعله الدفع لم يتغيّر — انتقل كما هو إلى `channels/push.py`.
        # -------------------------------------------------------------
        from notifications.services.channel_router import ChannelRouter

        notification.attempts += 1

        chain_result = ChannelRouter.deliver(notification, push_backend=backend)

        if chain_result.delivered:
            return cls._finish(
                notification,
                NotificationStatus.SENT,
                f"عبر {chain_result.delivered_by}",
            )

        if chain_result.nothing_tried:
            # لم يُسأل مزوّد واحد: لا أجهزة، ولا حساب مربوط، ولا مزوّد
            # مهيّأ، ولا حدث يستحقّ رسالة مدفوعة. متخطّى لا فاشل —
            # وإعادة المحاولة على العدم لا تغيّر شيئًا.
            reason = chain_result.skip_reason or "لا قناة متاحة"
            return cls._finish(notification, NotificationStatus.SKIPPED, reason)

        last_error = chain_result.last_error

        # كلّ ما جُرّب مات نهائيًّا: لا رمز حيّ ولا عنوان صالح. محاولة رابعة
        # على العدم مضيعة صريحة.
        if chain_result.all_permanent:
            return cls._finish(notification, NotificationStatus.FAILED, last_error)

        if notification.attempts >= MAX_ATTEMPTS:
            return cls._finish(notification, NotificationStatus.FAILED, last_error)

        notification.last_error = last_error[:300]
        notification.save(update_fields=["attempts", "last_error"])

        return notification

    @staticmethod
    def _try_fallback(notification):
        """
        القناة الاحتياطية (رسالة نصّية) للأحداث الحرجة وحدها.

        شروطها كلّها داخل `FallbackChannel.should_use`، وهي مقيّدة عمدًا:
        قناة مدفوعة تُفتح على مصراعيها تصير فاتورة قبل أن تصير خدمة.
        """
        try:
            from notifications.services.fallback import FallbackChannel

            return FallbackChannel.send(notification)
        except Exception:  # noqa: BLE001
            logger.exception("notifications: انهارت القناة الاحتياطية")
            return False

    # =================================================================
    # الصيانة
    # =================================================================

    @classmethod
    def expire_stale(cls):
        """
        يُستدعى دوريًا. إشعارات انقضت وهي ما زالت بالانتظار (العامل كان
        متوقفًا مثلًا) تُعلَّم بدل أن تُرسَل متأخرة عند عودته.
        """
        stale = Notification.objects.filter(
            status=NotificationStatus.PENDING,
            expires_at__isnull=False,
            expires_at__lte=timezone.now(),
        )

        return stale.update(
            status=NotificationStatus.EXPIRED,
            last_error="انقضى قبل الإرسال",
        )

    @classmethod
    def retry_pending(cls, limit=100):
        pending = (
            Notification.objects
            .filter(status=NotificationStatus.PENDING, attempts__lt=MAX_ATTEMPTS)
            .order_by("created_at")[:limit]
        )

        for notification in pending:
            cls.dispatch(notification.id)

        return len(pending)

    # =================================================================

    @staticmethod
    def _finish(notification, status, error):
        notification.status = status
        notification.last_error = (error or "")[:300]

        if status == NotificationStatus.SENT:
            notification.sent_at = timezone.now()

        notification.save(
            update_fields=["status", "last_error", "sent_at", "attempts"]
        )

        return notification


# =====================================================================
# تسجيل الأجهزة
# =====================================================================

class DeviceService:

    @staticmethod
    @transaction.atomic
    def register(user, token, platform="android"):
        """
        رمز الجهاز فريد عالميًا لا لكل مستخدم — وهكذا هو معرَّف في
        users.DeviceToken أصلًا (unique=True).

        وهذا سبب وجود هذه الدالة: الهاتف ينتقل. يُعار، أو يسجّل صاحبه
        خروجًا ويدخل غيره، فيصل الرمز نفسه باسم مستخدم آخر. الإنشاء
        الساذج يرتطم بـIntegrityError، والأسوأ منه صفّان لرمز واحد:
        إشعار يصل الشخص الخطأ، وهو تسريب لا إزعاج. update_or_create
        يَنقل الرمز لصاحبه الجديد.
        """
        device, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "user": user,
                "platform": platform,
                "is_active": True,
            },
        )

        return device, created

    @staticmethod
    def unregister(user, token):
        return DeviceToken.objects.filter(user=user, token=token).update(
            is_active=False
        )

    @staticmethod
    def deactivate_all(user):
        return DeviceToken.objects.filter(user=user, is_active=True).update(
            is_active=False
        )
