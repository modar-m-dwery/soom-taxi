"""
عقد الحدث الموحّد لكل الأحداث اللحظية في المشروع (offers/rides/trips لاحقًا).

القاعدة: الـServices فقط هي من تنادي EventBus.publish (أبدًا من Consumer
أو View مباشرة). هذا يبقي REST وWebSocket قناتين لنفس المنطق، تمامًا
كما في فلسفة مشروعك الأصلية ("API ليست طبقة قرار").

كل حدث يحمل:
    event_id    - UUID فريد (لأجل idempotency على العميل)
    event_type  - مثل "offer.created"
    entity_type - مثل "ride"
    entity_id   - معرف الكيان
    version     - رقم تصاعدي *لكل entity* (وليس عام) - يُستخدم للـresync
    timestamp   - unix time
    payload     - بيانات الحدث الفعلية
"""
import json
import time
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from realtime.redis_client import get_redis

EVENT_LOG_MAX_LEN = 50          # آخر N حدث محفوظين لكل entity لإعادة اللحاق
EVENT_LOG_TTL_SECONDS = 3600    # ساعة كافية لمعظم دورة حياة الرحلة الواحدة


class EventBus:

    VERSION_KEY = "events:version:{entity_type}:{entity_id}"
    LOG_KEY = "events:log:{entity_type}:{entity_id}"

    # -----------------------------------------------------------
    # VERSIONING
    # -----------------------------------------------------------

    @classmethod
    def _next_version(cls, entity_type, entity_id):
        r = get_redis()
        key = cls.VERSION_KEY.format(entity_type=entity_type, entity_id=entity_id)
        return r.incr(key)

    @classmethod
    def get_current_version(cls, entity_type, entity_id):
        r = get_redis()
        key = cls.VERSION_KEY.format(entity_type=entity_type, entity_id=entity_id)
        value = r.get(key)
        return int(value) if value else 0

    # -----------------------------------------------------------
    # EVENT LOG (لأجل resync قصير المدى - وليس تخزينًا دائمًا)
    # -----------------------------------------------------------

    @classmethod
    def _store_in_log(cls, entity_type, entity_id, event):
        r = get_redis()
        key = cls.LOG_KEY.format(entity_type=entity_type, entity_id=entity_id)

        pipe = r.pipeline()
        pipe.rpush(key, json.dumps(event))
        pipe.ltrim(key, -EVENT_LOG_MAX_LEN, -1)
        pipe.expire(key, EVENT_LOG_TTL_SECONDS)
        pipe.execute()

    @classmethod
    def get_events_since(cls, entity_type, entity_id, since_version):
        """
        best-effort فقط. لو الفجوة تجاوزت EVENT_LOG_MAX_LEN حدثًا أو
        EVENT_LOG_TTL_SECONDS، النتيجة قد تكون غير كاملة - عندها يجب أن
        يلجأ العميل لـsnapshot كامل بدل محاولة اللحاق بالأحداث الفائتة
        (هذا بالضبط ما يفعله RideConsumer.receive_json عند "resync").
        """
        r = get_redis()
        key = cls.LOG_KEY.format(entity_type=entity_type, entity_id=entity_id)
        raw_events = r.lrange(key, 0, -1)

        events = [json.loads(e) for e in raw_events]
        return [e for e in events if e["version"] > since_version]

    # -----------------------------------------------------------
    # BUILD + PUBLISH (أحداث أعمال نسخية - قابلة للّحاق عند resync)
    # -----------------------------------------------------------

    @classmethod
    def build_event(cls, event_type, entity_type, entity_id, payload):
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "version": cls._next_version(entity_type, entity_id),
            "timestamp": time.time(),
            "payload": payload,
        }
        cls._store_in_log(entity_type, entity_id, event)
        return event

    @classmethod
    def publish(cls, group_name, event_type, entity_type, entity_id, payload):
        """
        يبني الحدث ويبثّه فورًا عبر channel layer.

        تحذير مهم: هذه الدالة *متزامنة* (sync) عمدًا لأن الـServices عندك
        متزامنة (transaction.atomic عادي، ليس async). لكن هذا يعني أنك
        **لا يجب أن تناديها مباشرة داخل transaction.atomic** - لو نُشر
        الحدث والمعاملة لم تُثبَّت بعد (commit)، العميل قد يستقبل الحدث
        ثم يطلب REST فيجد بيانات قديمة، أو أسوأ: تفشل المعاملة لاحقًا
        فيصبح الحدث "وهميًا". استخدم دائمًا:

            transaction.on_commit(lambda: EventBus.publish(...))

        داخل أي دالة مزينة بـ@transaction.atomic. راجع
        realtime/INTEGRATION_PART_E.md لأمثلة دقيقة من matching/services.

        استخدم هذه الدالة فقط لأحداث الأعمال (offer/ride/trip). لبيانات
        حية عالية التردد وinherently "آخر قيمة تفوز" مثل driver.location،
        استخدم publish_ephemeral بالأسفل بدلاً منها.
        """
        event = cls.build_event(event_type, entity_type, entity_id, payload)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "broadcast.event",
                "event_type": event["event_type"],
                "payload": {
                    "event_id": event["event_id"],
                    "entity_type": event["entity_type"],
                    "entity_id": event["entity_id"],
                    "version": event["version"],
                    "timestamp": event["timestamp"],
                    "data": event["payload"],
                },
            },
        )

        return event

    # -----------------------------------------------------------
    # EPHEMERAL PUBLISH - بلا version/event_id/سجل. للبيانات عالية
    # التردد التي لا تحتاج إعادة تشغيل عند resync (driver.location مثلاً).
    # -----------------------------------------------------------

    @classmethod
    def publish_ephemeral(cls, group_name, event_type, payload):
        """
        بث حي دون بناء حدث نسخي. يُستخدم حصرًا للبيانات "آخر قيمة تفوز"
        عالية التردد مثل driver.location. لا تستخدمها لأي حدث أعمال
        (offer/trip/ride) - تلك يجب أن تمر عبر publish() لتبقى قابلة
        للّحاق بعد انقطاع الاتصال، وإلا ستُغرق سجل الـresync القصير
        (EVENT_LOG_MAX_LEN) بأحداث GPS خلال ثوانٍ معدودة، فتصبح إعادة
        مزامنة الأحداث المهمة بعد انقطاع غير موثوقة.
        """
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "broadcast.event",
                "event_type": event_type,
                "payload": payload,
            },
        )