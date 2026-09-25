"""
نقاط الخطر: تسجيل الإشارة، وإعادة حساب الحساب، وفتح القضيّة، والتقييد.

النقاط = مجموع أوزان الإشارات الفعّالة، كلٌّ منها مضروبٌ في تلاشٍ أُسّيّ
بعمر نصفٍ قابل للإعداد (14 يومًا افتراضًا). إشارةٌ عمرها أسبوعان تساوي
نصف وزنها، وعمرها شهران تكاد تختفي — من أخطأ مرّة يستعيد سمعته وحده.

الحساب يُعاد من الإشارات كلّ مرّة ولا يُزاد تراكميًّا: إسقاط إشارة كاذبة
يُنزل النقاط فورًا، ولا ينحرف الملفّ عن الحقيقة مهما تكرّر التشغيل.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from integrity import registry
from integrity.models import (
    LEVEL_ORDER,
    CaseStatus,
    RiskCase,
    RiskLevel,
    RiskNote,
    RiskProfile,
    RiskSignal,
    SignalStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    RiskLevel.WATCH: 20,
    RiskLevel.REVIEW: 40,
    RiskLevel.RESTRICTED: 70,
}

# الإشارات الأقدم من هذا لا تدخل الحساب أصلًا: بعد ستّة أعمار نصف لا يبقى
# من الوزن إلّا 1.5٪، وقراءتها كلفةٌ بلا أثر.
MAX_AGE_DAYS = 90

RESTRICTED_DRIVERS_CACHE_KEY = "integrity:restricted-driver-ids:v1"
RESTRICTED_CACHE_TTL = 60


def half_life_days():
    return float(getattr(settings, "INTEGRITY_HALF_LIFE_DAYS", 14))


def thresholds():
    custom = getattr(settings, "INTEGRITY_LEVEL_THRESHOLDS", None) or {}
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update({RiskLevel(k): int(v) for k, v in custom.items()})
    return merged


def auto_restrict_enabled():
    return bool(getattr(settings, "INTEGRITY_AUTO_RESTRICT", True))


def level_for(score):
    limits = thresholds()
    if score >= limits[RiskLevel.RESTRICTED]:
        return RiskLevel.RESTRICTED
    if score >= limits[RiskLevel.REVIEW]:
        return RiskLevel.REVIEW
    if score >= limits[RiskLevel.WATCH]:
        return RiskLevel.WATCH
    return RiskLevel.CLEAR


def decayed(weight, age_days, half_life=None):
    half_life = half_life or half_life_days()
    if age_days <= 0:
        return float(weight)
    return float(weight) * 0.5 ** (age_days / half_life)


class IntegrityService:

    # ------------------------------------------------------------------
    # التسجيل
    # ------------------------------------------------------------------

    @classmethod
    def record(
        cls,
        user,
        kind,
        *,
        evidence=None,
        ride=None,
        trip=None,
        counterpart=None,
        dedupe_key=None,
        weight=None,
        at=None,
    ):
        """
        يسجّل إشارةً ويعيد حساب صاحبها. يرجع الإشارة، أو None إن كانت
        مكرّرة (المفتاح نفسه سُجّل من قبل) أو كان المستخدم غير موجود.
        """
        if user is None:
            return None

        definition = registry.get(kind)
        at = at or timezone.now()

        try:
            with transaction.atomic():
                signal = RiskSignal.objects.create(
                    user=user,
                    kind=definition.code,
                    weight=definition.weight if weight is None else int(weight),
                    evidence=evidence or {},
                    ride=ride,
                    trip=trip,
                    counterpart=counterpart,
                    dedupe_key=dedupe_key,
                    created_at=at,
                )
        except IntegrityError:
            return None

        cls.recompute(user, now=at, trigger=signal)
        return signal

    # ------------------------------------------------------------------
    # إعادة الحساب
    # ------------------------------------------------------------------

    @classmethod
    def score_for(cls, user, now=None):
        now = now or timezone.now()
        since = now - timedelta(days=MAX_AGE_DAYS)
        half_life = half_life_days()
        rows = RiskSignal.objects.filter(
            user=user, status=SignalStatus.ACTIVE, created_at__gte=since,
        ).values_list("weight", "created_at")
        total = sum(
            decayed(weight, (now - created).total_seconds() / 86400, half_life)
            for weight, created in rows
        )
        return min(100, int(round(total)))

    @classmethod
    @transaction.atomic
    def recompute(cls, user, now=None, trigger=None):
        now = now or timezone.now()
        profile, _ = RiskProfile.objects.select_for_update().get_or_create(user=user)
        previous = profile.level

        score = cls.score_for(user, now)
        level = level_for(score)
        if level == RiskLevel.RESTRICTED and not auto_restrict_enabled():
            # التقييد الآليّ مطفأ: أعلى ما يبلغه الحساب وحده «بحاجة مراجعة».
            level = RiskLevel.REVIEW

        stats = RiskSignal.objects.filter(user=user, status=SignalStatus.ACTIVE)
        profile.score = score
        profile.level = level
        profile.signals_count = stats.count()
        last = stats.order_by("-created_at").values_list("created_at", flat=True).first()
        profile.last_signal_at = last
        profile.save()

        if LEVEL_ORDER[level] > LEVEL_ORDER[previous]:
            cls._escalated(profile, previous, trigger, now)
        elif LEVEL_ORDER[level] < LEVEL_ORDER[previous]:
            RiskNote.objects.create(
                user=user,
                text=(
                    f"انخفض المستوى من «{RiskLevel(previous).label}» إلى "
                    f"«{RiskLevel(level).label}» (النقاط {score})."
                ),
                created_at=now,
            )

        if RiskLevel.RESTRICTED in (previous, level):
            cls._invalidate_restricted_cache()

        return profile

    @classmethod
    def _escalated(cls, profile, previous, trigger, now):
        user = profile.user
        cause = f" — آخر إشارة: {trigger.kind_label}" if trigger is not None else ""
        RiskNote.objects.create(
            user=user,
            text=(
                f"ارتفع المستوى من «{RiskLevel(previous).label}» إلى "
                f"«{RiskLevel(profile.level).label}» (النقاط {profile.score}){cause}."
            ),
            created_at=now,
        )

        if LEVEL_ORDER[profile.level] >= LEVEL_ORDER[RiskLevel.REVIEW]:
            cls.open_case(profile, now=now)

        if profile.level == RiskLevel.RESTRICTED:
            RiskNote.objects.create(
                user=user,
                text=(
                    "قُيِّد الحساب آليًّا: بلا خصومات وأرصدة، بلا «اختر سيارتك»، "
                    "وللسائق بلا «الأقرب» وبلا مكافآت الحوافز — حتّى يراجعه موظّف."
                ),
                created_at=now,
            )

    # ------------------------------------------------------------------
    # القضايا
    # ------------------------------------------------------------------

    @classmethod
    def open_case(cls, profile, now=None):
        now = now or timezone.now()
        kinds = (
            RiskSignal.objects.filter(user=profile.user, status=SignalStatus.ACTIVE)
            .values_list("kind", flat=True).distinct()
        )
        labels = sorted({registry.KINDS[k].label for k in kinds if k in registry.KINDS})
        reason = "، ".join(labels)[:255] or "نقاط خطر مرتفعة"
        try:
            with transaction.atomic():
                return RiskCase.objects.create(
                    user=profile.user,
                    reason=reason,
                    score_at_open=profile.score,
                    opened_at=now,
                )
        except IntegrityError:
            # قضيّة مفتوحة أصلًا: حدّث سببها بدل أن تفتح ثانية.
            RiskCase.objects.filter(user=profile.user, status=CaseStatus.OPEN).update(
                reason=reason,
            )
            return RiskCase.objects.filter(user=profile.user, status=CaseStatus.OPEN).first()

    @classmethod
    @transaction.atomic
    def resolve_case(cls, case, status, author=None, note="", restrict_days=None):
        """
        confirmed: غشٌّ مؤكَّد — يبقى الحساب مقيّدًا بقرار بشريّ
            (`restrict_days` فارغ = حتّى إشعار آخر).
        dismissed: إنذار كاذب — تُسقط إشارات الحساب الفعّالة، ويُعلَّم
            «سليم» ثلاثين يومًا كي لا يعود الإنذار نفسه من النمط القديم.
        """
        now = timezone.now()
        case = RiskCase.objects.select_for_update().get(pk=case.pk)
        if case.status != CaseStatus.OPEN:
            return case

        case.status = status
        case.resolved_at = now
        case.resolved_by = author
        case.resolution_note = note
        case.save()

        profile, _ = RiskProfile.objects.get_or_create(user=case.user)
        if status == CaseStatus.CONFIRMED:
            profile.manual_level = RiskLevel.RESTRICTED
            profile.manual_until = (
                now + timedelta(days=restrict_days) if restrict_days else None
            )
            text = "أكّد موظّف الغش: الحساب مقيّد بقرار الإدارة."
        else:
            RiskSignal.objects.filter(
                user=case.user, status=SignalStatus.ACTIVE, created_at__lte=now,
            ).update(status=SignalStatus.DISMISSED)
            profile.manual_level = RiskLevel.CLEAR
            profile.manual_until = now + timedelta(days=30)
            text = "رفض موظّف الإنذار: أُسقطت الإشارات وعُلِّم الحساب سليمًا 30 يومًا."
        profile.save()

        cls.add_note(case.user, f"{text} {note}".strip(), author=author)
        cls.recompute(case.user, now=now)
        cls._invalidate_restricted_cache()
        return case

    # ------------------------------------------------------------------
    # قرارات الإدارة
    # ------------------------------------------------------------------

    @classmethod
    def add_note(cls, user, text, author=None):
        return RiskNote.objects.create(user=user, author=author, text=text)

    @classmethod
    def set_manual_level(cls, user, level, author=None, days=None, note=""):
        profile, _ = RiskProfile.objects.get_or_create(user=user)
        profile.manual_level = level or ""
        profile.manual_until = (
            timezone.now() + timedelta(days=days) if (level and days) else None
        )
        profile.save()
        label = RiskLevel(level).label if level else "بلا تجاوز (حسب النقاط)"
        cls.add_note(user, f"قرار إداريّ: {label}. {note}".strip(), author=author)
        cls._invalidate_restricted_cache()
        return profile

    # ------------------------------------------------------------------
    # الأسئلة التي تطرحها بقيّة المنصّة
    # ------------------------------------------------------------------

    @staticmethod
    def is_restricted(user):
        if user is None or getattr(user, "pk", None) is None:
            return False
        profile = RiskProfile.objects.filter(user_id=user.pk).first()
        return bool(profile and profile.is_restricted)

    @classmethod
    def restricted_driver_ids(cls):
        """معرّفات DriverProfile المقيّدة — مخزّنة دقيقة، تُسأل في كلّ جولة «الأقرب»."""
        cached = cache.get(RESTRICTED_DRIVERS_CACHE_KEY)
        if cached is not None:
            return cached

        from users.models import DriverProfile

        now = timezone.now()
        restricted_user_ids = [
            p.user_id
            for p in RiskProfile.objects.exclude(level=RiskLevel.CLEAR, manual_level="")
            if p.effective_level(now) == RiskLevel.RESTRICTED
        ]
        ids = set(
            DriverProfile.objects.filter(user_id__in=restricted_user_ids)
            .values_list("id", flat=True)
        )
        cache.set(RESTRICTED_DRIVERS_CACHE_KEY, ids, RESTRICTED_CACHE_TTL)
        return ids

    @staticmethod
    def _invalidate_restricted_cache():
        cache.delete(RESTRICTED_DRIVERS_CACHE_KEY)
