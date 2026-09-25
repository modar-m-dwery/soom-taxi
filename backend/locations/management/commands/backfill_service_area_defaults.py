"""
تعبئة الحقول القائمة على القوائم في مناطق الخدمة الموجودة.

سبب وجود هذا الأمر: الهجرة تكتب default=list في الصفوف القائمة *مباشرةً*
بلا استدعاء save()، فبقيت JAB وLAT بقوائم فارغة — وقائمة فارغة في
invitation_allowed_modes تعني "الدعوة المباشرة معطّلة في هذه المدينة"،
وهو معنى لم يقصده أحد.

الكود صار يقرأ الافتراضات عند القراءة (effective_*)، فالنظام يعمل بدون هذا
الأمر. لكن لوحة الإدارة تعرض ما هو *مخزَّن* لا ما هو فعّال، فبلا تعبئة
سيرى الأدمن مربّعات فارغة ويظن أن شيئًا معطّلًا.

الاستخدام:
    python manage.py backfill_service_area_defaults
    python manage.py backfill_service_area_defaults --dry-run
"""
from django.core.management.base import BaseCommand

from locations.models import ServiceArea
from locations.services import LocationService


class Command(BaseCommand):
    help = "Fill empty JSON list settings on existing ServiceArea rows."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        touched = 0

        for area in ServiceArea.objects.all():
            missing = []

            if not area.allowed_pricing_policies:
                missing.append(
                    f"allowed_pricing_policies -> {area.default_pricing_policies()}"
                )
            if not area.invitation_allowed_modes:
                missing.append(
                    f"invitation_allowed_modes -> {area.default_invitation_allowed_modes()}"
                )
            if not area.invitation_ttl_options:
                missing.append(
                    f"invitation_ttl_options -> {area.default_invitation_ttl_options()}"
                )

            if not missing:
                self.stdout.write(f"[skip] {area.code} — مكتملة")
                continue

            touched += 1
            self.stdout.write(self.style.WARNING(f"[fill] {area.code} — {area.name}"))
            for line in missing:
                self.stdout.write(f"        {line}")

            if not dry:
                # save() في الموديل هي من تملأ الافتراضات
                area.save()

        if dry:
            self.stdout.write(self.style.WARNING(
                f"\n(dry-run) {touched} منطقة تحتاج تعبئة. أعد التشغيل بلا --dry-run."
            ))
            return

        LocationService.invalidate_cache()
        self.stdout.write(self.style.SUCCESS(
            f"\nاكتمل: عُبِّئت {touched} منطقة، وأُبطل كاش المناطق."
        ))
