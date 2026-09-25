from django.apps import AppConfig


class OpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ops'
    verbose_name = "أدوات التشغيل"

    def ready(self):
        # ربط التقاط انتقالات الحالة. هنا لا في مستوى الوحدة: النماذج
        # لا تكون جاهزة قبل اكتمال تحميل التطبيقات.
        from ops import audit_signals

        audit_signals.connect()

