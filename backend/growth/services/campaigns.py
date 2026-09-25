"""
إرسال عرض: الجمهور يُحسب لحظة الإرسال، الرصيد يُمنح، والإشعار يصل.

آمنٌ للتكرار: `CampaignRecipient` فريدٌ لكلّ (حملة، مستخدم)، فالضغط مرّتين
أو مهمّةٌ أُعيدت لا تمنح الرصيد مرّتين. والرصيد نفسه `CustomerCredit` القائم:
يُخصم تلقائيًّا عند فتح دفعة الرحلة التالية ويُقيَّد على المنصّة (PROMOTION)
بلا أيّ مسار ماليّ جديد.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from growth.models import Campaign, CampaignRecipient
from growth.services.reports import Reports

logger = logging.getLogger(__name__)


class CampaignService:

    @classmethod
    def preview_count(cls, campaign):
        return len(Reports.audience_user_ids(campaign))

    @classmethod
    def send(cls, campaign):
        """يرسل ويرجع عدد من وصلهم الآن (مَن وصله سابقًا لا يُحسب)."""
        from notifications.models import AppKind
        from notifications.services.dispatch import NotificationService
        from payments.models import CustomerCredit

        user_ids = Reports.audience_user_ids(campaign)
        users = get_user_model().objects.filter(id__in=user_ids, is_active=True)
        app = AppKind.DRIVER if campaign.targets_drivers else AppKind.CUSTOMER
        sent = 0

        for user in users.iterator():
            try:
                with transaction.atomic():
                    recipient = CampaignRecipient.objects.create(campaign=campaign, user=user)
                    if campaign.credit_amount and not campaign.targets_drivers:
                        recipient.credit = CustomerCredit.objects.create(
                            customer=user,
                            amount=campaign.credit_amount,
                            currency=campaign.currency,
                            reason=CustomerCredit.Reason.CAMPAIGN,
                        )
                        recipient.save(update_fields=["credit"])
                    NotificationService.create(
                        user=user,
                        event_type="campaign.offer",
                        title=campaign.title,
                        body=campaign.body,
                        data={
                            "campaign_id": campaign.id,
                            "credit": str(campaign.credit_amount or ""),
                        },
                        app=app,
                        dedupe_key=f"campaign:{campaign.id}:{user.id}",
                    )
            except IntegrityError:
                continue  # وصله من قبل
            sent += 1

        Campaign.objects.filter(pk=campaign.pk).update(
            status=Campaign.Status.SENT,
            sent_at=timezone.now(),
            recipients_count=CampaignRecipient.objects.filter(campaign=campaign).count(),
        )
        logger.info("growth: campaign %s sent to %s users", campaign.pk, sent)
        return sent
