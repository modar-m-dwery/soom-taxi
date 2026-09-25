"""
مصادقة توكن تُعلن هوية الفاعل لحظة معرفتها.

المشكلة
-------
`RequestContextMiddleware` يضبط `actor` **بعد** تنفيذ الـview، لأنّ
مصادقة DRF تجري داخل الـview لا في وسيط. وهذا كافٍ لسطر ملخّص الطلب،
لكنّه متأخّر جدًّا لسجلّ التدقيق: كلّ انتقال حالة يقع أثناء الـview،
أي حين يكون `actor` فارغًا — فتُكتب الانتقالات كلّها باسم "system"
وتضيع نسبة الفعل إلى فاعله، وهي كلّ الغرض من السجلّ.

الحلّ
-----
نضبط السياق في اللحظة الوحيدة التي تُعرف فيها الهوية فعلًا: نجاح
المصادقة. يكفي أن تكون هذه هي `DEFAULT_AUTHENTICATION_CLASSES`.

لا تُغيّر هذه الفئة سلوك المصادقة نفسه بأيّ شكل — ترث كلّ شيء وتضيف
سطرين. أيّ منطق تحقّق هنا كان سيكون خطأً معماريًّا.
"""
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from config.observability.context import set_actor


class ContextTokenAuthentication(TokenAuthentication):
    """`TokenAuthentication` القياسية، مع تسمية الفاعل في سياق الحادثة."""

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is not None:
            from config.security import token_expired

            user, token = result
            if token_expired(token):
                # يُحذف فلا يُجرَّب ثانيةً؛ التطبيق يعود لشاشة الدخول عند 401.
                token.delete()
                raise AuthenticationFailed("انتهت صلاحية الجلسة. سجّل الدخول من جديد.")
            try:
                set_actor(f"user:{getattr(user, 'phone', user.pk)}")
            except Exception:  # noqa: BLE001 — السياق لا يُسقط المصادقة
                pass

        return result
