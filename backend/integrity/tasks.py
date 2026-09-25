from celery import shared_task

from integrity.services.detectors import Detectors


@shared_task
def run_integrity_detectors():
    """الكواشف الدوريّة كلّها — كلّ نصف ساعة. آمنة للتكرار (مفاتيح منع التكرار)."""
    return Detectors.run_all()


@shared_task
def recompute_risk_scores():
    """التلاشي يحدث مع الوقت لا مع الأحداث: حسابٌ خمل غشّه يعود سليمًا وحده."""
    from integrity.models import RiskLevel, RiskProfile
    from integrity.services.scoring import IntegrityService

    count = 0
    for profile in RiskProfile.objects.exclude(level=RiskLevel.CLEAR).select_related("user"):
        IntegrityService.recompute(profile.user)
        count += 1
    return count
