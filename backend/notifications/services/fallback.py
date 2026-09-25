"""
قناة احتياطية للإشعارات الحرجة — الوثيقة §10.

«WebSocket داخل الرحلة ثم Push ثم SMS fallback للحالات الحرجة.»
الطبقتان الأوليان قائمتان. هذه هي الثالثة.

متى تعمل بالضبط
---------------
ثلاثة شروط معًا، ومَن أسقط أيًّا منها أغرق مستخدميه برسائل:

  ١. الإشعار **عاجل** (`urgent`). دعوة سائق ولحظة وصول — لا تحديث تقييم.
  ٢. الدفع **لم يصل**: لا أجهزة مسجَّلة، أو كلّ رموزها ماتت، أو فشل.
  ٣. الحدث في قائمة بيضاء صريحة (`NOTIFICATION_SMS_FALLBACK_EVENTS`).

الشرط الثالث هو الحارس الحقيقي. بدونه يكفي عطلٌ في FCM ليتحوّل كلّ
إشعار في المنصّة إلى رسالة نصّية مدفوعة — فاتورةٌ من خمسة أرقام في ليلة.

خنق التكرار
-----------
مفتاح في Redis لكلّ (مستخدم، حدث) يمنع أكثر من رسالة كلّ
`NOTIFICATION_SMS_FALLBACK_COOLDOWN` ثانية. سائقٌ تصله عشر دعوات في
دقيقة يجب ألّا تصله عشر رسائل.

بلا مزوّد؟
----------
`OTP_DELIVERY_BACKEND` الافتراضي هو الطابعة، فتُطبع الرسالة في السجلّ
ويُسجَّل الأثر كما لو أُرسلت. أي أنّ كلّ المنطق فوقها — الشروط، الخنق،
التسجيل — قابلٌ للاختبار اليوم، وحين تشترك بمزوّد لا يتغيّر سطر واحد
هنا: يتغيّر مفتاح إعدادات واحد.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger("notifications")


#: الأحداث التي تستحقّ رسالة نصّية حين يفشل الدفع. قائمة بيضاء لا سوداء.
DEFAULT_FALLBACK_EVENTS = (
    "invitation.sent",
    "offer.accepted",
    "driver.arrived",
    "trip.started",
    "ride.cancelled_by_driver",
)


def _enabled():
    return getattr(settings, "NOTIFICATION_SMS_FALLBACK", False)


def _events():
    return set(
        getattr(settings, "NOTIFICATION_SMS_FALLBACK_EVENTS", DEFAULT_FALLBACK_EVENTS)
    )


def _cooldown():
    return int(getattr(settings, "NOTIFICATION_SMS_FALLBACK_COOLDOWN", 300))


class FallbackChannel:
    """قناة احتياطية واحدة. تُستدعى فقط بعد إخفاق الدفع."""

    @classmethod
    def should_use(cls, notification) -> bool:
        from notifications.models import NotificationPriority

        if not _enabled():
            return False

        if notification.priority != NotificationPriority.URGENT:
            return False

        if notification.event_type not in _events():
            return False

        phone = getattr(notification.user, "phone", "")
        return bool(phone)

    @classmethod
    def send(cls, notification) -> bool:
        """
        يحاول الإرسال. يعيد True إن قُبل الطلب.

        لا يرمي أبدًا: هذه قناة احتياطية، وانهيارها يجب ألّا يحوّل إشعارًا
        فاشلًا إلى طلب فاشل.
        """
        if not cls.should_use(notification):
            return False

        phone = notification.user.phone
        key = f"sms_fallback:{notification.user_id}:{notification.event_type}"

        # add() ذرّية: تنجح لأوّل من يصل فقط، فلا يتسلّل تكرار بين عاملين
        if not cache.add(key, 1, timeout=_cooldown()):
            logger.info(
                "sms-fallback: مخنوق لـ%s (%s)",
                notification.user_id, notification.event_type,
            )
            return False

        message = cls._compose(notification)

        try:
            from users.services.delivery import get_backend

            backend = get_backend()
            backend.check_ready()
            result = backend.send(phone, message)

        except Exception as exc:  # noqa: BLE001
            logger.warning("sms-fallback: تعذّر الإرسال إلى %s: %s", phone, exc)
            return False

        ok = bool(getattr(result, "ok", False))

        # الأثر: رسالة نصّية مدفوعة يجب أن يكون لها سجلّ يُسأل عنه لاحقًا.
        try:
            from ops.models import AuditAction, AuditEntity
            from ops.services.audit import AuditService

            AuditService.record(
                AuditEntity.USER,
                notification.user_id,
                action=AuditAction.UPDATED,
                to_state="sms_fallback_sent" if ok else "sms_fallback_failed",
                actor_label="system:notifications",
                reason=f"قناة احتياطية للحدث {notification.event_type}",
                notification_id=notification.id,
                event_type=notification.event_type,
            )
        except Exception:  # noqa: BLE001
            logger.exception("sms-fallback: تعذّر تسجيل الأثر")

        return ok

    @staticmethod
    def _compose(notification) -> str:
        """
        نصّ قصير بلا روابط ولا بيانات حسّاسة.

        الرسالة تعبر شبكة المشغّل ويقرؤها من يمسك الهاتف. لا اسم زبون
        ولا وجهة ولا مبلغ — العنوان وحده، والتفصيل في التطبيق.
        """
        title = (notification.title or "").strip()
        body = (notification.body or "").strip()

        text = f"{title} - {body}" if body else title
        return text[:150] or "لديك تحديث في تطبيق سووم تكسي."
