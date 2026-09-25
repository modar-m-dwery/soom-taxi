from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from trips.models import Trip, TripLocation, TripStatus


# §17 في الوثيقة: "الموقع الخام لا يجب أن يبقى إلى الأبد."
RETENTION_DAYS = getattr(settings, "TRIP_LOCATION_RETENTION_DAYS", 30)
CLEANUP_BATCH = 5000


@shared_task
def cleanup_old_trip_locations():
    """
    يحذف نقاط مسار الرحلات المنتهية بعد مدة الاحتفاظ.

    TripCompletionRecord لا يُمَس: هو الإثبات الدائم بأن الرحلة وقعت
    بأرقامها ولحظاتها. ما يُحذف هو المسار التفصيلي فقط — وهو ما يتضخّم.
    """
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)

    trip_ids = list(
        Trip.objects
        .filter(
            status__in=[TripStatus.COMPLETED, TripStatus.CANCELLED],
            completed_at__lt=cutoff,
        )
        .values_list("id", flat=True)[:200]
    )

    if not trip_ids:
        return "no trips past retention"

    ids = list(
        TripLocation.objects
        .filter(trip_id__in=trip_ids)
        .values_list("id", flat=True)[:CLEANUP_BATCH]
    )

    if not ids:
        return f"{len(trip_ids)} trips already clean"

    deleted, _ = TripLocation.objects.filter(id__in=ids).delete()

    return f"deleted {deleted} location points from {len(trip_ids)} old trips"
