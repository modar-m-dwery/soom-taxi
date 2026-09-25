"""
طبقة القنوات.

ما تحرسه هذه الاختبارات ثلاثة أشياء، وكلّها انكسرت في أنظمة حقيقية:

  ١. **أوّل قناة تُسلّم توقف السلسلة.** الإشعار الواحد يصل مرّة واحدة. من
     أسقط هذه القاعدة أرسل الدعوة نفسها دفعًا وتليغرامًا ورسالةً نصّية،
     فأطفأ المستخدم إشعاراته كلّها في أسبوع.

  ٢. **الفرق بين «متخطّى» و«فاشل».** الفاشل يدخل طابور إعادة المحاولة،
     والمتخطّى يُترك. خلطهما يعني إمّا طابورًا يمتلئ بالعدم، وإمّا إشعارًا
     حرجًا يُهمَل.

  ٣. **الافتراض لم يتغيّر.** مستخدم لم يضبط شيئًا يجب أن يتلقّى تمامًا كما
     كان قبل هذه الطبقة — وإلّا كانت «إعادة بناء» لا «إضافة».
"""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from config.testkit import auth, make_customer
from notifications.channels import registry
from notifications.channels.base import BaseChannel, ChannelResult, Outcome
from notifications.models import (
    AppKind,
    ChannelCode,
    ChannelDelivery,
    NotificationPriority,
    NotificationStatus,
    UserChannelPreference,
)
from notifications.services.channel_router import ChannelRouter
from notifications.services.dispatch import NotificationService


# =====================================================================
# قنوات وهمية
# =====================================================================


class _Recorder(BaseChannel):
    """قناة تسجّل أنّها نوديت وتُعيد ما يُملى عليها."""

    outcome = Outcome.DELIVERED
    default_enabled = True
    min_priority = "low"

    def __init__(self):
        self.calls = []

    def deliver(self, user, notification, address=None, **kwargs):
        self.calls.append(notification.id)
        if self.outcome == Outcome.DELIVERED:
            return ChannelResult.delivered_to(self.code)
        return ChannelResult(self.outcome, error=f"{self.code} says no")


class AlphaChannel(_Recorder):
    code = "alpha"
    label = "ألفا"


class BetaChannel(_Recorder):
    code = "beta"
    label = "بيتا"


class ExplodingChannel(BaseChannel):
    code = "boom"
    label = "منهارة"
    default_enabled = True
    min_priority = "low"

    def deliver(self, user, notification, address=None, **kwargs):
        raise RuntimeError("انهارت")


FAKE_CHANNELS = [
    "notifications.tests.AlphaChannel",
    "notifications.tests.BetaChannel",
]


class ChannelTestBase(APITestCase):
    """APITestCase لا TestCase: نقاط الويب هوك والتفضيلات تحتاج APIClient،
    وعميل جانغو العادي يبتلع format="json" كترويسة فيصل الجسم مسطَّحًا."""


    def setUp(self):
        registry.reset_cache()
        self.user = make_customer()

    def tearDown(self):
        registry.reset_cache()

    def make_notification(self, priority=NotificationPriority.NORMAL, **kwargs):
        return NotificationService.create(
            user=self.user,
            event_type=kwargs.pop("event_type", "test.event"),
            title="عنوان",
            body="نصّ",
            app=AppKind.CUSTOMER,
            priority=priority,
            dispatch=False,
            **kwargs,
        )


# =====================================================================
# السلسلة
# =====================================================================


@override_settings(NOTIFICATION_CHANNELS=FAKE_CHANNELS)
class ChainOrderTests(ChannelTestBase):

    def test_first_success_stops_the_chain(self):
        notification = self.make_notification()

        NotificationService.dispatch(notification.id)

        alpha, beta = registry.all_channels()
        self.assertEqual(len(alpha.calls), 1)
        self.assertEqual(beta.calls, [], "بيتا نوديت رغم نجاح ألفا")

    def test_failure_falls_through_to_the_next_channel(self):
        alpha, beta = registry.all_channels()
        alpha.outcome = Outcome.TRANSIENT

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        self.assertEqual(len(beta.calls), 1)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SENT)

    def test_user_priority_reorders_the_chain(self):
        UserChannelPreference.objects.create(
            user=self.user, channel="beta", priority=10
        )

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        alpha, beta = registry.all_channels()
        self.assertEqual(len(beta.calls), 1)
        self.assertEqual(alpha.calls, [], "ألفا سبقت بيتا رغم أولوية المستخدم")

    def test_disabled_channel_is_never_called(self):
        UserChannelPreference.objects.create(
            user=self.user, channel="alpha", is_enabled=False
        )

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        alpha, beta = registry.all_channels()
        self.assertEqual(alpha.calls, [])
        self.assertEqual(len(beta.calls), 1)

    def test_every_attempt_is_recorded(self):
        alpha, _ = registry.all_channels()
        alpha.outcome = Outcome.TRANSIENT

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        rows = list(
            ChannelDelivery.objects
            .filter(notification=notification)
            .order_by("id")
            .values_list("channel", "outcome")
        )

        self.assertEqual(
            rows, [("alpha", Outcome.TRANSIENT), ("beta", Outcome.DELIVERED)]
        )


@override_settings(NOTIFICATION_CHANNELS=FAKE_CHANNELS)
class ChainOutcomeTests(ChannelTestBase):
    """الفرق بين متخطّى وفاشل — وهو فرق عملي لا تسمية."""

    def test_nothing_applicable_is_skipped_not_failed(self):
        for channel in registry.all_channels():
            channel.outcome = Outcome.NOT_APPLICABLE

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SKIPPED)

    def test_unconfigured_provider_is_skipped_not_failed(self):
        for channel in registry.all_channels():
            channel.outcome = Outcome.NOT_CONFIGURED

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SKIPPED)

    def test_all_permanent_fails_immediately(self):
        # لا رمز حيّ ولا عنوان صالح: محاولة رابعة على العدم مضيعة.
        for channel in registry.all_channels():
            channel.outcome = Outcome.PERMANENT

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.FAILED)
        self.assertEqual(notification.attempts, 1)

    def test_transient_stays_pending_for_retry(self):
        for channel in registry.all_channels():
            channel.outcome = Outcome.TRANSIENT

        notification = self.make_notification()
        NotificationService.dispatch(notification.id)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.PENDING)
        self.assertEqual(notification.attempts, 1)

    def test_retries_are_capped(self):
        for channel in registry.all_channels():
            channel.outcome = Outcome.TRANSIENT

        notification = self.make_notification()

        for _ in range(5):
            NotificationService.dispatch(notification.id)
            notification.refresh_from_db()

        self.assertEqual(notification.status, NotificationStatus.FAILED)


@override_settings(
    NOTIFICATION_CHANNELS=[
        "notifications.tests.ExplodingChannel",
        "notifications.tests.BetaChannel",
    ]
)
class ChannelResilienceTests(ChannelTestBase):

    def test_a_crashing_channel_does_not_stop_the_rest(self):
        # التعاقد يقول إنّ deliver لا ترمي — لكنّ التعاقد ليس حارسًا.
        notification = self.make_notification()

        NotificationService.dispatch(notification.id)

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SENT)

        outcomes = dict(
            ChannelDelivery.objects
            .filter(notification=notification)
            .values_list("channel", "outcome")
        )
        self.assertEqual(outcomes["boom"], Outcome.TRANSIENT)
        self.assertEqual(outcomes["beta"], Outcome.DELIVERED)

    def test_a_broken_channel_path_is_skipped_at_load(self):
        with override_settings(
            NOTIFICATION_CHANNELS=[
                "notifications.does.not.Exist",
                "notifications.tests.BetaChannel",
            ]
        ):
            registry.reset_cache()
            codes = registry.channel_codes()

        self.assertEqual(codes, ["beta"])


# =====================================================================
# الأولوية
# =====================================================================


class _UrgentOnlyChannel(_Recorder):
    code = "urgent_only"
    label = "للعاجل فقط"
    min_priority = "urgent"


@override_settings(
    NOTIFICATION_CHANNELS=["notifications.tests._UrgentOnlyChannel"]
)
class PriorityThresholdTests(ChannelTestBase):
    """قناة مكلفة ترفع عتبتها فلا تُفتح على مصراعيها."""

    def test_normal_notification_does_not_reach_an_urgent_only_channel(self):
        notification = self.make_notification(priority=NotificationPriority.NORMAL)
        NotificationService.dispatch(notification.id)

        self.assertEqual(registry.all_channels()[0].calls, [])

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SKIPPED)

    def test_urgent_notification_does_reach_it(self):
        notification = self.make_notification(priority=NotificationPriority.URGENT)
        NotificationService.dispatch(notification.id)

        self.assertEqual(len(registry.all_channels()[0].calls), 1)


# =====================================================================
# الافتراض لم يتغيّر
# =====================================================================


class DefaultBehaviourTests(ChannelTestBase):
    """
    مستخدم لم يضبط شيئًا: دفعٌ أوّلًا، ثمّ رسالة نصّية للحرج وحده — وهو
    بالضبط سلوك ما قبل طبقة القنوات.
    """

    def test_default_chain_is_push_then_sms(self):
        notification = self.make_notification(priority=NotificationPriority.URGENT)

        chain = [c.code for c, _ in ChannelRouter.build_chain(self.user, notification)]

        self.assertEqual(chain[0], "push")
        self.assertNotIn("telegram", chain, "تليغرام دخل السلسلة بلا ربط")

    def test_telegram_is_absent_until_linked(self):
        notification = self.make_notification()

        codes = [c.code for c, _ in ChannelRouter.build_chain(self.user, notification)]

        self.assertNotIn("telegram", codes)

    @override_settings(TELEGRAM_BOT_TOKEN="test-token")
    def test_telegram_joins_the_chain_once_linked(self):
        UserChannelPreference.objects.create(
            user=self.user,
            channel=ChannelCode.TELEGRAM,
            address="123456",
            is_enabled=True,
            priority=110,
        )

        notification = self.make_notification()

        codes = [c.code for c, _ in ChannelRouter.build_chain(self.user, notification)]

        self.assertIn("telegram", codes)


# =====================================================================
# تليغرام
# =====================================================================


class _Response:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_BOT_USERNAME="soum_bot")
class TelegramChannelTests(ChannelTestBase):

    def setUp(self):
        super().setUp()
        from notifications.channels.telegram import TelegramChannel

        self.channel = TelegramChannel()
        self.notification = self.make_notification()

    def _link(self, chat_id="99"):
        UserChannelPreference.objects.create(
            user=self.user,
            channel=ChannelCode.TELEGRAM,
            address=chat_id,
            is_enabled=True,
        )

    def test_not_applicable_without_a_linked_chat(self):
        result = self.channel.deliver(self.user, self.notification)
        self.assertEqual(result.outcome, Outcome.NOT_APPLICABLE)

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_not_configured_without_a_bot_token(self):
        result = self.channel.deliver(self.user, self.notification)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)

    def test_successful_send(self):
        self._link()

        with patch("requests.post", return_value=_Response(200, {"ok": True})) as post:
            result = self.channel.deliver(self.user, self.notification)

        self.assertTrue(result.delivered)

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "99")
        self.assertIn("عنوان", payload["text"])

    def test_blocked_bot_is_a_permanent_failure(self):
        # المستخدم حظر البوت: إعادة المحاولة عبثٌ أبدي.
        self._link()

        response = _Response(
            403, {"description": "Forbidden: bot was blocked by the user"}
        )

        with patch("requests.post", return_value=response):
            result = self.channel.deliver(self.user, self.notification)

        self.assertEqual(result.outcome, Outcome.PERMANENT)

    def test_rate_limit_is_transient(self):
        # 429 يعني «لاحقًا» لا «أبدًا» — إبطال العنوان هنا خسارة مجّانية.
        self._link()

        response = _Response(429, {"description": "Too Many Requests"})

        with patch("requests.post", return_value=response):
            result = self.channel.deliver(self.user, self.notification)

        self.assertEqual(result.outcome, Outcome.TRANSIENT)

    def test_network_error_is_transient(self):
        self._link()

        with patch("requests.post", side_effect=OSError("no network")):
            result = self.channel.deliver(self.user, self.notification)

        self.assertEqual(result.outcome, Outcome.TRANSIENT)

    def test_message_carries_no_third_party_identity(self):
        self._link()

        notification = self.make_notification(
            event_type="invitation.sent",
        )
        notification.data = {"driver_phone": "+963900000000"}
        notification.save()

        with patch("requests.post", return_value=_Response(200, {"ok": True})) as post:
            self.channel.deliver(self.user, notification)

        self.assertNotIn("+963900000000", post.call_args.kwargs["json"]["text"])


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_BOT_USERNAME="soum_bot")
class TelegramLinkingTests(ChannelTestBase):

    def setUp(self):
        super().setUp()
        from notifications.services.telegram_link import TelegramLinkService

        self.service = TelegramLinkService

    def test_link_binds_the_chat_to_the_user(self):
        code, deep_link = self.service.issue(self.user)

        self.assertIn("soum_bot", deep_link)
        self.assertIn(code, deep_link)

        linked = self.service.redeem(code, 4242)

        self.assertEqual(linked, self.user)

        preference = UserChannelPreference.objects.get(
            user=self.user, channel=ChannelCode.TELEGRAM
        )
        self.assertEqual(preference.address, "4242")
        self.assertIsNotNone(preference.verified_at)

    def test_a_code_works_only_once(self):
        # وإلّا كان من يلتقط الرابط يربط حسابه بإشعارات غيره.
        code, _ = self.service.issue(self.user)

        self.assertIsNotNone(self.service.redeem(code, 1))
        self.assertIsNone(self.service.redeem(code, 2))

    def test_unknown_code_is_rejected(self):
        self.assertIsNone(self.service.redeem("not-a-real-code", 1))

    def test_relinking_a_chat_moves_it_off_the_previous_user(self):
        other = make_customer()

        code_a, _ = self.service.issue(self.user)
        self.service.redeem(code_a, 777)

        code_b, _ = self.service.issue(other)
        self.service.redeem(code_b, 777)

        self.assertFalse(
            UserChannelPreference.objects
            .filter(user=self.user, channel=ChannelCode.TELEGRAM)
            .exists()
        )
        self.assertTrue(
            UserChannelPreference.objects
            .filter(user=other, channel=ChannelCode.TELEGRAM, address="777")
            .exists()
        )

    def test_unlink_removes_the_preference(self):
        code, _ = self.service.issue(self.user)
        self.service.redeem(code, 555)

        self.service.unlink(self.user)

        self.assertFalse(
            UserChannelPreference.objects
            .filter(user=self.user, channel=ChannelCode.TELEGRAM)
            .exists()
        )


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_BOT_USERNAME="soum_bot")
class TelegramWebhookTests(ChannelTestBase):

    URL = "/api/v1/notifications/webhooks/telegram/"

    def _update(self, text, chat_id=321):
        return {"message": {"chat": {"id": chat_id}, "text": text}}

    def test_start_with_a_valid_code_links_the_account(self):
        from notifications.services.telegram_link import TelegramLinkService

        code, _ = TelegramLinkService.issue(self.user)

        with patch("requests.post", return_value=_Response(200, {"ok": True})):
            response = self.client.post(
                self.URL, self._update(f"/start {code}"), format="json"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserChannelPreference.objects
            .filter(user=self.user, channel=ChannelCode.TELEGRAM, address="321")
            .exists()
        )

    def test_garbage_update_answers_200(self):
        # تليغرام يعيد إرسال أيّ تحديث لم يُجَب عليه بنجاح إلى الأبد.
        response = self.client.post(self.URL, {"nonsense": True}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_start_without_a_code_does_not_crash(self):
        with patch("requests.post", return_value=_Response(200, {"ok": True})):
            response = self.client.post(self.URL, self._update("/start"), format="json")

        self.assertEqual(response.status_code, 200)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="s3cret")
    def test_wrong_secret_is_forbidden(self):
        response = self.client.post(self.URL, self._update("/start x"), format="json")
        self.assertEqual(response.status_code, 403)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="s3cret")
    def test_correct_secret_passes(self):
        response = self.client.post(
            self.URL,
            self._update("/start x"),
            format="json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret",
        )
        self.assertEqual(response.status_code, 200)


# =====================================================================
# واجهة التفضيلات
# =====================================================================


class ChannelPreferenceApiTests(ChannelTestBase):

    def setUp(self):
        super().setUp()
        auth(self.client, self.user)

    def test_listing_shows_every_registered_channel(self):
        response = self.client.get("/api/v1/me/notification-channels/")

        self.assertEqual(response.status_code, 200)
        codes = [c["code"] for c in response.data["channels"]]
        self.assertEqual(codes, registry.channel_codes())

    def test_channel_can_be_disabled(self):
        response = self.client.patch(
            "/api/v1/me/notification-channels/push/",
            {"is_enabled": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["enabled"])

        preference = UserChannelPreference.objects.get(
            user=self.user, channel="push"
        )
        self.assertFalse(preference.is_enabled)

    def test_priority_can_be_changed(self):
        response = self.client.patch(
            "/api/v1/me/notification-channels/push/",
            {"priority": 5},
            format="json",
        )

        self.assertEqual(response.data["priority"], 5)

    def test_unknown_channel_is_404(self):
        response = self.client.patch(
            "/api/v1/me/notification-channels/carrier-pigeon/",
            {"is_enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_empty_patch_is_rejected(self):
        response = self.client.patch(
            "/api/v1/me/notification-channels/push/", {}, format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_another_user_preferences_are_untouched(self):
        other = make_customer()
        UserChannelPreference.objects.create(
            user=other, channel="push", is_enabled=True, priority=100
        )

        self.client.patch(
            "/api/v1/me/notification-channels/push/",
            {"is_enabled": False},
            format="json",
        )

        self.assertTrue(
            UserChannelPreference.objects.get(user=other, channel="push").is_enabled
        )

    def test_link_endpoint_is_unavailable_without_a_bot(self):
        response = self.client.post(
            "/api/v1/notifications/channels/telegram/link/"
        )
        self.assertEqual(response.status_code, 503)

    @override_settings(TELEGRAM_BOT_TOKEN="t", TELEGRAM_BOT_USERNAME="soum_bot")
    def test_link_endpoint_returns_a_deep_link(self):
        response = self.client.post(
            "/api/v1/notifications/channels/telegram/link/"
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("t.me/soum_bot", response.data["deep_link"])
