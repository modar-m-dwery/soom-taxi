"""
معالج استثناءات موحّد لـDRF.

يحلّ ثلاث مشاكل وجدها التدقيق:

  1. **شكلان مختلفان للخطأ 400** على النقطة الواحدة: خطأ الخدمة يعطي
     {"detail": "..."} وخطأ التحقّق يعطي {"pickup_lat": ["..."]}. أي
     كود catch مبني على error.detail ينهار صامتًا على الثاني.

  2. **لا رمز خطأ**. التطبيق لا يملك إلا مقارنة نصوص عربية وإنجليزية
     مختلطة.

  3. **استثناء غير متوقّع يصير 500 بلا سطر سجلّ مفيد** — أو أسوأ، يُبتلع
     في الخدمة ويعود 400.

الشكل الخارج، واحدًا لكل خطأ في المشروع:

    {
      "detail":     "نصّ للعرض على المستخدم",
      "code":       "invitation.expired",
      "request_id": "a3f21c9e77b2",
      "fields":     {"pickup_lat": ["..."]}      // عند أخطاء التحقّق فقط
    }

`detail` يبقى كما كان — فلا ينكسر أي عميل قائم. الجديد يُضاف بجانبه.
"""
import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.db import DatabaseError
from django.http import Http404
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from config.observability.context import get_request_id
from config.observability.errors import AppError, resolve

logger = logging.getLogger("api")


def api_exception_handler(exc, context):
    view = context.get("view")
    view_name = type(view).__name__ if view else "?"

    response = drf_exception_handler(exc, context)

    # -----------------------------------------------------------------
    # الحالة الأولى: استثناء يعرفه DRF (تحقّق، صلاحية، 404، throttle)
    # -----------------------------------------------------------------
    if response is not None:
        return _shape(response, exc, view_name)

    # -----------------------------------------------------------------
    # الحالة الثانية: أخطاء أعمالنا — AppError أو استثناءات الخدمات
    # -----------------------------------------------------------------
    if isinstance(exc, AppError):
        return _business(exc, exc.code, exc.status_code, view_name, exc.fields)

    if isinstance(exc, (PermissionDenied,)):
        return _business(exc, "forbidden", 403, view_name)

    if isinstance(exc, Http404):
        return _business(exc, "not_found", 404, view_name)

    if isinstance(exc, DjangoValidationError):
        return _business(exc, "invalid", 400, view_name)

    if _is_service_error(exc):
        code, status_code = resolve(exc)
        return _business(exc, code, status_code, view_name)

    # -----------------------------------------------------------------
    # الحالة الثالثة: ما لم نتوقّعه. يُسجَّل كاملًا ويعود 500 عامًّا.
    # -----------------------------------------------------------------
    #
    # لا نُظهر str(exc) للمستخدم هنا: نصّ AttributeError أو IntegrityError
    # لا يعني له شيئًا، وقد يكشف بنية داخلية. المعرّف هو الجسر بينه وبين
    # السجلّ الذي يحمل القصّة كاملة.

    is_db = isinstance(exc, DatabaseError)

    logger.exception(
        "unhandled exception in %s: %s",
        view_name, type(exc).__name__,
        extra={
            "event": "api.unhandled",
            "error_code": "internal_error",
        },
    )

    return Response(
        {
            "detail": (
                "تعذّر إتمام العملية. حاول مرة أخرى، وإن تكرّر الأمر أبلغ "
                "الدعم بهذا الرقم."
            ),
            "code": "database_error" if is_db else "internal_error",
            "request_id": get_request_id(),
        },
        status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ---------------------------------------------------------------------


def _is_service_error(exc):
    """
    استثناءات خدماتنا كلّها ترث Exception مباشرة وتنتهي بـError.

    الفحص بالاسم لا بالنوع مقصود: استيراد استثناءات كل التطبيقات هنا
    يخلق دورة استيراد (config يستورد matching الذي يستورد config).
    """
    from config.observability.errors import EXCEPTION_CODES

    return type(exc).__name__ in EXCEPTION_CODES


def _business(exc, code, status_code, view_name, fields=None):
    """خطأ متوقّع: يُسجَّل سطرًا واحدًا بلا traceback — ليس عطلًا."""
    logger.info(
        "%s rejected: %s",
        view_name, code,
        extra={"event": "api.rejected", "error_code": code,
               "status_code": status_code},
    )

    body = {
        "detail": str(exc),
        "code": code,
        "request_id": get_request_id(),
    }

    if fields:
        body["fields"] = fields

    return Response(body, status=status_code)


def _shape(response, exc, view_name):
    """
    يوحّد ردود DRF القياسية.

    خطأ التحقّق يأتي بشكل {"pickup_lat": ["..."]}؛ نُبقيه كما هو تحت
    `fields` ونضيف فوقه `detail` واحدًا قابلًا للعرض. فيصير عند العميل
    مسار قراءة واحد لكل الأخطاء، ومسار ثانٍ اختياري لإبراز الحقل الخاطئ
    في النموذج.
    """
    data = response.data
    code = getattr(exc, "default_code", "") or "error"
    fields = None
    detail = ""

    if isinstance(data, dict):
        if "detail" in data and len(data) == 1:
            detail = str(data["detail"])
        else:
            fields = data
            detail = _first_message(data)
    elif isinstance(data, list):
        fields = {"non_field_errors": data}
        detail = _first_message({"non_field_errors": data})
    else:
        detail = str(data)

    if response.status_code == 400 and fields:
        code = "validation_error"
    elif response.status_code == 401:
        code = "unauthenticated"
    elif response.status_code == 403:
        code = "forbidden"
    elif response.status_code == 404:
        code = "not_found"
    elif response.status_code == 429:
        code = "throttled"

    body = {
        "detail": detail,
        "code": code,
        "request_id": get_request_id(),
    }

    if fields:
        body["fields"] = fields

    if response.status_code >= 400:
        logger.info(
            "%s rejected: %s",
            view_name, code,
            extra={"event": "api.rejected", "error_code": code,
                   "status_code": response.status_code},
        )

    response.data = body
    return response


def _first_message(data):
    """أول رسالة قابلة للعرض من قاموس أخطاء التحقّق."""
    for key, value in data.items():
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
    return "البيانات المرسلة غير صالحة."
