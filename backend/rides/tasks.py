# -*- coding: utf-8 -*-
"""مهامّ الطلبات الدورية."""

from celery import shared_task


@shared_task
def materialize_ride_subscriptions():
    """
    اشتراكات الصباح: كلّ خمس دقائق يُنشأ الطلب المجدول لمن حان تحضيره
    (قبل موعده بـ lead_minutes). الإنشاء متكافئ: يومٌ واحد = طلبٌ واحد.
    """
    from rides.services.subscription import SubscriptionService

    return SubscriptionService.materialize_due()
