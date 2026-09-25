# عند تعديل على الملف يجب حذف الكاش والكاش هنا ريديس لذا تحتاج تعليمة خاصة :
# python manage.py shell -c "from django.core.cache import cache; cache.clear(); print('CACHE CLEARED')"
# التنفيذ:
# python run_modern_taxi_tests.py
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import requests


BASE_URL = os.getenv("TAXI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20

PASS = 0
FAIL = 0
SKIP = 0


def utc_future(minutes=30):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def utc_past(minutes=10):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def phone():
    return "+96399" + "".join(random.choice("0123456789") for _ in range(9))


def req(method, path, *, token=None, expected=None, **kwargs):
    global PASS, FAIL

    url = BASE_URL + path
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Token {token}"
    headers.setdefault("Accept", "application/json")

    try:
        r = requests.request(
            method,
            url,
            headers=headers,
            timeout=TIMEOUT,
            **kwargs,
        )
    except Exception as exc:
        print(f"[FAIL] {method} {path} -> request error: {exc}")
        FAIL += 1
        return None

    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text

    ok = expected is None or r.status_code in set(expected)
    label = "PASS" if ok else "FAIL"

    if ok:
        PASS += 1
    else:
        FAIL += 1

    print(f"[{label}] {method} {path} -> {r.status_code}")
    if not ok:
        print(json.dumps(body, ensure_ascii=False, indent=2, default=str))

    return r


# =============================================================================
# === جديد: أدوات حماية السكربت من الانهيار الجزئي (Robustness helpers) ===
# =============================================================================

def safe_json_get(response, key, step_name=""):
    """
    يرجع القيمة المطلوبة من استجابة JSON، أو None مع رسالة واضحة بدل ما
    يكسر السكربت بالكامل بـ KeyError غامض عندما يفشل طلب سابق (401/400/...).
    """
    global FAIL

    if response is None:
        print(f"[ABORT] {step_name}: no response object (request failed earlier).")
        FAIL += 1
        return None

    try:
        data = response.json()
    except Exception:
        print(f"[ABORT] {step_name}: response is not JSON: {response.text}")
        FAIL += 1
        return None

    if not isinstance(data, dict) or key not in data:
        print(f"[ABORT] {step_name}: missing '{key}' in response: {data}")
        FAIL += 1
        return None

    return data[key]


def require_token(token, section_name):
    """
    يتأكد إن otp_login نجحت فعلاً قبل ما نكمل نستخدم التوكن. لو فشلت
    (غالبًا بسبب rate limiting)، بيوقف القسم الحالي فقط بدل ما يكسر
    باقي السكربت بطلبات 401 متتالية.
    """
    global FAIL

    if token is None:
        print(f"[ABORT SECTION] {section_name}: OTP login failed (likely rate-limited or invalid).")
        FAIL += 1
        return False

    return True


def clear_throttle_cache():
    """
    يمسح كاش الـ throttling (OTP rate limit وغيره) بين أقسام السكربت،
    عشان اختبارات قسم معيّن (مثل rate limit المتعمّد) ما تأثرش على باقي
    الأقسام اللي بتحتاج تسجل دخول مستخدمين جدد بنجاح.
    """
    shell("from django.core.cache import cache; cache.clear()")


# =============================================================================


def shell(code):
    """Run a Django shell command from the project root."""
    p = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    if p.returncode != 0:
        print("[SHELL ERROR]")
        print(p.stderr)
        raise RuntimeError("Django shell command failed")
    return p.stdout.strip()


def shell_json(code):
    out = shell(code)
    # django shell may emit extra lines in some environments; use last JSON line.
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    if not lines:
        raise RuntimeError("No JSON returned from Django shell")
    return json.loads(lines[-1])


def get_choice(model_expr, preferred=None):
    data = shell_json(
        f"""
import json
from {model_expr.rsplit('.', 1)[0]} import {model_expr.rsplit('.', 1)[1]}
print(json.dumps([x[0] for x in {model_expr.rsplit('.', 1)[1]}.choices]))
"""
    )
    if preferred in data:
        return preferred
    return data[0]


def get_constants():
    return shell_json(
        """
import json
from rides.models import RideMode, TripCategory
from vehicles.models import VehicleType
from drivers.models import DocumentType, REQUIRED_DOCUMENT_TYPES

def val(x):
    return getattr(x, "value", x)

print(json.dumps({
    "shared_mode": val(RideMode.SHARED),
    "standard_mode": val(RideMode.STANDARD),
    "city_category": val(TripCategory.CITY),
    "intercity_category": val(TripCategory.INTERCITY),
    "service_line_category": val(TripCategory.SERVICE_LINE),
    "recreational_category": val(TripCategory.RECREATIONAL),
    "vehicle_type": val(VehicleType.choices[0][0]),
    "required_docs": [val(x) for x in REQUIRED_DOCUMENT_TYPES],
}))
"""
    )


def get_or_create_admin_token():
    return shell_json(
        """
import json
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from users.models import UserRole

User = get_user_model()

admin = User.objects.filter(is_superuser=True).order_by("id").first()

if admin is None:
    phone = "+963990000001"
    admin, _ = User.objects.get_or_create(
        phone=phone,
        defaults={
            "name": "QA Admin",
            "role": UserRole.ADMIN,
            "is_verified": True,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        },
    )
else:
    changed = []
    if hasattr(UserRole, "ADMIN") and admin.role != UserRole.ADMIN:
        admin.role = UserRole.ADMIN
        changed.append("role")
    if not admin.is_staff:
        admin.is_staff = True
        changed.append("is_staff")
    if not admin.is_superuser:
        admin.is_superuser = True
        changed.append("is_superuser")
    if not admin.is_verified:
        admin.is_verified = True
        changed.append("is_verified")
    if not admin.is_active:
        admin.is_active = True
        changed.append("is_active")
    if changed:
        admin.save(update_fields=changed)

token, _ = Token.objects.get_or_create(user=admin)
print(json.dumps({"user_id": admin.id, "token": token.key}))
"""
    )


def otp_login(phone_number, device_id):
    r = req(
        "POST",
        "/api/v1/auth/request-otp/",
        expected=[201],
        json={
            "phone": phone_number,
            "device_id": device_id,
        },
    )
    if not r or r.status_code != 201:
        print(f"[WARN] otp_login: request-otp did not return 201 for {phone_number}; aborting login.")
        return None

    try:
        data = r.json()
    except Exception:
        print(f"[WARN] otp_login: request-otp response is not JSON for {phone_number}.")
        return None

    code = data.get("development_code")
    if not code:
        raise RuntimeError(
            "DEBUG OTP code was not returned. Run this test suite with DEBUG=True "
            "or provide a test SMS integration."
        )

    r2 = req(
        "POST",
        "/api/v1/auth/verify-otp/",
        expected=[200],
        json={
            "phone": phone_number,
            "device_id": device_id,
            "code": code,
        },
    )
    if not r2 or r2.status_code != 200:
        return None

    try:
        return r2.json()["token"]
    except Exception:
        return None


def set_driver_location(driver_id, lat=33.5138, lng=36.2765, fresh=True):
    age = "timezone.now()" if fresh else (
        "timezone.now() - timedelta(minutes=10)"
    )
    shell(
        f"""
from django.contrib.gis.geos import Point
from django.utils import timezone
from datetime import timedelta
from users.models import DriverProfile
p = DriverProfile.objects.get(id={driver_id})
p.current_location = Point({lng}, {lat}, srid=4326)
p.last_location_at = {age}
p.current_occupancy = 0
p.save(update_fields=["current_location", "last_location_at", "current_occupancy"])
"""
    )


def get_latest_id(model_path):
    return shell_json(
        f"""
import json
from {model_path.rsplit('.', 1)[0]} import {model_path.rsplit('.', 1)[1]}
Model = {model_path.rsplit('.', 1)[1]}
obj = Model.objects.order_by("-id").first()
print(json.dumps({{"id": obj.id if obj else None}}))
"""
    )["id"]


def main():
    global PASS, FAIL, SKIP

    print("=" * 80)
    print("MODERN TAXI - FULL API / BUSINESS FLOW TEST SUITE")
    print("=" * 80)
    print("Base URL:", BASE_URL)
    print()

    # === جديد: نبدأ بكاش نظيف حتى لو تشغيلة سابقة فشلت وسط الطريق ===
    clear_throttle_cache()

    constants = get_constants()
    print("Detected constants:")
    print(json.dumps(constants, ensure_ascii=False, indent=2))
    print()

    # ------------------------------------------------------------------
    # USERS / TOKENS
    # ------------------------------------------------------------------
    customer_phone = phone()
    customer_device = "qa-customer-" + str(random.randint(100000, 999999))

    driver_phone = phone()
    driver_device = "qa-driver-" + str(random.randint(100000, 999999))

    rejected_driver_phone = phone()
    rejected_driver_device = "qa-rejected-" + str(random.randint(100000, 999999))

    admin = get_or_create_admin_token()
    admin_token = admin["token"]

    print("=== 1-4 Authentication ===")
    customer_token = otp_login(customer_phone, customer_device)
    driver_token = otp_login(driver_phone, driver_device)
    rejected_driver_token = otp_login(
        rejected_driver_phone,
        rejected_driver_device,
    )

    if not (
        require_token(customer_token, "1-4 Authentication (customer)")
        and require_token(driver_token, "1-4 Authentication (driver)")
        and require_token(rejected_driver_token, "1-4 Authentication (rejected driver)")
    ):
        print("[FATAL] Could not obtain base tokens. Aborting entire suite.")
        print(f"RESULTS: PASS={PASS} FAIL={FAIL} SKIP={SKIP}")
        sys.exit(1)

    # TC: customer /me
    req(
        "GET",
        "/api/v1/auth/me/",
        token=customer_token,
        expected=[200],
    )

    # ------------------------------------------------------------------
    # BECOME DRIVER
    # ------------------------------------------------------------------
    print("\n=== 5-7 Driver onboarding ===")

    req(
        "POST",
        "/api/v1/auth/become-driver/",
        token=driver_token,
        expected=[200],
    )

    # rejected driver also becomes driver
    req(
        "POST",
        "/api/v1/auth/become-driver/",
        token=rejected_driver_token,
        expected=[200],
    )

    # Register main driver's vehicle
    vehicle_payload = {
        "type": constants["vehicle_type"],
        "make": "Toyota",
        "model": "Camry",
        "year": 2022,
        "color": "White",
        "plate_number": "QA-" + str(random.randint(100000, 999999)),
        "seats": 4,
    }

    r = req(
        "POST",
        "/api/v1/vehicles/",
        token=driver_token,
        expected=[201],
        json=vehicle_payload,
    )
    main_vehicle_id = safe_json_get(r, "id", "5-7 register main vehicle")
    if main_vehicle_id is None:
        print("[FATAL] Could not register main driver's vehicle. Aborting entire suite.")
        print(f"RESULTS: PASS={PASS} FAIL={FAIL} SKIP={SKIP}")
        sys.exit(1)

    # Activate it early: eligibility requires active vehicle.
    req(
        "POST",
        f"/api/v1/vehicles/{main_vehicle_id}/activate/",
        token=driver_token,
        expected=[200],
    )

    # Required docs
    submitted_doc_ids = []
    future_expiry = utc_future(minutes=365)
    for doc_type in constants["required_docs"]:
        fd, filename = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"QA test document: {doc_type}\n")

        with open(filename, "rb") as upload:
            r = req(
                "POST",
                "/api/v1/drivers/documents/",
                token=driver_token,
                expected=[201],
                files={
                    "file": (
                        os.path.basename(filename),
                        upload,
                        "text/plain",
                    )
                },
                data={
                    "type": doc_type,
                    "expires_at": future_expiry,
                },
            )
            doc_id = safe_json_get(r, "id", f"5-7 submit document ({doc_type})")
            if doc_id is not None:
                submitted_doc_ids.append(doc_id)

        os.unlink(filename)

    # ------------------------------------------------------------------
    # ADMIN DOCUMENT REVIEW
    # ------------------------------------------------------------------
    print("\n=== 8-12 Admin verification ===")

    r = req(
        "GET",
        "/api/v1/drivers/admin/documents/pending/",
        token=admin_token,
        expected=[200],
    )

    for doc_id in submitted_doc_ids:
        req(
            "POST",
            f"/api/v1/drivers/admin/documents/{doc_id}/review/",
            token=admin_token,
            expected=[200],
            json={
                "approve": True,
                "rejection_reason": "",
            },
        )

    req(
        "GET",
        "/api/v1/drivers/admin/pending/",
        token=admin_token,
        expected=[200],
    )

    driver_profile = shell_json(
        f"""
import json
from users.models import DriverProfile
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(phone="{driver_phone}")
p = DriverProfile.objects.get(user=u)
print(json.dumps({{"id": p.id, "user_id": u.id}}))
"""
    )
    driver_profile_id = driver_profile["id"]

    req(
        "POST",
        f"/api/v1/drivers/admin/{driver_profile_id}/verify/",
        token=admin_token,
        expected=[200],
        json={
            "approve": True,
            "verification_note": "QA approval",
        },
    )

    # ------------------------------------------------------------------
    # DRIVER AVAILABILITY
    # ------------------------------------------------------------------
    print("\n=== 13-15 Driver availability ===")
    set_driver_location(driver_profile_id, fresh=True)

    req(
        "GET",
        "/api/v1/auth/driver/profile/",
        token=driver_token,
        expected=[200],
    )

    req(
        "POST",
        "/api/v1/drivers/me/go-online/",
        token=driver_token,
        expected=[200],
    )

    # ------------------------------------------------------------------
    # BASIC RIDE + MATCHING
    # ------------------------------------------------------------------
    print("\n=== 16-20 Normal ride / offers ===")

    ride_payload = {
        "pickup_lat": 33.5138,
        "pickup_lng": 36.2765,
        "destination_lat": 33.5102,
        "destination_lng": 36.2913,
        "mode": constants["standard_mode"],
        "passenger_count": 1,
        "trip_category": constants["city_category"],
    }

    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=ride_payload,
    )
    normal_ride_id = safe_json_get(r, "id", "16-20 create normal ride")

    if normal_ride_id is not None:
        req(
            "GET",
            "/api/v1/driver/rides/candidates/",
            token=driver_token,
            expected=[200],
        )

        r = req(
            "POST",
            f"/api/v1/driver/rides/{normal_ride_id}/offers/",
            token=driver_token,
            expected=[201],
            json={
                "gross_fare": "25.50",
                "eta_minutes": 7,
            },
        )
        normal_offer_id = safe_json_get(r, "id", "16-20 submit offer")

        if normal_offer_id is not None:
            req(
                "GET",
                f"/api/v1/customer/rides/{normal_ride_id}/offers/",
                token=customer_token,
                expected=[200],
            )

            req(
                "POST",
                f"/api/v1/customer/rides/{normal_ride_id}/offers/{normal_offer_id}/select/",
                token=customer_token,
                expected=[200],
            )

            shell(
                f"""
from rides.models import RideRequest, RideStatus
ride = RideRequest.objects.get(id={normal_ride_id})
ride.status = RideStatus.COMPLETED
ride.save(update_fields=["status", "updated_at"])
"""
            )
    else:
        print("[SKIP] Skipping rest of section 16-20 due to earlier failure.")

    # ------------------------------------------------------------------
    # SHARED INSTANT
    # ------------------------------------------------------------------
    print("\n=== 21 Instant Shared ===")

    host_payload = {
        "pickup_lat": 33.5138,
        "pickup_lng": 36.2765,
        "destination_lat": 33.5102,
        "destination_lng": 36.2913,
        "mode": constants["shared_mode"],
        "passenger_count": 3,
        "trip_category": constants["city_category"],
    }

    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=host_payload,
    )
    host_ride_id = safe_json_get(r, "id", "21 create host ride")

    candidate1_phone = phone()
    candidate1_token = otp_login(
        candidate1_phone,
        "qa-shared-1-" + str(random.randint(100000, 999999)),
    )

    candidate2_phone = phone()
    candidate2_token = otp_login(
        candidate2_phone,
        "qa-shared-2-" + str(random.randint(100000, 999999)),
    )

    if (
        host_ride_id is not None
        and require_token(candidate1_token, "21 Instant Shared (candidate 1)")
        and require_token(candidate2_token, "21 Instant Shared (candidate 2)")
    ):
        candidate_payload = {
            **host_payload,
            "passenger_count": 1,
        }

        r = req(
            "POST",
            "/api/v1/rides/",
            token=candidate1_token,
            expected=[201],
            json=candidate_payload,
        )
        shared_candidate_1 = safe_json_get(r, "id", "21 create candidate 1 ride")

        r = req(
            "POST",
            "/api/v1/rides/",
            token=candidate2_token,
            expected=[201],
            json=candidate_payload,
        )
        shared_candidate_2 = safe_json_get(r, "id", "21 create candidate 2 ride")

        r = req(
            "POST",
            f"/api/v1/driver/rides/{host_ride_id}/offers/",
            token=driver_token,
            expected=[201],
            json={
                "gross_fare": "40.00",
                "eta_minutes": 8,
            },
        )
        shared_host_offer_id = safe_json_get(r, "id", "21 submit host offer")

        if shared_candidate_1 is not None and shared_host_offer_id is not None:
            r = req(
                "GET",
                f"/api/v1/customer/rides/{shared_candidate_1}/shared-offers/",
                token=candidate1_token,
                expected=[200],
            )

            offers1 = r.json() if r else []
            if offers1:
                join_id_1 = offers1[0]["id"]
                req(
                    "POST",
                    f"/api/v1/customer/shared-offers/{join_id_1}/accept/",
                    token=candidate1_token,
                    expected=[200],
                )

        if shared_candidate_2 is not None:
            # Candidate 2 should still have a pending request generated while
            # one seat was available; accepting it now should fail.
            r = req(
                "GET",
                f"/api/v1/customer/rides/{shared_candidate_2}/shared-offers/",
                token=candidate2_token,
                expected=[200],
            )

            offers2 = r.json() if r else []
            if offers2:
                join_id_2 = offers2[0]["id"]
                req(
                    "POST",
                    f"/api/v1/customer/shared-offers/{join_id_2}/accept/",
                    token=candidate2_token,
                    expected=[400],
                )
            else:
                print("[INFO] Shared insufficient-seat case produced no pending join request.")
    else:
        print("[SKIP] Skipping rest of section 21 due to earlier failure.")

    # ------------------------------------------------------------------
    # SCHEDULED SHARED CITY FLOW
    # ------------------------------------------------------------------
    print("\n=== 22 Scheduled Shared ===")

    scheduled_time = utc_future(minutes=90)

    scheduled_payload = {
        "pickup_lat": 33.5138,
        "pickup_lng": 36.2765,
        "destination_lat": 33.5102,
        "destination_lng": 36.2913,
        "mode": constants["shared_mode"],
        "passenger_count": 1,
        "scheduled_at": scheduled_time,
        "trip_category": constants["city_category"],
    }

    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=scheduled_payload,
    )
    scheduled_ride_id = safe_json_get(r, "id", "22 create scheduled ride")

    scheduled_trip_id = None

    if scheduled_ride_id is not None:
        r = req(
            "POST",
            f"/api/v1/driver/rides/{scheduled_ride_id}/offers/",
            token=driver_token,
            expected=[201],
            json={
                "gross_fare": "30.00",
                "eta_minutes": 10,
            },
        )
        scheduled_offer_id = safe_json_get(r, "id", "22 submit scheduled offer")

        if scheduled_offer_id is not None:
            req(
                "POST",
                f"/api/v1/customer/rides/{scheduled_ride_id}/offers/{scheduled_offer_id}/select/",
                token=customer_token,
                expected=[200],
            )

            scheduled_trip = shell_json(
                f"""
import json
from matching.models import ScheduledSharedTrip
trip = ScheduledSharedTrip.objects.filter(source_offer_id={scheduled_offer_id}).first()
print(json.dumps({{"id": trip.id if trip else None}}))
"""
            )
            scheduled_trip_id = scheduled_trip["id"]

    if scheduled_trip_id is not None:
        # A second scheduled shared ride attempts to find the city trip.
        sched2_phone = phone()
        sched2_token = otp_login(
            sched2_phone,
            "qa-sched2-" + str(random.randint(100000, 999999)),
        )

        if require_token(sched2_token, "22 Scheduled Shared (second rider)"):
            r = req(
                "POST",
                "/api/v1/rides/",
                token=sched2_token,
                expected=[201],
                json=scheduled_payload,
            )
            scheduled_ride_2 = safe_json_get(r, "id", "22 create second scheduled ride")

            if scheduled_ride_2 is not None:
                r = req(
                    "GET",
                    f"/api/v1/customer/rides/{scheduled_ride_2}/scheduled-shared-trips/",
                    token=sched2_token,
                    expected=[200],
                )

                if r and r.json():
                    req(
                        "POST",
                        f"/api/v1/customer/rides/{scheduled_ride_2}/scheduled-shared-trips/{scheduled_trip_id}/join/",
                        token=sched2_token,
                        expected=[200],
                    )

        shell(
            f"""
from rides.models import RideRequest, RideStatus
ride = RideRequest.objects.get(id={scheduled_ride_id})
ride.status = RideStatus.COMPLETED
ride.save(update_fields=["status", "updated_at"])
"""
        )
    else:
        print("[SKIP] Skipping rest of section 22 due to earlier failure.")

    # ------------------------------------------------------------------
    # PUBLISHED TRIPS
    # ------------------------------------------------------------------
    print("\n=== 23-24 Published Trips / Booking ===")

    published_time = utc_future(minutes=180)

    r = req(
        "POST",
        "/api/v1/driver/trips/publish/",
        token=driver_token,
        expected=[201],
        json={
            "vehicle_id": main_vehicle_id,
            "trip_category": constants["intercity_category"],
            "scheduled_at": published_time,
            "capacity": 4,
            "pickup_lat": 33.5138,
            "pickup_lng": 36.2765,
            "destination_lat": 34.7300,
            "destination_lng": 36.7000,
            "origin_city": "Damascus",
            "destination_city": "Homs",
            "price_per_seat": "10.00",
            "title": "QA Damascus - Homs",
            "description": "QA published trip",
            "features": ["AC", "WiFi"],
        },
    )
    published_trip_id = safe_json_get(r, "id", "23-24 publish trip")

    booked_ride_id = None

    if published_trip_id is not None:
        req(
            "GET",
            "/api/v1/trips/",
            expected=[200],
        )

        booking_customer_token = customer_token
        r = req(
            "POST",
            f"/api/v1/trips/{published_trip_id}/book/",
            token=booking_customer_token,
            expected=[201],
            json={
                "passenger_count": 2,
            },
        )
        booked_ride_id = safe_json_get(r, "ride_id", "23-24 book published trip")
    else:
        print("[SKIP] Skipping rest of section 23-24 due to earlier failure.")

    # ------------------------------------------------------------------
    # 25 CANCELLATION
    # ------------------------------------------------------------------
    print("\n=== 25 Cancellation ===")
    if booked_ride_id is not None:
        req(
            "POST",
            f"/api/v1/rides/{booked_ride_id}/cancel/",
            token=customer_token,
            expected=[200],
        )
    else:
        print("[SKIP] Skipping section 25 due to earlier failure.")

    # ------------------------------------------------------------------
    # 26 INVALID OTP
    # ------------------------------------------------------------------
    print("\n=== 26 Invalid OTP ===")
    bad_phone = phone()
    bad_device = "qa-invalid-otp-" + str(random.randint(100000, 999999))
    r = req(
        "POST",
        "/api/v1/auth/request-otp/",
        expected=[201],
        json={
            "phone": bad_phone,
            "device_id": bad_device,
        },
    )
    real_code = safe_json_get(r, "development_code", "26 invalid otp: request-otp")

    if real_code is not None:
        wrong_code = "000000" if real_code != "000000" else "999999"

        req(
            "POST",
            "/api/v1/auth/verify-otp/",
            expected=[400],
            json={
                "phone": bad_phone,
                "device_id": bad_device,
                "code": wrong_code,
            },
        )
    else:
        print("[SKIP] Skipping section 26 due to earlier failure.")

    # ------------------------------------------------------------------
    # 27 EXPIRED OTP
    #
    # === إصلاح الباج الأصلي ===
    # الكود القديم كان بيعدّل على object واحد في الذاكرة (بدون حفظ)،
    # ثم يعمل query جديد تماماً من القاعدة (نسخة غير متأثرة) ويحفظها.
    # النتيجة: الـ expires_at الفعلي في القاعدة لم يتغيّر أبداً، فنجح
    # التحقق (200) رغم أن الاختبار كان يتوقع 400.
    #
    # الإصلاح: استخدام نفس الـ object من البداية للتعديل والحفظ معاً،
    # داخل استدعاء shell واحد.
    # ------------------------------------------------------------------
    print("\n=== 27 Expired OTP ===")
    expired_phone = phone()
    expired_device = "qa-expired-otp-" + str(random.randint(100000, 999999))
    r = req(
        "POST",
        "/api/v1/auth/request-otp/",
        expected=[201],
        json={
            "phone": expired_phone,
            "device_id": expired_device,
        },
    )
    expired_code = safe_json_get(r, "development_code", "27 expired otp: request-otp")

    if expired_code is not None:
        shell(
            f"""
from django.utils import timezone
from users.models import OTPChallenge

obj = OTPChallenge.objects.filter(
    phone="{expired_phone}",
    device_id="{expired_device}",
    consumed_at__isnull=True,
).order_by("-created_at").first()

obj.expires_at = timezone.now()
obj.save(update_fields=["expires_at"])
"""
        )

        req(
            "POST",
            "/api/v1/auth/verify-otp/",
            expected=[400],
            json={
                "phone": expired_phone,
                "device_id": expired_device,
                "code": expired_code,
            },
        )
    else:
        print("[SKIP] Skipping section 27 due to earlier failure.")

    # ------------------------------------------------------------------
    # 28 OTP RATE LIMIT
    #
    # === إصلاح: نمسح كاش الـ throttle قبل الاختبار مباشرة ===
    # بدون هذا، الطلبات المتراكمة من كل الأقسام السابقة (customer, driver,
    # rejected_driver, candidate1/2, sched2, bad_phone, expired_phone) من
    # نفس الـ IP تخلي هذا القسم يسقط بدري جداً (كما حدث في التشغيلة
    # السابقة)، وتنهار كل الأقسام التالية بسبب توكنات فارغة.
    # ------------------------------------------------------------------
    print("\n=== 28 OTP Rate Limit ===")
    clear_throttle_cache()

    rate_phone = phone()
    for i in range(4):
        req(
            "POST",
            "/api/v1/auth/request-otp/",
            expected=[201] if i < 3 else [429],
            json={
                "phone": rate_phone,
                "device_id": f"qa-rate-{i}",
            },
        )

    # === إصلاح: نمسح الكاش تاني بعد القسم عشان ما يأثرش على الأقسام
    # التالية اللي بتحتاج تسجّل مستخدمين جدد بنجاح ===
    clear_throttle_cache()

    # ------------------------------------------------------------------
    # 29 DRIVER WITHOUT VEHICLE
    # ------------------------------------------------------------------
    print("\n=== 29 Driver without vehicle ===")
    no_vehicle_phone = phone()
    no_vehicle_token = otp_login(
        no_vehicle_phone,
        "qa-no-vehicle-" + str(random.randint(100000, 999999)),
    )

    if require_token(no_vehicle_token, "29 Driver without vehicle"):
        req(
            "POST",
            "/api/v1/auth/become-driver/",
            token=no_vehicle_token,
            expected=[200],
        )

        req(
            "POST",
            "/api/v1/drivers/me/go-online/",
            token=no_vehicle_token,
            expected=[400],
        )
    else:
        print("[SKIP] Skipping section 29 due to earlier failure.")

    # ------------------------------------------------------------------
    # 30 REJECTED DOCUMENT
    # ------------------------------------------------------------------
    print("\n=== 30 Driver with rejected document ===")
    rejected_profile = shell_json(
        f"""
import json
from django.contrib.auth import get_user_model
from users.models import DriverProfile
User = get_user_model()
u = User.objects.get(phone="{rejected_driver_phone}")
p = DriverProfile.objects.get(user=u)
print(json.dumps({{"id": p.id}}))
"""
    )["id"]

    rejected_vehicle_payload = {
        **vehicle_payload,
        "plate_number": "REJ-" + str(random.randint(100000, 999999)),
    }

    r = req(
        "POST",
        "/api/v1/vehicles/",
        token=rejected_driver_token,
        expected=[201],
        json=rejected_vehicle_payload,
    )
    rejected_vehicle_id = safe_json_get(r, "id", "30 register rejected-driver vehicle")

    if rejected_vehicle_id is not None:
        req(
            "POST",
            f"/api/v1/vehicles/{rejected_vehicle_id}/activate/",
            token=rejected_driver_token,
            expected=[200],
        )

        # submit all required docs, reject first
        first_doc = constants["required_docs"][0]
        fd, filename = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Rejected QA document\n")

        with open(filename, "rb") as upload:
            r = req(
                "POST",
                "/api/v1/drivers/documents/",
                token=rejected_driver_token,
                expected=[201],
                files={
                    "file": (
                        os.path.basename(filename),
                        upload,
                        "text/plain",
                    )
                },
                data={
                    "type": first_doc,
                    "expires_at": utc_future(minutes=365),
                },
            )
            rejected_doc_id = safe_json_get(r, "id", "30 submit rejected document")
        os.unlink(filename)

        if rejected_doc_id is not None:
            req(
                "POST",
                f"/api/v1/drivers/admin/documents/{rejected_doc_id}/review/",
                token=admin_token,
                expected=[200],
                json={
                    "approve": False,
                    "rejection_reason": "QA rejection",
                },
            )

            req(
                "POST",
                "/api/v1/drivers/me/go-online/",
                token=rejected_driver_token,
                expected=[400],
            )
    else:
        print("[SKIP] Skipping rest of section 30 due to earlier failure.")

    # ------------------------------------------------------------------
    # 31 EXPIRED DOCUMENT
    # ------------------------------------------------------------------
    print("\n=== 31 Expired document ===")
    expired_driver_phone = phone()
    expired_driver_token = otp_login(
        expired_driver_phone,
        "qa-exp-doc-" + str(random.randint(100000, 999999)),
    )

    if require_token(expired_driver_token, "31 Expired document"):
        req(
            "POST",
            "/api/v1/auth/become-driver/",
            token=expired_driver_token,
            expected=[200],
        )

        r = req(
            "POST",
            "/api/v1/vehicles/",
            token=expired_driver_token,
            expected=[201],
            json={
                **vehicle_payload,
                "plate_number": "EXP-" + str(random.randint(100000, 999999)),
            },
        )
        expired_vehicle_id = safe_json_get(r, "id", "31 register expired-doc vehicle")

        if expired_vehicle_id is not None:
            req(
                "POST",
                f"/api/v1/vehicles/{expired_vehicle_id}/activate/",
                token=expired_driver_token,
                expected=[200],
            )

            expired_docs = []
            for doc_type in constants["required_docs"]:
                fd, filename = tempfile.mkstemp(suffix=".txt")
                os.close(fd)
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"QA expired flow {doc_type}\n")

                with open(filename, "rb") as upload:
                    r = req(
                        "POST",
                        "/api/v1/drivers/documents/",
                        token=expired_driver_token,
                        expected=[201],
                        files={
                            "file": (
                                os.path.basename(filename),
                                upload,
                                "text/plain",
                            )
                        },
                        data={
                            "type": doc_type,
                            "expires_at": utc_future(minutes=365),
                        },
                    )
                    doc_id = safe_json_get(r, "id", f"31 submit document ({doc_type})")
                    if doc_id is not None:
                        expired_docs.append(doc_id)
                os.unlink(filename)

            for doc_id in expired_docs:
                req(
                    "POST",
                    f"/api/v1/drivers/admin/documents/{doc_id}/review/",
                    token=admin_token,
                    expected=[200],
                    json={
                        "approve": True,
                        "rejection_reason": "",
                    },
                )

            expired_profile = shell_json(
                f"""
import json
from django.contrib.auth import get_user_model
from users.models import DriverProfile
User = get_user_model()
u = User.objects.get(phone="{expired_driver_phone}")
p = DriverProfile.objects.get(user=u)
print(json.dumps({{"id": p.id}}))
"""
            )["id"]

            req(
                "POST",
                f"/api/v1/drivers/admin/{expired_profile}/verify/",
                token=admin_token,
                expected=[200],
                json={
                    "approve": True,
                    "verification_note": "Initial activation",
                },
            )

            # Now submit a NEW latest version with past expiration; service should
            # automatically return driver to PENDING/offline.
            expired_type = constants["required_docs"][0]
            fd, filename = tempfile.mkstemp(suffix=".txt")
            os.close(fd)
            with open(filename, "w", encoding="utf-8") as f:
                f.write("Newest expired document\n")

            with open(filename, "rb") as upload:
                req(
                    "POST",
                    "/api/v1/drivers/documents/",
                    token=expired_driver_token,
                    expected=[201],
                    files={
                        "file": (
                            os.path.basename(filename),
                            upload,
                            "text/plain",
                        )
                    },
                    data={
                        "type": expired_type,
                        "expires_at": utc_past(minutes=1),
                    },
                )
            os.unlink(filename)

            req(
                "POST",
                "/api/v1/drivers/me/go-online/",
                token=expired_driver_token,
                expected=[400],
            )
        else:
            print("[SKIP] Skipping rest of section 31 due to earlier failure.")
    else:
        print("[SKIP] Skipping section 31 due to earlier failure.")

    # ------------------------------------------------------------------
    # 32 INACTIVE DRIVER
    # ------------------------------------------------------------------
    print("\n=== 32 Inactive driver ===")
    req(
        "POST",
        f"/api/v1/drivers/admin/{driver_profile_id}/suspend/",
        token=admin_token,
        expected=[200],
        json={
            "reason": "QA suspension",
        },
    )

    req(
        "POST",
        "/api/v1/drivers/me/go-online/",
        token=driver_token,
        expected=[400],
    )

    # Re-activate main driver in DB for remaining matching edge tests.
    shell(
        f"""
from users.models import DriverProfile
p = DriverProfile.objects.get(id={driver_profile_id})
p.status = DriverProfile.DriverStatus.ACTIVE
p.online = True
p.save(update_fields=["status", "online"])
"""
    )
    set_driver_location(driver_profile_id, fresh=True)

    # ------------------------------------------------------------------
    # 33 STALE LOCATION
    # ------------------------------------------------------------------
    print("\n=== 33 Stale driver location ===")

    set_driver_location(driver_profile_id, fresh=False)

    stale_ride_payload = {
        "pickup_lat": 33.5138,
        "pickup_lng": 36.2765,
        "destination_lat": 33.5102,
        "destination_lng": 36.2913,
        "mode": constants["standard_mode"],
        "passenger_count": 1,
        "trip_category": constants["city_category"],
    }

    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=stale_ride_payload,
    )
    stale_ride_id = safe_json_get(r, "id", "33 create stale-location test ride")

    if stale_ride_id is not None:
        r = req(
            "GET",
            "/api/v1/driver/rides/candidates/",
            token=driver_token,
            expected=[200],
        )
        candidates = r.json() if r else []
        if any(item.get("id") == stale_ride_id for item in candidates):
            print("[FAIL] stale driver was returned in candidates")
            FAIL += 1
        else:
            print("[PASS] stale driver excluded from candidates")
            PASS += 1
    else:
        print("[SKIP] Skipping section 33 due to earlier failure.")

    set_driver_location(driver_profile_id, fresh=True)

    # ------------------------------------------------------------------
    # 34 INSUFFICIENT SEATS
    # ------------------------------------------------------------------
    print("\n=== 34 Insufficient seats ===")
    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json={
            **ride_payload,
            "passenger_count": 5,
        },
    )
    too_many_ride_id = safe_json_get(r, "id", "34 create over-capacity ride")

    if too_many_ride_id is not None:
        req(
            "POST",
            f"/api/v1/driver/rides/{too_many_ride_id}/offers/",
            token=driver_token,
            expected=[400],
            json={
                "gross_fare": "50.00",
                "eta_minutes": 10,
            },
        )
    else:
        print("[SKIP] Skipping section 34 due to earlier failure.")

    # ------------------------------------------------------------------
    # 35 EXPIRED OFFER
    # ------------------------------------------------------------------
    print("\n=== 35 Expired offer ===")
    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=ride_payload,
    )
    expired_offer_ride_id = safe_json_get(r, "id", "35 create ride")

    if expired_offer_ride_id is not None:
        r = req(
            "POST",
            f"/api/v1/driver/rides/{expired_offer_ride_id}/offers/",
            token=driver_token,
            expected=[201],
            json={
                "gross_fare": "20.00",
                "eta_minutes": 6,
            },
        )
        expired_offer_id = safe_json_get(r, "id", "35 submit offer")

        if expired_offer_id is not None:
            shell(
                f"""
from django.utils import timezone
from matching.models import RideOffer
o = RideOffer.objects.get(id={expired_offer_id})
from datetime import timedelta

o.expires_at = timezone.now() - timedelta(minutes=1)
o.save(update_fields=["expires_at"])
"""
            )

            req(
                "POST",
                f"/api/v1/customer/rides/{expired_offer_ride_id}/offers/{expired_offer_id}/select/",
                token=customer_token,
                expected=[409],
            )
    else:
        print("[SKIP] Skipping section 35 due to earlier failure.")

    # ------------------------------------------------------------------
    # 36 UNAVAILABLE OFFER
    # ------------------------------------------------------------------
    print("\n=== 36 Unavailable offer ===")
    r = req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[201],
        json=ride_payload,
    )
    unavailable_ride_id = safe_json_get(r, "id", "36 create ride")

    if unavailable_ride_id is not None:
        r = req(
            "POST",
            f"/api/v1/driver/rides/{unavailable_ride_id}/offers/",
            token=driver_token,
            expected=[201],
            json={
                "gross_fare": "21.00",
                "eta_minutes": 6,
            },
        )
        unavailable_offer_id = safe_json_get(r, "id", "36 submit offer")

        if unavailable_offer_id is not None:
            shell(
                f"""
from matching.models import RideOffer, OfferStatus
o = RideOffer.objects.get(id={unavailable_offer_id})
o.status = OfferStatus.CANCELLED
o.save(update_fields=["status", "updated_at"])
"""
            )

            req(
                "POST",
                f"/api/v1/customer/rides/{unavailable_ride_id}/offers/{unavailable_offer_id}/select/",
                token=customer_token,
                expected=[409],
            )
    else:
        print("[SKIP] Skipping section 36 due to earlier failure.")

    # ------------------------------------------------------------------
    # 38 EXPIRED SCHEDULED TRIP
    # ------------------------------------------------------------------
    print("\n=== 38 Expired scheduled trip ===")

    expired_published_time = utc_future(minutes=20)

    r = req(
        "POST",
        "/api/v1/driver/trips/publish/",
        token=driver_token,
        expected=[201],
        json={
            "vehicle_id": main_vehicle_id,
            "trip_category": constants["intercity_category"],
            "scheduled_at": expired_published_time,
            "capacity": 4,
            "pickup_lat": 33.5138,
            "pickup_lng": 36.2765,
            "destination_lat": 34.7300,
            "destination_lng": 36.7000,
            "origin_city": "Damascus",
            "destination_city": "Homs",
            "price_per_seat": "12.00",
            "title": "QA expiry trip",
            "features": [],
        },
    )
    expired_trip_id = safe_json_get(r, "id", "38 publish trip")

    if expired_trip_id is not None:
        shell(
            f"""
from django.utils import timezone
from matching.models import ScheduledSharedTrip
t = ScheduledSharedTrip.objects.get(id={expired_trip_id})
from datetime import timedelta

t.scheduled_at = timezone.now() - timedelta(minutes=1)
t.save(update_fields=["scheduled_at"])
"""
        )

        req(
            "POST",
            f"/api/v1/trips/{expired_trip_id}/book/",
            token=customer_token,
            expected=[400],
            json={
                "passenger_count": 1,
            },
        )
    else:
        print("[SKIP] Skipping section 38 due to earlier failure.")

    # ------------------------------------------------------------------
    # 39 RECREATIONAL VIA /rides/
    # ------------------------------------------------------------------
    print("\n=== 39 Recreational via /rides/ ===")
    req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[400],
        json={
            **ride_payload,
            "trip_category": constants["recreational_category"],
        },
    )

    # ------------------------------------------------------------------
    # 40 ROLE AUTHORIZATION
    # ------------------------------------------------------------------
    print("\n=== 40 Unauthorized role access ===")

    # Customer -> admin
    req(
        "GET",
        "/api/v1/drivers/admin/pending/",
        token=customer_token,
        expected=[403],
    )

    # Driver -> customer-only offers for another customer's ride
    if normal_ride_id is not None:
        req(
            "GET",
            f"/api/v1/customer/rides/{normal_ride_id}/offers/",
            token=driver_token,
            expected=[403],
        )
    else:
        print("[SKIP] Skipping driver->customer-only check (no normal_ride_id).")

    # Admin -> driver-only candidate list
    req(
        "GET",
        "/api/v1/driver/rides/candidates/",
        token=admin_token,
        expected=[403],
    )

    # No token
    req(
        "GET",
        "/api/v1/auth/me/",
        expected=[401],
    )

    # ------------------------------------------------------------------
    # 41 INVALID COORDINATES
    # ------------------------------------------------------------------
    print("\n=== 41 Invalid coordinates ===")
    req(
        "GET",
        "/api/v1/maps/route/",
        token=customer_token,
        expected=[400],
        params={
            "pickup_lat": "not-a-number",
            "pickup_lng": "36.2765",
            "destination_lat": "33.5102",
            "destination_lng": "36.2913",
        },
    )

    req(
        "POST",
        "/api/v1/rides/",
        token=customer_token,
        expected=[400],
        json={
            **ride_payload,
            "pickup_lat": "not-a-number",
        },
    )

    # ------------------------------------------------------------------
    # 42 ROUTING PROVIDER FAILURE
    # ------------------------------------------------------------------
    print("\n=== 42 Routing provider failure ===")

    # API-level failure would require changing settings inside the already
    # running server process. Instead we deterministically test the service
    # through Django shell with override_settings.
    result = shell_json(
        """
import json
from django.test import override_settings
from django.contrib.gis.geos import Point
from maps.services.routing import RoutingService, RoutingError

with override_settings(
    MAPS_ROUTING_BASE_URL="http://127.0.0.1:1",
    MAPS_ROUTING_TIMEOUT_SECONDS=1,
):
    RoutingService.BASE_URL = "http://127.0.0.1:1"
    try:
        RoutingService.route(
            Point(36.2765, 33.5138, srid=4326),
            Point(36.2913, 33.5102, srid=4326),
        )
        print(json.dumps({"ok": False, "error": "RoutingError was not raised"}))
    except RoutingError as exc:
        print(json.dumps({"ok": True, "message": str(exc)}))
"""
    )

    if result.get("ok"):
        print("[PASS] Routing service converts provider failure into RoutingError")
        PASS += 1
    else:
        print("[FAIL] Routing service failure handling")
        FAIL += 1

    print()
    print("=" * 80)
    print(f"RESULTS: PASS={PASS} FAIL={FAIL} SKIP={SKIP}")
    print("=" * 80)

    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
