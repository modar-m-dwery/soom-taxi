from django.core.exceptions import ValidationError
from django.db import models

from users.models import DriverProfile


class VehicleType(models.TextChoices):
    """
    الفئات الأربع الأصلية — بقيت هنا لغرضين فقط: زرع الافتراضات في أوّل
    ترحيل، وإعطاء الاختبارات والبذور رموزًا ثابتة تكتبها.

    لم تعد مصدر الحقيقة. الفئات المتاحة فعلًا صفوفٌ في VehicleCategory
    يضيفها المشغّل من لوحة الإدارة، ولا شيء في المنطق يتحقّق من هذا الصنف.
    لا تُضِف عضوًا هنا لتضيف فئة — أضف صفًّا.
    """
    SEDAN = "sedan", "Sedan"
    HATCHBACK = "hatchback", "Hatchback"
    SUV = "suv", "SUV"
    VAN = "van", "Van"


class VehicleCategory(models.Model):
    """
    فئة المركبة كصفّ لا كعضو في enum.

    لماذا كان الـenum خطأً: إضافة «تكتك» أو «ميكروباص» أو «سيارة نسائية»
    كانت تعني تعديل شيفرة، وترحيلًا، ونشرًا، وإصدارًا جديدًا من التطبيق —
    لقرار تجاريّ بحت لا تقنيّ. والمشغّل الذي يريد تجربة فئة أسبوعًا ثمّ
    إلغاءها لا يستطيع.

    ثلاثة قرارات في هذا النموذج تستحقّ التوضيح:

    ١. `code` هو المفتاح الأساسي، لا رقم متسلسل. الرمز النصّي هو ما يظهر في
       الـAPI ("sedan")، وهو ما يخزّنه التطبيق ويرسله. جعله المفتاح يعني أنّ
       عمود Vehicle.type يبقى varchar كما كان — فلا ينكسر عميل واحد، ولا
       يتغيّر شكل ردّ واحد — ومع ذلك نكسب تكامل مرجعيّ حقيقيًّا.

    ٢. `code` غير قابل للتعديل بعد الإنشاء. لأنّه عقدٌ منشور على أجهزة لا
       نملكها: تغييره يجعل تطبيقًا مثبَّتًا يرسل رمزًا لم يعد موجودًا. أخفِ
       الفئة بـ is_active بدل أن تعيد تسميتها.

    ٣. الحذف محميّ بـPROTECT. مركبةٌ مسجَّلة بفئة محذوفة هي صفٌّ يتيم، ورحلةٌ
       طلبتها هي سجلّ لا يمكن قراءته بعد سنة. الإخفاء يفعل ما يريده المشغّل
       فعلًا بلا هذا الثمن.
    """

    code = models.CharField(
        max_length=20,
        primary_key=True,
        help_text=(
            "الرمز الثابت في الـAPI (حروف لاتينية صغيرة وشرطات سفلية). "
            "لا يمكن تغييره بعد الإنشاء — أخفِ الفئة بدل إعادة تسميتها."
        ),
    )

    name = models.CharField(
        max_length=60,
        help_text="الاسم المعروض في التطبيق.",
    )

    name_en = models.CharField(
        max_length=60,
        blank=True,
        default="",
        help_text="الاسم الإنجليزي — اختياري.",
    )

    seats = models.PositiveSmallIntegerField(
        default=4,
        help_text="عدد الركّاب المعتاد لهذه الفئة (بلا السائق).",
    )

    fare_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text=(
            "معامل السعر مقارنةً بالفئة الأساسية. 1.00 يعني بلا فرق. "
            "لا يُطبَّق تلقائيًّا اليوم — محجوز لتسعير الفئات."
        ),
    )

    # فارغة = متاحة في كلّ المدن. هذا هو الافتراض المقصود: المشغّل الذي
    # يضيف فئة يريدها في الغالب لكلّ مدنه، وإجباره على تحديدها واحدةً واحدةً
    # يُنتج فئةً لا تظهر لأحد ولا يعرف لماذا.
    areas = models.ManyToManyField(
        "locations.ServiceArea",
        blank=True,
        related_name="vehicle_categories",
        help_text=(
            "المدن التي تتوفّر فيها هذه الفئة. "
            "اتركها فارغة لتتوفّر في كلّ المدن."
        ),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="إخفاء الفئة من التطبيق بلا حذفها ولا مسّ مركبات مسجَّلة.",
    )

    sort_order = models.PositiveSmallIntegerField(
        default=100,
        help_text="ترتيب العرض في التطبيق — الأصغر أوّلًا.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "فئة مركبة"
        verbose_name_plural = "فئات المركبات"

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        errors = {}

        code = (self.code or "").strip()

        if not code:
            errors["code"] = "الرمز مطلوب."
        elif not code.replace("_", "").isalnum() or not code.isascii():
            errors["code"] = (
                "الرمز يقبل الحروف اللاتينية والأرقام والشرطة السفلية فقط — "
                "لأنّه يظهر في الـURL وفي أجسام الطلبات."
            )
        elif code != code.lower():
            errors["code"] = "الرمز بحروف صغيرة حصرًا."

        if self.seats is not None and not (1 <= self.seats <= 20):
            errors["seats"] = "عدد المقاعد بين 1 و20."

        if errors:
            raise ValidationError(errors)

    # -----------------------------------------------------------------
    # القراءة
    # -----------------------------------------------------------------

    @classmethod
    def active_for_area(cls, area=None):
        """
        الفئات المتاحة في منطقة بعينها: الفئات العامّة (بلا مدن محدّدة) زائد
        الفئات المخصّصة لهذه المدينة.

        النتيجة قائمة لا queryset لأنّ الاتّحاد يقع في بايثون: فئات المنصّة
        وحدات لا آلاف، والاستعلامان أرخص من UNION بشرط M2M.
        """
        queryset = cls.objects.filter(is_active=True).prefetch_related("areas")

        if area is None:
            return list(queryset)

        return [
            category
            for category in queryset
            if not category.areas.exists()
            or area.id in {a.id for a in category.areas.all()}
        ]

    @classmethod
    def active_codes(cls, area=None):
        return [category.code for category in cls.active_for_area(area)]


class Vehicle(models.Model):
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.CASCADE,
        related_name="vehicles",
    )

    # مفتاح أجنبي يخزّن الرمز النصّي نفسه في العمود نفسه باسمه السابق.
    # النتيجة: التكامل المرجعي مضمون، وشكل الـAPI لم يتغيّر بحرف — ما زال
    # vehicle["type"] == "sedan"، وما زال filter(type="sedan") يعمل.
    type = models.ForeignKey(
        VehicleCategory,
        db_column="type",
        on_delete=models.PROTECT,
        related_name="vehicles",
    )

    make = models.CharField(
        max_length=100,
    )

    model = models.CharField(
        max_length=100,
    )

    year = models.PositiveSmallIntegerField()

    color = models.CharField(
        max_length=50,
    )

    plate_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
    )

    seats = models.PositiveSmallIntegerField()

    active = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["driver", "active"],
            ),
        ]

    def __str__(self):
        return (
            f"{self.make} {self.model} "
            f"({self.plate_number})"
        )
