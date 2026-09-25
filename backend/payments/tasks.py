"""
مهامّ المدفوعات — شبكات أمان لا مسارات أساسية.

كل مهمّة هنا تصحّح انحرافًا يُفترض ألّا يحدث. وجودها ليس اعترافًا بضعف
المسار الأساسي بل اعتراف بأن الأنظمة الموزّعة تنحرف: عملية تموت بين
كتابتين، وسيط يفقد رسالة، مزوّد يردّ بعد انقضاء المهلة. النظام الذي
يفترض أن ذلك لا يحدث هو الذي ينهار عند أوّل مرّة يحدث فيها.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from payments.models import Payment, PaymentStatus


logger = logging.getLogger(__name__)

#: مهلة قبل اعتبار رحلة مكتملة بلا دفعة انحرافًا. قصيرة بما يكفي ليُصلَح
#: قبل أن يسأل السائق، وطويلة بما يكفي ألّا تسابق المعاملة نفسها.
BACKFILL_GRACE_MINUTES = 3

#: أقصى ما تعالجه دفعة واحدة. الحدّ يمنع مهمّة واحدة من احتلال العامل
#: ساعةً بعد انقطاع طويل.
BATCH_LIMIT = 200


@shared_task(name="payments.tasks.backfill_missing_payments")
def backfill_missing_payments():
    """
    يُنشئ الدفعات الناقصة للرحلات المكتملة.

    يلتقط الحالة التي يتركها `TripService._open_payment` عمدًا حين يفشل:
    الرحلة انتهت والمال مستحقّ ولا سجلّ له.
    """
    from trips.models import Trip, TripStatus
    from payments.services.payment import PaymentService

    cutoff = timezone.now() - timedelta(minutes=BACKFILL_GRACE_MINUTES)

    trips = (
        Trip.objects.filter(
            status=TripStatus.COMPLETED,
            completed_at__lte=cutoff,
            payment__isnull=True,
        )
        .select_related("ride", "driver", "customer")
        .order_by("completed_at")[:BATCH_LIMIT]
    )

    created = 0
    failed = 0

    for trip in trips:
        try:
            PaymentService.open_for_trip(trip)
            created += 1
        except Exception:
            failed += 1
            logger.exception(
                "payments: تعذّر استدراك دفعة الرحلة %s", trip.pk
            )

    if created or failed:
        logger.info(
            "payments: استُدرِكت %d دفعة، وفشلت %d.", created, failed
        )

    return {"created": created, "failed": failed}


@shared_task(name="payments.tasks.retry_stuck_payments")
def retry_stuck_payments():
    """
    يعيد محاولة الدفعات العالقة في PROCESSING.

    الحالة تنشأ حين يفشل نداء المزوّد فشلًا عابرًا: الدفعة ليست مدفوعة
    وليست فاشلة، وتنتظر من يعيد المحاولة. البوابات غير الإلكترونية
    مستثناة — لا شيء يُعاد نداؤه في النقدي.
    """
    from payments.gateways import get_gateway
    from payments.services.payment import PaymentService

    cutoff = timezone.now() - timedelta(minutes=5)

    stuck = (
        Payment.objects.filter(
            status=PaymentStatus.PROCESSING,
            updated_at__lte=cutoff,
        )
        .filter(Q(attempts__lt=5))
        .order_by("updated_at")[:BATCH_LIMIT]
    )

    retried = 0

    for payment in stuck:
        try:
            gateway = get_gateway(payment.gateway_code)
        except Exception:
            logger.exception(
                "payments: بوابة الدفعة %s غير معروفة", payment.pk
            )
            continue

        if not gateway.is_online:
            continue

        try:
            # مهمّة تعويض داخلية: لا مستخدم يقف خلفها، وصلاحيتها من
            # كونها تعمل داخل الخادم لا من هويّة فاعل.
            PaymentService.charge(payment.pk, system=True)
            retried += 1
        except Exception as exc:
            # الفشل هنا متوقّع تمامًا — المهمّة تعيد المحاولة لا تضمن النجاح.
            logger.info(
                "payments: ما زالت الدفعة %s متعثّرة: %s", payment.pk, exc
            )

    return {"retried": retried}


@shared_task(name="payments.tasks.audit_ledger")
def audit_ledger():
    """
    يفحص توازن الدفتر.

    يجب أن يعيد قائمة فارغة دائمًا. أي عنصر فيها يعني أن مالًا كُتب
    غير متوازن — وهي حادثة تُحقَّق فورًا لا رقم يُسجَّل في تقرير.
    """
    from payments.services.ledger import LedgerService

    broken = LedgerService.audit_all()

    if broken:
        logger.error(
            "payments: %d حركة غير متوازنة في الدفتر: %s",
            len(broken),
            broken[:10],
        )

    return {"unbalanced": len(broken)}
