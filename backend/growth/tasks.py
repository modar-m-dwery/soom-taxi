from celery import shared_task


@shared_task
def evaluate_driver_incentives(driver_id):
    """بعد كلّ رحلة مكتملة — المكافأة تصل لحظة بلوغ الهدف لا آخر النهار."""
    from growth.services.incentives import IncentiveService
    from users.models import DriverProfile

    driver = DriverProfile.objects.filter(id=driver_id).first()
    if driver is not None:
        IncentiveService.evaluate(driver)


@shared_task
def evaluate_all_incentives():
    """شبكة أمان يوميّة: رحلةٌ فاتها التقييم الفوريّ (worker متوقّف) تُلتقط هنا."""
    from growth.services.incentives import IncentiveService
    from users.models import DriverProfile

    count = 0
    for driver in DriverProfile.objects.filter(status=DriverProfile.DriverStatus.ACTIVE).iterator():
        count += len(IncentiveService.evaluate(driver))
    return f"granted {count} awards"


@shared_task
def send_campaign(campaign_id):
    from growth.models import Campaign
    from growth.services.campaigns import CampaignService

    campaign = Campaign.objects.filter(id=campaign_id).first()
    if campaign is not None:
        return CampaignService.send(campaign)
    return 0
