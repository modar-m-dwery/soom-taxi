# -*- coding: utf-8 -*-
"""
سائقٌ آليّ — يلعب دور تطبيق السائق عبر الـAPI والمقبس.

لماذا: اختبار رحلة واحدة يحتاج طرفَين في اللحظة نفسها. هذا يحرّرك من
الحاجة إلى جهاز ثانٍ: تطلب أنت من المحاكي بصفتك زبونًا، وهذا يعرض ويصل
ويبدأ وينهي — فترى قوس الرحلة كاملًا وحدك.

يُشغَّل داخل حاوية الخادم لأنّ `websocket-client` مثبَّتة فيها:

    docker compose -f compose.dev.yaml exec web python scripts/sim_driver.py

المفتاح في هذا الملفّ — وهو ما لا تقوله الوثيقة:

  • `POST /drivers/me/go-online/` **يتجاهل الإحداثيات في الجسم**. قناة
    الموقع الوحيدة هي نبضة `location.update` على `/ws/driver/{id}/`.
  • والقاعدة لا تتحدّث من تلك النبضة إلّا كلّ خمس ثوانٍ
    (`DB_SYNC_MIN_INTERVAL_SECONDS`)، والفحوص الجغرافية تقرأ من القاعدة.
    لذلك نبعث نبضةً ونمهل قبل كلّ من «وصلت» و«أنهيت».

فسائقٌ يتبع الوثيقة حرفيًّا لا تصله طلبات أبدًا، ولا يعرف لماذا.
"""

import json
import sys
import threading
import time
import urllib.request

import websocket  # websocket-client — من requirements.txt

# ---------------------------------------------------------------- إعداد

BASE = "http://127.0.0.1:8000/api/v1"
WS_BASE = "ws://127.0.0.1:8000"
TOKEN = "e6a3debcec1b538dde7dbc778a82f8acf4873c41"   # السائق المزروع
PROFILE_ID = 1

# جبلة — نفس المنطقة التي يجب أن يكون فيها المحاكي.
LAT, LNG = 35.3617, 35.9275  # مركز مدينة جبلة. القيمة السابقة (35.36, 35.90) في البحر: «وصلت» تُرفض بـ2500 م

FARE = "6000.00"
ETA_MINUTES = 4
HEARTBEAT_SECONDS = 5          # §6.2، وهو أيضًا نافذة الكتابة للقاعدة
DB_SYNC_WINDOW = 6             # ننتظر أكثر من الخمس لنضمن وصول الموقع


def say(msg):
    print(msg, flush=True)


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Token " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw[:400]}


# ------------------------------------------------------------- النبضة

class Heartbeat(threading.Thread):
    """نبضة الموقع. هذه — لا جسم الطلب — هي ما يجعل السائق موجودًا."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.ws = None
        self.alive = True
        self.acks = 0

    def run(self):
        url = "%s/ws/driver/%d/?token=%s" % (WS_BASE, PROFILE_ID, TOKEN)
        try:
            self.ws = websocket.create_connection(url, timeout=10)
        except Exception as exc:
            say("!! تعذّر فتح المقبس: %s" % exc)
            say("   بلا نبضة لن تصل طلبات إلى السائق إطلاقًا.")
            return

        say(".. المقبس مفتوح، النبض كلّ %ds" % HEARTBEAT_SECONDS)
        while self.alive:
            try:
                self.ws.send(json.dumps(
                    {"type": "location.update", "lat": LAT, "lng": LNG}))
                self.ws.send(json.dumps({"type": "heartbeat"}))
                self.ws.settimeout(2)
                try:
                    while True:
                        frame = json.loads(self.ws.recv())
                        # الخادم يسمّي الحقل `event_type` لا `type` — بالاسم
                        # الخطأ لم يُحسب إقرارٌ قطّ وطُبع تحذيرٌ كاذب.
                        if frame.get("event_type", frame.get("type")) == "presence.ack":
                            self.acks += 1
                except Exception:
                    pass
            except Exception as exc:
                say("!! انقطع المقبس: %s" % exc)
                return
            time.sleep(HEARTBEAT_SECONDS)

    def stop(self):
        self.alive = False
        try:
            self.ws and self.ws.close()
        except Exception:
            pass


# -------------------------------------------------------------- الرحلة

def run_trip(ride_id, hb):
    say("\n== طلب #%d ==" % ride_id)

    code, offer = api("POST", "/driver/rides/%d/offers/" % ride_id,
                      {"gross_fare": FARE, "eta_minutes": ETA_MINUTES})
    if code >= 400:
        say("!! العرض رُفض (%d): %s" % (code, offer))
        return
    say(">> عرضٌ مقدَّم: %s ل.س، وصولٌ خلال %d دقائق" % (FARE, ETA_MINUTES))
    say("   اختره الآن من المحاكي...")

    # ننتظر أن يختار الزبون. `/driver/rides/candidates/` يفرغ منه حين يُختار.
    for _ in range(60):
        time.sleep(2)
        code, active = api("GET", "/me/active-ride/")
        if code < 400 and active and active.get("has_active_ride"):
            break
    else:
        say("!! لم يُختَر العرض خلال دقيقتين — انتهت مهلته على الأرجح.")
        return

    say("<< اختاره الزبون. الرحلة قائمة.")

    # الموقع من القاعدة لا من الجسم، والقاعدة متأخّرة خمس ثوانٍ.
    say(".. أمهل %ds حتى تصل النبضة إلى القاعدة قبل الفحص الجغرافيّ" % DB_SYNC_WINDOW)
    time.sleep(DB_SYNC_WINDOW)

    for label, path, body in [
        ("وصلت",  "/driver/rides/%d/arrived/" % ride_id, {"lat": LAT, "lng": LNG}),
        ("بدأت",  "/driver/rides/%d/start/" % ride_id,   None),
    ]:
        code, res = api("POST", path, body)
        if code >= 400:
            say("!! %s رُفضت (%d): %s" % (label, code, res))
            return
        say(">> %s" % label)
        time.sleep(2)

    say(".. الرحلة جارية، عشر ثوانٍ ثمّ الإنهاء")
    time.sleep(10)

    code, res = api("POST", "/driver/rides/%d/complete/" % ride_id,
                    {"lat": LAT, "lng": LNG})
    if code >= 400:
        say("!! الإنهاء رُفض (%d): %s" % (code, res))
        return
    say(">> أنهيت. الأجرة: %s" % json.dumps(res, ensure_ascii=False)[:200])

    # قبض النقد يؤكّده **السائق** وحده — الزبون لا يملك هذا الزرّ. بلا
    # هذا النداء كان الزبون يبقى على «بانتظار تأكيد السائق قبض المبلغ»
    # إلى الأبد بعد كلّ رحلة مع السائق الآليّ.
    time.sleep(3)
    code, pay = api("POST", "/trips/%d/payment/charge/" % ride_id, {})
    if code >= 400:
        say("!! تأكيد القبض رُفض (%d): %s" % (code, pay))
    else:
        say(">> قبضتُ النقد: %s" % (pay.get("status") if isinstance(pay, dict) else pay))
    say("   قيّم الرحلة من المحاكي.")


# ---------------------------------------------------------------- main

def main():
    say("سائق سوم الآليّ — جبلة (%.4f, %.4f)" % (LAT, LNG))

    code, res = api("POST", "/drivers/me/go-online/", {"lat": LAT, "lng": LNG})
    if code >= 400:
        say("!! go-online رُفض (%d): %s" % (code, res))
        say("   تحقّق أنّ السائق موثَّق وله مركبة مفعَّلة.")
        return 1
    say(">> متاح")

    hb = Heartbeat()
    hb.start()
    time.sleep(HEARTBEAT_SECONDS + 2)   # نبضةٌ واحدة على الأقلّ في القاعدة
    if hb.acks == 0:
        say("!! لم يصل أيّ presence.ack — الموقع لن يُقرأ، ولن تصل طلبات.")
    else:
        say(">> النبض يعمل (%d إقرارات)" % hb.acks)

    say("\nبانتظار طلب من المحاكي. اطلب رحلةً الآن.  (Ctrl+C للإنهاء)\n")
    seen = set()
    try:
        while True:
            code, body = api("GET", "/driver/rides/candidates/")
            if code >= 400:
                say("!! candidates (%d): %s" % (code, body))
                time.sleep(5)
                continue

            rows = body.get("results", body) if isinstance(body, dict) else body
            for ride in rows or []:
                rid = ride.get("id")
                if rid and rid not in seen:
                    seen.add(rid)
                    run_trip(rid, hb)
                    say("\nبانتظار الطلب التالي...\n")
            time.sleep(3)
    except KeyboardInterrupt:
        say("\n.. إنهاء")
    finally:
        hb.stop()
        api("POST", "/drivers/me/go-offline/")
        say(">> غير متاح")
    return 0


if __name__ == "__main__":
    sys.exit(main())
