"""
قناة الدفع — غلافٌ حول ما كان يعمل، لا إعادة كتابة له.

منطق الدفع الحالي فيه تفاصيل كُسبت بالتجربة: التمييز بين الفشل العابر
والدائم، وإبطال الرمز الميت بدل إعادة المحاولة عليه أبدًا، وتحديث
`updated_at` عند النجاح. إعادة كتابته ضمن الطبقة الجديدة كانت ستُسقط أحدها
بصمت.

فالقناة هنا لا تفعل شيئًا جديدًا: تنادي المزوّد نفسه بالقواعد نفسها،
وتترجم نتيجته إلى لغة القنوات.
"""
from __future__ import annotations

import logging

from django.utils import timezone

from notifications.backends.base import NotConfigured
from notifications.channels.base import BaseChannel, ChannelResult


logger = logging.getLogger("notifications")


class PushChannel(BaseChannel):

    code = "push"
    label = "إشعار الدفع"
    requires_address = False
    default_enabled = True
    min_priority = "low"

    def is_configured(self):
        from notifications.services.dispatch import get_backend

        try:
            get_backend().check_ready()
            return True
        except NotConfigured:
            return False
        except Exception:  # noqa: BLE001
            logger.exception("push: تعذّر فحص جاهزية المزوّد")
            return False

    def deliver(self, user, notification, address=None, backend=None):
        """
        `backend` منفذ اختبار صريح لا خيار تشغيلي: أوامر الفحص الشاملة
        تحقن مزوّدًا وهميًّا لتجرّب الفشل العابر والدائم بلا شبكة. تسميته
        بما هو خيرٌ من إخفائه خلف إعداد عامّ يُنسى مضبوطًا.
        """
        from notifications.services.dispatch import get_backend
        from users.models import DeviceToken

        tokens = list(DeviceToken.objects.filter(user=user, is_active=True))

        if not tokens:
            # ليس فشلًا: مستخدم بلا تطبيق مثبَّت حالة طبيعية، والقناة
            # التالية هي الجواب لا إعادة المحاولة على العدم.
            return ChannelResult.not_applicable("لا أجهزة مسجَّلة")

        try:
            backend = backend or get_backend()
            backend.check_ready()
        except NotConfigured as exc:
            return ChannelResult.not_configured(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("push: انهار تهيئة المزوّد")
            return ChannelResult.transient(exc)

        delivered = 0
        dead = 0
        last_error = ""

        for token in tokens:
            try:
                result = backend.send(token, notification)
            except Exception as exc:  # noqa: BLE001
                logger.exception("push: انهار الإرسال إلى الرمز %s", token.id)
                last_error = str(exc)
                continue

            if result.ok:
                delivered += 1
                DeviceToken.objects.filter(id=token.id).update(
                    updated_at=timezone.now()
                )
                continue

            last_error = result.error

            if result.permanent_failure:
                # الرمز نفسه مات (حُذف التطبيق، أُعيد ضبط الجهاز). إعادة
                # المحاولة عليه عبثٌ أبدي.
                dead += 1
                DeviceToken.objects.filter(id=token.id).update(is_active=False)
                logger.warning(
                    "device token %s deactivated: %s", token.id, result.error
                )

        if delivered:
            return ChannelResult.delivered_to(f"{delivered}/{len(tokens)} جهازًا")

        if dead == len(tokens):
            # لم يبقَ رمز فعّال واحد: هذا فشل دائم على مستوى القناة لا
            # على مستوى رمز، فلا معنى لمحاولة رابعة.
            return ChannelResult.permanent(last_error or "كلّ الأجهزة ميتة")

        return ChannelResult.transient(last_error or "لم يصل إلى أيّ جهاز")
