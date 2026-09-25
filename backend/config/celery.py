import os

from celery import Celery


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("taxi_backend")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

from config.observability.celery_hooks import install
install()