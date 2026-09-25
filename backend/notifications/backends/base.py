"""
واجهة مزوّد الإرسال.

التقسيم المهم هنا ليس بين "نجح" و"فشل"، بل بين **فشل عابر** و**فشل دائم**:

- عابر: انقطاع شبكة، مهلة، ضغط على المزوّد. يُعاد.
- دائم: الرمز غير صالح - حُذف التطبيق من الجهاز، أو أُعيد ضبطه.
  إعادة المحاولة عليه عبثٌ إلى الأبد، والصحيح إبطال الرمز.

خلط الحالتين هو ما يجعل طوابير الإشعارات تمتلئ برموز ميتة تُحاوَل ألف مرة.
"""


class SendResult:

    def __init__(self, ok, permanent_failure=False, error=""):
        self.ok = ok
        self.permanent_failure = permanent_failure
        self.error = error

    def __repr__(self):
        return (
            f"SendResult(ok={self.ok}, "
            f"permanent={self.permanent_failure}, error={self.error!r})"
        )

    @classmethod
    def success(cls):
        return cls(True)

    @classmethod
    def transient(cls, error):
        return cls(False, permanent_failure=False, error=str(error)[:300])

    @classmethod
    def permanent(cls, error):
        return cls(False, permanent_failure=True, error=str(error)[:300])


class NotConfigured(Exception):
    """المزوّد غير مهيّأ - ليس خطأً بل حالة تشغيل مشروعة قبل النشر."""


class BaseBackend:

    name = "base"

    def check_ready(self):
        """يرفع NotConfigured إن لم يكن جاهزًا. يُستدعى مرة قبل الدفعة."""
        return True

    def send(self, token, notification):
        raise NotImplementedError
