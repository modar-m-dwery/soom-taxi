"""
وسوم التقييم الافتراضية.

تُنشأ مرة واحدة ثم يعدّلها الأدمن من اللوحة. الأمر idempotent: تشغيله
مرارًا لا يُنشئ نسخًا، ولا يدهس تعديلات الأدمن على النصوص - يُنشئ الناقص
فقط.
"""
from django.core.management.base import BaseCommand

from feedback.models import RatingDirection, RatingTag, TagPolarity


# (code, label, polarity, min_score, max_score)
CUSTOMER_TO_DRIVER = [
    ("clean_car", "سيارة نظيفة", TagPolarity.POSITIVE, 4, 5),
    ("safe_driving", "قيادة آمنة", TagPolarity.POSITIVE, 4, 5),
    ("polite", "تعامل مهذّب", TagPolarity.POSITIVE, 4, 5),
    ("on_time", "وصل في وقته", TagPolarity.POSITIVE, 4, 5),
    ("knows_roads", "يعرف الطرقات", TagPolarity.POSITIVE, 4, 5),

    ("late", "تأخّر كثيرًا", TagPolarity.NEGATIVE, 1, 3),
    ("rude", "تعامل غير لائق", TagPolarity.NEGATIVE, 1, 3),
    ("dirty_car", "سيارة غير نظيفة", TagPolarity.NEGATIVE, 1, 3),
    ("reckless", "قيادة متهوّرة", TagPolarity.NEGATIVE, 1, 3),
    ("long_route", "سلك طريقًا أطول", TagPolarity.NEGATIVE, 1, 3),
    ("extra_fare", "طلب أكثر من الأجرة", TagPolarity.NEGATIVE, 1, 3),
]

DRIVER_TO_CUSTOMER = [
    ("ready", "كان جاهزًا عند وصولي", TagPolarity.POSITIVE, 4, 5),
    ("respectful", "تعامل محترم", TagPolarity.POSITIVE, 4, 5),
    ("clear_address", "عنوان واضح", TagPolarity.POSITIVE, 4, 5),

    ("kept_waiting", "أبقاني منتظرًا", TagPolarity.NEGATIVE, 1, 3),
    ("wrong_address", "عنوان غير صحيح", TagPolarity.NEGATIVE, 1, 3),
    ("disrespectful", "تعامل غير محترم", TagPolarity.NEGATIVE, 1, 3),
    ("extra_passengers", "ركّاب أكثر من المتفق", TagPolarity.NEGATIVE, 1, 3),
]


class Command(BaseCommand):
    help = "إنشاء وسوم التقييم الافتراضية (idempotent)"

    def handle(self, *args, **options):
        created_total = 0

        for direction, rows in (
            (RatingDirection.CUSTOMER_TO_DRIVER, CUSTOMER_TO_DRIVER),
            (RatingDirection.DRIVER_TO_CUSTOMER, DRIVER_TO_CUSTOMER),
        ):
            for order, (code, label, polarity, low, high) in enumerate(rows):
                _tag, created = RatingTag.objects.get_or_create(
                    code=code,
                    direction=direction,
                    defaults={
                        "label": label,
                        "polarity": polarity,
                        "min_score": low,
                        "max_score": high,
                        "order": order,
                        "active": True,
                    },
                )
                created_total += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"وسوم التقييم: أُنشئ {created_total} جديدًا، "
            f"المجموع {RatingTag.objects.count()}."
        ))
