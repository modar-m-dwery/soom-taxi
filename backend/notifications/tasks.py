from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def dispatch_notification(self, notification_id):
    """
    إرسال إشعار واحد.

    لا نعيد المحاولة على إشعار منقضٍ: مهلته هي مهلة الشيء الذي يخبر عنه،
    وإعادة محاولته بعد انقضائه إصرارٌ على إيصال خبر لم يعد صحيحًا.
    """
    from notifications.models import NotificationStatus
    from notifications.services.dispatch import NotificationService

    notification = NotificationService.dispatch(notification_id)

    if notification is None:
        return "not found"

    if (
        notification.status == NotificationStatus.PENDING
        and not notification.is_expired
    ):
        raise self.retry(exc=Exception(notification.last_error or "pending"))

    return notification.status


@shared_task
def expire_stale_notifications():
    from notifications.services.dispatch import NotificationService

    count = NotificationService.expire_stale()

    return f"expired {count} notifications"


@shared_task
def retry_pending_notifications():
    from notifications.services.dispatch import NotificationService

    count = NotificationService.retry_pending()

    return f"retried {count} notifications"


@shared_task
def cleanup_old_notifications(days=30):
    """
    الصندوق الصادر ليس أرشيفًا. ما مضى عليه شهر لا يُقرأ ولا يُدقَّق.
    """
    from datetime import timedelta

    from django.utils import timezone

    from notifications.models import Notification

    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(created_at__lt=cutoff).delete()

    return f"deleted {deleted} notifications"
