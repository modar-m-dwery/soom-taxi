# -*- coding: utf-8 -*-
"""
الزبائن المسجَّلون قبل 0008 بلا رمز دعوة: الرمز يُولَّد في save() فقط،
ولا أحد يستدعي save() على ملفٍّ قديم. فيُملأ هنا مرّةً واحدة.
"""

import secrets

from django.db import migrations

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def backfill(apps, schema_editor):
    CustomerProfile = apps.get_model("users", "CustomerProfile")
    taken = set(
        CustomerProfile.objects.exclude(referral_code__isnull=True)
        .exclude(referral_code="")
        .values_list("referral_code", flat=True)
    )
    for profile in CustomerProfile.objects.filter(referral_code__isnull=True) | \
            CustomerProfile.objects.filter(referral_code=""):
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            if code not in taken:
                break
        taken.add(code)
        profile.referral_code = code
        profile.save(update_fields=["referral_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_promotions"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
