"""كلّ حفظ أو حذف في جداول الكتالوج يمسح الكاش — الأثر فوريّ لا بعد خمس دقائق."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import FeatureFlag, FeatureFlagAreaOverride, Service, ServiceAreaOverride
from catalog.services import invalidate


@receiver([post_save, post_delete], sender=Service)
@receiver([post_save, post_delete], sender=ServiceAreaOverride)
@receiver([post_save, post_delete], sender=FeatureFlag)
@receiver([post_save, post_delete], sender=FeatureFlagAreaOverride)
def _invalidate(**kwargs):
    invalidate()
