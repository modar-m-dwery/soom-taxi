"""
أماكن الإعلانات — مطفأة افتراضًا (ميزة `ads` في الكتالوج) حتّى يكبر التطبيق.

إعلانٌ = صورة، ووجهة (رابط https أو خدمة داخل التطبيق)، ومكان ظهور، ومدّة،
ومدن. الظهور والنقر يُعدّان ليُعرف ما يستحقّ ثمنه.
"""

import os

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import F

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 1024 * 1024  # ميغابايت: شبكةٌ ضعيفة لا تحمّل إعلانًا أثقل


def validate_ad_image(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError("الصورة jpg أو png أو webp فقط.")
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError("الصورة أكبر من ميغابايت — صغّرها.")


class Placement(models.TextChoices):
    CUSTOMER_HOME = "customer_home", "رئيسية الزبون (شريط أعلى الخدمات)"
    TRIP_FINISHED = "trip_finished", "شاشة انتهاء الرحلة"
    DRIVER_HOME = "driver_home", "رئيسية السائق"


class Ad(models.Model):
    title = models.CharField(max_length=80, help_text="يظهر نصًّا بديلًا وفي التقارير.")
    image = models.FileField(upload_to="ads/%Y/%m/", validators=[validate_ad_image])
    placement = models.CharField(max_length=20, choices=Placement.choices)
    link_url = models.CharField(
        max_length=300, blank=True,
        help_text="رابط https يفتح خارج التطبيق عند اللمس. فارغ = بلا رابط.",
    )
    service_code = models.CharField(
        max_length=40, blank=True,
        help_text="أو خدمة داخل التطبيق (مثال: published_trips) تُفتح عند اللمس.",
    )
    areas = models.ManyToManyField(
        "locations.ServiceArea", blank=True, related_name="ads",
        help_text="فارغ = كلّ المدن.",
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=100, help_text="الأصغر أوّلًا.")
    is_active = models.BooleanField(default=True)
    impressions = models.PositiveIntegerField(default=0, editable=False)
    clicks = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "-created_at"]
        verbose_name = "إعلان"
        verbose_name_plural = "الإعلانات"

    def __str__(self):
        return self.title

    def clean(self):
        if self.link_url:
            URLValidator(schemes=["https"])(self.link_url)
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "النهاية قبل البداية."})

    @property
    def ctr(self):
        return round(self.clicks * 100 / self.impressions, 1) if self.impressions else 0.0

    def count(self, kind):
        """عدٌّ في القاعدة لا في الذاكرة: جهازان يعرضان الإعلان معًا لا يضيع أحدهما."""
        field = "clicks" if kind == "click" else "impressions"
        Ad.objects.filter(pk=self.pk).update(**{field: F(field) + 1})
