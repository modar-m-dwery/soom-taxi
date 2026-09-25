from django.db import models

from catalog.registry import ServiceStatus


class Service(models.Model):
    """حالة خدمةٍ عرّفتها الشيفرة (catalog/registry.py). الرمز لا يُحرَّر."""

    code = models.SlugField(max_length=40, unique=True, editable=False)
    name = models.CharField(max_length=60)
    name_en = models.CharField(max_length=60, blank=True)
    icon = models.CharField(
        max_length=40, blank=True,
        help_text="اسم أيقونة Material (مثال: local_taxi). يرسمها التطبيق.",
    )
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20, choices=ServiceStatus.CHOICES, default=ServiceStatus.ACTIVE,
    )
    sort_order = models.PositiveSmallIntegerField(default=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "خدمة"
        verbose_name_plural = "الخدمات"

    def __str__(self):
        return f"{self.name} ({self.code})"


class ServiceAreaOverride(models.Model):
    """حالةٌ مختلفة لخدمة في مدينة بعينها — تغلب حالتها العامّة."""

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="area_overrides")
    area = models.ForeignKey(
        "locations.ServiceArea", on_delete=models.CASCADE, related_name="service_overrides",
    )
    status = models.CharField(max_length=20, choices=ServiceStatus.CHOICES)

    class Meta:
        unique_together = [("service", "area")]
        verbose_name = "استثناء مدينة"
        verbose_name_plural = "استثناءات المدن"


class FeatureFlag(models.Model):
    key = models.SlugField(max_length=40, unique=True, editable=False)
    description = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = "ميزة"
        verbose_name_plural = "الميزات"

    def __str__(self):
        return self.key


class FeatureFlagAreaOverride(models.Model):
    flag = models.ForeignKey(FeatureFlag, on_delete=models.CASCADE, related_name="area_overrides")
    area = models.ForeignKey(
        "locations.ServiceArea", on_delete=models.CASCADE, related_name="feature_overrides",
    )
    enabled = models.BooleanField()

    class Meta:
        unique_together = [("flag", "area")]
        verbose_name = "استثناء مدينة"
        verbose_name_plural = "استثناءات المدن"
