from django.apps import AppConfig


class IntegrityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrity"
    verbose_name = "النزاهة: كشف الغش والتلاعب"

    def ready(self):
        from integrity import signals  # noqa: F401  ربط الإلغاء والشكاوى والإتمام
