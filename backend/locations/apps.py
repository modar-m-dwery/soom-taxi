from django.apps import AppConfig


class LocationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'locations'
    verbose_name = "Locations & Service Areas"

    def ready(self):
        from django.db.models.signals import post_save, post_delete

        from locations.models import ServiceArea
        from locations.services import LocationService

        def _invalidate(*args, **kwargs):
            # فوري: أي تعديل من الإدارة (تغيير دقة الخلايا لمدينة، تفعيل/
            # تعطيل، إضافة مدينة جديدة) ينعكس على أول نبضة GPS تالية،
            # دون انتظار انتهاء CACHE_TTL_SECONDS الاحتياطي.
            LocationService.invalidate_cache()

        post_save.connect(_invalidate, sender=ServiceArea, dispatch_uid="service_area_cache_invalidate_save")
        post_delete.connect(_invalidate, sender=ServiceArea, dispatch_uid="service_area_cache_invalidate_delete")
