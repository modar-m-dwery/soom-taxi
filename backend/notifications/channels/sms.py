"""
قناة الرسائل النصّية — الأغلى، والأخيرة دائمًا.

المنطق الذي يقرّر متى تستحقّ رسالةٌ مدفوعة أن تُرسَل موجودٌ ومُختبَر في
`services/fallback.py`: القائمة البيضاء للأحداث، والخنق في Redis، وكتابة
الأثر. هذه القناة تناديه ولا تكرّره — نسختان من قاعدة «متى نرسل SMS»
تتباعدان عند أوّل تعديل، والثمن فاتورة.
"""
from __future__ import annotations

import logging

from notifications.channels.base import BaseChannel, ChannelResult


logger = logging.getLogger("notifications")


class SmsChannel(BaseChannel):

    code = "sms"
    label = "رسالة نصّية"
    requires_address = False
    # تُجرَّب تلقائيًّا، لكنّ `FallbackChannel.should_use` هو الحارس الحقيقي:
    # ثلاثة شروط معًا، ومن أسقط أيًّا منها أغرق مستخدميه.
    default_enabled = True
    min_priority = "urgent"

    def is_configured(self):
        from notifications.services.fallback import _enabled

        return bool(_enabled())

    def resolve_address(self, user):
        return getattr(user, "phone", "") or None

    def deliver(self, user, notification, address=None):
        from notifications.services.fallback import FallbackChannel

        if not FallbackChannel.should_use(notification):
            # ليس فشلًا: الحدث لا يستحقّ رسالة مدفوعة، أو القناة معطّلة.
            return ChannelResult.not_applicable("خارج شروط القناة الاحتياطية")

        try:
            ok = FallbackChannel.send(notification)
        except Exception as exc:  # noqa: BLE001
            logger.exception("sms: انهارت القناة")
            return ChannelResult.transient(exc)

        if ok:
            return ChannelResult.delivered_to("sms")

        # False هنا تعني إمّا خنقًا وإمّا رفض المزوّد. كلاهما لا يستحقّ
        # إبطالًا دائمًا للرقم: الخنق يزول، والمزوّد يعود.
        return ChannelResult.transient("لم يقبل المزوّد الرسالة أو كانت مخنوقة")
