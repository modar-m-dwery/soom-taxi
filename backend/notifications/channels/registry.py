"""
سجلّ القنوات — المكان الوحيد الذي يعرف ما هي القنوات الموجودة.

إضافة قناة جديدة (واتساب حين يُتاح، بريد، مكالمة آلية) خطوتان:

    1. ملفّ في هذا المجلّد يرث BaseChannel.
    2. سطر في NOTIFICATION_CHANNELS في الإعدادات.

ولا شيء ثالث. `dispatch` لا تتغيّر، ولا يتغيّر أيّ مستدعٍ لها.

القنوات تُبنى مرّة وتُخزَّن: بناؤها رخيص لكنّه ليس مجّانيًّا، والمسار هنا
يُنفَّذ لكلّ إشعار. والتخزين على مستوى الوحدة لا الطلب لأنّ القناة عديمة
الحالة — كلّ ما تحتاجه يصلها في `deliver`.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils.module_loading import import_string


logger = logging.getLogger("notifications")


DEFAULT_CHANNELS = (
    "notifications.channels.push.PushChannel",
    "notifications.channels.telegram.TelegramChannel",
    "notifications.channels.sms.SmsChannel",
)

_cache = None


def _paths():
    return tuple(getattr(settings, "NOTIFICATION_CHANNELS", DEFAULT_CHANNELS))


def all_channels():
    """كلّ القنوات المسجَّلة، بترتيب الإعدادات."""
    global _cache

    if _cache is not None:
        return _cache

    channels = []

    for path in _paths():
        try:
            channels.append(import_string(path)())
        except Exception:  # noqa: BLE001
            # قناة معطوبة يجب ألّا تُسقط الإشعارات كلّها. تُسجَّل وتُتخطّى،
            # ويبقى ما بقي يعمل.
            logger.exception("notifications: تعذّر تحميل القناة %s", path)

    _cache = tuple(channels)
    return _cache


def get_channel(code):
    for channel in all_channels():
        if channel.code == code:
            return channel
    return None


def channel_codes():
    return [channel.code for channel in all_channels()]


def reset_cache():
    """للاختبارات ولإعادة التحميل بعد override_settings."""
    global _cache
    _cache = None
