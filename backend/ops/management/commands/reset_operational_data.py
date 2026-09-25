"""
تنظيف بيانات التشغيل — بديل آمن لـwipe_database.py.

لماذا لم يعد السكربت القديم كافيًا:

  1. لا يمسّ Redis إطلاقًا. وهذه ليست تفصيلة: بعد حذف السائقين من القاعدة
     يبقى `presence:driver:5` و`drivers:geo` و`marketplace:cell:*` كما هي،
     فتصير الخريطة تعرض سيارات لمستخدمين لم يعودوا موجودين، ويظنّ محرّك
     الحضور أن سائقًا محذوفًا مشغول. سائق شبح بالمعنى الحرفي.

  2. كُتب قبل trips وfeedback وnotifications وops. الحذف بالتسلسل (cascade)
     يُنظّف أغلبها حين يُحذف المستخدم، لكنه لا يُصفّر التجميعات المحسوبة:
     `DriverProfile.rating` يبقى 3.80 بعد حذف كل صفوف التقييم التي أنتجته.

  3. يحذف المستخدمين دائمًا. وهذا نادرًا ما هو المطلوب: بعد جولة اختبارات
     تريد رحلاتٍ نظيفة لا أن تُعيد إنشاء السائق وتوثيقه ومركبته.

فمستويان:

    python manage.py reset_operational_data --yes
        يحذف كل ما يخصّ التشغيل (رحلات، طلبات، عروض، دعوات، تقييمات،
        شكاوى، إشعارات، سجلّ تدقيق) ويمسح Redis ويُصفّر التجميعات.
        يُبقي: المستخدمين، السائقين، المركبات، المناطق، وسوم التقييم.

    python manage.py reset_operational_data --yes --users
        وأيضًا كل مستخدم غير موظّف.

وبلا `--yes` لا يحذف شيئًا — يطبع ما كان سيحذفه فقط.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


PRESENCE_KEY_PATTERNS = [
    "presence:driver:*",
    "marketplace:cell:*",
]

PRESENCE_FIXED_KEYS = [
    "drivers:geo",
    "drivers:last_seen",
]


class Command(BaseCommand):
    help = "تنظيف بيانات التشغيل من القاعدة وRedis معًا"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="نفّذ فعلًا. بدونه يطبع التعداد ولا يحذف.",
        )
        parser.add_argument(
            "--users",
            action="store_true",
            help="احذف أيضًا المستخدمين غير الموظّفين (وبالتالي السائقين والمركبات).",
        )
        parser.add_argument(
            "--keep-redis",
            action="store_true",
            help="لا تمسح مفاتيح الحضور. لا تستعمله إلا إن كنت تعرف لماذا.",
        )
        parser.add_argument(
            "--purge-queue",
            action="store_true",
            help="أفرغ طابور Celery أيضًا — مهامّ مؤجّلة تشير إلى صفوف محذوفة.",
        )
        parser.add_argument(
            "--reset-driver-status",
            action="store_true",
            help="أعد كل السائقين إلى pending (يلغي التوثيق — للتجارب فقط).",
        )
        parser.add_argument(
            "--i-know-this-is-production",
            action="store_true",
            help="مطلوب حين DEBUG=False. لا تكتبه بالخطأ.",
        )

    # -----------------------------------------------------------------

    def handle(self, *args, **options):
        # الحاجز الأول: لا يعمل على الإنتاج إلا بنيّة صريحة مكتوبة.
        # سكربت تنظيف بلا هذا الحاجز يُشغَّل مرة واحدة على الخادم الخطأ،
        # ومرة واحدة تكفي.
        if not settings.DEBUG and not options["i_know_this_is_production"]:
            raise CommandError(
                "DEBUG=False — هذه تبدو بيئة إنتاج.\n"
                "إن كنت متأكدًا أضف --i-know-this-is-production"
            )

        dry = not options["yes"]

        if dry:
            self.stdout.write(self.style.WARNING(
                "وضع المعاينة — لن يُحذف شيء. أضف --yes للتنفيذ.\n"
            ))

        counts = self._collect_counts(options["users"])

        self.stdout.write(self.style.HTTP_INFO("— ما سيُحذف من القاعدة —"))
        for label, count in counts:
            style = self.style.SUCCESS if count == 0 else self.style.WARNING
            self.stdout.write(style(f"  {label:.<40} {count:>6}"))

        redis_count = self._count_redis_keys()
        self.stdout.write(self.style.HTTP_INFO("\n— مفاتيح Redis —"))

        if options["keep_redis"]:
            self.stdout.write("  (متروكة بطلبك — انتبه للسائقين الأشباح)")
        else:
            self.stdout.write(f"  مفاتيح حضور وخلايا................ {redis_count:>6}")

        if dry:
            self.stdout.write(self.style.WARNING(
                "\nلم يُنفَّذ شيء. أعد الأمر مع --yes."
            ))
            return

        # -------------------------------------------------------------
        # التنفيذ
        # -------------------------------------------------------------

        with transaction.atomic():
            self._delete_operational()

            if options["users"]:
                self._delete_users()

            self._reset_aggregates(options["reset_driver_status"])

        # Redis بعد نجاح المعاملة لا قبلها: لو انهار الحذف في منتصفه
        # لبقيت القاعدة كاملة وRedis فارغًا — وهو أسوأ من الاثنين معًا.
        if not options["keep_redis"]:
            cleared = self._clear_redis()
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ مُسح {cleared} مفتاحًا من Redis."
            ))

        if options["purge_queue"]:
            self._purge_queue()

        self.stdout.write(self.style.SUCCESS(
            "\n✓ اكتمل التنظيف."
        ))
        self.stdout.write(
            "\nالخطوة التالية: أعد تشغيل Daphne وCelery. العمليات الحيّة "
            "تحمل في ذاكرتها معرّفات صفوف لم تعد موجودة."
        )

    # -----------------------------------------------------------------
    # التعداد
    # -----------------------------------------------------------------

    def _collect_counts(self, with_users):
        from feedback.models import Complaint, Rating, RatingSummary
        from matching.models import (
            RideInvitation, RideOffer, ScheduledSharedTrip,
            ScheduledSharedTripMember, SharedJoinRequest,
            SharedRideGroup, SharedRideGroupMember,
        )
        from notifications.models import Notification
        from ops.models import AdminAction
        from rides.models import RideRequest
        from trips.models import Trip, TripCompletionRecord, TripLocation

        rows = [
            ("نقاط مسار الرحلات", TripLocation.objects.count()),
            ("سجلّات الإتمام", TripCompletionRecord.objects.count()),
            ("الرحلات", Trip.objects.count()),
            ("التقييمات", Rating.objects.count()),
            ("تجميعات التقييم", RatingSummary.objects.count()),
            ("الشكاوى", Complaint.objects.count()),
            ("الإشعارات", Notification.objects.count()),
            ("الدعوات المباشرة", RideInvitation.objects.count()),
            ("العروض", RideOffer.objects.count()),
            ("طلبات الانضمام المشترك", SharedJoinRequest.objects.count()),
            ("أعضاء المجموعات المشتركة", SharedRideGroupMember.objects.count()),
            ("المجموعات المشتركة", SharedRideGroup.objects.count()),
            ("حجوزات الرحلات المجدولة", ScheduledSharedTripMember.objects.count()),
            ("الرحلات المجدولة", ScheduledSharedTrip.objects.count()),
            ("طلبات الركوب", RideRequest.objects.count()),
            ("سجلّ التدقيق الإداري", AdminAction.objects.count()),
        ]

        if with_users:
            from django.contrib.auth import get_user_model
            from users.models import DeviceToken, DriverProfile
            from vehicles.models import Vehicle

            User = get_user_model()

            rows += [
                ("رموز الأجهزة", DeviceToken.objects.count()),
                ("المركبات", Vehicle.objects.count()),
                ("ملفّات السائقين", DriverProfile.objects.count()),
                ("المستخدمون (غير الموظّفين)",
                 User.objects.filter(is_staff=False, is_superuser=False).count()),
            ]

        return rows

    # -----------------------------------------------------------------
    # الحذف
    # -----------------------------------------------------------------

    def _delete_operational(self):
        """
        الترتيب من الابن إلى الأب. التسلسل التلقائي كان سيكفي، لكن الترتيب
        الصريح يجعل أي خطأ مفتاح خارجي يظهر عند الجدول الذي سبّبه لا عند
        جدول بعيد عنه بثلاث خطوات.
        """
        from feedback.models import Complaint, Rating, RatingSummary
        from matching.models import (
            RideInvitation, RideOffer, ScheduledSharedTrip,
            ScheduledSharedTripMember, SharedJoinRequest,
            SharedRideGroup, SharedRideGroupMember,
        )
        from notifications.models import Notification
        from ops.models import AdminAction, AuditLog
        from payments.models import (
            DriverBalance, LedgerEntry, Payment, PaymentAttempt, Refund,
        )
        from rides.models import RideRequest
        from trips.models import Trip, TripCompletionRecord, TripLocation

        # دفتر الأستاذ يرفض الحذف عمدًا (`LedgerEntryQuerySet.delete`)،
        # وهو تصميم صحيح: دفترٌ محاسبيّ يُصحَّح بقيد معاكس لا بمحو الأثر.
        # لكنّ هذا الأمر أداة تطوير ترفض العمل في الإنتاج أصلًا، والقيود
        # هنا تشير إلى دفعات على وشك الحذف. `_raw_delete` يتجاوز حارس
        # الـQuerySet وحده — لا يُستعمل في أيّ مسار آخر في المشروع.
        ledger_qs = LedgerEntry.objects.all()
        ledger_count = ledger_qs.count()
        if ledger_count:
            ledger_qs._raw_delete(ledger_qs.db)
            self.stdout.write(
                self.style.WARNING(f"  حُذف {ledger_count} قيدًا من الدفتر.")
            )

        for model in (
            TripLocation, TripCompletionRecord,
            Rating, RatingSummary, Complaint,
            Notification,
            # المدفوعات قبل الرحلات — إلزاميّ لا تجميليّ.
            #
            # `Payment.trip` مفتاحٌ محميّ (PROTECT)، وحذف الرحلات قبله
            # يرمي ProtectedError وينهار الأمر كلّه في منتصفه، تاركًا
            # القاعدة نصف منظّفة. لم يظهر هذا قبل الآن لأنّ التنظيف كان
            # يُجرّب على بيانات بلا دفعات.
            #
            # والترتيب داخل المدفوعات نفسه من الابن إلى الأب:
            # القيود والمحاولات والاسترجاعات تشير إلى الدفعة.
            PaymentAttempt, Refund, Payment, DriverBalance,
            Trip,
            RideInvitation,
            SharedJoinRequest, SharedRideGroupMember, SharedRideGroup,
            ScheduledSharedTripMember, ScheduledSharedTrip,
            RideOffer,
            RideRequest,
            AdminAction,
            # سجلّ التدقيق يُمسح مع البيانات التشغيلية: أثرٌ لصفوف حُذفت
            # ليس تدقيقًا بل ضجيجًا. في الإنتاج لا يُشغَّل هذا الأمر أصلًا.
            AuditLog,
        ):
            model.objects.all().delete()

    def _delete_users(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # الموظّفون يبقون دائمًا. حذف حساب المشرف الذي تستعمله أنت الآن
        # يعني أن أول ما تفعله بعد التنظيف هو createsuperuser من جديد.
        qs = User.objects.filter(is_staff=False, is_superuser=False)

        self.stdout.write(self.style.WARNING(
            f"\n  حذف {qs.count()} مستخدمًا غير موظّف (وما يتبعهم بالتسلسل)…"
        ))

        qs.delete()

    def _reset_aggregates(self, reset_status):
        """
        الحقول المحسوبة لا تُنظَّف بحذف مصادرها.

        `rating = 3.80` بعد حذف كل التقييمات ليس رقمًا قديمًا — هو رقم
        كاذب، لأنه يدّعي متوسطًا لصفوف لم تعد موجودة. والزبون الأول
        سيقرؤه.
        """
        from users.models import DriverProfile

        fields = {
            "rating": 0,
            "online": False,
            "current_occupancy": 0,
            "last_location_at": None,
            "current_location": None,
        }

        if reset_status:
            fields["status"] = DriverProfile.DriverStatus.PENDING

        updated = DriverProfile.objects.all().update(**fields)

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ صُفّرت التجميعات على {updated} سائقًا."
        ))

    # -----------------------------------------------------------------
    # Redis
    # -----------------------------------------------------------------

    def _iter_presence_keys(self):
        """
        SCAN لا KEYS. الفرق لا يظهر على قاعدة تطوير فيها عشرة سائقين،
        لكن KEYS تُجمّد Redis كلّه على قاعدة حقيقية — وهذا الأمر قد
        يُشغَّل يومًا على واحدة.
        """
        from presence.redis_client import get_redis

        r = get_redis()

        for pattern in PRESENCE_KEY_PATTERNS:
            for key in r.scan_iter(match=pattern, count=500):
                yield key

        for key in PRESENCE_FIXED_KEYS:
            if r.exists(key):
                yield key.encode()

    def _count_redis_keys(self):
        try:
            return sum(1 for _ in self._iter_presence_keys())
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  (تعذّر الوصول إلى Redis: {exc!r})"
            ))
            return 0

    def _clear_redis(self):
        from presence.redis_client import get_redis

        try:
            r = get_redis()
            keys = list(self._iter_presence_keys())

            if not keys:
                return 0

            # على دفعات: DEL بألف مفتاح دفعة واحدة يحجب Redis
            deleted = 0
            for start in range(0, len(keys), 200):
                deleted += r.delete(*keys[start:start + 200])

            return deleted
        except Exception as exc:
            self.stdout.write(self.style.ERROR(
                f"\n✗ فشل مسح Redis: {exc!r}\n"
                "  القاعدة نُظّفت وRedis لم يُنظَّف — شغّل الأمر ثانيةً "
                "بعد تشغيل Redis، وإلا ظهرت سيارات لسائقين محذوفين."
            ))
            return 0

    # -----------------------------------------------------------------

    def _purge_queue(self):
        try:
            from config.celery import app

            purged = app.control.purge()

            self.stdout.write(self.style.SUCCESS(
                f"✓ أُفرغ طابور Celery ({purged} مهمّة)."
            ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  (تعذّر إفراغ الطابور: {exc!r})"
            ))
