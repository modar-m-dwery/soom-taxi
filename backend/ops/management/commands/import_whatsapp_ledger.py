# -*- coding: utf-8 -*-
"""
استيراد دفتر واتساب (جدول Google بثلاث صفحات) إلى الخادم — يوم الإطلاق.

    python manage.py import_whatsapp_ledger --customers customers.csv
        --drivers drivers.csv --rides rides.csv [--dry-run]

كلّ صفحة تُصدَّر من Google Sheets كـCSV بأعمدتها كما في وثيقة «بوّابة
واتساب» حرفًا بحرف:

  زبائن : phone, name, area, usual_pickup, first_seen, rides, last_ride,
          source, saved_us, channel
  سوّاق : phone, name, category, color, plate, area, founder_no, joined,
          rides, complaints, status
  رحلات : datetime, customer_phone, driver_phone, from, to, area, offers,
          price, minutes_to_offer, status, fail_reason, rating

ما يفعله:
  • الزبون → User(role=customer, is_verified) + CustomerProfile، والأعمدة التي
    لا حقل لها (usual_pickup, source, saved_us, channel, first_seen, rides)
    تُحفظ في preferences["whatsapp"] — فيوم يفتح الزبون التطبيق ويُدخل رقمه
    يجد تاريخه بانتظاره.
  • السائق → User(role=driver) + DriverProfile(status=pending) + Vehicle
    بالفئة السورية من عمود category (رمزًا أو اسمًا عربيًّا). «سائق مؤسّس»
    يُكتب في verification_note مع رقمه. الحالة pending عمدًا: الوثائق الأربع
    تُرفع من التطبيق، والتوثيق قرار المشغّل لا قرار الدفتر.
  • الرحلة → LegacyRide كما هي، مربوطةً بالمستخدمين بالهاتف.

إعادة التشغيل آمنة: الهاتف مفتاح الزبون والسائق، و(datetime, customer_phone)
مفتاح الرحلة. الصفّ المعطوب يُرفض بسطر واضح ولا يوقف الباقي.
"""

import csv
import io
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from locations.models import ServiceArea
from ops.models import LegacyRide
from users.models import CustomerProfile, DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleCategory

PHONE_RE = re.compile(r"^\+9639\d{8}$")

# الأسماء العربية كما يكتبها موظّف واتساب — تُقبل إلى جانب الرمز.
CATEGORY_ALIASES = {
    "تكسي": "taxi", "تاكسي": "taxi",
    "خصوصي": "private", "خصوصى": "private", "خاصة": "private",
    "جيب": "jeep",
    "فان": "van", "ستاركس": "van",
    "ميكرو": "micro", "سرفيس": "micro", "ميكروباص": "micro",
    "تكتك": "tuktuk",
}

YES = {"نعم", "yes", "y", "1", "true", "آه", "اه"}

STATUS_ALIASES = {
    "تم": LegacyRide.Status.DONE, "تمّ": LegacyRide.Status.DONE,
    "done": LegacyRide.Status.DONE,
    "ألغيت": LegacyRide.Status.CANCELLED, "الغيت": LegacyRide.Status.CANCELLED,
    "cancelled": LegacyRide.Status.CANCELLED,
    "لم تخدم": LegacyRide.Status.UNSERVED, "لم تُخدَم": LegacyRide.Status.UNSERVED,
    "unserved": LegacyRide.Status.UNSERVED,
}


def normalize_phone(raw):
    """+9639XXXXXXXX من أيّ صيغة شائعة (09XX، 9XX، مسافات، شرطات)."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00963"):
        digits = digits[2:]
    if digits.startswith("09") and len(digits) == 10:
        digits = "963" + digits[1:]
    elif digits.startswith("9") and len(digits) == 9:
        digits = "963" + digits
    phone = "+" + digits
    if not PHONE_RE.match(phone):
        raise ValueError(f"رقم غير سوريّ أو غير مكتمل: {raw!r}")
    return phone


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    formats = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
               "%d/%m/%Y %H:%M", "%d/%m/%Y")
    for fmt in formats:
        try:
            value = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    raise ValueError(f"تاريخ غير مفهوم: {raw!r}")


def parse_int(raw, field):
    raw = (raw or "").strip()
    if raw == "":
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if digits == "":
        raise ValueError(f"{field} ليس عددًا: {raw!r}")
    return int(digits)


def resolve_category(raw):
    raw = (raw or "").strip()
    code = CATEGORY_ALIASES.get(raw, raw.lower())
    try:
        return VehicleCategory.objects.get(code=code)
    except VehicleCategory.DoesNotExist:
        available = ", ".join(VehicleCategory.objects.values_list("code", flat=True))
        raise ValueError(f"فئة مركبة غير معروفة: {raw!r} — المتاح: {available}")


def resolve_area(raw):
    raw = (raw or "").strip().upper()
    if raw in ("", "OUT"):
        return None
    try:
        return ServiceArea.objects.get(code=raw)
    except ServiceArea.DoesNotExist:
        raise ValueError(f"منطقة غير معروفة: {raw!r} (المتاح JAB / LAT / OUT)")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise CommandError(f"{path}: الملفّ فارغ أو بلا صفّ عناوين")
    return rows


class Command(BaseCommand):
    help = "يستورد دفتر واتساب (زبائن/سوّاق/رحلات CSV) إلى الخادم يوم الإطلاق."

    def add_arguments(self, parser):
        parser.add_argument("--customers", help="CSV صفحة «زبائن»")
        parser.add_argument("--drivers", help="CSV صفحة «سوّاق»")
        parser.add_argument("--rides", help="CSV صفحة «رحلات»")
        parser.add_argument("--dry-run", action="store_true",
                            help="افحص واطبع بلا كتابة.")

    def handle(self, *args, **options):
        if not any(options[k] for k in ("customers", "drivers", "rides")):
            raise CommandError("أعطِ ملفًّا واحدًا على الأقلّ: --customers/--drivers/--rides")

        self.dry = options["dry_run"]
        self.errors = []
        totals = {}

        with transaction.atomic():
            if options["customers"]:
                totals["زبائن"] = self._import_customers(read_csv(options["customers"]))
            if options["drivers"]:
                totals["سوّاق"] = self._import_drivers(read_csv(options["drivers"]))
            if options["rides"]:
                totals["رحلات"] = self._import_rides(read_csv(options["rides"]))
            if self.dry:
                transaction.set_rollback(True)

        for name, (created, updated) in totals.items():
            self.stdout.write(f"{name}: {created} جديد · {updated} محدَّث")
        for line in self.errors:
            self.stdout.write(self.style.WARNING("  ✗ " + line))
        if self.dry:
            self.stdout.write(self.style.NOTICE("dry-run: لم يُكتب شيء."))
        elif self.errors:
            self.stdout.write(self.style.WARNING(
                f"{len(self.errors)} صفًّا رُفض — صحّحها في الجدول وأعد التشغيل."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("تمّ الاستيراد بلا أخطاء."))

    # ------------------------------------------------------------------ زبائن
    def _import_customers(self, rows):
        created = updated = 0
        for index, row in enumerate(rows, start=2):
            try:
                phone = normalize_phone(row.get("phone"))
                name = (row.get("name") or "").strip()
                user, was_created = User.objects.get_or_create(
                    phone=phone,
                    defaults={"role": UserRole.CUSTOMER, "name": name, "is_verified": True},
                )
                if not was_created and name and not user.name:
                    user.name = name
                    user.save(update_fields=["name"])
                profile, _ = CustomerProfile.objects.get_or_create(user=user)
                prefs = dict(profile.preferences or {})
                prefs["whatsapp"] = {
                    "area": (row.get("area") or "").strip().upper() or None,
                    "usual_pickup": (row.get("usual_pickup") or "").strip(),
                    "first_seen": (row.get("first_seen") or "").strip(),
                    "rides": parse_int(row.get("rides"), "rides") or 0,
                    "last_ride": (row.get("last_ride") or "").strip(),
                    "source": (row.get("source") or "").strip(),
                    "saved_us": (row.get("saved_us") or "").strip().lower() in YES,
                    "channel": (row.get("channel") or "").strip().lower() in YES,
                }
                profile.preferences = prefs
                profile.save(update_fields=["preferences"])
                created += was_created
                updated += not was_created
            except (ValueError, KeyError) as exc:
                self.errors.append(f"زبائن سطر {index}: {exc}")
        return created, updated

    # ------------------------------------------------------------------ سوّاق
    def _import_drivers(self, rows):
        created = updated = 0
        for index, row in enumerate(rows, start=2):
            try:
                phone = normalize_phone(row.get("phone"))
                name = (row.get("name") or "").strip()
                category = resolve_category(row.get("category"))
                plate = (row.get("plate") or "").strip()
                if not plate:
                    raise ValueError("اللوحة فارغة")
                area = resolve_area(row.get("area"))
                founder_no = parse_int(row.get("founder_no"), "founder_no")
                complaints = parse_int(row.get("complaints"), "complaints") or 0

                user, was_created = User.objects.get_or_create(
                    phone=phone,
                    defaults={"role": UserRole.DRIVER, "name": name, "is_verified": True},
                )
                if user.role != UserRole.DRIVER:
                    user.role = UserRole.DRIVER
                    user.save(update_fields=["role"])
                if not was_created and name and not user.name:
                    user.name = name
                    user.save(update_fields=["name"])

                note = f"سائق مؤسّس #{founder_no}" if founder_no else ""
                if complaints:
                    note = (note + " · " if note else "") + f"شكاوى واتساب: {complaints}"
                driver, _ = DriverProfile.objects.get_or_create(
                    user=user, defaults={"status": DriverProfile.DriverStatus.PENDING},
                )
                fields = []
                if founder_no and (driver.founder_number != founder_no or not driver.commission_exempt):
                    driver.founder_number = founder_no
                    driver.commission_exempt = True
                    fields += ["founder_number", "commission_exempt"]
                if area is not None and driver.home_service_area_id != area.id:
                    driver.home_service_area = area
                    fields.append("home_service_area")
                if note and driver.verification_note != note:
                    driver.verification_note = note
                    fields.append("verification_note")
                if fields:
                    driver.save(update_fields=fields)

                Vehicle.objects.update_or_create(
                    plate_number=plate,
                    defaults={
                        "driver": driver, "type": category, "make": "", "model": "",
                        "year": timezone.now().year,
                        "color": (row.get("color") or "").strip(),
                        "seats": category.seats, "active": True,
                    },
                )
                created += was_created
                updated += not was_created
            except (ValueError, KeyError) as exc:
                self.errors.append(f"سوّاق سطر {index}: {exc}")
        return created, updated

    # ------------------------------------------------------------------ رحلات
    def _import_rides(self, rows):
        created = updated = 0
        for index, row in enumerate(rows, start=2):
            try:
                when = parse_date(row.get("datetime"))
                if when is None:
                    raise ValueError("datetime فارغ")
                customer_phone = normalize_phone(row.get("customer_phone"))
                driver_raw = (row.get("driver_phone") or "").strip()
                driver_phone = normalize_phone(driver_raw) if driver_raw else ""
                status_raw = (row.get("status") or "").strip()
                status = STATUS_ALIASES.get(status_raw) or STATUS_ALIASES.get(status_raw.lower())
                if status is None:
                    raise ValueError(f"status غير معروف: {status_raw!r} (تمّ / ألغيت / لم تُخدَم)")
                rating = parse_int(row.get("rating"), "rating")
                if rating is not None and not 1 <= rating <= 5:
                    raise ValueError(f"rating خارج 1–5: {rating}")

                _, was_created = LegacyRide.objects.update_or_create(
                    datetime=when, customer_phone=customer_phone,
                    defaults={
                        "driver_phone": driver_phone,
                        "origin": (row.get("from") or "").strip(),
                        "destination": (row.get("to") or "").strip(),
                        "area": (row.get("area") or "").strip().upper(),
                        "offers": parse_int(row.get("offers"), "offers") or 0,
                        "price": parse_int(row.get("price"), "price"),
                        "minutes_to_offer": parse_int(row.get("minutes_to_offer"), "minutes_to_offer"),
                        "status": status,
                        "fail_reason": (row.get("fail_reason") or "").strip(),
                        "rating": rating,
                        "customer": User.objects.filter(phone=customer_phone).first(),
                        "driver": (User.objects.filter(phone=driver_phone).first()
                                   if driver_phone else None),
                    },
                )
                created += was_created
                updated += not was_created
            except (ValueError, KeyError) as exc:
                self.errors.append(f"رحلات سطر {index}: {exc}")
        return created, updated
