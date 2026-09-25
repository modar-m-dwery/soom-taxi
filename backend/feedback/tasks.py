from celery import shared_task


@shared_task
def escalate_stale_complaints():
    """
    شكوى مفتوحة يومين بلا حراك تُرفَع درجتها. الهدف ليس إزعاج الإدارة بل
    منع الصمت: شكوى بلا موعد نهائي تبقى مفتوحة إلى الأبد وتُنسى.
    """
    from feedback.services.complaint import ComplaintService

    escalated = ComplaintService.escalate_stale()

    return f"escalated {len(escalated)} complaints: {escalated}"


@shared_task
def recalculate_rating_summaries(limit=200):
    """
    شبكة أمان لا مسار أساسي: التجميع يجري عند كل تقييم. هذه للحالات التي
    فشل فيها ذلك (سقوط، حذف صف من لوحة الإدارة) - ولأن إعادة الحساب
    idempotent فتشغيلها الدوري بلا ضرر.
    """
    from feedback.models import Rating, RatingDirection
    from feedback.services.rating import RatingService

    driver_ids = list(
        Rating.objects
        .filter(direction=RatingDirection.CUSTOMER_TO_DRIVER)
        .values_list("driver_id", flat=True)
        .distinct()[:limit]
    )

    for driver_id in driver_ids:
        RatingService.recalculate(driver_id=driver_id)

    return f"recalculated {len(driver_ids)} driver summaries"
