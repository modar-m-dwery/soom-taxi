"""
تسليم وثائق السائقين خلف مصادقة.

الثغرة التي يسدّها هذا
----------------------
`docker/nginx.conf` كان يخدم `/media/` مباشرةً من القرص بلا أيّ فحص،
و`config/urls.py` يفعل الشيء نفسه في وضع التطوير. الملفّات هناك هي
صور الهويّات الشخصية ورخص القيادة ودفاتر المركبات ووثائق التأمين
لكلّ سائق في المنصّة — ومساراتها متوقّعة لأنّ التخزين يحتفظ باسم
الملفّ الذي أرسله العميل.

أي أنّ أخطر بيانات في النظام كانت الوحيدة التي لا تحرسها مصادقة.

كيف يُخدَم الآن
---------------
`X-Accel-Redirect`: جانغو يفحص الصلاحية ثمّ يردّ بترويسة تُخبر Nginx
أن يخدم الملفّ من مسار **داخلي** (`internal`) لا يصله طلب خارجي أبدًا.
فيبقى الفحص في بايثون وتبقى الكفاءة في Nginx — لا يمرّ محتوى الملفّ
عبر عملية جانغو إطلاقًا.

وبلا Nginx (التطوير) نخدم الملفّ مباشرةً من جانغو، وهو مقبول لأنّ عدد
الطلبات صغير والملفّات محدودة.

مَن يرى ماذا
------------
  • السائق: وثائقه هو وحدها
  • المشغّل (is_staff): كلّ الوثائق — مراجعتها وظيفته
  • أيّ أحد آخر: 404 لا 403، فلا تكشف الاستجابةُ وجودَ الملفّ
"""
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse

from drf_spectacular.utils import extend_schema

# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from drivers.models import DriverDocument


class DriverDocumentFileView(APIView):
    """`GET /api/v1/drivers/documents/{document_id}/file/`"""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Drivers"],
        operation_id="driver_document_file",
        summary="Download a driver document",
        description=(
            "Serves the file behind an authorization check. A driver may "
            "read only their own documents; staff may read any. Anyone "
            "else receives 404 — not 403 — so the response does not "
            "confirm that the document exists."
        ),
        responses={200: bytes, 404: None},
    )
    def get(self, request, document_id):
        document = (
            DriverDocument.objects
            .select_related("driver", "driver__user")
            .filter(pk=document_id)
            .first()
        )

        if document is None or not document.file:
            raise Http404

        if not self._may_read(request.user, document):
            # 404 لا 403: الردّ المختلف يؤكّد وجود الوثيقة لمن يبحث.
            raise Http404

        return self._serve(document)

    # -----------------------------------------------------------

    @staticmethod
    def _may_read(user, document):
        if getattr(user, "is_staff", False):
            return True

        profile = getattr(user, "driver_profile", None)
        return profile is not None and profile.pk == document.driver_id

    @staticmethod
    def _serve(document):
        internal_prefix = getattr(settings, "MEDIA_INTERNAL_PREFIX", "")

        if internal_prefix:
            # Nginx يتولّى الإرسال من مسار داخلي محجوب عن الخارج.
            response = HttpResponse(status=200)
            response["X-Accel-Redirect"] = (
                f"{internal_prefix.rstrip('/')}/{document.file.name}"
            )
            response["Content-Type"] = ""  # يستنتجه Nginx
            response["Content-Disposition"] = (
                f'inline; filename="{os.path.basename(document.file.name)}"'
            )
            return response

        return FileResponse(document.file.open("rb"))
