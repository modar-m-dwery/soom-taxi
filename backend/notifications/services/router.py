"""
NotificationRouter — من حدث في النظام إلى إشعار على هاتف.

الخيار المعماري: قاموس واحد يربط نوع الحدث ببانٍ يقرر المستلم والنصّ
والأولوية والمهلة. إضافة حدث جديد لاحقًا = مدخل واحد هنا، لا نداء جديد
مبعثر في خدمة أخرى.

ولماذا لا نشتقّ النصّ آليًا من حمولة الحدث؟ لأن ما يُعرض على شاشة مقفلة
ليس ترجمة لحمولة تقنية: "لديك دعوة" ليست `invitation.created`، والأولوية
والمهلة قراران بشريان لا حقلان في الحمولة.
"""
import logging

from django.utils import timezone

from notifications.models import AppKind, NotificationPriority
from notifications.services.dispatch import NotificationService

logger = logging.getLogger("notifications")


class NotificationRouter:

    @classmethod
    def handle(cls, event_type, **context):
        """
        نقطة الدخول الوحيدة من الخدمات. لا ترفع أبدًا: فشل الإشعار لا يجوز
        أن يُسقط قبول دعوة أو إنهاء رحلة.
        """
        builder = BUILDERS.get(event_type)

        if builder is None:
            return None

        try:
            # نمرّر نوع الحدث دائمًا: البُناة المشتركة بين حدثين (الانتهاء
            # والإلغاء مثلًا) تحتاجه لتمييز مفتاح منع التكرار.
            return builder(event_type=event_type, **context)
        except Exception as exc:
            logger.exception("notification build failed for %s: %s", event_type, exc)
            return None


# =====================================================================
# البناة
# =====================================================================

def _invitation_created(invitation=None, **_kwargs):
    """
    الإشعار الذي بُنيت هذه المرحلة كلها من أجله.

    الدعوة المباشرة مهلتها عشرون إلى ستين ثانية، وتفترض أن تطبيق السائق
    مفتوح ومتصل بـWebSocket. وهو ليس كذلك أغلب اليوم — الهاتف في جيبه
    والشاشة مقفلة. بلا هذا الإشعار كانت ميزة الخريطة الحيّة كلها تعمل على
    الورق فقط.
    """
    if invitation is None:
        return None

    driver_user = invitation.driver.user
    ride = invitation.ride

    return NotificationService.create(
        user=driver_user,
        event_type="invitation.created",
        title="طلب رحلة لك",
        body=(
            f"زبون اختارك مباشرة · {invitation.quoted_fare} "
            f"{getattr(ride, 'currency', '') or ''}"
        ).strip(),
        data={
            "screen": "invitation",
            "invitation_id": invitation.id,
            "ride_id": invitation.ride_id,
            "ttl_seconds": invitation.ttl_seconds,
            "eta_minutes": invitation.eta_minutes or "",
        },
        app=AppKind.DRIVER,
        priority=NotificationPriority.URGENT,
        # المهلة هي مهلة الدعوة نفسها لا رقمًا مستقلًا: إشعار يعيش أطول من
        # الدعوة يَعِد بعمل لم يعد موجودًا.
        expires_at=invitation.expires_at,
        dedupe_key=f"invitation.created:{invitation.id}",
    )


def _invitation_closed(invitation=None, event_type="invitation.expired", **_kwargs):
    """
    إشعار صامت يمسح البطاقة من شاشة السائق.

    بلا هذا تبقى دعوة منتهية معروضة عليه إلى أن يفتح التطبيق ويكتشف
    بنفسه — ويضغط عليها فيُرفض.
    """
    if invitation is None:
        return None

    return NotificationService.create(
        user=invitation.driver.user,
        event_type=event_type,
        title="انتهت الدعوة",
        body="",
        data={
            "screen": "invitation_dismiss",
            "invitation_id": invitation.id,
            "ride_id": invitation.ride_id,
            "silent": "1",
        },
        app=AppKind.DRIVER,
        priority=NotificationPriority.LOW,
        expires_at=timezone.now() + timezone.timedelta(minutes=5),
        dedupe_key=f"{event_type}:{invitation.id}",
    )


def _driver_arrived(trip=None, **_kwargs):
    if trip is None:
        return None

    return NotificationService.create(
        user=trip.customer,
        event_type="driver.arrived",
        title="سائقك وصل",
        body="السيارة في انتظارك عند نقطة الالتقاء.",
        data={"screen": "ride", "ride_id": trip.ride_id},
        app=AppKind.CUSTOMER,
        priority=NotificationPriority.URGENT,
        expires_at=timezone.now() + timezone.timedelta(minutes=15),
        dedupe_key=f"driver.arrived:{trip.id}",
    )


def _trip_started(trip=None, **_kwargs):
    if trip is None:
        return None

    return NotificationService.create(
        user=trip.customer,
        event_type="trip.started",
        title="بدأت رحلتك",
        body="",
        data={"screen": "ride", "ride_id": trip.ride_id, "silent": "1"},
        app=AppKind.CUSTOMER,
        priority=NotificationPriority.LOW,
        expires_at=timezone.now() + timezone.timedelta(minutes=30),
        dedupe_key=f"trip.started:{trip.id}",
    )


def _trip_completed(trip=None, **_kwargs):
    if trip is None:
        return None

    return NotificationService.create(
        user=trip.customer,
        event_type="trip.completed",
        title="انتهت رحلتك",
        body=f"الأجرة {trip.final_fare} {trip.currency}. كيف كانت؟",
        data={
            "screen": "rate_trip",
            "ride_id": trip.ride_id,
            "fare": str(trip.final_fare),
        },
        app=AppKind.CUSTOMER,
        priority=NotificationPriority.NORMAL,
        # مهلة التقييم أربعة عشر يومًا، لكن الإشعار نفسه يفقد معناه بعد
        # يوم: التذكير المتأخر يزعج ولا يُقيَّم.
        expires_at=timezone.now() + timezone.timedelta(days=1),
        dedupe_key=f"trip.completed:{trip.id}",
    )


def _trip_cancelled(trip=None, actor="customer", **_kwargs):
    if trip is None:
        return None

    if actor == "customer":
        user, app = trip.driver.user, AppKind.DRIVER
        body = "ألغى الزبون الرحلة."
    else:
        user, app = trip.customer, AppKind.CUSTOMER
        body = "اعتذر السائق عن الرحلة. نبحث لك عن بديل."

    return NotificationService.create(
        user=user,
        event_type="trip.cancelled",
        title="أُلغيت الرحلة",
        body=body,
        data={"screen": "ride", "ride_id": trip.ride_id},
        app=app,
        priority=NotificationPriority.URGENT,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
        dedupe_key=f"trip.cancelled:{trip.id}",
    )


def _offer_accepted(ride=None, driver=None, **_kwargs):
    if ride is None:
        return None

    name = ""
    if driver is not None:
        name = getattr(getattr(driver, "user", None), "name", "") or ""

    return NotificationService.create(
        user=ride.customer,
        event_type="offer.accepted",
        title="تم تثبيت سائقك",
        body=(f"{name} في طريقه إليك." if name else "السائق في طريقه إليك."),
        data={"screen": "ride", "ride_id": ride.id},
        app=AppKind.CUSTOMER,
        priority=NotificationPriority.URGENT,
        expires_at=timezone.now() + timezone.timedelta(minutes=20),
        dedupe_key=f"offer.accepted:{ride.id}",
    )


def _complaint_updated(complaint=None, **_kwargs):
    if complaint is None:
        return None

    return NotificationService.create(
        user=complaint.complainant,
        event_type="complaint.updated",
        title="تحديث على شكواك",
        body=complaint.resolution_note[:200] or "راجعنا شكواك.",
        data={"screen": "complaint", "complaint_id": complaint.id},
        app=AppKind.CUSTOMER,
        priority=NotificationPriority.NORMAL,
        expires_at=timezone.now() + timezone.timedelta(days=7),
        dedupe_key=f"complaint.updated:{complaint.id}:{complaint.status}",
    )


BUILDERS = {
    "invitation.created": _invitation_created,
    "invitation.expired": _invitation_closed,
    "invitation.cancelled": _invitation_closed,
    "offer.accepted": _offer_accepted,
    "driver.arrived": _driver_arrived,
    "trip.started": _trip_started,
    "trip.completed": _trip_completed,
    "trip.cancelled": _trip_cancelled,
    "complaint.updated": _complaint_updated,
}
