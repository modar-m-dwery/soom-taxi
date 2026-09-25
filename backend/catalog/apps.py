from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "الخدمات والميزات"

    def ready(self):
        from django.db.models.signals import post_migrate

        from catalog import signals  # noqa: F401  إبطال الكاش عند الحفظ
        from catalog.sync import sync_definitions

        post_migrate.connect(sync_definitions, sender=self)
