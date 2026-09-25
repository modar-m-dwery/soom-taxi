from datetime import timedelta

from django.conf import settings
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db import transaction
from django.utils import timezone

from matching.models import (
    RideOffer,
    OfferStatus,
    SharedJoinRequest,
    SharedJoinStatus,
    SharedRideGroup,
    SharedRideGroupMember,
    SharedGroupStatus,
)

from matching.services.shared_scoring import get_active_strategy

from rides.models import RideRequest, RideMode, RideStatus


class SharedMatchingError(Exception):
    pass


class SharedMatchingService:

    @classmethod
    def is_enabled(cls):
        return getattr(settings, "MATCHING_SHARED_ENABLED", False)

    @staticmethod
    def _offer_vehicle_seats(offer):
        vehicle = (
            offer.driver.vehicles
            .filter(active=True)
            .order_by("-seats")
            .first()
        )
        return vehicle.seats if vehicle else 0

    @staticmethod
    def _get_or_create_group(offer):
        vehicle = (
            offer.driver.vehicles
            .filter(active=True)
            .order_by("-seats")
            .first()
        )

        if not vehicle:
            raise SharedMatchingError("Driver has no active vehicle.")

        group, created = SharedRideGroup.objects.get_or_create(
            host_offer=offer,
            defaults={
                "driver": offer.driver,
                "vehicle": vehicle,
                "status": SharedGroupStatus.ACTIVE,
            },
        )

        if created:
            SharedRideGroupMember.objects.get_or_create(
                group=group,
                ride=offer.ride,
                defaults={"is_host": True},
            )

        return group

    @classmethod
    @transaction.atomic
    def broadcast_offer_to_candidates(cls, offer):
        """
        تُستدعى فور تقديم عرض على رحلة SHARED. تضمن وجود SharedRideGroup،
        ثم تبحث عن طلبات SHARED منتظرة وقريبة ومتوافقة ضمن السعة المتبقية
        الفعلية للمجموعة، وتنشئ SharedJoinRequest لكل مرشح مؤهل.
        """
        if not cls.is_enabled():
            return []

        host_ride = offer.ride

        if host_ride.mode != RideMode.SHARED:
            return []

        group = cls._get_or_create_group(offer)
        available_seats = group.remaining_capacity

        if available_seats <= 0:
            return []

        # نصف قطر المشاركة من مدينة الرحلة المستضيفة: رفعه يزيد المطابقات
        # ويزيد انعراج الراكب الأوّل، وهذه موازنةٌ يملكها مشغّل المدينة.
        _area = getattr(host_ride, "service_area", None)
        radius = D(
            km=(
                _area.effective_shared_join_radius_km
                if _area is not None
                else settings.MATCHING_SHARED_JOIN_RADIUS_KM
            )
        )

        candidates = (
            RideRequest.objects
            .filter(
                mode=RideMode.SHARED,
                status=RideStatus.SEARCHING,
                passenger_count__lte=available_seats,
            )
            # الرحلة لسه مش عضو في أي مجموعة مشتركة تانية
            .filter(shared_group_membership__isnull=True)
            .exclude(id=host_ride.id)
            .exclude(customer=host_ride.customer)
            .annotate(distance=Distance("pickup", host_ride.pickup))
            .filter(distance__lte=radius)
        )

        strategy = get_active_strategy()
        created = []

        for candidate in candidates:
            score = strategy.score(host_ride, candidate)

            if score < settings.MATCHING_SHARED_MIN_SCORE:
                continue

            join_request, _created = SharedJoinRequest.objects.update_or_create(
                host_offer=offer,
                candidate_ride=candidate,
                defaults={
                    "host_ride": host_ride,
                    "compatibility_score": score,
                    "scoring_strategy": strategy.name,
                    "status": SharedJoinStatus.PENDING,
                    "expires_at": (
                        timezone.now()
                        + timedelta(seconds=settings.MATCHING_SHARED_JOIN_TTL_SECONDS)
                    ),
                },
            )
            created.append(join_request)

        return created

    @classmethod
    def get_available_offers_for_customer(cls, ride):
        if ride.mode != RideMode.SHARED:
            return SharedJoinRequest.objects.none()

        return (
            SharedJoinRequest.objects
            .filter(
                candidate_ride=ride,
                status=SharedJoinStatus.PENDING,
                expires_at__gt=timezone.now(),
                host_offer__status=OfferStatus.PENDING,
                host_offer__expires_at__gt=timezone.now(),
            )
            .select_related(
                "host_offer",
                "host_offer__driver",
                "host_offer__driver__user",
                "host_ride",
                "host_ride__customer",
            )
            .order_by("-compatibility_score")
        )

    @staticmethod
    def _expire_join_request_if_stale(join_request_id):
        with transaction.atomic():
            (
                SharedJoinRequest.objects
                .filter(
                    id=join_request_id,
                    status=SharedJoinStatus.PENDING,
                    expires_at__lte=timezone.now(),
                )
                .update(status=SharedJoinStatus.EXPIRED)
            )

    @classmethod
    def accept_join(cls, join_request_id, candidate_customer):
        cls._expire_join_request_if_stale(join_request_id)

        return cls._accept_join_atomic(
            join_request_id=join_request_id,
            candidate_customer=candidate_customer,
        )

    @classmethod
    @transaction.atomic
    def _accept_join_atomic(cls, join_request_id, candidate_customer):

        join_request = (
            SharedJoinRequest.objects
            .select_for_update()
            .select_related("host_offer", "host_ride", "candidate_ride")
            .get(
                id=join_request_id,
                candidate_ride__customer=candidate_customer,
            )
        )

        if join_request.status != SharedJoinStatus.PENDING:
            raise SharedMatchingError("طلب الانضمام لم يعد متاحًا.")

        if join_request.expires_at <= timezone.now():
            join_request.status = SharedJoinStatus.EXPIRED
            join_request.save(update_fields=["status", "updated_at"])
            raise SharedMatchingError("انتهت صلاحية هذا العرض.")

        candidate_ride = (
            RideRequest.objects
            .select_for_update()
            .get(id=join_request.candidate_ride_id)
        )

        # الراكب لا يمكن أن ينضم مرتين لمجموعتين مختلفتين
        if SharedRideGroupMember.objects.filter(ride=candidate_ride).exists():
            raise SharedMatchingError("الراكب منضم بالفعل لرحلة مشتركة أخرى.")

        host_offer = (
            RideOffer.objects
            .select_for_update()
            .get(id=join_request.host_offer_id)
        )

        now = timezone.now()

        if (
            host_offer.status != OfferStatus.PENDING
            or host_offer.expires_at <= now
        ):
            raise SharedMatchingError(
                "عرض السائق لم يعد متاحًا."
            )

        # قفل صف المجموعة نفسه: يمنع سباقًا بين قبولين متزامنين
        # يحاولان يملأوا آخر مقعد في نفس اللحظة
        group = (
            SharedRideGroup.objects
            .select_for_update()
            .get(host_offer=host_offer)
        )

        if group.status != SharedGroupStatus.ACTIVE:
            raise SharedMatchingError("Shared ride group is no longer active.")

        if candidate_ride.passenger_count > group.remaining_capacity:
            raise SharedMatchingError("لا توجد مقاعد كافية بعد الآن.")

        from django.db import IntegrityError

        try:
            with transaction.atomic():
                SharedRideGroupMember.objects.create(
                    group=group,
                    ride=candidate_ride,
                    is_host=False,
                )
        except IntegrityError:
            raise SharedMatchingError(
                "الراكب منضم بالفعل لرحلة مشتركة أخرى."
            )

        candidate_ride.status = join_request.host_ride.status
        candidate_ride.save(update_fields=["status", "updated_at"])

        join_request.status = SharedJoinStatus.ACCEPTED
        join_request.save(update_fields=["status", "updated_at"])

        (
            SharedJoinRequest.objects
            .filter(
                candidate_ride=candidate_ride,
                status=SharedJoinStatus.PENDING,
            )
            .exclude(id=join_request.id)
            .update(status=SharedJoinStatus.WITHDRAWN)
        )

        return join_request

    @classmethod
    @transaction.atomic
    def cancel_group_for_offer(cls, offer):
        """
        تُستدعى فقط عند سقوط عرض السائق نفسه (انتهاء صلاحية/رفض) — أي عندما
        السائق نفسه لم يعد متاحًا لتوصيل أي راكب، فمن المنطقي إرجاع الجميع
        للبحث. هذا يختلف عن إلغاء راكب واحد لرحلته (انظر
        cancel_ride_membership تحت) الذي لا يجب أن يُسقط باقي الركاب.
        """
        group = (
            SharedRideGroup.objects
            .select_for_update()
            .filter(host_offer=offer)
            .first()
        )

        if not group or group.status != SharedGroupStatus.ACTIVE:
            return

        member_ride_ids = list(
            group.members
            .exclude(is_host=True)
            .values_list("ride_id", flat=True)
        )

        if member_ride_ids:
            RideRequest.objects.filter(
                id__in=member_ride_ids,
                status__in=[
                    RideStatus.SEARCHING,
                    RideStatus.OFFERS_RECEIVED,
                ],
            ).update(
                status=RideStatus.SEARCHING,
                updated_at=timezone.now(),
            )

        group.status = SharedGroupStatus.CANCELLED
        group.save(update_fields=["status", "updated_at"])

        SharedJoinRequest.objects.filter(
            host_offer=offer,
            status=SharedJoinStatus.PENDING,
        ).update(status=SharedJoinStatus.WITHDRAWN)

        SharedJoinRequest.objects.filter(
            host_offer=offer,
            status=SharedJoinStatus.ACCEPTED,
        ).update(status=SharedJoinStatus.CANCELLED)

    @classmethod
    @transaction.atomic
    def cancel_ride_membership(cls, ride_id):
        """
        إلغاء راكب واحد (سواء كان المضيف أو أحد المنضمين) من مجموعة مشاركة
        فورية، دون التأثير على باقي الركاب. لو الملغي هو المضيف ولسه فيه
        ركاب، بيترقّى أقدم راكب متبقٍ ليكون المضيف الجديد (السائق والمركبة
        يفضلوا كما هم لأنهم مخزنين مباشرة على group.driver / group.vehicle).
        """
        membership = (
            SharedRideGroupMember.objects
            .select_for_update()
            .select_related("group")
            .filter(ride_id=ride_id)
            .first()
        )

        if not membership:
            return None

        group = (
            SharedRideGroup.objects
            .select_for_update()
            .select_related("driver", "vehicle")
            .get(id=membership.group_id)
        )

        if group.status != SharedGroupStatus.ACTIVE:
            return group

        was_host = membership.is_host

        membership.delete()

        remaining = list(
            SharedRideGroupMember.objects
            .select_for_update()
            .filter(group=group)
            .order_by("joined_at")
        )

        if remaining:

            if was_host and not any(m.is_host for m in remaining):
                new_host = remaining[0]
                new_host.is_host = True
                new_host.save(update_fields=["is_host"])

            return group

        # لا يوجد ركاب متبقين -> إلغاء المجموعة بالكامل
        group.status = SharedGroupStatus.CANCELLED
        group.save(update_fields=["status", "updated_at"])
        return group

    @classmethod
    def propagate_status_to_members(cls, host_ride, new_status):
        """
        يُستدعى من select_offer عند أي تحول حالة على رحلة المضيف
        (DRIVER_SELECTED الآن، ولاحقًا DRIVER_ARRIVING/IN_PROGRESS/...).
        """
        member_ride_ids = (
            SharedRideGroupMember.objects
            .filter(group__host_offer__ride=host_ride)
            .exclude(ride=host_ride)
            .values_list("ride_id", flat=True)
        )

        if not member_ride_ids:
            return

        RideRequest.objects.filter(id__in=member_ride_ids).update(
            status=new_status,
            updated_at=timezone.now(),
        )

        if new_status == RideStatus.DRIVER_SELECTED:
            cls._attach_members_to_driver(host_ride, member_ride_ids)

    @classmethod
    def _attach_members_to_driver(cls, host_ride, member_ride_ids):
        """
        كلّ راكب منضمّ يصير رحلةً كاملة عند السائق: عرضٌ مقبول بأجرته هو
        (المسعَّرة مشتركةً عند إنشاء طلبه) ورحلةٌ بتسلسلها الخاصّ. قبل هذا
        كان المنضمّون يُعلَّمون «اختير سائق» ثمّ لا شيء: لا رحلة ولا دفعة،
        ولا يعرف السائق نقطة التقاطهم أصلًا.
        """
        from trips.services.trip import TripService

        host_offer = (
            RideOffer.objects
            .filter(ride=host_ride, status=OfferStatus.ACCEPTED)
            .select_related("driver")
            .first()
        )
        if host_offer is None:
            return

        now = timezone.now()
        for member in RideRequest.objects.filter(id__in=member_ride_ids):
            offer, _ = RideOffer.objects.update_or_create(
                ride=member,
                driver=host_offer.driver,
                defaults={
                    "gross_fare": member.gross_fare,
                    "eta_minutes": host_offer.eta_minutes or 1,
                    "status": OfferStatus.ACCEPTED,
                    "expires_at": now + timedelta(
                        seconds=getattr(settings, "RIDE_OFFER_TTL_SECONDS", 30)
                    ),
                    "accepted_at": now,
                },
            )
            TripService.ensure_trip(member, offer=offer)