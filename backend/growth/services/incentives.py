"""
الحوافز: تقدّم كلّ سائق نحو هدفه، ومنح المكافأة عند بلوغه.

التقدّم يُحسب من الرحلات المكتملة لا من عدّادٍ يُزاد: عدّادٌ يُزاد يضيع
عند أوّل انتقال فاشل، والحساب من الحقيقة يصحّح نفسه. ويُقيَّم عند إتمام
كلّ رحلة ويوميًّا شبكةَ أمان — والمنح فريدٌ لكلّ فترة فلا يتضاعف.
"""

from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from growth.models import IncentiveAward, IncentiveProgram
from trips.models import Trip, TripStatus


def period_start(period, today=None):
    today = today or timezone.localdate()
    if period == IncentiveProgram.Period.DAY:
        return today
    if period == IncentiveProgram.Period.WEEK:
        # الأسبوع السوريّ يبدأ السبت.
        return today - timedelta(days=(today.weekday() - 5) % 7)
    return today.replace(day=1)


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


class IncentiveService:

    @staticmethod
    def programs_for(driver):
        group_ids = list(driver.growth_groups.values_list("id", flat=True))
        programs = IncentiveProgram.objects.filter(is_active=True).filter(
            Q(group__isnull=True) | Q(group_id__in=group_ids)
        )
        area_id = driver.home_service_area_id
        return [p for p in programs if p.area_id is None or p.area_id == area_id]

    @staticmethod
    def completed_since(driver, start_day):
        return Trip.objects.filter(
            driver=driver,
            status=TripStatus.COMPLETED,
            completed_at__gte=_aware(start_day),
        ).count()

    @classmethod
    def progress(cls, driver):
        """ما يراه السائق: كلّ برنامج، كم أنجز، كم بقي، وهل استحقّ."""
        rows = []
        for program in cls.programs_for(driver):
            start = period_start(program.period)
            done = cls.completed_since(driver, start)
            award = IncentiveAward.objects.filter(
                program=program, driver=driver, period_start=start,
            ).first()
            rows.append({
                "program_id": program.id,
                "name": program.name,
                "description": program.description,
                "period": program.period,
                "period_start": start,
                "target_trips": program.target_trips,
                "completed_trips": done,
                "remaining_trips": max(program.target_trips - done, 0),
                "reward_label": program.reward_label or f"{program.reward_amount}",
                "earned": award is not None,
                "award_status": award.status if award else None,
            })
        return rows

    @classmethod
    def evaluate(cls, driver):
        """يمنح ما بلغه السائق. يرجع المكافآت الجديدة."""
        from notifications.models import AppKind
        from notifications.services.dispatch import NotificationService

        granted = []
        for program in cls.programs_for(driver):
            if program.min_rating is not None and (
                driver.rating is None or driver.rating < program.min_rating
            ):
                continue
            start = period_start(program.period)
            done = cls.completed_since(driver, start)
            if done < program.target_trips:
                continue
            try:
                with transaction.atomic():
                    award = IncentiveAward.objects.create(
                        program=program, driver=driver,
                        period_start=start, trips_completed=done,
                    )
            except IntegrityError:
                continue  # مُنحت لهذه الفترة
            granted.append(award)
            NotificationService.create(
                user=driver.user,
                event_type="incentive.earned",
                title="مبروك! استحققت مكافأة",
                body=f"{program.name}: {program.reward_label or program.reward_amount}",
                data={"award_id": award.id, "program_id": program.id},
                app=AppKind.DRIVER,
                dedupe_key=f"incentive:{award.id}",
            )
        return granted
