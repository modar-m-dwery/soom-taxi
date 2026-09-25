import time

from presence.constants import (
    PresenceState,
    ENGAGEMENT_FIELDS,
    HEARTBEAT_FRESH_SECONDS,
    HEARTBEAT_STALE_SECONDS,
    LOCATION_FRESH_SECONDS,
    PRESENCE_KEY_PREFIX,
    SHARED_MODE,
    GEO_KEY,
    LAST_SEEN_KEY,
)
from presence.redis_client import get_redis

import logging

logger = logging.getLogger(__name__)

class PresenceError(Exception):
    pass


class PresenceService:
    """
    Driver Presence Engine.

    PostgreSQL/PostGIS يبقى المصدر الدائم لكل شيء (DriverProfile.current_location,
    online, current_occupancy...). هذه الطبقة لا تستبدله؛ هي طبقة سريعة فوقه
    (hot state) في Redis.

    عند فشل Redis: النظام يجب أن يستمر بالعمل عبر PostGIS (fallback)،
    هذه الخدمة لا تُستخدم كمصدر حقيقة دائم أبدًا.
    """

    # -----------------------------------------------------------
    # KEY HELPERS
    # -----------------------------------------------------------

    @staticmethod
    def _key(driver_id):
        return f"{PRESENCE_KEY_PREFIX}{driver_id}"

    @classmethod
    def _exists(cls, driver_id):
        return bool(get_redis().exists(cls._key(driver_id)))

    # -----------------------------------------------------------
    # GO ONLINE / OFFLINE
    # -----------------------------------------------------------

    @classmethod
    def _resolve_engagement(cls, driver_id):
        """
        الارتباط برحلة حقيقة دائمة في PostgreSQL لا مجرد علامة في Redis.

        سابقًا كانت go_online تكتب busy="0" دائمًا. وسائق ينقطع اتصاله وسط
        رحلة ثم يعود - وهذا يحدث كل يوم في شبكة الهاتف - كان يعود PRESENT
        فيظهر على الخريطة الحية كسيارة فارغة وهو يقلّ راكبًا فعلًا.

        الجواب كله عند EngagementResolver في تطبيق trips: هو وحده يرى الرحلات
        النشطة وأنماطها والمقاعد المحجوزة. نستورده هنا استيرادًا كسولًا لأن
        العكس (أن يعرف Presence بنية الرحلات) يقلب ترتيب الطبقات.
        """
        try:
            from trips.services.engagement import EngagementResolver

            return EngagementResolver.resolve(driver_id)
        except Exception:
            logger.exception("engagement resolve failed for driver %s", driver_id)
            return {"busy": True}

    @classmethod
    def go_online(cls, driver, engagement=None):
        """
        driver: instance من users.models.DriverProfile.

        engagement: اتركه None ليُشتقّ من القاعدة (السلوك الصحيح). مرّر {}
        صراحةً في اختبارات الحمل التي تستخدم سائقين وهميين، لتوفير استعلام
        لكل نداء.

        إصلاح مهم: لا نزرع driver.current_location في فهرس GEO إلا إذا كان
        last_location_at حديثًا فعلًا. سائق أغلق التطبيق أمس ثم ضغط Go Online
        اليوم يحمل current_location من الأمس؛ زرعها هنا مع last_heartbeat=now
        كان يجعله يظهر فورًا كـPRESENT في مكان لم يعد فيه. الآن يبقى
        UNAVAILABLE حتى وصول أول نبضة GPS حقيقية.
        """
        r = get_redis()
        now = time.time()

        if engagement is None:
            engagement = cls._resolve_engagement(driver.id)

        mapping = {
            "driver_id": driver.id,
            "online": "1",
            "last_heartbeat": now,
            "occupancy": driver.current_occupancy,
            "available_seats": driver.available_seats,
            "status": driver.status,
        }
        mapping.update(cls._engagement_mapping(engagement))

        # getattr: يبقي presence_load_test.FakeDriver يعمل حتى لو لم يعرّف الحقل
        last_location_at = getattr(driver, "last_location_at", None)

        location_is_fresh = (
            driver.current_location is not None
            and last_location_at is not None
            and (
                now - last_location_at.timestamp()
            ) <= LOCATION_FRESH_SECONDS
        )

        pipe = r.pipeline()
        pipe.hset(cls._key(driver.id), mapping=mapping)
        pipe.zadd(LAST_SEEN_KEY, {str(driver.id): now})

        if location_is_fresh:
            pipe.hset(
                cls._key(driver.id),
                mapping={
                    "lng": driver.current_location.x,
                    "lat": driver.current_location.y,
                    "last_location_at": last_location_at.timestamp(),
                },
            )
            pipe.geoadd(
                GEO_KEY,
                (driver.current_location.x, driver.current_location.y, str(driver.id)),
            )
        else:
            # موقع قديم أو غير موجود -> نمسحه صراحةً بدل تركه يخدع get_state
            pipe.hdel(cls._key(driver.id), "lng", "lat", "last_location_at")
            pipe.zrem(GEO_KEY, str(driver.id))

        pipe.execute()

    @classmethod
    def go_offline(cls, driver_id):
        r = get_redis()
        pipe = r.pipeline()
        pipe.hset(cls._key(driver_id), "online", "0")
        pipe.zrem(LAST_SEEN_KEY, str(driver_id))
        pipe.zrem(GEO_KEY, str(driver_id))
        pipe.execute()

    # -----------------------------------------------------------
    # HEARTBEAT (مستقل عن location، كما اتفقنا)
    # -----------------------------------------------------------

    @classmethod
    def heartbeat(cls, driver_id):
        """
        إصلاح فشل صامت: سابقًا كنا نتحقق فقط من وجود المفتاح. لكن بعد أن يمرّ
        sweep_stale_drivers على سائق ويضع online=0، يبقى المفتاح موجودًا -
        فكانت النبضة تُقبل وتردّ presence.ack بينما السائق ما زال OFFLINE فعليًا
        وغير موجود في drivers:geo. أي أن تطبيق السائق يظن أنه متصل ولا يصله أي
        طلب إلى الأبد.

        الآن نرفع PresenceError في هذه الحالة، وDriverRoomConsumer يعالجها
        أصلًا بإعادة go_online ضمنيًا (المسار موجود عنده بالفعل).
        """
        r = get_redis()
        key = cls._key(driver_id)

        online_flag = r.hget(key, "online")

        if online_flag is None:
            raise PresenceError(
                "Driver presence not initialized. Call go_online() first."
            )

        if online_flag != "1":
            raise PresenceError(
                "Driver presence was expired by sweep. Re-arm with go_online()."
            )

        now = time.time()

        pipe = r.pipeline()
        pipe.hset(key, "last_heartbeat", now)
        pipe.zadd(LAST_SEEN_KEY, {str(driver_id): now})
        pipe.execute()

    # -----------------------------------------------------------
    # LOCATION UPDATE
    # -----------------------------------------------------------

    @classmethod
    def update_location(
        cls,
        driver_id,
        lng,
        lat,
        speed=None,
        heading=None,
        accuracy=None,
        source="app",
    ):
        """
        تحديث موقع لحظي. لا يكتب إلى PostgreSQL هنا (سياسة الـbatching في
        DriverRoomConsumer). location update يُحسب أيضًا كـheartbeat ضمنيًا.

        إضافة: source ضمن quality metadata (نقطة #20 في خطة المرحلة 6) -
        يفرّق لاحقًا بين GPS حقيقي وموقع مُدخل يدويًا/محاكى، وهو مدخل أساسي
        لكشف الاحتيال في المرحلة 11.
        """
        r = get_redis()
        now = time.time()

        pipe = r.pipeline()
        pipe.hset(
            cls._key(driver_id),
            mapping={
                "lng": lng,
                "lat": lat,
                "speed": speed if speed is not None else "",
                "heading": heading if heading is not None else "",
                "accuracy": accuracy if accuracy is not None else "",
                "source": source or "",
                "last_location_at": now,
                "last_heartbeat": now,
            },
        )
        pipe.geoadd(GEO_KEY, (lng, lat, str(driver_id)))
        pipe.zadd(LAST_SEEN_KEY, {str(driver_id): now})
        pipe.execute()

    # -----------------------------------------------------------
    # OCCUPANCY / BUSY
    # -----------------------------------------------------------

    @classmethod
    def sync_occupancy(cls, driver_id, occupancy, available_seats):
        if not cls._exists(driver_id):
            return
        get_redis().hset(
            cls._key(driver_id),
            mapping={"occupancy": occupancy, "available_seats": available_seats},
        )

    @classmethod
    def sync_from_driver(cls, driver):
        """
        دفعة مزامنة واحدة من DriverProfile (المصدر الدائم) إلى Redis.
        تُستدعى عند أي تغيير إداري: تفعيل/تعطيل مركبة، تغيير السعة،
        إيقاف السائق، قبول/رفض التوثيق. بدونها تبقى قيم Redis من لحظة
        go_online فقط، وهذا يخالف بند الـchecklist في الوثيقة:
        "عدد الركاب والمقاعد المتاحة يتحدثان مع آخر heartbeat صالح".
        """
        if not cls._exists(driver.id):
            return
        get_redis().hset(
            cls._key(driver.id),
            mapping={
                "occupancy": driver.current_occupancy,
                "available_seats": driver.available_seats,
                "status": driver.status,
            },
        )

    @classmethod
    def set_busy(cls, driver_id, busy: bool):
        """
        لا ننشئ مفتاحًا جديدًا لسائق ليس في Presence أصلًا - وإلا نترك في Redis
        مفاتيح يتيمة بحقل واحد وبلا TTL.

        بقيت كما هي للتوافق مع النداءات القديمة. المسار الصحيح بعد المرحلة 8ب
        هو set_engagement، لأن "مشغول" وحدها لم تعد تصف الحالة: سائق مشترك
        فيه مقعد فارغ ليس مشغولًا وليس متاحًا للجميع.
        """
        if not cls._exists(driver_id):
            return
        cls.set_engagement(driver_id, {"busy": bool(busy)} if busy else {})

    # -----------------------------------------------------------
    # ENGAGEMENT - الارتباط برحلة (المرحلة 8ب)
    # -----------------------------------------------------------

    @staticmethod
    def _engagement_mapping(engagement):
        """
        قاموس واحد يُكتب دفعة واحدة. نكتب كل الحقول في كل مرة - بما فيها
        الفارغة - حتى لا تبقى بقايا حالة سابقة تتناقض مع الحالية، مثل
        dest_cell قديمة على سائق صار مشغولًا برحلة فردية.
        """
        engagement = engagement or {}

        free_seats = engagement.get("free_seats")

        return {
            "busy": "1" if engagement.get("busy") else "0",
            "sharing": "1" if engagement.get("sharing") else "0",
            "trip_mode": engagement.get("trip_mode") or "",
            "dest_cell": engagement.get("dest_cell") or "",
            "free_seats": "" if free_seats is None else int(free_seats),
        }

    @classmethod
    def set_engagement(cls, driver_id, engagement=None):
        """
        engagement: dict من EngagementResolver، أو {} لتحرير السائق تمامًا.
        """
        if not cls._exists(driver_id):
            return

        get_redis().hset(
            cls._key(driver_id),
            mapping=cls._engagement_mapping(engagement),
        )

    @classmethod
    def clear_engagement(cls, driver_id):
        cls.set_engagement(driver_id, {})

    # -----------------------------------------------------------
    # STATE RESOLUTION - قلب المرحلة 6
    # -----------------------------------------------------------

    @classmethod
    def get_snapshot(cls, driver_id):
        return get_redis().hgetall(cls._key(driver_id))

    @classmethod
    def get_state(cls, driver_id):
        """
        صار مجرد غلاف حول _resolve_state_from_snapshot. سابقًا كان المنطق
        مكتوبًا مرتين حرفيًا (هنا وفي النسخة bulk)، وأي تعديل مستقبلي على أحدهما
        كان سيجعل Matching وMarketplace يعطيان إجابتين مختلفتين لنفس السائق -
        وهو بالضبط ما تمنعه نقطة #9 في الخطة.
        """
        return cls._resolve_state_from_snapshot(cls.get_snapshot(driver_id))

    @classmethod
    def _resolve_state_from_snapshot(cls, data, now=None):
        if not data or data.get("online") != "1":
            return PresenceState.OFFLINE

        now = now if now is not None else time.time()

        heartbeat_age = now - float(data.get("last_heartbeat") or 0)

        if heartbeat_age > HEARTBEAT_STALE_SECONDS:
            return PresenceState.OFFLINE

        # ملاحظة تصميمية مقصودة: BUSY تُفحص قبل STALE. سائق مرتبط برحلة نشطة
        # لا يُعرض كخيار في أي حال، والانقطاع أثناء الرحلة يعالجه
        # sweep_stale_driver_presence ببث driver.offline لغرفة تلك الرحلة.
        if data.get("busy") == "1":
            return PresenceState.BUSY

        if heartbeat_age > HEARTBEAT_FRESH_SECONDS:
            return PresenceState.STALE

        # جديد: صلاحية الموقع، وليس النبض فقط
        last_location_at = data.get("last_location_at")

        if not last_location_at:
            return PresenceState.UNAVAILABLE

        if (now - float(last_location_at)) > LOCATION_FRESH_SECONDS:
            return PresenceState.UNAVAILABLE

        # SHARING تأتي هنا لا مع BUSY في الأعلى، والفرق جوهري: السائق المشغول
        # لا يُعرض أصلًا فلا يضرّ أن تكون بياناته قديمة، أما المشارك فسيُرسَم
        # على الخريطة - وسيارة مرسومة بموقع عمره خمس دقائق أسوأ من سيارة
        # غير مرسومة. لذلك تمرّ أولًا من فحصَي النبض والموقع.
        if data.get("sharing") == "1":
            # المقعد الفارغ هو ما يجعلها SHARING لا BUSY. لو امتلأت السيارة
            # بينما الحقل sharing ما زال مكتوبًا - سباق نظري بين حجز مقعد
            # وكتابة الحالة - نرجّح الامتلاء ونعتبره مشغولًا. الخطأ في هذا
            # الاتجاه يفوّت مطابقة، والخطأ في الاتجاه الآخر يبيع مقعدًا
            # غير موجود.
            try:
                free_seats = int(float(data.get("free_seats") or 0))
            except ValueError:
                free_seats = 0

            return PresenceState.SHARING if free_seats > 0 else PresenceState.BUSY

        try:
            available_seats = int(float(data.get("available_seats") or 0))
            occupancy = int(float(data.get("occupancy") or 0))
        except ValueError:
            return PresenceState.UNAVAILABLE

        if (available_seats - occupancy) <= 0:
            return PresenceState.UNAVAILABLE

        return PresenceState.PRESENT

    @classmethod
    def is_available(cls, driver_id, for_mode=None):
        """
        التعريف الموحّد لـ"Available Driver" الذي تستخدمه
        Matching / Marketplace / Nearby Vehicles / Admin Live Map معًا.

        for_mode غيّر السؤال من "هل هو متاح؟" إلى "هل هو متاح لهذا الطلب؟"،
        وهو تغيير جوهري لا تجميلي: سائق على رحلة مشتركة بمقعد فارغ متاح
        لراكب مشترك وغير متاح لراكب يريد سيارة لنفسه. الجواب واحد لا يكفي.

        تركه None يعني "الطلب العادي": PRESENT فقط. أي نداء قديم لم يُعدَّل
        يبقى إذن على سلوكه السابق تمامًا، ولا ينكسر شيء.
        """
        state = cls.get_state(driver_id)

        if state == PresenceState.PRESENT:
            return True

        if state == PresenceState.SHARING:
            return for_mode == SHARED_MODE

        return False

    @classmethod
    def get_remaining_seats(cls, driver_id, snapshot=None):
        """المقاعد المتاحة كما يراها Presence - تحتاجها حمولة الماركت بليس."""
        data = snapshot if snapshot is not None else cls.get_snapshot(driver_id)
        try:
            return max(
                int(float(data.get("available_seats") or 0))
                - int(float(data.get("occupancy") or 0)),
                0,
            )
        except (ValueError, AttributeError):
            return 0

    # -----------------------------------------------------------
    # NEARBY QUERY عبر Redis GEO
    # -----------------------------------------------------------

    @classmethod
    def get_nearby_driver_ids(cls, lng, lat, radius_km, limit=50):
        raw = get_redis().geosearch(
            GEO_KEY,
            longitude=lng,
            latitude=lat,
            radius=radius_km,
            unit="km",
            count=limit,
            sort="ASC",
        )
        return [int(driver_id) for driver_id in raw]

    @classmethod
    def get_available_nearby_driver_ids(cls, lng, lat, radius_km, limit=50, for_mode=None):
        """
        نسخة بسيطة (round-trip لكل مرشح). للأعداد الكبيرة استخدم
        get_available_nearby_with_snapshots.
        """
        candidates = cls.get_nearby_driver_ids(lng, lat, radius_km, limit=limit * 2)
        return [
            driver_id for driver_id in candidates
            if cls.is_available(driver_id, for_mode=for_mode)
        ][:limit]

    # -----------------------------------------------------------
    # BULK SNAPSHOTS - جزء C
    # -----------------------------------------------------------

    @classmethod
    def get_snapshots_bulk(cls, driver_ids):
        if not driver_ids:
            return {}

        pipe = get_redis().pipeline()

        for driver_id in driver_ids:
            pipe.hgetall(cls._key(driver_id))

        results = pipe.execute()

        return {
            driver_id: snapshot
            for driver_id, snapshot in zip(driver_ids, results)
        }

    @classmethod
    def get_available_nearby_with_snapshots(
        cls, lng, lat, radius_km, limit=50, for_mode=None
    ):
        """
        النسخة الموصى بها لواجهات الماركت بليس/الخريطة الحية:
        GEOSEARCH واحد + pipeline واحد + فلترة في الذاكرة.

        for_mode="shared" يضيف السيارات المشتركة ذات المقعد الفارغ إلى
        النتيجة، ومعها dest_cell الخشنة وعدد المقاعد - وهو كل ما تحتاجه
        طبقة التوافق أعلاه للفلترة.

        ما لا يخرج من هنا أبدًا: وجهة الركّاب الحاليين بإحداثيات دقيقة.
        هي غير مخزَّنة في Redis أصلًا، لا محجوبة عند العرض - الفرق أن
        الخصوصية هنا خاصية بنيوية لا انضباط عند كل استدعاء.
        """
        candidate_ids = cls.get_nearby_driver_ids(lng, lat, radius_km, limit=limit * 3)

        if not candidate_ids:
            return []

        snapshots = cls.get_snapshots_bulk(candidate_ids)
        now = time.time()

        acceptable = {PresenceState.PRESENT}

        if for_mode == SHARED_MODE:
            acceptable.add(PresenceState.SHARING)

        result = []
        for driver_id in candidate_ids:
            data = snapshots.get(driver_id) or {}
            state = cls._resolve_state_from_snapshot(data, now=now)

            if state not in acceptable:
                continue

            result.append(
                {
                    "driver_id": driver_id,
                    "lng": float(data.get("lng")) if data.get("lng") else None,
                    "lat": float(data.get("lat")) if data.get("lat") else None,
                    "heading": data.get("heading") or None,
                    "available_seats": cls.get_remaining_seats(driver_id, snapshot=data),
                    "state": state,
                    # حقول المشاركة: فارغة لسائق غير مرتبط برحلة مشتركة
                    "is_sharing": state == PresenceState.SHARING,
                    "trip_mode": data.get("trip_mode") or None,
                    "dest_cell": data.get("dest_cell") or None,
                }
            )

            if len(result) >= limit:
                break

        return result

    # -----------------------------------------------------------
    # ACTIVE CELL (الجزء G)
    # -----------------------------------------------------------

    @classmethod
    def get_current_cell(cls, driver_id):
        return get_redis().hget(cls._key(driver_id), "cell_id")

    @classmethod
    def set_current_cell(cls, driver_id, cell_id):
        r = get_redis()
        if cell_id is None:
            r.hdel(cls._key(driver_id), "cell_id")
        else:
            r.hset(cls._key(driver_id), "cell_id", cell_id)

    # -----------------------------------------------------------
    # SWEEP: يُستدعى دوريًا من Celery beat
    # -----------------------------------------------------------

    @classmethod
    def sweep_stale_drivers(cls):
        """
        يبحث عن سائقين تجاوز آخر ظهور لهم HEARTBEAT_STALE_SECONDS ويخرجهم من
        الفهارس، ويرجّع قائمة IDs للمستدعي (presence.tasks) لمزامنة PostgreSQL
        وبثّ driver.offline.

        إصلاح سباق: بين قراءة ZRANGEBYSCORE وتنفيذ الـpipeline قد يصل heartbeat
        جديد من سائق كان على حافة المهلة، فنُطفئه ظلمًا ويفقد رحلته الحالية.
        لذلك نعيد قراءة last_heartbeat لكل مرشح قبل إطفائه، ونستثني من عاد للحياة.
        النافذة تصبح ميلي ثانية بدل دورة كاملة، وهو تحسّن كافٍ عمليًا دون Lua.
        """
        stale = cls.stale_candidates(HEARTBEAT_STALE_SECONDS)

        if not stale:
            return []

        return cls.mark_offline([driver_id for driver_id, _ in stale])

    @classmethod
    def stale_candidates(cls, stale_seconds):
        """
        من تجاوز صمتُه `stale_seconds`، مع آخر نبضة لكلّ منهم.

        فُصلت عن الكنس لأنّ المهل صارت لكلّ مدينة: المستدعي يقرأ بأقسى مهلة
        ممكنة ليجمع كلّ المرشّحين، ثمّ يُسقط من لم يتجاوز مهلة مدينته هو.
        والفصل يُبقي طبقة الحضور جاهلة بالمناطق — وهي يجب أن تبقى كذلك، فهي
        تحتها لا فوقها، وإلّا صار الاستيراد دائريًّا عند أوّل توسّع.

        النتيجة أزواج (id, آخر نبضة) لا معرّفات فقط: القرار الثاني يحتاج
        الرقم نفسه لا مجرّد «تجاوز أم لا».
        """
        r = get_redis()
        cutoff = time.time() - stale_seconds

        candidate_ids = r.zrangebyscore(LAST_SEEN_KEY, "-inf", cutoff)

        if not candidate_ids:
            return []

        pipe = r.pipeline()
        for driver_id in candidate_ids:
            pipe.hget(cls._key(int(driver_id)), "last_heartbeat")
        heartbeats = pipe.execute()

        return [
            (int(driver_id), float(heartbeat or 0))
            for driver_id, heartbeat in zip(candidate_ids, heartbeats)
            if float(heartbeat or 0) <= cutoff
        ]

    @classmethod
    def mark_offline(cls, driver_ids):
        """إخراج من ثبت انقطاعه من الفهارس. تنفيذٌ بلا قرار."""
        keys = [str(driver_id) for driver_id in driver_ids]

        if not keys:
            return []

        r = get_redis()
        pipe = r.pipeline()
        for driver_id in keys:
            pipe.hset(cls._key(int(driver_id)), "online", "0")
            pipe.zrem(GEO_KEY, driver_id)
        pipe.zrem(LAST_SEEN_KEY, *keys)
        pipe.execute()

        return [int(driver_id) for driver_id in keys]
