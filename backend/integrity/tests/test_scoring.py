"""
نقاط الخطر: التسجيل، منع التكرار، التلاشي، المستويات، القضايا، وقرارات الإدارة.
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from config.testkit import make_admin, make_customer, make_driver
from integrity import registry
from integrity.models import (
    CaseStatus,
    RiskCase,
    RiskLevel,
    RiskNote,
    RiskProfile,
    RiskSignal,
    SignalStatus,
)
from integrity.services.scoring import IntegrityService, decayed, level_for


class DecayAndLevelTests(TestCase):

    def test_weight_halves_after_half_life(self):
        self.assertAlmostEqual(decayed(20, 14, half_life=14), 10.0)
        self.assertAlmostEqual(decayed(20, 0, half_life=14), 20.0)
        self.assertAlmostEqual(decayed(20, 28, half_life=14), 5.0)

    def test_levels_follow_thresholds(self):
        self.assertEqual(level_for(0), RiskLevel.CLEAR)
        self.assertEqual(level_for(19), RiskLevel.CLEAR)
        self.assertEqual(level_for(20), RiskLevel.WATCH)
        self.assertEqual(level_for(40), RiskLevel.REVIEW)
        self.assertEqual(level_for(70), RiskLevel.RESTRICTED)

    @override_settings(INTEGRITY_LEVEL_THRESHOLDS={"watch": 5, "review": 10, "restricted": 15})
    def test_thresholds_are_configurable(self):
        self.assertEqual(level_for(12), RiskLevel.REVIEW)


class RecordTests(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def test_record_creates_signal_and_profile(self):
        signal = IntegrityService.record(self.customer, registry.MULTI_ACCOUNT_DEVICE.code)
        self.assertIsNotNone(signal)
        profile = RiskProfile.objects.get(user=self.customer)
        self.assertEqual(profile.score, registry.MULTI_ACCOUNT_DEVICE.weight)
        self.assertEqual(profile.level, RiskLevel.WATCH)
        self.assertEqual(profile.signals_count, 1)

    def test_same_dedupe_key_counts_once(self):
        first = IntegrityService.record(
            self.customer, registry.MULTI_ACCOUNT_DEVICE.code, dedupe_key="dev:1",
        )
        second = IntegrityService.record(
            self.customer, registry.MULTI_ACCOUNT_DEVICE.code, dedupe_key="dev:1",
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(RiskSignal.objects.filter(user=self.customer).count(), 1)

    def test_none_user_is_ignored(self):
        self.assertIsNone(IntegrityService.record(None, registry.MANUAL_REPORT.code))

    def test_one_signal_never_restricts(self):
        # أقوى إشارة وحدها لا تكفي للتقييد — عائلة تتشارك هاتفًا ليست محتالة.
        strongest = max(k.weight for k in registry.KINDS.values())
        IntegrityService.record(self.customer, registry.REFERRAL_SAME_DEVICE.code, weight=strongest)
        self.assertNotEqual(
            RiskProfile.objects.get(user=self.customer).level, RiskLevel.RESTRICTED,
        )

    def test_old_signals_decay(self):
        old = timezone.now() - timedelta(days=28)
        IntegrityService.record(
            self.customer, registry.MANUAL_REPORT.code, weight=40, at=old,
        )
        IntegrityService.recompute(self.customer)
        # 40 بعد عمرَي نصف = 10
        self.assertEqual(RiskProfile.objects.get(user=self.customer).score, 10)

    def test_score_is_capped_at_100(self):
        for i in range(5):
            IntegrityService.record(self.customer, registry.MANUAL_REPORT.code, weight=40, dedupe_key=f"m{i}")
        self.assertEqual(RiskProfile.objects.get(user=self.customer).score, 100)


class EscalationTests(TestCase):

    def setUp(self):
        self.driver = make_driver()
        self.user = self.driver.user

    def _push(self, total):
        IntegrityService.record(self.user, registry.MANUAL_REPORT.code, weight=total, dedupe_key=f"p{total}")

    def test_review_opens_case_and_note(self):
        self._push(45)
        profile = RiskProfile.objects.get(user=self.user)
        self.assertEqual(profile.level, RiskLevel.REVIEW)
        self.assertTrue(RiskCase.objects.filter(user=self.user, status=CaseStatus.OPEN).exists())
        self.assertTrue(RiskNote.objects.filter(user=self.user, author__isnull=True).exists())

    def test_restricted_is_reversible_and_single_case(self):
        self._push(45)
        self._push(30)
        profile = RiskProfile.objects.get(user=self.user)
        self.assertEqual(profile.level, RiskLevel.RESTRICTED)
        self.assertTrue(IntegrityService.is_restricted(self.user))
        self.assertEqual(RiskCase.objects.filter(user=self.user, status=CaseStatus.OPEN).count(), 1)
        self.assertIn(self.driver.id, IntegrityService.restricted_driver_ids())

    @override_settings(INTEGRITY_AUTO_RESTRICT=False)
    def test_auto_restrict_off_caps_at_review(self):
        self._push(90)
        profile = RiskProfile.objects.get(user=self.user)
        self.assertEqual(profile.level, RiskLevel.REVIEW)
        self.assertFalse(IntegrityService.is_restricted(self.user))

    def test_dismissing_case_drops_score_and_whitelists(self):
        self._push(75)
        case = RiskCase.objects.get(user=self.user, status=CaseStatus.OPEN)
        admin = make_admin()
        IntegrityService.resolve_case(case, CaseStatus.DISMISSED, author=admin, note="تحقّقنا")
        profile = RiskProfile.objects.get(user=self.user)
        self.assertEqual(profile.score, 0)
        self.assertEqual(profile.effective_level(), RiskLevel.CLEAR)
        self.assertFalse(IntegrityService.is_restricted(self.user))
        self.assertTrue(
            RiskSignal.objects.filter(user=self.user, status=SignalStatus.DISMISSED).exists()
        )
        self.assertNotIn(self.driver.id, IntegrityService.restricted_driver_ids())

    def test_confirming_case_keeps_restriction_after_decay(self):
        self._push(75)
        case = RiskCase.objects.get(user=self.user, status=CaseStatus.OPEN)
        IntegrityService.resolve_case(case, CaseStatus.CONFIRMED, author=make_admin())
        RiskSignal.objects.filter(user=self.user).update(created_at=timezone.now() - timedelta(days=80))
        IntegrityService.recompute(self.user)
        profile = RiskProfile.objects.get(user=self.user)
        self.assertLess(profile.score, 10)
        self.assertTrue(IntegrityService.is_restricted(self.user))

    def test_manual_level_expires(self):
        IntegrityService.set_manual_level(self.user, RiskLevel.RESTRICTED, days=1)
        self.assertTrue(IntegrityService.is_restricted(self.user))
        RiskProfile.objects.filter(user=self.user).update(
            manual_until=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(IntegrityService.is_restricted(self.user))

    def test_level_drop_writes_note(self):
        self._push(25)
        RiskSignal.objects.filter(user=self.user).update(status=SignalStatus.DISMISSED)
        IntegrityService.recompute(self.user)
        self.assertTrue(
            RiskNote.objects.filter(user=self.user, text__contains="انخفض").exists()
        )
