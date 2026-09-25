# -*- coding: utf-8 -*-
"""
توليد طلبات «اشتراك الصباح».

تُنادى من مهمّة Celery كلّ خمس دقائق. لكلّ اشتراك فعّال: إن كان اليوم من
أيامه، والموعد بعد أقلّ من `lead_minutes`، ولم يُنشأ له طلب اليوم — يُنشأ
طلبٌ مجدول عاديّ عبر `RideRequestService.create_ride_request` نفسها، فيمرّ
بكلّ تحقّقاتها (المنطقة، الفئة، المقاعد، طلبٌ قائم واحد).

التوقيت المحلّيّ ثابتٌ للساحل السوريّ (Asia/Damascus): الاشتراك يقول
«7:30» بتوقيت الزبون لا بتوقيت الخادم (UTC).
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from rides.models import RideSubscription
from rides.services.ride_request import (
    RideRequestService,
    RideRequestValidationError,
)

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Damascus")


class SubscriptionService:

    @staticmethod
    def next_occurrence(subscription, now=None):
        """أقرب موعدٍ قادم (اليوم إن لم يمضِ، وإلّا أوّل يومٍ فعّال بعده)."""
        now = now or timezone.now()
        local_now = now.astimezone(LOCAL_TZ)
        for offset in range(0, 8):
            day = (local_now + timedelta(days=offset)).date()
            if not subscription.runs_on(day.weekday()):
                continue
            candidate = datetime.combine(day, subscription.departure_time, tzinfo=LOCAL_TZ)
            if candidate > local_now:
                return candidate.astimezone(dt_timezone.utc)
        return None

    @classmethod
    def materialize_due(cls, now=None):
        """يُنشئ طلبات الاشتراكات التي حان تحضيرها. يعيد عدد ما أُنشئ."""
        now = now or timezone.now()
        created = 0
        for subscription in RideSubscription.objects.filter(is_active=True).select_related("customer"):
            occurrence = cls.next_occurrence(subscription, now)
            if occurrence is None:
                continue
            lead = timedelta(minutes=subscription.lead_minutes)
            if occurrence - now > lead:
                continue
            local_day = occurrence.astimezone(LOCAL_TZ).date()
            if subscription.last_materialized_on == local_day:
                continue
            if cls._materialize(subscription, occurrence, local_day):
                created += 1
        return created

    @classmethod
    def _materialize(cls, subscription, occurrence, local_day):
        try:
            with transaction.atomic():
                locked = RideSubscription.objects.select_for_update().get(pk=subscription.pk)
                if locked.last_materialized_on == local_day or not locked.is_active:
                    return False
                ride = RideRequestService.create_ride_request(
                    customer=locked.customer,
                    pickup=locked.pickup,
                    destination=locked.destination,
                    mode=locked.mode,
                    passenger_count=locked.passenger_count,
                    scheduled_at=occurrence,
                    requested_vehicle_type=locked.requested_vehicle_type,
                )
                ride.subscription = locked
                ride.save(update_fields=["subscription"])
                locked.last_materialized_on = local_day
                locked.save(update_fields=["last_materialized_on"])
        except RideRequestValidationError as exc:
            # طلبٌ قائم، أو منطقة مغلقة… لا يوقف بقيّة الاشتراكات، ويُعاد في
            # الدورة التالية ما دام الموعد لم يمضِ.
            logger.warning("subscription %s: لم يُنشأ الطلب — %s", subscription.pk, exc)
            return False
        logger.info("subscription %s: طلب مجدول #%s لموعد %s", subscription.pk, ride.pk, occurrence)
        return True
