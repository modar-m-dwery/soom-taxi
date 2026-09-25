"""
القناة — الطبقة التي كانت ناقصة بين «الإشعار» و«المزوّد».

ما كان قائمًا: مزوّد دفع واحد (`NOTIFICATION_BACKEND`) وقناة احتياطية واحدة
مثبَّتة في الشيفرة. أي أنّ إضافة تليغرام كانت تعني تعديل `dispatch()` نفسه،
وإضافة واتساب بعدها تعديله مرّة أخرى — وكلّ تعديل يمرّ على المنطق الذي
يقرّر متى يُرسَل الإشعار أصلًا.

الفصل هنا سطر واحد: **`dispatch` تقرّر متى، والقناة تقرّر كيف.** إضافة قناة
جديدة صارت ملفًّا في هذا المجلّد وسطرًا في السجلّ، بلا لمس منطق الإرسال.

لماذا `ChannelResult` وليس bool
--------------------------------
الفرق بين «فشل عابر» و«فشل دائم» هو ما يمنع طوابير الإشعارات من الامتلاء
بعناوين ميتة تُحاوَل إلى الأبد. وهو تمييزٌ موجود أصلًا في مزوّدات الدفع
(`SendResult`)، والقنوات ترثه بدل أن تخترع لغتها.

و`NOT_CONFIGURED` ليست فشلًا: قناة لم يشترك بها المشغّل بعد يجب أن تُتخطّى
بصمت وتُجرَّب التالية، لا أن تُحسب محاولةً فاشلة تستهلك سقف المحاولات.
"""
from __future__ import annotations

import logging


logger = logging.getLogger("notifications")


class Outcome:
    DELIVERED = "delivered"
    TRANSIENT = "transient"          # أعِد المحاولة لاحقًا
    PERMANENT = "permanent"          # العنوان نفسه ميت — أبطِله
    NOT_CONFIGURED = "not_configured"  # القناة غير مهيّأة — تخطَّ بصمت
    NOT_APPLICABLE = "not_applicable"  # القناة لا تنطبق على هذا الإشعار


class ChannelResult:

    def __init__(self, outcome, error="", detail=""):
        self.outcome = outcome
        self.error = (error or "")[:300]
        self.detail = detail

    @property
    def delivered(self):
        return self.outcome == Outcome.DELIVERED

    @property
    def should_try_next(self):
        """
        هل ننتقل إلى القناة التالية؟

        نعم في كلّ ما ليس تسليمًا. حتّى الفشل العابر: المستخدم ينتظر الآن،
        وقناةٌ أخرى تصله في هذه الثانية خيرٌ من إعادة محاولة بعد دقيقتين
        على القناة نفسها. وإعادة المحاولة تبقى قائمة فوق ذلك.
        """
        return self.outcome != Outcome.DELIVERED

    def __repr__(self):
        return f"ChannelResult({self.outcome}, error={self.error!r})"

    @classmethod
    def delivered_to(cls, detail=""):
        return cls(Outcome.DELIVERED, detail=detail)

    @classmethod
    def transient(cls, error):
        return cls(Outcome.TRANSIENT, error=str(error))

    @classmethod
    def permanent(cls, error):
        return cls(Outcome.PERMANENT, error=str(error))

    @classmethod
    def not_configured(cls, error=""):
        return cls(Outcome.NOT_CONFIGURED, error=str(error))

    @classmethod
    def not_applicable(cls, error=""):
        return cls(Outcome.NOT_APPLICABLE, error=str(error))


class BaseChannel:
    """
    كلّ قناة ترث هذا وتُعرّف `code` و`deliver`.

    التعاقد:

      • `deliver` **لا ترمي أبدًا**. القناة التي تنهار يجب أن تُعيد نتيجة
        عابرة فتُجرَّب التالية — لا أن تُسقط الإشعار كلّه معها.

      • `requires_address` يقول إن كانت القناة تحتاج عنوانًا يسجّله
        المستخدم (chat_id في تليغرام مثلًا). قناة تحتاجه ولا تجده تُعيد
        NOT_APPLICABLE لا فشلًا.

      • `is_configured` تسأل عن الإعدادات لا عن المستخدم: مفتاح البوت
        موجود أم لا.
    """

    code = ""
    label = ""
    requires_address = False

    #: هل تُجرَّب هذه القناة تلقائيًّا حين لا يضبط المستخدم تفضيلاته؟
    #: القنوات المدفوعة تبقى False فلا تُفتح على مصراعيها بالخطأ.
    default_enabled = False

    #: أصغر أولوية إشعار تستحقّ هذه القناة. قناة مكلفة ترفع العتبة.
    min_priority = "low"

    def is_configured(self):
        return True

    def resolve_address(self, user):
        """العنوان على هذه القناة، أو None. تُستعمل حين requires_address."""
        return None

    def deliver(self, user, notification, address=None):
        raise NotImplementedError

    # -----------------------------------------------------------------

    def __repr__(self):
        return f"<{type(self).__name__} {self.code}>"
