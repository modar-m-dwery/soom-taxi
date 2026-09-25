"""
البثّ إلى غرفة لوحة التشغيل — نقطة واحدة لأسماء الأحداث.

لماذا وسيطٌ بدل استدعاء `EventBus.publish` من كلّ مكان: أسماء أحداث
اللوحة تصير عقدًا مع واجهتها. تركُها متناثرة في عشرة ملفّات يعني أنّ
إعادة تسمية واحدة تكسر اللوحة بصمت، ولا يُكتشف ذلك إلّا حين يحتاجها
مشغّل في لحظة عطل.

كلّ دالّة هنا آمنة: انهيار البثّ لا يُسقط العملية التي سبّبته. اللوحة
أداةُ مراقبة، وسقوط الرحلة لأنّ لوحةً لم تُحدَّث انقلابٌ في الأولويات.
"""
from __future__ import annotations

import logging

from django.db import transaction


logger = logging.getLogger("realtime")


class OpsLiveBroadcaster:

    GROUP = "admin_live"

    # -----------------------------------------------------------
    # الأحداث
    # -----------------------------------------------------------

    @classmethod
    def driver_moved(cls, driver_id, lng, lat, state=None, occupancy=None):
        """
        موقع سائق تغيّر — بثّ عابر لا يدخل سجلّ إعادة المزامنة.

        مواقع خمسمئة سائق كلّ خمس ثوانٍ تُغرق أيّ سجلّ أحداث خلال ثوانٍ
        وتجعل لحاق اللوحة بعد انقطاع بلا معنى. آخر قيمة تفوز، والقديم
        لا يُعاد.
        """
        cls._ephemeral(
            "admin.driver_location",
            {
                "driver_id": driver_id,
                "lng": lng,
                "lat": lat,
                "state": state,
                "occupancy": occupancy,
            },
        )

    @classmethod
    def needs_attention(cls, kind, entity_type, entity_id, detail=""):
        """
        شيءٌ يحتاج إنسانًا الآن: رحلة عالقة، دفعة متوقّفة، سائق شبح.

        حدث دائم لا عابر — هذا بالضبط ما يجب أن يلحق به المشغّل بعد
        انقطاع اتصاله.
        """
        cls._durable(
            "admin.attention",
            entity_type,
            entity_id,
            {"kind": kind, "detail": str(detail)[:300]},
        )

    @classmethod
    def admin_action(cls, kind, target_type, target_id, actor_label, reason=""):
        """تدخّل إداري وقع — تراه بقيّة اللوحات المفتوحة فورًا."""
        cls._durable(
            "admin.action",
            target_type,
            target_id,
            {
                "kind": kind,
                "actor": actor_label,
                "reason": str(reason)[:255],
            },
        )

    @classmethod
    def state_changed(cls, entity_type, entity_id, from_state, to_state, ride_id=None):
        """انتقال حالة يهمّ اللوحة — رحلة أُلغيت، دفعة فشلت."""
        cls._durable(
            "admin.state_changed",
            entity_type,
            entity_id,
            {
                "from_state": from_state,
                "to_state": to_state,
                "ride_id": ride_id,
            },
        )

    # -----------------------------------------------------------
    # داخلي
    # -----------------------------------------------------------

    @classmethod
    def _durable(cls, event_type, entity_type, entity_id, payload):
        def _go():
            try:
                from realtime.events import EventBus

                EventBus.publish(
                    group_name=cls.GROUP,
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id or 0,
                    payload=payload,
                )
            except Exception:  # noqa: BLE001
                logger.exception("ops-live: تعذّر بثّ %s", event_type)

        # بعد التثبيت لا قبله: حدثٌ عن معاملة لم تُثبَّت بعدُ يجعل اللوحة
        # تعرض ما لم يقع.
        try:
            transaction.on_commit(_go)
        except Exception:  # noqa: BLE001 — خارج أيّ معاملة
            _go()

    @classmethod
    def _ephemeral(cls, event_type, payload):
        try:
            from realtime.events import EventBus

            EventBus.publish_ephemeral(
                group_name=cls.GROUP,
                event_type=event_type,
                payload=payload,
            )
        except Exception:  # noqa: BLE001
            logger.exception("ops-live: تعذّر بثّ عابر %s", event_type)
