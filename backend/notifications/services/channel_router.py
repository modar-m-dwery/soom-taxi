"""
سلسلة القنوات — من يُجرَّب، وبأيّ ترتيب، ومتى نتوقّف.

القاعدة في سطر: **أوّل قناة تُسلّم توقف السلسلة.** الإشعار الواحد يصل مرّة
واحدة، لا ثلاث مرّات على ثلاث قنوات. مستخدمٌ يتلقّى الدعوة نفسها دفعًا
وتليغرامًا ورسالةً نصّية يُطفئ الإشعارات كلّها في أسبوع.

كيف تُبنى السلسلة
------------------
تفضيلات المستخدم أوّلًا إن وُجدت، مرتّبةً بـ`priority`. فإن لم يضبط شيئًا
تُستعمل القنوات ذات `default_enabled` بترتيب السجلّ — وهو بالضبط سلوك ما
قبل هذه الطبقة: دفعٌ ثمّ رسالة نصّية للحرج وحده.

التصفية قبل المحاولة
--------------------
تُستبعد القناة قبل أن تُنادى إن: كانت معطّلة للمستخدم، أو غير مهيّأة في
الخادم، أو كانت أولوية الإشعار أدنى من عتبتها، أو كانت تحتاج عنوانًا ولا
عنوان. الاستبعاد المسبق ليس تحسينًا فحسب — هو ما يمنع محاولةً فاشلة من
استهلاك سقف المحاولات على قناة لم تكن مؤهّلة أصلًا.
"""
from __future__ import annotations

import logging

from notifications.channels.base import Outcome
from notifications.channels.registry import all_channels


logger = logging.getLogger("notifications")


#: ترتيب الأولويات تصاعديًّا. يُستعمل لمقارنة عتبة القناة بأولوية الإشعار.
PRIORITY_RANK = {"low": 0, "normal": 1, "urgent": 2}


class ChannelChainResult:

    def __init__(self, delivered_by=None, attempts=None):
        self.delivered_by = delivered_by
        self.attempts = attempts or []

    @property
    def delivered(self):
        return self.delivered_by is not None

    @property
    def last_error(self):
        for channel_code, result in reversed(self.attempts):
            if result.error:
                return result.error
        return ""

    @property
    def _real_attempts(self):
        """
        المحاولات التي وصلت المزوّد فعلًا وردّ عليها بفشل.

        NOT_APPLICABLE وNOT_CONFIGURED ليستا منها: الأولى تعني «هذه القناة
        لا تخصّ هذا المستخدم» (لا أجهزة، لا حساب مربوط)، والثانية «المشغّل
        لم يشترك بعد». كلتاهما حالة تشغيل لا خطأ، ولا شيء فيهما يُعاد.
        """
        return [
            result for _, result in self.attempts
            if result.outcome in (Outcome.PERMANENT, Outcome.TRANSIENT)
        ]

    @property
    def nothing_tried(self):
        """
        لم تصل السلسلة إلى مزوّد واحد.

        هذا هو الفرق بين «متخطّى» و«فاشل»، وهو فرقٌ عملي لا تسمية: الفاشل
        يدخل طابور إعادة المحاولة ويُحاوَل ثلاث مرّات، والمتخطّى يُترك.
        إشعارٌ لمستخدم بلا تطبيق مثبَّت لا يتغيّر حاله بعد دقيقتين.
        """
        return not self._real_attempts

    @property
    def skip_reason(self):
        """سبب التخطّي كما قالته آخر قناة — ليقرأه المشغّل لا ليخمّنه."""
        for _, result in self.attempts:
            if result.error:
                return result.error
        return ""

    @property
    def all_permanent(self):
        """
        هل كلّ ما جُرّب فعلًا مات نهائيًّا؟ عندها لا معنى لمحاولة رابعة.
        """
        real = self._real_attempts
        return bool(real) and all(
            result.outcome == Outcome.PERMANENT for result in real
        )


class ChannelRouter:

    @classmethod
    def deliver(cls, notification, push_backend=None):
        """
        يمشي في السلسلة ويتوقّف عند أوّل تسليم.

        لا يرمي أبدًا: قناة تنهار تُسجَّل وتُتخطّى، فانهيار مزوّد واحد لا
        يمنع الثاني من إيصال الرسالة.

        `push_backend` منفذ اختبار يمرّ إلى قناة الدفع وحدها — أوامر الفحص
        تحقن مزوّدًا وهميًّا لتجرّب الفشل بلا شبكة.
        """
        user = notification.user
        chain = cls.build_chain(user, notification, push_backend=push_backend)

        attempts = []
        delivered_by = None

        for channel, address in chain:
            kwargs = {"address": address}
            if push_backend is not None and channel.code == "push":
                kwargs["backend"] = push_backend

            try:
                result = channel.deliver(user, notification, **kwargs)
            except Exception as exc:  # noqa: BLE001
                # التعاقد يقول إنّ deliver لا ترمي — لكنّ التعاقد ليس
                # حارسًا. القناة التي تخالفه تُسجَّل وتُتخطّى.
                logger.exception("notifications: انهارت القناة %s", channel.code)
                from notifications.channels.base import ChannelResult

                result = ChannelResult.transient(exc)

            attempts.append((channel.code, result))
            cls._record(notification, channel.code, result)

            if result.delivered:
                delivered_by = channel.code
                break

        return ChannelChainResult(delivered_by=delivered_by, attempts=attempts)

    # -----------------------------------------------------------------
    # بناء السلسلة
    # -----------------------------------------------------------------

    @classmethod
    def build_chain(cls, user, notification, push_backend=None):
        """[(channel, address)] بالترتيب الذي ستُجرَّب به."""
        preferences = cls._preferences(user)
        rank = PRIORITY_RANK.get(notification.priority, 1)

        ordered = cls._order(preferences)

        chain = []

        for channel in ordered:
            preference = preferences.get(channel.code)
            injected = push_backend is not None and channel.code == "push"

            if preference is not None and not preference.is_enabled:
                continue

            if preference is None and not channel.default_enabled:
                # قناة لم يفعّلها المستخدم ولا تُفتح تلقائيًّا: تليغرام
                # بلا ربط مثلًا. الصمت هنا صحيح لا نقص.
                continue

            if rank < PRIORITY_RANK.get(channel.min_priority, 0):
                continue

            # مزوّد محقون يتجاوز فحص الجاهزية: الفحص يسأل عن المزوّد
            # الحقيقي، والمحقون هو ما سيُستعمل فعلًا.
            if not injected and not channel.is_configured():
                continue

            address = ""
            if channel.requires_address:
                address = (preference.address if preference else "") or (
                    channel.resolve_address(user) or ""
                )
                if not address:
                    continue

            chain.append((channel, address))

        return chain

    @staticmethod
    def _preferences(user):
        from notifications.models import UserChannelPreference

        return {
            row.channel: row
            for row in UserChannelPreference.objects.filter(user=user)
        }

    @staticmethod
    def _order(preferences):
        """
        ترتيب القنوات: ما ضبطه المستخدم أوّلًا بأولوياته، ثمّ الباقي
        بترتيب السجلّ. قناة بلا تفضيل تأخذ أولوية 100 وهي أكبر من
        الافتراضات المعقولة، فتقع بعد ما اختاره المستخدم صراحةً.
        """
        channels = list(all_channels())

        def key(channel):
            preference = preferences.get(channel.code)
            explicit = preference.priority if preference else 100
            return (explicit, channels.index(channel))

        return sorted(channels, key=key)

    # -----------------------------------------------------------------

    @staticmethod
    def _record(notification, channel_code, result):
        """
        سجلّ التسليم. الكتابة هنا لا تُسقط الإرسال أبدًا: إشعارٌ وصل
        وسجلٌّ لم يُكتب أفضل من إشعار لم يصل لأنّ السجلّ فشل.
        """
        from notifications.models import ChannelDelivery

        try:
            ChannelDelivery.objects.create(
                notification=notification,
                channel=channel_code,
                outcome=result.outcome,
                error=result.error[:300],
                detail=(result.detail or "")[:120],
            )
        except Exception:  # noqa: BLE001
            logger.exception("notifications: تعذّر تسجيل محاولة التسليم")
