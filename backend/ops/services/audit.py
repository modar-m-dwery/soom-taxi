"""
كتابة سجلّ التدقيق — نقطة واحدة، لا تُسقط عملية أبدًا.

قاعدتان تحكمان هذا الملفّ:

**١. الأثر لا يُسقط الفعل.** لو انهارت كتابة الأثر لأيّ سبب — حقل أطول
من حدّه، اتصال متقطّع — فالرحلة يجب أن تكتمل. نبتلع الاستثناء ونسجّله
بمستوى `exception` كي يظهر في `errors.log`. سجلّ ناقص مشكلة؛ رحلةٌ لا
تكتمل لأنّ سجلًّا لم يُكتب كارثة.

**٢. لا أسرار ولا هويّات في `metadata`.** الوثيقة (§11) تشترط سجلّات
بلا أسرار، و`metadata` هو المكان الوحيد الذي يقبل شكلًا حرًّا — أي
المكان الوحيد الذي يتسرّب منه رقم هاتف أو توكن. `_scrub` يمنع ذلك
بقائمة مفاتيح محظورة وبقصّ الطول.
"""
from __future__ import annotations

import logging

from django.db import transaction

from config.observability.context import (
    current_user,
    get_request_id,
    resolve_actor,
)


logger = logging.getLogger("audit")


# مفاتيح لا تُكتب في metadata مهما مرّرها المستدعي.
_FORBIDDEN_KEYS = {
    "token", "password", "secret", "api_key", "apikey", "authorization",
    "code", "otp", "code_hash", "phone", "phone_number", "email",
    "national_id", "card", "card_number", "cvv", "pan", "service_account",
}

_MAX_VALUE_LEN = 500
_MAX_KEYS = 30


class AuditService:

    # -----------------------------------------------------------
    # الكتابة
    # -----------------------------------------------------------

    @classmethod
    def record(
        cls,
        entity_type,
        entity_id,
        *,
        action=None,
        from_state="",
        to_state="",
        actor=None,
        actor_label=None,
        reason="",
        **metadata,
    ):
        """
        يكتب صفَّ تدقيق واحدًا. لا يرمي أبدًا.

        `actor` كائن مستخدم إن عُرف. وإلّا يُؤخذ الوسم من سياق الطلب،
        فمهمّة Celery تُسجَّل باسمها ولا تظهر كأنّ مستخدمًا فعلها.
        """
        from ops.models import AuditAction, AuditLog

        try:
            label = actor_label or cls._label_for(actor)

            # نقطة حفظ (savepoint) لا محاولة عارية.
            #
            # هذا ليس تجميلًا: لو أخفق الإدراج داخل معاملة الاستدعاء —
            # مفتاح أجنبي لمستخدم حُذف، قيمة أطول من حقلها — فابتلاع
            # الاستثناء وحده **يترك المعاملة مسمومة**، وكلّ استعلام بعده
            # في الطلب نفسه يفشل بـInFailedSqlTransaction. أي أنّ وعد
            # «الأثر لا يُسقط الفعل» يصير كذبًا، والعطل يظهر بعيدًا عن
            # سببه. نقطة الحفظ تتراجع وحدها وتترك ما حولها سليمًا.
            with transaction.atomic():
                AuditLog.objects.create(
                    entity_type=str(entity_type)[:20],
                    entity_id=int(entity_id),
                    action=action or AuditAction.STATUS_CHANGED,
                    from_state=str(from_state or "")[:40],
                    to_state=str(to_state or "")[:40],
                    actor_user=(actor if cls._is_user(actor) else current_user()),
                    actor_label=label[:64],
                    actor_role=cls._role_for(actor)[:20],
                    reason=str(reason or "")[:255],
                    metadata=cls._scrub(metadata),
                    request_id=get_request_id()[:32],
                )

        except Exception:  # noqa: BLE001 — قاعدة ١ أعلاه
            logger.exception(
                "audit: تعذّرت كتابة الأثر لـ%s#%s (%s → %s)",
                entity_type, entity_id, from_state, to_state,
            )

    @classmethod
    def record_bulk(
        cls,
        entity_type,
        entity_ids,
        *,
        to_state,
        from_state="",
        action=None,
        actor_label=None,
        reason="",
        **metadata,
    ):
        """
        أثرٌ لمجموعة كيانات انتقلت معًا — بإدراج واحد لا صفٍّ لكلّ كيان.

        هذا هو الطريق لتحديثات `queryset.update()` الجماعية (انتهاء
        العروض والرحلات والدعوات). الإشارات لا تراها، وتركها بلا أثر
        كان يعني أنّ «لماذا انتهى طلبي؟» سؤالٌ بلا جواب — وهو أكثر
        ما يُسأل فعلًا.
        """
        from ops.models import AuditAction, AuditLog

        ids = [int(i) for i in entity_ids or []]
        if not ids:
            return

        try:
            clean = cls._scrub(metadata)
            label = (actor_label or cls._label_for(None))[:64]
            request_id = get_request_id()[:32]

            with transaction.atomic():
                AuditLog.objects.bulk_create(
                    [
                        AuditLog(
                            entity_type=str(entity_type)[:20],
                            entity_id=entity_id,
                            action=action or AuditAction.STATUS_CHANGED,
                            from_state=str(from_state or "")[:40],
                            to_state=str(to_state or "")[:40],
                            actor_label=label,
                            reason=str(reason or "")[:255],
                            metadata=clean,
                            request_id=request_id,
                        )
                        for entity_id in ids
                    ],
                    batch_size=500,
                )

        except Exception:  # noqa: BLE001 — قاعدة ١
            logger.exception(
                "audit: تعذّرت كتابة أثر جماعي لـ%s (%s صفًّا)",
                entity_type, len(ids),
            )

    @classmethod
    def record_on_commit(cls, *args, **kwargs):
        """
        نسخة تؤجّل الكتابة إلى ما بعد نجاح المعاملة.

        تُستعمل حين يكون الحدث المُسجَّل أثرًا جانبيًا (إشعار أُرسل، حدث
        بُثّ) لا الانتقال نفسه — فذاك يُكتب داخل المعاملة.
        """
        transaction.on_commit(lambda: cls.record(*args, **kwargs))

    # -----------------------------------------------------------
    # قراءة الجدول الزمني
    # -----------------------------------------------------------

    @staticmethod
    def timeline(entity_type, entity_id, limit=200):
        from ops.models import AuditLog

        return (
            AuditLog.objects
            .filter(entity_type=entity_type, entity_id=entity_id)
            .select_related("actor_user")
            .order_by("created_at", "id")[:limit]
        )

    @staticmethod
    def ride_story(ride_id, limit=400):
        """
        كلّ ما جرى حول رحلة واحدة: الطلب والعروض والدعوات والرحلة والدفعة.

        الاستعلام واحد لا خمسة: العلاقة بينها ليست مفتاحًا أجنبيًا في هذا
        الجدول، لكنّ `metadata.ride_id` يحملها في كلّ صفّ يخصّ الرحلة.
        """
        from django.db.models import Q

        from ops.models import AuditEntity, AuditLog

        # الدفعة والشكوى مرتبطتان بالرحلة (Trip) لا بالطلب (RideRequest)،
        # فنحلّ معرّف الرحلة مرّة واحدة ونضمّه إلى الشرط بدل ترك صفوفهما
        # خارج القصّة — وهي أكثر ما يُسأل عنه في نزاع مالي.
        from trips.models import Trip

        trip_id = (
            Trip.objects.filter(ride_id=ride_id)
            .values_list("id", flat=True)
            .first()
        )

        condition = Q(entity_type=AuditEntity.RIDE, entity_id=ride_id) | Q(
            metadata__ride_id=ride_id
        )

        if trip_id:
            condition |= Q(metadata__trip_id=trip_id)
            condition |= Q(entity_type=AuditEntity.TRIP, entity_id=trip_id)

        return (
            AuditLog.objects
            .filter(condition)
            .select_related("actor_user")
            .order_by("created_at", "id")[:limit]
        )

    # -----------------------------------------------------------
    # داخلي
    # -----------------------------------------------------------

    @staticmethod
    def _is_user(actor):
        return actor is not None and hasattr(actor, "pk") and hasattr(actor, "phone")

    @classmethod
    def _label_for(cls, actor):
        if cls._is_user(actor):
            return f"user:{actor.phone}"

        # سياق الطلب (يُحلّ كسولًا من المستخدم المصادَق) أو وسم المهمّة
        # الذي يضبطه bind() في Celery. و"system" آخر ملاذ لا أوّل خيار.
        return resolve_actor() or "system"

    @classmethod
    def _role_for(cls, actor):
        if cls._is_user(actor):
            return getattr(actor, "role", "") or ""

        user = current_user()
        if user is not None:
            return getattr(user, "role", "") or ""
        return ""

    @classmethod
    def _scrub(cls, data):
        """يحذف المفاتيح الحسّاسة ويقصّ القيم الطويلة."""
        if not isinstance(data, dict):
            return {}

        clean = {}

        for key, value in list(data.items())[:_MAX_KEYS]:
            lowered = str(key).lower()

            if any(bad in lowered for bad in _FORBIDDEN_KEYS):
                clean[key] = "[محذوف]"
                continue

            if isinstance(value, (dict, list)):
                text = str(value)
                clean[key] = text[:_MAX_VALUE_LEN] if len(text) > _MAX_VALUE_LEN else value
            elif isinstance(value, (int, float, bool)) or value is None:
                clean[key] = value
            else:
                clean[key] = str(value)[:_MAX_VALUE_LEN]

        return clean
