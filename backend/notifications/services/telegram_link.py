"""
ربط حساب تليغرام.

المشكلة التي يحلّها هذا الملفّ ليست تقنية بل قيدٌ في تليغرام نفسه: **البوت
لا يستطيع بدء محادثة**. معرفة رقم هاتف المستخدم لا تكفي، ولا اسمه. لا سبيل
للإرسال إليه حتّى يفتح هو المحادثة ويضغط «ابدأ»، فيصلنا حينها `chat_id`.

الدورة كاملة
------------
    1. التطبيق ينادي  POST /api/v1/notifications/channels/telegram/link/
    2. الخادم يولّد رمزًا لمرّة واحدة ويرجّع  https://t.me/<bot>?start=<code>
    3. المستخدم يفتح الرابط ويضغط «ابدأ»
    4. تليغرام يرسل webhook فيه  "/start <code>"  و chat_id
    5. الخادم يبدّل الرمز بـ chat_id ويُنشئ تفضيل القناة

لماذا الرمز لمرّة واحدة وقصير العمر
------------------------------------
لأنّه بلا ذلك يصير سرقةَ حساب: من يلتقط الرابط يربط حسابه هو بإشعارات
غيره — فيقرأ متى تبدأ رحلاته وأين. الرمز يُستهلك عند أوّل استعمال ويموت
بعد عشر دقائق، ويُخزَّن في Redis لا في القاعدة لأنّه بطبيعته عابر.
"""
from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger("notifications")


KEY_PREFIX = "telegram:link:"


def _ttl():
    return int(getattr(settings, "TELEGRAM_LINK_TTL_SECONDS", 600))


class TelegramLinkService:

    @staticmethod
    def _key(code):
        return f"{KEY_PREFIX}{code}"

    @classmethod
    def issue(cls, user):
        """
        يولّد رمز ربط ويرجّع (code, deep_link).

        `token_urlsafe(16)` لا رقمًا متسلسلًا ولا معرّف المستخدم: الرمز
        يمرّ عبر تليغرام ويظهر في محادثة، فلا يجوز أن يكون تخمينه ممكنًا
        ولا أن يكشف من أصدره.
        """
        from notifications.channels.telegram import bot_username

        code = secrets.token_urlsafe(16)

        cache.set(cls._key(code), user.id, timeout=_ttl())

        username = bot_username()
        deep_link = (
            f"https://t.me/{username}?start={code}" if username else ""
        )

        return code, deep_link

    @classmethod
    def redeem(cls, code, chat_id):
        """
        يستهلك الرمز ويربط المحادثة بالمستخدم. يرجّع المستخدم أو None.

        الاستهلاك قبل الربط عمدًا: `cache.delete` بعد `get` يترك نافذة
        يمكن فيها استعمال الرمز مرّتين. ونستعمل الحذف كإقرار — من نجح
        حذفه هو صاحب الحقّ، ومن جاء بعده يجد لا شيء.
        """
        from notifications.models import ChannelCode, UserChannelPreference
        from users.models import User

        key = cls._key(code)
        user_id = cache.get(key)

        if user_id is None:
            return None

        # من يحذف أوّلًا يربح. الثاني يجد الرمز مستهلكًا.
        if not cache.delete(key):
            return None

        user = User.objects.filter(id=user_id).first()

        if user is None:
            return None

        chat_id = str(chat_id)

        # محادثة واحدة لمستخدم واحد: من ربط حسابًا ثمّ ربط آخر بالمحادثة
        # نفسها يجب ألّا يبقى متلقّيًا لإشعارات الأوّل.
        UserChannelPreference.objects.filter(
            channel=ChannelCode.TELEGRAM, address=chat_id
        ).exclude(user=user).delete()

        UserChannelPreference.objects.update_or_create(
            user=user,
            channel=ChannelCode.TELEGRAM,
            defaults={
                "address": chat_id,
                "is_enabled": True,
                "verified_at": timezone.now(),
                # أعلى من الدفع (100 افتراضًا) لا: نتركه بعده. الدفع أسرع
                # وأرخص، وتليغرام هو ما يلتقط من لا يصله الدفع.
                "priority": 110,
            },
        )

        return user

    @classmethod
    def unlink(cls, user):
        from notifications.models import ChannelCode, UserChannelPreference

        return UserChannelPreference.objects.filter(
            user=user, channel=ChannelCode.TELEGRAM
        ).delete()[0]
