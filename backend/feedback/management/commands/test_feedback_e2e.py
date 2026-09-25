"""
اختبار المرحلة 9ب — التقييم والشكاوى.

لا يحتاج Daphne ولا Celery.

يحتاج رحلة مكتملة، ويُنشئها بنفسه: طلب -> عرض -> تثبيت -> وصول -> بدء ->
إنهاء، بنفس المسار الذي يمرّ منه التطبيق.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from feedback.models import (
    Complaint,
    ComplaintCategory,
    ComplaintSeverity,
    ComplaintStatus,
    Rating,
    RatingDirection,
    RatingTag,
)
from feedback.services.complaint import ComplaintError, ComplaintService
from feedback.services.rating import RatingError, RatingService
from locations.services import LocationService
from matching.models import OfferStatus, RideOffer
from matching.services.matching import MatchingService
from rides.models import RideMode, RideRequest, RideStatus, TripCategory
from trips.models import Trip, TripStatus
from trips.services.trip import TripService
from users.models import DriverProfile, User
from vehicles.models import Vehicle


JABLEH_LNG = 35.9200
JABLEH_LAT = 35.3600
DEST_LNG, DEST_LAT = 35.9300, 35.4000


class Command(BaseCommand):
    help = "اختبار التقييم المتبادل والشكاوى وتجميد الأدلّة"

    def add_arguments(self, parser):
        parser.add_argument("--customer-phone", required=True)
        parser.add_argument("--driver-id", type=int, required=True)

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        self.passed = 0
        self.failed = 0
        self.created_rides = []

        customer = User.objects.filter(phone=options["customer_phone"]).first()
        if customer is None:
            return self._setup_fail("لا يوجد زبون بهذا الرقم.")

        driver = DriverProfile.objects.filter(id=options["driver_id"]).first()
        if driver is None:
            return self._setup_fail("لا يوجد سائق بهذا المعرّف.")

        area = LocationService.resolve_area(JABLEH_LNG, JABLEH_LAT)
        if area is None:
            return self._setup_fail("لا توجد ServiceArea تغطي جبلة.")

        if not Vehicle.objects.filter(driver=driver, active=True).exists():
            return self._setup_fail("لا مركبة فعّالة للسائق.")

        if not RatingTag.objects.filter(active=True).exists():
            return self._setup_fail(
                "لا وسوم تقييم. شغّل: python manage.py seed_rating_tags"
            )

        self.customer = customer
        self.driver = driver
        self.driver_user = driver.user
        self.area = area

        self._run()

        total = self.passed + self.failed

        if self.failed:
            self.stdout.write(self.style.ERROR(
                f"\nFeedback E2E: {self.passed}/{total} passed, {self.failed} FAILED."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nFeedback E2E: {self.passed}/{total} passed."
            ))

    # =================================================================

    def _run(self):
        self._cleanup_orphans()

        self._phase_setup()
        self._phase_blind()
        self._phase_aggregate()
        self._phase_guards()
        self._phase_complaints()
        self._phase_evidence()

    # -----------------------------------------------------------------
    # أ — رحلة مكتملة وتقييم أول
    # -----------------------------------------------------------------

    def _phase_setup(self):
        self._section("أ: التقييم الأول")

        self.trip = self._completed_trip()

        self._check(
            self.trip.status == TripStatus.COMPLETED,
            f"1) رحلة مكتملة جاهزة للتقييم (trip={self.trip.status})",
        )

        state = RatingService.for_trip(self.trip, self.customer)
        self._check(
            state["can_rate"] and state["mine"] is None,
            "2) الزبون يستطيع التقييم ولم يقيّم بعد",
        )

        tags = list(
            RatingService.available_tags(
                RatingDirection.CUSTOMER_TO_DRIVER, score=5, service_area=self.area
            ).values_list("code", flat=True)
        )
        negative = list(
            RatingService.available_tags(
                RatingDirection.CUSTOMER_TO_DRIVER, score=1, service_area=self.area
            ).values_list("code", flat=True)
        )

        self._check(
            tags and negative and not set(tags) & set(negative),
            f"3) وسوم الدرجة العالية ({len(tags)}) منفصلة تمامًا عن المنخفضة "
            f"({len(negative)})",
        )

        rating = RatingService.submit(
            ride_id=self.trip.ride_id,
            rater=self.customer,
            score=5,
            tags=tags[:2],
            comment="سائق ممتاز",
        )

        self._check(
            rating.direction == RatingDirection.CUSTOMER_TO_DRIVER
            and rating.driver_id == self.driver.id,
            f"4) الاتجاه استُنتج من المُقيِّم لا من الطلب ({rating.direction})",
        )

    # -----------------------------------------------------------------
    # ب — الحجب المتبادل
    # -----------------------------------------------------------------

    def _phase_blind(self):
        self._section("ب: الحجب المتبادل")

        driver_view = RatingService.for_trip(self.trip, self.driver_user)

        self._check(
            driver_view["theirs"] is None and not driver_view["theirs_visible"],
            "5) ★ السائق لا يرى تقييم الزبون قبل أن يقيّم — لا انتقام",
        )
        self._check(
            driver_view["can_rate"],
            "6) لكنه يستطيع التقييم",
        )

        customer_view = RatingService.for_trip(self.trip, self.customer)
        self._check(
            customer_view["mine"] is not None and customer_view["theirs"] is None,
            "7) والزبون يرى تقييمه هو فقط",
        )

        RatingService.submit(
            ride_id=self.trip.ride_id,
            rater=self.driver_user,
            score=4,
            tags=[],
            comment="",
        )

        after_customer = RatingService.for_trip(self.trip, self.customer)
        after_driver = RatingService.for_trip(self.trip, self.driver_user)

        self._check(
            after_customer["theirs"] is not None
            and after_customer["theirs"].score == 4,
            "8) ★ وبعد أن قيّم الطرفان انكشف كلٌّ للآخر",
        )
        self._check(
            after_driver["theirs"] is not None and after_driver["theirs"].score == 5,
            "9) في الاتجاهين معًا",
        )

        # الكشف بانتهاء المهلة: رحلة قديمة قيّمها طرف واحد
        old_trip = self._completed_trip()
        RatingService.submit(
            ride_id=old_trip.ride_id, rater=self.customer, score=5, comment="",
        )

        # نُرجع تاريخ الإنهاء بعد التقييم لا قبله: المهلة تُقاس منه، ولو
        # أرجعناه أولًا لرُفض التقييم نفسه.
        Trip.objects.filter(id=old_trip.id).update(
            completed_at=timezone.now() - timedelta(days=90)
        )
        old_trip.refresh_from_db()

        old_driver_view = RatingService.for_trip(old_trip, self.driver_user)
        self._check(
            old_driver_view["theirs_visible"]
            and old_driver_view["theirs"] is not None,
            "10) ★ وانتهاء المهلة يكشف التقييم حتى لو لم يقيّم الطرف الآخر",
        )
        self._check(
            not old_driver_view["can_rate"],
            "11) لكنه لا يستطيع التقييم بعد انتهائها",
        )

    # -----------------------------------------------------------------
    # ج — التجميع
    # -----------------------------------------------------------------

    def _phase_aggregate(self):
        self._section("ج: المتوسط والمرآة")

        summary = RatingService.recalculate(driver_id=self.driver.id)

        expected = (
            Rating.objects
            .filter(driver=self.driver, direction=RatingDirection.CUSTOMER_TO_DRIVER)
            .count()
        )

        self._check(
            summary is not None and summary.count == expected,
            f"12) عدد التقييمات محسوب من الصفوف ({summary.count if summary else '—'})",
        )

        self.driver.refresh_from_db()
        self._check(
            self.driver.rating is not None
            and abs(float(self.driver.rating) - float(summary.average)) < 0.01,
            f"13) ★ DriverProfile.rating صار له مصدر أخيرًا "
            f"({self.driver.rating}) — الخريطة تعرضه منذ المرحلة 6",
        )

        distribution_total = (
            summary.one_star + summary.two_star + summary.three_star
            + summary.four_star + summary.five_star
        )
        self._check(
            distribution_total == summary.count,
            f"14) التوزيع يطابق العدد ({distribution_total}/{summary.count})",
        )

        # إعادة الحساب idempotent: تشغيلها مرتين لا يضاعف شيئًا
        again = RatingService.recalculate(driver_id=self.driver.id)
        self._check(
            again.count == summary.count and again.average == summary.average,
            "15) وإعادة الحساب مرتين لا تغيّر النتيجة (تصحّح نفسها)",
        )

    # -----------------------------------------------------------------
    # د — الحواجز
    # -----------------------------------------------------------------

    def _phase_guards(self):
        self._section("د: ما يُرفض")

        self._expect_error(
            lambda: RatingService.submit(
                ride_id=self.trip.ride_id, rater=self.customer, score=5
            ),
            "16) تقييم مكرر للرحلة نفسها", RatingError,
        )

        self._expect_error(
            lambda: RatingService.submit(
                ride_id=self.trip.ride_id, rater=self.customer, score=9
            ),
            "17) درجة خارج 1..5", RatingError,
        )

        # رحلة لطرف آخر
        stranger = (
            User.objects
            .exclude(id=self.customer.id)
            .exclude(id=self.driver_user.id)
            .first()
        )

        if stranger is not None:
            self._expect_error(
                lambda: RatingService.submit(
                    ride_id=self.trip.ride_id, rater=stranger, score=5
                ),
                "18) تقييم من شخص ليس طرفًا في الرحلة", RatingError,
            )
        else:
            self._check(True, "18) (لا يوجد مستخدم ثالث للاختبار — تخطّي)")

        # رحلة غير مكتملة
        pending_trip = self._assigned_trip()
        self._expect_error(
            lambda: RatingService.submit(
                ride_id=pending_trip.ride_id, rater=self.customer, score=5
            ),
            "19) ★ تقييم رحلة لم تكتمل — بابها الشكوى لا النجوم", RatingError,
        )

        # نُنهي هذه الرحلة بالإلغاء: تركها نشطة يُبقي السائق مرتبطًا،
        # فترفض المطابقة كل رحلة تالية في الاختبار ويسقط ما لا علاقة له.
        TripService.cancel(
            ride_id=pending_trip.ride_id, actor="customer", reason="اختبار"
        )

        # تقييم منخفض بلا سبب
        low_trip = self._completed_trip()
        self._expect_error(
            lambda: RatingService.submit(
                ride_id=low_trip.ride_id, rater=self.customer, score=1
            ),
            "20) ★ نجمة واحدة بلا سبب", RatingError,
        )

        # وسم لا يناسب الدرجة
        positive_code = (
            RatingService.available_tags(
                RatingDirection.CUSTOMER_TO_DRIVER, score=5, service_area=self.area
            ).values_list("code", flat=True).first()
        )
        self._expect_error(
            lambda: RatingService.submit(
                ride_id=low_trip.ride_id, rater=self.customer, score=1,
                tags=[positive_code], comment="سيئ",
            ),
            "21) ★ وسم إيجابي مع نجمة واحدة يُرفض لا يُتجاهَل", RatingError,
        )

        ok = RatingService.submit(
            ride_id=low_trip.ride_id, rater=self.customer, score=1,
            tags=[], comment="تأخّر ساعة كاملة",
        )
        self._check(
            ok.score == 1,
            "22) والتقييم المنخفض مع سبب يمرّ",
        )

        self.pending_trip = pending_trip

    # -----------------------------------------------------------------
    # هـ — الشكاوى
    # -----------------------------------------------------------------

    def _phase_complaints(self):
        self._section("هـ: الشكاوى")

        complaint = ComplaintService.open(
            ride_id=self.trip.ride_id,
            complainant=self.customer,
            category=ComplaintCategory.FARE,
            description="طلب مني مبلغًا أكبر من الأجرة المعروضة في التطبيق.",
        )

        self._check(
            complaint.against_driver_id == self.driver.id
            and complaint.against_customer_id is None,
            "23) الطرف المشتكى عليه استُنتج من هوية المشتكي",
        )
        self._check(
            complaint.severity == ComplaintSeverity.NORMAL,
            f"24) شكوى أجرة: خطورة عادية ({complaint.severity})",
        )

        safety = ComplaintService.open(
            ride_id=self.trip.ride_id,
            complainant=self.customer,
            category=ComplaintCategory.SAFETY,
            description="قاد بسرعة عالية جدًا وتجاوز إشارة حمراء.",
        )
        self._check(
            safety.severity == ComplaintSeverity.CRITICAL,
            "25) ★ شكوى سلامة تُصعَّد تلقائيًا إلى حرجة",
        )

        self._expect_error(
            lambda: ComplaintService.open(
                ride_id=self.trip.ride_id, complainant=self.customer,
                category=ComplaintCategory.FARE, description="نفس الشكوى مرة أخرى.",
            ),
            "26) شكوى مكررة من الفئة نفسها وهي ما زالت مفتوحة", ComplaintError,
        )

        self._expect_error(
            lambda: ComplaintService.open(
                ride_id=self.trip.ride_id, complainant=self.customer,
                category=ComplaintCategory.OTHER, description="قصير",
            ),
            "27) وصف أقصر من عشرة أحرف", ComplaintError,
        )

        # الرحلة الملغاة: يجوز الاشتكاء منها بخلاف التقييم
        cancelled = self._cancelled_trip()
        cancel_complaint = ComplaintService.open(
            ride_id=cancelled.ride_id,
            complainant=self.customer,
            category=ComplaintCategory.NO_SHOW,
            description="ألغى الرحلة بعد أن انتظرته عشرين دقيقة.",
        )
        self._check(
            cancel_complaint.id is not None,
            "28) ★ الرحلة الملغاة يجوز الاشتكاء منها — وهي أكثر ما يُشتكى منه",
        )

        # الإغلاق يحتاج سببًا
        self._expect_error(
            lambda: ComplaintService.set_status(
                complaint.id, ComplaintStatus.RESOLVED, self.driver_user, note=""
            ),
            "29) ★ إغلاق شكوى بلا سبب مكتوب", ComplaintError,
        )

        resolved = ComplaintService.set_status(
            complaint.id, ComplaintStatus.RESOLVED, self.driver_user,
            note="روجعت الأجرة: المبلغ مطابق. أُبلغ الزبون.",
        )
        self._check(
            resolved.status == ComplaintStatus.RESOLVED
            and resolved.resolved_at is not None,
            "30) والإغلاق بسبب مكتوب يمرّ ويُسجَّل وقته",
        )

        self._expect_error(
            lambda: ComplaintService.set_status(
                complaint.id, ComplaintStatus.OPEN, self.driver_user, note="إعادة فتح"
            ),
            "31) ولا تُعاد الشكوى المغلقة عبر الخدمة", ComplaintError,
        )

        # التصعيد الزمني
        Complaint.objects.filter(id=safety.id).update(
            severity=ComplaintSeverity.NORMAL
        )
        Complaint.objects.filter(id=safety.id).update(
            created_at=timezone.now() - timedelta(days=5)
        )

        escalated = ComplaintService.escalate_stale()
        safety.refresh_from_db()

        self._check(
            safety.id in escalated and safety.severity != ComplaintSeverity.NORMAL,
            f"32) شكوى راكدة يومين تُصعَّد تلقائيًا ({safety.severity})",
        )

        self.complaint = resolved

    # -----------------------------------------------------------------
    # و — تجميد الأدلّة
    # -----------------------------------------------------------------

    def _phase_evidence(self):
        self._section("و: الأدلّة المجمّدة")

        evidence = self.complaint.evidence

        self._check(
            evidence.get("frozen_at") and evidence.get("trip_id") == self.trip.id,
            "33) اللقطة مؤرَّخة ومربوطة برحلتها",
        )

        self._check(
            evidence["measurements"]["distance_m"] == self.trip.distance_m
            and evidence["measurements"]["gps_points_count"] == self.trip.gps_points_count,
            f"34) القياسات مجمّدة كما كانت "
            f"({evidence['measurements']['distance_m']}م، "
            f"{evidence['measurements']['gps_points_count']} نقطة)",
        )

        self._check(
            evidence["verification"]["pickup_verified"] is True
            and "dropoff_verified" in evidence["verification"],
            "35) ونتائج التحقق الجغرافي معها",
        )

        self._check(
            evidence["money"]["final_fare"] == str(self.trip.final_fare),
            f"36) والأجرة النهائية ({evidence['money']['final_fare']})",
        )

        # الاختبار الحقيقي: احذف المسار كما تفعل مهمة الاحتفاظ، ثم اسأل
        # هل بقيت الشكوى قابلة للحسم؟
        before = self.trip.locations.count()
        self.trip.locations.all().delete()

        self.complaint.refresh_from_db()

        self._check(
            before > 0 and self.trip.locations.count() == 0,
            f"37) حُذفت {before} نقطة مسار كما تفعل سياسة الاحتفاظ بعد 30 يومًا",
        )

        self._check(
            self.complaint.evidence["measurements"]["gps_points_count"] == before
            and self.complaint.evidence["money"]["final_fare"]
            == str(self.trip.final_fare),
            "38) ★ والشكوى ما زالت تحمل دليلها كاملًا — هذا كل الغرض",
        )

    # =================================================================
    # أدوات
    # =================================================================

    ACTIVE_RIDE_STATUSES = [
        RideStatus.DRIVER_SELECTED, RideStatus.DRIVER_ARRIVING,
        RideStatus.DRIVER_ARRIVED, RideStatus.IN_PROGRESS,
    ]
    ACTIVE_TRIP_STATUSES = [
        TripStatus.CREATED, TripStatus.DRIVER_ARRIVING,
        TripStatus.DRIVER_ARRIVED, TripStatus.IN_PROGRESS,
    ]

    def _cleanup_orphans(self):
        """
        إلغاء الرحلة وحدها لا يكفي: "مشغول" يُعرَّف بعرضٍ مقبول على طلب
        نشط، فطلب عالق من تشغيل سابق يُبقي السائق مشغولًا إلى الأبد مهما
        ألغينا من رحلات. نُغلق السلسلة كاملة: عرض -> طلب -> رحلة.
        """
        stale_ride_ids = list(
            RideOffer.objects
            .filter(
                driver=self.driver,
                status=OfferStatus.ACCEPTED,
                ride__status__in=self.ACTIVE_RIDE_STATUSES,
            )
            .values_list("ride_id", flat=True)
        )

        if stale_ride_ids:
            Trip.objects.filter(ride_id__in=stale_ride_ids).update(
                status=TripStatus.CANCELLED
            )
            RideRequest.objects.filter(id__in=stale_ride_ids).update(
                status=RideStatus.CANCELLED
            )
            RideOffer.objects.filter(
                ride_id__in=stale_ride_ids, status=OfferStatus.ACCEPTED
            ).update(status=OfferStatus.CANCELLED)

            self.stdout.write(self.style.WARNING(
                f"نُظّفت طلبات عالقة: {stale_ride_ids}"
            ))

        remaining = Trip.objects.filter(
            driver=self.driver, status__in=self.ACTIVE_TRIP_STATUSES
        ).update(status=TripStatus.CANCELLED)

        if remaining:
            self.stdout.write(self.style.WARNING(f"أُغلقت {remaining} رحلة يتيمة."))

        DriverProfile.objects.filter(id=self.driver.id).update(current_occupancy=0)

    def _explain_ineligibility(self, ride):
        """
        MatchingError واحدة لعشرة أسباب مختلفة. نفحصها واحدًا واحدًا
        ونقول أيّها منع فعلًا - أنفع من قراءة الشرط في الكود كل مرة.
        """
        from django.contrib.gis.db.models.functions import Distance

        driver = DriverProfile.objects.filter(id=self.driver.id).first()
        reasons = []

        if driver.status != DriverProfile.DriverStatus.ACTIVE:
            reasons.append(f"حالة السائق '{driver.status}' لا ACTIVE")

        if not driver.online:
            reasons.append("السائق غير متصل (online=False)")

        if driver.current_location is None:
            reasons.append("لا موقع مسجَّل للسائق")
        elif not MatchingService.is_driver_location_fresh(driver):
            reasons.append(f"موقع قديم (آخر تحديث {driver.last_location_at})")

        remaining = (driver.available_seats or 0) - (driver.current_occupancy or 0)
        if remaining < ride.passenger_count:
            reasons.append(
                f"مقاعد غير كافية: متاح {remaining} "
                f"(سعة {driver.available_seats} - ركّاب {driver.current_occupancy})"
            )

        blocking = list(
            RideOffer.objects
            .filter(
                driver=driver,
                status=OfferStatus.ACCEPTED,
                ride__status__in=self.ACTIVE_RIDE_STATUSES,
            )
            .values_list("ride_id", "ride__status")
        )
        if blocking:
            reasons.append(f"مرتبط بطلبات نشطة: {blocking}")

        if not Vehicle.objects.filter(
            driver=driver, active=True, seats__gte=ride.passenger_count
        ).exists():
            reasons.append("لا مركبة فعّالة بسعة كافية")

        distance = (
            DriverProfile.objects
            .filter(id=driver.id)
            .annotate(distance=Distance("current_location", ride.pickup))
            .values_list("distance", flat=True)
            .first()
        )
        radius = MatchingService.get_radius_km(ride)
        if distance is None or distance.km > radius:
            reasons.append(f"خارج النطاق ({distance} > {radius}كم)")

        return reasons or ["لم أجد سببًا ظاهرًا — راجع can_driver_submit_offer"]

    def _refresh_driver(self, at_point):
        self.driver.refresh_from_db()
        self.driver.current_location = at_point
        self.driver.last_location_at = timezone.now()
        self.driver.online = True
        self.driver.status = DriverProfile.DriverStatus.ACTIVE
        self.driver.current_occupancy = 0

        vehicle = (
            Vehicle.objects
            .filter(driver=self.driver, active=True)
            .order_by("-seats")
            .first()
        )
        if vehicle is not None:
            self.driver.available_seats = vehicle.seats

        self.driver.save(update_fields=[
            "current_location", "last_location_at", "online", "status",
            "current_occupancy", "available_seats", "updated_at",
        ])

    def _make_ride(self):
        pickup = Point(JABLEH_LNG, JABLEH_LAT, srid=4326)
        destination = Point(DEST_LNG, DEST_LAT, srid=4326)

        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=pickup,
            destination=destination,
            mode=RideMode.FAST,
            trip_category=TripCategory.CITY,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=self.area,
            gross_fare=Decimal("25.00"),
            customer_total=Decimal("25.00"),
            driver_net=Decimal("25.00"),
            pricing_policy="platform_fixed",
            currency=self.area.currency_code,
            route_distance_km=Decimal("4.50"),
        )
        self.created_rides.append(ride.id)
        return ride

    def _assigned_trip(self):
        """طلب مثبَّت عليه السائق، بلا وصول ولا بدء."""
        self._refresh_driver(Point(JABLEH_LNG, JABLEH_LAT, srid=4326))

        ride = self._make_ride()

        try:
            offer = MatchingService.create_offer(
                ride_id=ride.id, driver=self.driver,
                gross_fare=Decimal("25.00"), eta_minutes=4,
            )
        except Exception as exc:
            reasons = "\n  - ".join(self._explain_ineligibility(ride))
            raise CommandError(
                f"تعذّر تثبيت السائق ({exc}). السبب:\n  - {reasons}"
            )
        MatchingService.select_offer(
            ride_id=ride.id, offer_id=offer.id, customer=self.customer
        )

        return Trip.objects.get(ride_id=ride.id)

    def _completed_trip(self, completed_at=None):
        trip = self._assigned_trip()
        ride = trip.ride

        self._refresh_driver(ride.pickup)
        TripService.arrived(ride_id=ride.id, driver=self.driver)

        # نأخذ الكائن العائد لا القديم: record_location تفحص الحالة على
        # النسخة الممرَّرة، والنسخة القديمة ما زالت driver_arriving فتُرجع
        # None صامتة ويبقى المسار فارغًا.
        trip = TripService.start(ride_id=ride.id, driver=self.driver)

        # نقاط مسار حقيقية حتى يكون للأدلّة ما تجمّده
        base = timezone.now()
        for i in range(4):
            TripService.record_location(
                trip,
                lng=JABLEH_LNG + (i * 0.002),
                lat=JABLEH_LAT + (i * 0.010),
                speed=30.0,
                at=base + timedelta(seconds=i * 15),
            )

        self._refresh_driver(ride.destination)
        trip = TripService.complete(ride_id=ride.id, driver=self.driver)

        if completed_at is not None:
            Trip.objects.filter(id=trip.id).update(completed_at=completed_at)
            trip.refresh_from_db()

        return trip

    def _cancelled_trip(self):
        trip = self._assigned_trip()
        TripService.cancel(ride_id=trip.ride_id, actor="driver", reason="غيّر رأيه")
        trip.refresh_from_db()
        return trip

    # -----------------------------------------------------------------

    def _section(self, title):
        self.stdout.write(self.style.HTTP_INFO(f"\n— {title} —"))

    def _check(self, condition, label):
        if condition:
            self.passed += 1
            self.stdout.write(f"[OK]   {label}")
        else:
            self.failed += 1
            self.stdout.write(self.style.ERROR(f"[FAIL] {label}"))

    def _expect_error(self, callable_, label, exception_class):
        try:
            callable_()
        except exception_class as exc:
            self._check(True, f"{label} — {exc}")
            return
        except Exception as exc:
            self._check(False, f"{label} — استثناء غير متوقع: {exc!r}")
            return

        self._check(False, f"{label} — مرّ بلا رفض!")

    def _setup_fail(self, message):
        self.stderr.write(self.style.ERROR(f"[SETUP FAIL] {message}"))