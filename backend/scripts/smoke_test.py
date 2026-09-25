#!/usr/bin/env python3
"""
اختبار دخاني للباك إند عبر HTTP فقط — سووم تكسي.

الغرض: الإجابة عن سؤال واحد بعد ``docker compose up``:
«هل هذه البيئة تعمل فعلًا، وهل Swagger صالح للاستخدام؟»

يفحص أربع طبقات بالترتيب، ويتوقّف عند أوّل طبقة تنهار لأنّ ما بعدها
بلا معنى:

  1. الصحّة        — /api/v1/health/ يقول ok لقاعدة البيانات وريديس
  2. Swagger       — المخطّط يُولَّد، والصفحة تُفتح، **وملفّاتها الساكنة
                     تصل فعلًا**. هذه النقطة الأخيرة هي التي تسقط عادةً
                     تحت daphne وتُنتج «صفحة بيضاء» يظنّها الناس عطلًا
                     في drf-spectacular.
  3. المصادقة      — OTP كامل: طلب → رمز → توكن → /auth/me/
  4. دورة الرحلة   — إنشاء طلب → السائق أونلاين → عرض → اختيار →
                     وصل → بدأ → أنهى → تقييم

بلا أيّ اعتماد خارجي: المكتبة القياسية وحدها، فيعمل داخل الحاوية كما هو.

    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://localhost:8000
    python scripts/smoke_test.py --skip-ride
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------
# طباعة
# ---------------------------------------------------------------

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


PASS = 0
FAIL = 0
WARN = 0


def section(title: str) -> None:
    print()
    print(_c("1;36", f"── {title} " + "─" * max(0, 58 - len(title))))


def ok(msg: str, extra: str = "") -> None:
    global PASS
    PASS += 1
    print(f"  {_c('32', '✓')} {msg}" + (_c("90", f"  {extra}") if extra else ""))


def bad(msg: str, extra: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  {_c('31', '✗')} {msg}" + (_c("90", f"  {extra}") if extra else ""))


def warn(msg: str, extra: str = "") -> None:
    global WARN
    WARN += 1
    print(f"  {_c('33', '!')} {msg}" + (_c("90", f"  {extra}") if extra else ""))


# ---------------------------------------------------------------
# عميل HTTP
# ---------------------------------------------------------------


class Client:
    def __init__(self, base_url: str, timeout: int = 20):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None

    def request(self, method, path, data=None, token=None, raw=False, accept=None):
        url = path if path.startswith("http") else f"{self.base}{path}"
        body = None
        # صفحات Swagger وRedoc وملفّاتها الساكنة تُقدَّم HTML لا JSON،
        # وطلبها بـAccept: application/json يعيد 406 من DRF — وهو ردٌّ
        # صحيح يبدو عطلًا. لذلك يُمرَّر Accept صراحةً حيث يلزم.
        headers = {"Accept": accept or "application/json"}

        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"

        tok = token if token is not None else self.token
        if tok:
            headers["Authorization"] = f"Token {tok}"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
            ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        except Exception as exc:  # noqa: BLE001
            return 0, {"detail": f"{type(exc).__name__}: {exc}"}

        if raw or "json" not in ctype:
            return status, payload

        try:
            return status, json.loads(payload or b"{}")
        except json.JSONDecodeError:
            return status, {"raw": payload[:400].decode("utf-8", "replace")}

    def get(self, p, **kw):
        return self.request("GET", p, **kw)

    def post(self, p, data=None, **kw):
        return self.request("POST", p, data=data or {}, **kw)


def wait_for_server(client: Client, seconds: int = 90) -> bool:
    print(_c("90", f"  انتظار {client.base} ..."), end="", flush=True)
    deadline = time.time() + seconds
    while time.time() < deadline:
        status, _ = client.get("/api/v1/health/")
        if status:
            print(_c("90", " متاح."))
            return True
        print(_c("90", "."), end="", flush=True)
        time.sleep(2)
    print()
    return False


# ---------------------------------------------------------------
# 1. الصحّة
# ---------------------------------------------------------------


def check_health(c: Client) -> bool:
    section("1. الصحّة — قاعدة البيانات وريديس")

    status, body = c.get("/api/v1/health/")

    if status != 200:
        bad("GET /api/v1/health/", f"HTTP {status} — {body}")
        return False

    ok("GET /api/v1/health/", "HTTP 200")

    healthy = True
    for key, label in (("database", "PostgreSQL"), ("redis", "Redis")):
        value = body.get(key)
        if value == "ok":
            ok(f"{label} متصل")
        else:
            bad(f"{label} غير متصل", f"{key}={value!r}")
            healthy = False

    return healthy


# ---------------------------------------------------------------
# 2. Swagger
# ---------------------------------------------------------------


def check_swagger(c: Client) -> bool:
    section("2. Swagger — المخطّط والصفحة وملفّاتها الساكنة")

    # ---- المخطّط ----
    status, body = c.get("/api/schema/", raw=True)
    if status != 200:
        bad("GET /api/schema/", f"HTTP {status}")
        return False

    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)

    paths: dict = {}
    try:
        doc = json.loads(text)
        paths = doc.get("paths", {})
    except json.JSONDecodeError:
        # الصيغة الافتراضية YAML — نعدّ المسارات بتعبير نمطي
        for line in text.splitlines():
            m = re.match(r"^  (/[^:]+):\s*$", line)
            if m:
                paths[m.group(1)] = {}

    if not paths:
        bad("المخطّط لا يحوي أيّ مسار", "توليد OpenAPI فشل")
        return False

    ops = sum(
        1
        for spec in paths.values()
        for verb in (spec or {})
        if verb in {"get", "post", "put", "patch", "delete"}
    )
    ok(
        "GET /api/schema/",
        f"{len(paths)} مسار" + (f"، {ops} عملية" if ops else ""),
    )

    # تحذيرات التوليد تظهر داخل المخطّط نفسه
    if "Warning" in text[:4000] and "operationId" in text[:4000]:
        warn("المخطّط يحوي تحذيرات توليد", "راجع سجلّ الخادم")

    # ---- الصفحة ----
    status, page = c.get("/api/docs/", raw=True, accept="text/html")
    if status != 200:
        bad("GET /api/docs/", f"HTTP {status}")
        return False

    html = page.decode("utf-8", "replace") if isinstance(page, bytes) else str(page)
    ok("GET /api/docs/", f"HTTP 200، {len(html)} بايت")

    # ---- الملفّات الساكنة: النقطة الحاسمة ----
    #
    # daphne لا يخدم /static/ بنفسه. إن لم يُعالَج ذلك تعود الصفحة 200
    # بينما كلّ ملفّاتها 404، فتظهر بيضاء تمامًا. هذا ما نتحقّق منه هنا.
    assets = re.findall(r'(?:src|href)=["\']([^"\']*/static/[^"\']+)["\']', html)
    assets = list(dict.fromkeys(assets))

    if not assets:
        warn("لم أجد مراجع /static/ في الصفحة", "قد تكون الأصول مضمَّنة")
        return True

    broken = []
    for asset in assets[:8]:
        st, _ = c.get(asset, raw=True, accept="*/*")
        if st != 200:
            broken.append((asset, st))

    if broken:
        for asset, st in broken:
            bad("أصل Swagger مفقود", f"HTTP {st} — {asset}")
        bad(
            "واجهة Swagger ستظهر بيضاء",
            "الخادم لا يخدم /static/ — راجع SERVE_STATIC_FILES أو Nginx",
        )
        return False

    ok(f"ملفّات Swagger الساكنة تصل ({len(assets[:8])}/{len(assets)} فُحصت)")

    # ---- Redoc ----
    st, _ = c.get("/api/redoc/", raw=True, accept="text/html")
    (ok if st == 200 else warn)("GET /api/redoc/", f"HTTP {st}")

    return True


# ---------------------------------------------------------------
# 3. المصادقة
# ---------------------------------------------------------------


def login(c: Client, phone: str, device_id: str) -> str | None:
    status, body = c.post(
        "/api/v1/auth/request-otp/",
        {"phone": phone, "device_id": device_id},
        token="",
    )

    if status == 429:
        warn("تجاوز حدّ طلبات OTP", f"{phone} — {body.get('detail')}")
        return None

    if status != 201:
        bad("POST /auth/request-otp/", f"HTTP {status} — {body}")
        return None

    code = body.get("development_code")
    if not code:
        bad(
            "الاستجابة بلا development_code",
            "شغّل بـDEBUG=True أو اقرأ الرمز من سجلّ الحاوية",
        )
        return None

    ok("POST /auth/request-otp/", f"{phone} → رمز {code}")

    status, body = c.post(
        "/api/v1/auth/verify-otp/",
        {"phone": phone, "device_id": device_id, "code": code},
        token="",
    )

    if status != 200:
        bad("POST /auth/verify-otp/", f"HTTP {status} — {body}")
        return None

    token = body.get("token") or body.get("key")
    if not token:
        bad("لا توكن في استجابة verify-otp", str(body)[:200])
        return None

    ok("POST /auth/verify-otp/", "توكن مُصدَر")
    return token


def check_auth(c: Client, fallback: dict | None = None) -> dict:
    section("3. المصادقة — دورة OTP كاملة")

    fallback = fallback or {}
    tokens: dict = {}
    suffix = str(int(time.time()))[-6:]

    token = login(c, "+963990000101", f"smoke-customer-{suffix}")

    # حدّ 3 طلبات لكلّ رقم كلّ عشر دقائق سلوكٌ صحيح، لكنه يوقف الاختبار
    # عند تشغيله مرّتين متتاليتين. التوكن الجاهز من seed_mobile_demo يتيح
    # مواصلة فحص بقية التدفّق بدل التوقّف عند طبقة لم تفشل أصلًا.
    if not token and fallback.get("customer"):
        token = fallback["customer"]
        warn("استخدام توكن الزبون الجاهز", "بدل دورة OTP المحدودة")

    if not token:
        return tokens
    tokens["customer"] = token

    status, body = c.get("/api/v1/auth/me/", token=token)
    if status == 200:
        ok("GET /auth/me/", f"role={body.get('role')} phone={body.get('phone')}")
    else:
        bad("GET /auth/me/", f"HTTP {status} — {body}")

    # رفض بلا توكن — الصلاحيات تُفحص فعلًا لا بالنيّة
    status, _ = c.get("/api/v1/auth/me/", token="")
    if status in (401, 403):
        ok("طلب بلا توكن مرفوض", f"HTTP {status}")
    else:
        bad("طلب بلا توكن غير مرفوض", f"HTTP {status} — ثغرة صلاحيات")

    # رمز خاطئ يُرفض
    status, _ = c.post(
        "/api/v1/auth/verify-otp/",
        {"phone": "+963999999999", "device_id": f"bad-{suffix}", "code": "000000"},
        token="",
    )
    if status in (400, 429):
        ok("رمز OTP خاطئ مرفوض", f"HTTP {status}")
    else:
        bad("رمز OTP خاطئ غير مرفوض", f"HTTP {status}")

    driver_token = login(c, "+963990000102", f"smoke-driver-{suffix}")

    if not driver_token and fallback.get("driver"):
        driver_token = fallback["driver"]
        warn("استخدام توكن السائق الجاهز", "بدل دورة OTP المحدودة")

    if driver_token:
        tokens["driver"] = driver_token

    return tokens


# ---------------------------------------------------------------
# 4. دورة الرحلة
# ---------------------------------------------------------------


def check_ride(c: Client, tokens: dict) -> bool:
    section("4. دورة الرحلة — من الطلب إلى التقييم")

    cust = tokens.get("customer")
    drv = tokens.get("driver")

    if not cust or not drv:
        warn("تخطّي دورة الرحلة", "ينقص توكن الزبون أو السائق")
        return False

    # السائق أونلاين أوّلًا، وإلّا لم يجد الطلبُ مرشّحًا
    status, body = c.post("/api/v1/drivers/me/go-online/", token=drv)
    if status == 200:
        ok("POST /drivers/me/go-online/", f"online={body.get('online')}")
    else:
        warn("POST /drivers/me/go-online/", f"HTTP {status} — {body}")

    # إحداثيات جبلة.
    #
    # نقطة الالتقاط هي موقع سائق العرض بالضبط (35.90, 35.36) وليست قريبة
    # منه: تسجيل الوصول يشترط أن يكون السائق داخل TRIP_ARRIVAL_RADIUS_M
    # (200 م افتراضيًا)، وأيّ إزاحة أكبر تُرجع 400 — وهو سلوك صحيح يبدو
    # عطلًا في الاختبار. السائق الحقيقي يتحرّك عبر location.update على
    # الـWebSocket، وهذا اختبار HTTP.
    status, ride = c.post(
        "/api/v1/rides/",
        {
            "pickup_lat": 35.3600,
            "pickup_lng": 35.9000,
            "destination_lat": 35.3700,
            "destination_lng": 35.9300,
            "mode": "fast",
            "passenger_count": 1,
            "trip_category": "city",
        },
        token=cust,
    )

    if status not in (200, 201):
        bad("POST /rides/", f"HTTP {status} — {ride}")
        return False

    ride_id = ride.get("id") or (ride.get("ride") or {}).get("id")
    ok("POST /rides/", f"ride_id={ride_id} status={ride.get('status')}")

    if not ride_id:
        bad("لا معرّف رحلة في الاستجابة")
        return False

    # السائق يرى الطلب ضمن مرشّحيه
    status, cands = c.get("/api/v1/driver/rides/candidates/", token=drv)
    if status == 200:
        items = cands if isinstance(cands, list) else cands.get("results", cands)
        n = len(items) if isinstance(items, list) else "?"
        ok("GET /driver/rides/candidates/", f"{n} مرشّح")
    else:
        warn("GET /driver/rides/candidates/", f"HTTP {status} — {cands}")

    # عرض
    status, offer = c.post(
        f"/api/v1/driver/rides/{ride_id}/offers/",
        {"gross_fare": "5000.00", "eta_minutes": 5},
        token=drv,
    )
    if status not in (200, 201):
        bad("POST /driver/rides/{id}/offers/", f"HTTP {status} — {offer}")
        return False

    offer_id = offer.get("id")
    ok("POST /driver/rides/{id}/offers/", f"offer_id={offer_id}")

    status, offers = c.get(f"/api/v1/customer/rides/{ride_id}/offers/", token=cust)
    if status == 200:
        ok("GET /customer/rides/{id}/offers/")
    else:
        warn("GET /customer/rides/{id}/offers/", f"HTTP {status}")

    status, sel = c.post(
        f"/api/v1/customer/rides/{ride_id}/offers/{offer_id}/select/", token=cust
    )
    if status not in (200, 201):
        bad("اختيار العرض", f"HTTP {status} — {sel}")
        return False
    ok("POST .../offers/{id}/select/", "سائق مُختار")

    # دورة الحياة
    for path, label in (
        (f"/api/v1/driver/rides/{ride_id}/arrived/", "وصل السائق"),
        (f"/api/v1/driver/rides/{ride_id}/start/", "بدأت الرحلة"),
        (f"/api/v1/driver/rides/{ride_id}/complete/", "انتهت الرحلة"),
    ):
        status, body = c.post(path, token=drv)
        if status in (200, 201):
            ok(label, f"HTTP {status}")
        else:
            bad(label, f"HTTP {status} — {str(body)[:160]}")
            return False

    # التقييم
    status, body = c.post(
        f"/api/v1/trips/{ride_id}/rate/", {"score": 5, "comment": "smoke test"}, token=cust
    )
    if status in (200, 201):
        ok("POST /trips/{id}/rate/", f"HTTP {status}")
    else:
        warn("POST /trips/{id}/rate/", f"HTTP {status} — {str(body)[:160]}")

    # الدفعة تُنشأ تلقائيًا عند الإنهاء
    status, body = c.get(f"/api/v1/trips/{ride_id}/payment/", token=cust)
    if status == 200:
        ok("GET /trips/{id}/payment/", f"status={body.get('status')}")
    else:
        warn("GET /trips/{id}/payment/", f"HTTP {status}")

    return True


# ---------------------------------------------------------------
# 5. WebSocket
# ---------------------------------------------------------------


def check_websocket(base_url: str) -> bool:
    section("5. WebSocket — ترقية الاتصال عبر Channels")

    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        "GET /ws/connection-test/customer/1/ HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )

    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.sendall(handshake.encode())
            data = sock.recv(1024).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        bad("تعذّر فتح اتصال WebSocket", f"{type(exc).__name__}: {exc}")
        return False

    first = data.split("\r\n", 1)[0]

    if " 101 " in first:
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expected in data:
            ok("ترقية WebSocket نجحت", "HTTP 101 ومفتاح صحيح")
        else:
            warn("HTTP 101 لكن Sec-WebSocket-Accept غير مطابق")
        return True

    if " 403 " in first or " 401 " in first:
        ok("المسار حيّ ويرفض بلا مصادقة", first.strip())
        return True

    if " 404 " in first:
        bad("مسار WebSocket غير موجود", first.strip())
        return False

    warn("ردّ غير متوقّع على الترقية", first.strip())
    return False


# ---------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="اختبار دخاني لباك إند سووم تكسي")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--customer-token",
        default=os.environ.get("SMOKE_CUSTOMER_TOKEN", ""),
        help="توكن جاهز من seed_mobile_demo، يُستخدم إن حُدَّ معدّل OTP",
    )
    parser.add_argument(
        "--driver-token",
        default=os.environ.get("SMOKE_DRIVER_TOKEN", ""),
    )
    parser.add_argument("--skip-ride", action="store_true")
    parser.add_argument("--skip-ws", action="store_true")
    parser.add_argument("--wait", type=int, default=90, help="ثوانٍ انتظار الخادم")
    args = parser.parse_args()

    print(_c("1", f"\nاختبار دخاني — {args.base_url}"))

    c = Client(args.base_url)

    if not wait_for_server(c, args.wait):
        print(_c("31", "\n✗ الخادم لم يستجب. جرّب: docker compose -f compose.dev.yaml logs web\n"))
        return 2

    healthy = check_health(c)

    if not healthy:
        print(_c("31", "\n✗ الصحّة فشلت — لا معنى لما بعدها.\n"))
        return 1

    check_swagger(c)

    tokens = check_auth(
        c,
        {"customer": args.customer_token, "driver": args.driver_token},
    )

    if not args.skip_ride:
        check_ride(c, tokens)

    if not args.skip_ws:
        check_websocket(args.base_url)

    # ---- الخلاصة ----
    print()
    print(_c("1;36", "── الخلاصة " + "─" * 52))
    print(
        f"  {_c('32', str(PASS) + ' نجح')}   "
        f"{_c('33', str(WARN) + ' تحذير')}   "
        f"{_c('31', str(FAIL) + ' فشل')}"
    )
    print()

    if FAIL:
        print(_c("31", "✗ البيئة ليست جاهزة.\n"))
        return 1

    print(_c("32", f"✓ البيئة تعمل. Swagger: {args.base_url}/api/docs/\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
