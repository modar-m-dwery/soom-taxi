"""
ربط الكشف الآنيّ بأحداث المنصّة دون تعديل خدماتها: إنشاء سجلّ إلغاء، أو
شكوى، أو سجلّ إتمام رحلة. التنفيذ بعد تثبيت المعاملة — الإشارة لا تُسجَّل
لحدثٍ تراجعت عنه القاعدة.
"""

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from feedback.models import Complaint
from integrity.services import hooks
from trips.models import CancellationRecord, TripCompletionRecord


@receiver(post_save, sender=CancellationRecord, dispatch_uid="integrity_on_cancellation")
def _on_cancellation(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: hooks.on_cancellation(instance))


@receiver(post_save, sender=Complaint, dispatch_uid="integrity_on_complaint")
def _on_complaint(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: hooks.on_complaint(instance))


@receiver(post_save, sender=TripCompletionRecord, dispatch_uid="integrity_on_completion")
def _on_completion(sender, instance, created, **kwargs):
    if created:
        trip = instance.trip
        transaction.on_commit(lambda: hooks.on_trip_completed(trip))
