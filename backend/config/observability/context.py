"""
معرّف الحادثة (request_id) وسياقها، محمولًا عبر contextvars.

المشكلة التي يحلّها: حادثة واحدة عندك تمرّ بأربع طبقات — طلب REST، ثم
transaction.on_commit، ثم EventBus، ثم مهمّة Celery، ثم FCM. وحين يشتكي
سائق أن رحلته لم تُغلق، لا توجد اليوم أي وسيلة لجمع أسطر السجلّ التي
تخصّ حادثته من بين آلاف الأسطر.

معرّف واحد يُولَّد عند أول دخول ويُحمَل إلى كل ما ينبثق عنه يجعل الجواب
أمر بحث واحدًا:

    findstr "a3f21c9e" logs\\errors.log

contextvars لا threading.local: الأولى تعمل مع async (الـConsumers) ومع
الخيوط معًا، والثانية تضيع عند أول await.
"""
import contextvars
import uuid


_request_id = contextvars.ContextVar("request_id", default="")
_actor = contextvars.ContextVar("actor", default="")


def new_id():
    """معرّف قصير. اثنتا عشرة خانة كافية للتمييز داخل نافذة تشخيص."""
    return uuid.uuid4().hex[:12]


def get_request_id():
    return _request_id.get()


def set_request_id(value):
    """يرجّع الرمز المميّز للاستعادة (مهم في الـConsumers الطويلة العمر)."""
    return _request_id.set(value or new_id())


def reset_request_id(token):
    try:
        _request_id.reset(token)
    except ValueError:
        # سياق مختلف (خيط آخر) — ليس خطأ يستحق الإسقاط
        pass


# الطلب الجاري — لاستنتاج الفاعل كسولًا. راجع resolve_actor أدناه.
_request = contextvars.ContextVar("request", default=None)


def get_actor():
    return _actor.get()


def set_actor(value):
    return _actor.set(value or "")


def set_request(request):
    return _request.set(request)


def reset_request(token):
    try:
        _request.reset(token)
    except (ValueError, LookupError):
        pass


def resolve_actor():
    """
    مَن يفعل هذا — يُحلّ عند الحاجة لا عند بداية الطلب.

    لماذا كسولًا؟ لأنّ مصادقة DRF تجري **داخل** الـview. ضبط الفاعل في
    وسيط قبل ذلك يعطي "" دائمًا، وضبطه بعده متأخّر جدًّا لسجلّ التدقيق:
    كلّ انتقال حالة يقع أثناء الـview، فتُنسب الانتقالات كلّها إلى
    "system" وتضيع نسبة الفعل إلى فاعله — وهي كلّ الغرض من السجلّ.

    ولماذا من الطلب لا من صنف مصادقة؟ لأنّ معظم الـviews هنا تُعلن
    `authentication_classes` صراحةً فتتجاوز الافتراضي. لكنّ DRF يكتب
    المستخدم على الطلب الأصلي (setter الخاصّ بـ`Request.user` يضبط
    `self._request.user` أيضًا)، فقراءته من هنا تعمل مع كلّ view مهما أعلن.
    """
    explicit = _actor.get()
    if explicit:
        return explicit

    request = _request.get()
    if request is None:
        return ""

    try:
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return ""
        return f"user:{getattr(user, 'phone', user.pk)}"
    except Exception:  # noqa: BLE001
        return ""


def current_user():
    """كائن المستخدم المصادَق للطلب الجاري، أو None."""
    request = _request.get()
    if request is None:
        return None
    try:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
    except Exception:  # noqa: BLE001
        pass
    return None


def bind(request_id=None, actor=None, request=None):
    """
    يضبط الاثنين معًا ويرجّع دالة إلغاء. للاستعمال في المهامّ والـConsumers:

        unbind = bind(request_id=rid, actor=f"driver:{driver_id}")
        try:
            ...
        finally:
            unbind()
    """
    rid_token = set_request_id(request_id or new_id())
    actor_token = set_actor(actor)

    # الطلب يُربط ويُفكّ مع البقيّة. تركه معلّقًا بعد انتهاء الطلب كان
    # يجعل العمل الخلفي (ومهامّ الاختبارات) ينسب أفعاله إلى مستخدم طلبٍ
    # سابق — وقد يكون حسابًا حُذف، فينهار الإدراج على مفتاح أجنبي.
    request_token = _request.set(request)

    def unbind():
        reset_request_id(rid_token)
        try:
            _actor.reset(actor_token)
        except (ValueError, LookupError):
            pass
        reset_request(request_token)

    return unbind


def snapshot():
    """الحالة الحالية — لتمريرها إلى مهمّة Celery أو خيط آخر."""
    return {"request_id": get_request_id(), "actor": get_actor()}
