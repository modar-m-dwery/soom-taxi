"""
مهامّ المستخدمين — إيصال رمز الدخول خارج دورة الطلب.

لماذا خارج الطلب؟ لأن مزوّد الرسائل طرف ثالث بطيء أحيانًا ومتوقّف أحيانًا.
إرسال متزامن داخل `RequestOTPView` يعني أن كل تعثّر عند المزوّد يظهر
كتجمّد عشر ثوانٍ في شاشة تسجيل الدخول ثم خطأ — بينما التحدّي أُنشئ فعلًا
وكان يكفي إعادة المحاولة.

الفصل يقلب المعادلة: الطلب يعيد 201 فورًا، والإيصال يجري في الخلفية
بإعادة محاولة واحدة للفشل العابر.
"""
import logging

from celery import shared_task

from users.services.delivery import deliver_otp


logger = logging.getLogger(__name__)

#: إعادة واحدة فقط، وبعد ثوانٍ قليلة. رمز الدخول يعيش خمس دقائق —
#: إعادة المحاولة بعد دقيقتين تصل بعد أن يكون المستخدم قد طلب رمزًا جديدًا.
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 5


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_DELAY_SECONDS,
    name="users.tasks.send_otp_code",
)
def send_otp_code(self, phone, code, challenge_id=None):
    """
    يوصل الرمز. تُستدعى بـ`.delay()` من العرض.

    **الرمز لا يُسجَّل هنا ولا يظهر في أي أثر.** ويُمرَّر إلى Celery وسيطًا
    لا يُقرأ من قاعدة البيانات، لأن المخزَّن مجزَّأ بـSHA-256 ولا يمكن
    استرجاعه — وهذا هو التصميم الصحيح.
    """
    result = deliver_otp(phone, code)

    if result.ok:
        logger.info(
            "otp: أُرسل إلى %s (تحدٍّ %s، مرجع %s)",
            phone, challenge_id, result.reference or "-",
        )
        return {"ok": True, "reference": result.reference}

    if result.permanent_failure:
        # لا إعادة: رقم غير صالح أو مزوّد غير مهيّأ لن يُصلحهما التكرار.
        logger.error(
            "otp: فشل دائم في الإيصال إلى %s: %s", phone, result.error
        )
        return {"ok": False, "permanent": True, "error": result.error}

    logger.warning(
        "otp: فشل عابر في الإيصال إلى %s: %s", phone, result.error
    )

    try:
        raise self.retry(exc=RuntimeError(result.error))
    except self.MaxRetriesExceededError:
        logger.error(
            "otp: استُنفدت المحاولات للإيصال إلى %s: %s", phone, result.error
        )
        return {"ok": False, "permanent": False, "error": result.error}
