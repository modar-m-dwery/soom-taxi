"""
ترقيم بالمؤشّر (cursor) للنقاط التي تنمو بلا حدّ.

**لماذا مساعد صريح بدل `DEFAULT_PAGINATION_CLASS`؟**

لأن الإعداد العام في DRF يعمل مع الأصناف العامّة (`ListAPIView`,
`ViewSet`) فقط، ولا يعمل مع `APIView` — وكل واجهات هذا المشروع
`APIView`. ضبط الإعداد العام كان سيبدو صحيحًا ولا يفعل شيئًا إطلاقًا،
وهو أسوأ أنواع الأخطاء: إعداد موجود يوحي بأن المشكلة حُلّت.

**لماذا المؤشّر لا رقم الصفحة؟**

بيانات هذا النظام تتغيّر أثناء التصفّح: إشعار جديد يصل، رحلة تُضاف.
مع ترقيم الصفحات، وصول عنصر جديد يزيح كل شيء صفحةً فتتكرّر عناصر على
المستخدم أو تُفقد أخرى. المؤشّر يثبّت الموضع على قيمة الصفّ نفسه فلا
يتأثّر بما أُضيف بعده.

**ما لا يُرقَّم عمدًا**

القوائم الحيّة المحدودة أصلًا: مرشّحو المطابقة (محدودون بـ
`MATCHING_NORMAL_DRIVER_LIMIT`)، عروض رحلة، دعوات معلّقة (محدودة
بـ`invitation_max_parallel`)، السيارات القريبة، أوسمة التقييم، مركبات
السائق. ترقيم قائمة سيارات على خريطة حيّة ليس تحسينًا بل خطأ: التطبيق
يحتاجها كلّها دفعةً واحدة ليرسمها.

القاعدة: **يُرقَّم ما ينمو مع الزمن، ولا يُرقَّم ما يعبّر عن لحظة.**
"""
from rest_framework.pagination import CursorPagination


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class StandardCursorPagination(CursorPagination):
    """
    الشكل الخارج:

        {
          "next":     "https://…?cursor=cD0yMDI2…",   أو null
          "previous": null,
          "results":  [ … ]
        }

    التطبيق يتبع `next` كما هو ولا يبني الرابط بنفسه — هذا هو العقد.
    """

    page_size = DEFAULT_PAGE_SIZE
    max_page_size = MAX_PAGE_SIZE
    page_size_query_param = "page_size"
    cursor_query_param = "cursor"

    #: الأحدث أوّلًا. يجب أن يوافق ترتيب الاستعلام الممرَّر، وإلّا فرضه
    #: DRF وأبطل أي ترتيب آخر بصمت.
    ordering = "-created_at"


def paginate(request, queryset, serializer_class, view=None,
             ordering=None, context=None, page_size=None):
    """
    يرقّم استعلامًا ويعيد `Response` جاهزًا.

    الاستخدام داخل `APIView`:

        return paginate(request, queryset, MySerializer, view=self)

    ملاحظتان تمنعان خطأين شائعين:

      * `ordering` يجب أن يكون حقلًا **فريدًا أو شبه فريد** وغير متغيّر.
        `-created_at` مناسب؛ حقل حالة أو نصّ ليس كذلك — المؤشّر يعتمد
        على ترتيب مستقرّ.
      * يقبل `QuerySet` فقط لا قائمة بايثون. المؤشّر يقصّ في قاعدة
        البيانات، وقائمة جاهزة في الذاكرة لا تقبل ذلك — وتلك النقاط
        تُترك بلا ترقيم عمدًا (راجع رأس الملفّ).
    """
    paginator = StandardCursorPagination()

    if ordering:
        paginator.ordering = ordering

    if page_size:
        paginator.page_size = min(int(page_size), MAX_PAGE_SIZE)

    page = paginator.paginate_queryset(queryset, request, view=view)

    data = serializer_class(page, many=True, context=context or {}).data

    return paginator.get_paginated_response(data)
