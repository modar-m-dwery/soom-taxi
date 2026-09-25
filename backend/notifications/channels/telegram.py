"""
قناة تليغرام.

لماذا تليغرام لا واتساب
-----------------------
واتساب Business API مقيّد: يحتاج حساب أعمال موثَّقًا، ومزوّدًا معتمدًا، وقوالب
رسائل تُراجَع مسبقًا، ويُحاسَب بالمحادثة. وفي سوريا لا يُتاح عمليًّا.

تليغرام على النقيض: بوت يُنشأ في دقيقتين، مجّانيّ بلا سقف عملي، وواجهته
نداء HTTP واحد. وهو منتشر هنا انتشارًا يجعله قناةً أولى لا احتياطية.

الحدّ الذي يجب أن يُفهم
------------------------
تليغرام **لا يسمح للبوت ببدء محادثة**. لا يمكن الإرسال إلى مستخدم لم يفتح
المحادثة أوّلًا ويضغط «ابدأ». لذلك لا يكفي أن نعرف رقم هاتفه — نحتاج
`chat_id` يصلنا منه هو.

وهذا هو سبب وجود `linking.py`: رابط عميق يحمل رمزًا لمرّة واحدة، يفتحه
المستخدم فيصلنا webhook فيه رمزه و`chat_id`، فنربطهما. بلا هذه الدورة تبقى
القناة معطّلة مهما ضبط المشغّل من مفاتيح.
"""
from __future__ import annotations

import logging

from django.conf import settings

from notifications.channels.base import BaseChannel, ChannelResult


logger = logging.getLogger("notifications")

API_ROOT = "https://api.telegram.org"

#: أخطاء تليغرام التي تعني «هذا العنوان مات» لا «حاول لاحقًا».
#: المستخدم حظر البوت أو حذف المحادثة — إعادة المحاولة عبثٌ أبدي.
PERMANENT_MARKERS = (
    "bot was blocked by the user",
    "user is deactivated",
    "chat not found",
    "bot can't initiate conversation",
    "peer_id_invalid",
)


def bot_token():
    return getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""


def bot_username():
    return getattr(settings, "TELEGRAM_BOT_USERNAME", "") or ""


def _timeout():
    return float(getattr(settings, "TELEGRAM_TIMEOUT_SECONDS", 8))


class TelegramChannel(BaseChannel):

    code = "telegram"
    label = "تليغرام"
    requires_address = True
    # لا تُفتح تلقائيًّا: المستخدم يربط حسابه بنفسه، والربط هو الموافقة.
    default_enabled = False
    min_priority = "normal"

    def is_configured(self):
        return bool(bot_token())

    def resolve_address(self, user):
        from notifications.models import ChannelCode, UserChannelPreference

        row = (
            UserChannelPreference.objects
            .filter(user=user, channel=ChannelCode.TELEGRAM, is_enabled=True)
            .exclude(address="")
            .first()
        )

        return row.address if row else None

    def deliver(self, user, notification, address=None):
        if not self.is_configured():
            return ChannelResult.not_configured("TELEGRAM_BOT_TOKEN غير مضبوط")

        chat_id = address or self.resolve_address(user)

        if not chat_id:
            return ChannelResult.not_applicable("لا حساب تليغرام مربوط")

        return self._send(chat_id, self._compose(notification))

    # -----------------------------------------------------------------

    @staticmethod
    def _compose(notification):
        """
        نصّ الرسالة.

        بلا معلومات شخصية عن الطرف الآخر: تليغرام قناة قد تكون مفتوحة على
        حاسوب مشترك، والإشعار يُغري بفتح التطبيق لا يُغني عنه. الاسم ورقم
        الهاتف يبقيان داخل التطبيق حيث المصادقة.
        """
        lines = [notification.title]

        if notification.body:
            lines.append(notification.body)

        return "\n".join(lines)[:1000]

    def _send(self, chat_id, text):
        try:
            import requests
        except ImportError:  # pragma: no cover
            return ChannelResult.not_configured("مكتبة requests غير مثبَّتة")

        url = f"{API_ROOT}/bot{bot_token()}/sendMessage"

        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    # لا parse_mode: نصّ المستخدم قد يحمل _ أو * فيكسر
                    # التنسيق ويعيد 400 على إشعار سليم.
                    "disable_web_page_preview": True,
                },
                timeout=_timeout(),
            )
        except Exception as exc:  # noqa: BLE001
            # انقطاع شبكة أو مهلة: عابر بلا نقاش.
            return ChannelResult.transient(exc)

        if response.status_code == 200:
            return ChannelResult.delivered_to(f"chat {chat_id}")

        description = self._describe(response)

        # 403/400 مع رسالة معروفة = العنوان مات. غيرها عابر: 429 و5xx
        # وكلّ ما لا نفهمه يستحقّ محاولة أخرى لا إبطالًا نهائيًّا.
        lowered = description.lower()
        if response.status_code in (400, 403) and any(
            marker in lowered for marker in PERMANENT_MARKERS
        ):
            return ChannelResult.permanent(description)

        return ChannelResult.transient(f"HTTP {response.status_code}: {description}")

    @staticmethod
    def _describe(response):
        try:
            return str(response.json().get("description", ""))[:200]
        except Exception:  # noqa: BLE001
            return (response.text or "")[:200]
