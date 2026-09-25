# -*- coding: utf-8 -*-
"""
أسطولٌ آليّ للعرض والتجربة — عدّة سائقين يدورون في جبلة.

لماذا: الخريطة الحيّة وانزلاق السيارات و«الأقرب» و«اختر سيارتك» لا
تُرى بسائقٍ واحد واقف. هذا يُنشئ سائقين تجريبيّين (إن لم يوجدوا)، ويحرّك
كلّ واحد على حلقة حول مركز المدينة بنبضة موقع كلّ ثلاث ثوانٍ — كما يفعل
تطبيق السائق.

للتطوير فقط، داخل حاوية الخادم:
    docker compose -f compose.dev.yaml exec web python scripts/sim_fleet.py
    docker compose -f compose.dev.yaml exec web python scripts/sim_fleet.py --drivers 8 --accept

`--accept` يجعل السائقين يقبلون الدعوات تلقائيًّا بعد ثانيتين، فتُجرَّب
«الأقرب» و«اختر سيارتك» حتّى رحلة كاملة من المحاكي وحده.
"""
import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.request

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import websocket  # noqa: E402  websocket-client — من requirements.txt
from rest_framework.authtoken.models import Token  # noqa: E402

from users.models import DriverProfile, User, UserRole  # noqa: E402
from vehicles.models import Vehicle  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
WS_BASE = "ws://127.0.0.1:8000"

# مركز جبلة — نفس منطقة المحاكي.
CENTER_LAT, CENTER_LNG = 35.3617, 35.9275
BEAT_SECONDS = 3

CARS = [
    ("أبو علي", "Kia", "Rio", "أصفر"),
    ("سامر", "Hyundai", "Accent", "أبيض"),
    ("أبو خليل", "Toyota", "Corolla", "أصفر"),
    ("مازن", "Kia", "Cerato", "فضي"),
    ("رامي", "Hyundai", "Elantra", "أسود"),
    ("أبو محمد", "Chevrolet", "Aveo", "أصفر"),
    ("وسيم", "Peugeot", "405", "أبيض"),
    ("حسّان", "Saipa", "Saba", "أصفر"),
]


def say(msg):
    print(msg, flush=True)


def ensure_driver(index):
    name, make, model, color = CARS[index % len(CARS)]
    phone = "+96399000%04d" % (200 + index)
    user, _ = User.objects.get_or_create(
        phone=phone,
        defaults={"role": UserRole.DRIVER, "name": name, "is_verified": True},
    )
    driver, _ = DriverProfile.objects.get_or_create(
        user=user,
        defaults={"status": DriverProfile.DriverStatus.ACTIVE, "available_seats": 4},
    )
    if driver.status != DriverProfile.DriverStatus.ACTIVE:
        driver.status = DriverProfile.DriverStatus.ACTIVE
        driver.save(update_fields=["status"])
    if not Vehicle.objects.filter(driver=driver, active=True).exists():
        from vehicles.models import VehicleCategory
        category = VehicleCategory.objects.filter(is_active=True).order_by("sort_order").first()
        Vehicle.objects.create(
            driver=driver,
            type_id=category.code if category else "sedan",
            make=make, model=model, year=2015, color=color,
            plate_number="SIM-%03d" % index, seats=4, active=True,
        )
    # الوثائق الأربع موافَقًا عليها — وإلّا رفض الخادم «متاح» عن حقّ.
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from drivers.models import REQUIRED_DOCUMENT_TYPES, DocumentStatus, DriverDocument
    for doc_type in REQUIRED_DOCUMENT_TYPES:
        if not DriverDocument.objects.filter(
            driver=driver, type=doc_type, status=DocumentStatus.APPROVED
        ).exists():
            document = DriverDocument(
                driver=driver, type=doc_type, status=DocumentStatus.APPROVED,
                reviewed_at=timezone.now(),
            )
            document.file.save("sim-%s.txt" % doc_type, ContentFile(b"sim"), save=False)
            document.save()
    token, _ = Token.objects.get_or_create(user=user)
    return driver.id, token.key, name


def api(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Token " + token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


class Car(threading.Thread):
    def __init__(self, index, profile_id, token, name, accept, pace=1.0):
        super().__init__(daemon=True)
        self.profile_id, self.token, self.name, self.accept = profile_id, token, name, accept
        # كلّ سيارة على حلقة بنصف قطر وسرعة مختلفين، فلا تتحرّك كقطيع.
        self.radius_km = 0.35 + 0.25 * index
        self.phase = index * 0.9
        self.speed = pace * (0.035 + 0.01 * (index % 3)) * (1 if index % 2 else -1)

    def position(self, t):
        angle = self.phase + self.speed * t
        dlat = (self.radius_km / 111.0) * math.sin(angle)
        dlng = (self.radius_km / (111.0 * math.cos(math.radians(CENTER_LAT)))) * math.cos(angle)
        return CENTER_LAT + dlat, CENTER_LNG + dlng

    def run(self):
        lat, lng = self.position(0)
        code, res = api(self.token, "POST", "/drivers/me/go-online/", {"lat": lat, "lng": lng})
        if code >= 400:
            say("!! %s: go-online %s %s" % (self.name, code, res))
            return
        url = "%s/ws/driver/%d/?token=%s" % (WS_BASE, self.profile_id, self.token)
        ws = websocket.create_connection(url, timeout=10)
        say(">> %s يدور حول جبلة (%.1f كم)" % (self.name, self.radius_km))
        start = time.time()
        while True:
            lat, lng = self.position(time.time() - start)
            ws.send(json.dumps({"type": "location.update", "lat": lat, "lng": lng}))
            ws.send(json.dumps({"type": "heartbeat"}))
            deadline = time.time() + BEAT_SECONDS
            while time.time() < deadline:
                ws.settimeout(max(0.1, deadline - time.time()))
                try:
                    message = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    break
                except (ValueError, TypeError):
                    continue
                except Exception as exc:
                    # المقبس انقطع: نعيد الاتصال بدل الدوران الصامت إلى الأبد.
                    say("!! %s: انقطع المقبس (%s) — إعادة اتصال" % (self.name, exc))
                    time.sleep(2)
                    ws = websocket.create_connection(url, timeout=10)
                    break
                self.on_event(message)

    def on_event(self, message):
        kind = message.get("event_type") or message.get("type")
        data = message.get("payload") or message.get("data") or {}
        if kind in ("invitation.created", "invitation.received") and self.accept:
            # الحدث الدائم مغلَّف (تسلسل، كيان…) والعابر لا: نبحث عن المعرّف
            # في أيّ عمق بدل افتراض شكلٍ واحد.
            invitation_id = _find(message, "invitation_id")
            say(".. %s: دعوة %s — يقبل بعد ثانيتين" % (self.name, invitation_id))
            time.sleep(2)
            code, _ = api(self.token, "POST", "/driver/invitations/%s/accept/" % invitation_id)
            say(".. %s: قبول → %s" % (self.name, code))


def _find(node, key):
    if isinstance(node, dict):
        if node.get(key) is not None:
            return node[key]
        for value in node.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find(value, key)
            if found is not None:
                return found
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drivers", type=int, default=6)
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--pace", type=float, default=1.0,
                        help="مُعامل السرعة: 0.2 = خمس السرعة، أسهل للمس سيارة")
    args = parser.parse_args()

    cars = []
    for index in range(args.drivers):
        profile_id, token, name = ensure_driver(index)
        cars.append(Car(index, profile_id, token, name, args.accept, args.pace))
    for car in cars:
        car.start()
        time.sleep(0.3)
    say(">> %d سيارات تدور. Ctrl+C للإيقاف." % len(cars))
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
