"""
التقاط انتقالات الحالة آليًا — بلا استعلام إضافي.

الفكرة
------
لتعرف أنّ الحالة تغيّرت تحتاج القيمة القديمة. الطريقة الساذجة أن تقرأ
الصفّ من القاعدة في `pre_save`، وهذا استعلام إضافي عند **كلّ حفظ** لكلّ
رحلة وعرض ودعوة. مع خمسمئة سائق يعني ذلك مضاعفة حمل القاعدة لأجل
السجلّ — ثمنٌ لا يُدفع.

الطريقة هنا: نلتقط الحالة لحظة **قراءة** الصفّ من القاعدة. Django يمرّ
بـ`Model.from_db` عند بناء كلّ كائن من صفّ، فنخزّن الحالة على الكائن
نفسه. الاستعلام الذي جلب الصفّ أصلًا هو مصدرنا — صفر استعلام إضافي.

ما لا يلتقطه هذا
----------------
`queryset.update(status=...)` لا يمرّ بـ`save()` ولا بالإشارات. تلك
المواضع معدودة (انتهاء العروض والرحلات الجماعي) وتُسجَّل صراحةً في
`matching/tasks.py`. الاعتماد على الإشارات وحدها كان سيترك أكثر ما
يُسأل عنه بلا أثر.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save

from ops.models import AuditAction, AuditEntity
from ops.services.audit import AuditService


logger = logging.getLogger("audit")

_SENTINEL = object()


def _install_from_db(model):
    """يجعل كلّ كائن يحمل حالته كما قُرئت من القاعدة."""
    if getattr(model, "_audit_from_db_installed", False):
        return

    original_from_db = model.from_db.__func__

    def from_db(cls, db, field_names, values):
        instance = original_from_db(cls, db, field_names, values)
        try:
            instance._audit_prev_state = getattr(instance, "status", None)
        except Exception:  # noqa: BLE001
            instance._audit_prev_state = None
        return instance

    model.from_db = classmethod(from_db)
    model._audit_from_db_installed = True


def _handler(entity_type, extra_fn=None):
    def on_post_save(sender, instance, created, **kwargs):
        try:
            new_state = getattr(instance, "status", None)

            if new_state is None:
                return

            prev = getattr(instance, "_audit_prev_state", _SENTINEL)

            if created:
                action = AuditAction.CREATED
                from_state = ""
            else:
                if prev is _SENTINEL or prev == new_state:
                    # حفظٌ لم يغيّر الحالة (تحديث موقع، عدّاد) — لا أثر له
                    return
                action = AuditAction.STATUS_CHANGED
                from_state = prev or ""

            metadata = {}
            if extra_fn is not None:
                try:
                    metadata = extra_fn(instance) or {}
                except Exception:  # noqa: BLE001
                    metadata = {}

            AuditService.record(
                entity_type,
                instance.pk,
                action=action,
                from_state=from_state,
                to_state=new_state,
                **metadata,
            )

            # الحالة الجديدة تصير المرجع لأيّ حفظ لاحق على الكائن نفسه
            instance._audit_prev_state = new_state

        except Exception:  # noqa: BLE001 — الأثر لا يُسقط الفعل
            logger.exception("audit: فشل التقاط انتقال %s", entity_type)

    return on_post_save


# ---------------------------------------------------------------
# ما يُربط بالضبط، وما يُحمل معه من سياق
# ---------------------------------------------------------------


def _ride_extra(ride):
    return {
        "ride_id": ride.pk,
        "mode": getattr(ride, "mode", ""),
        "trip_category": getattr(ride, "trip_category", ""),
        "route_source": getattr(ride, "route_source", ""),
    }


def _offer_extra(offer):
    return {
        "ride_id": offer.__dict__.get("ride_id"),
        "driver_id": offer.__dict__.get("driver_id"),
        "gross_fare": str(getattr(offer, "gross_fare", "") or ""),
        "eta_minutes": getattr(offer, "eta_minutes", None),
    }


def _invitation_extra(inv):
    return {
        "ride_id": inv.__dict__.get("ride_id"),
        "driver_id": inv.__dict__.get("driver_id"),
        "ttl_seconds": getattr(inv, "ttl_seconds", None),
    }


def _trip_extra(trip):
    return {
        "ride_id": trip.__dict__.get("ride_id"),
        "driver_id": trip.__dict__.get("driver_id"),
        "needs_review": getattr(trip, "needs_review", None),
    }


def _payment_extra(payment):
    # Payment مرتبط بـTrip لا بـRideRequest مباشرةً. نقرأ المفتاح من
    # __dict__ لا عبر العلاقة: الثاني يوقظ استعلامًا لكلّ صفّ تدقيق.
    return {
        "trip_id": payment.__dict__.get("trip_id"),
        "amount": str(getattr(payment, "amount", "") or ""),
        "gateway": getattr(payment, "gateway_code", "") or "",
    }


def _driver_extra(driver):
    return {
        "driver_id": driver.pk,
        "online": getattr(driver, "online", None),
        "available_seats": getattr(driver, "available_seats", None),
    }


def _shared_join_extra(join):
    return {
        "ride_id": join.__dict__.get("candidate_ride_id"),
        "host_ride_id": join.__dict__.get("host_ride_id"),
    }


def _document_extra(doc):
    return {
        "driver_id": doc.__dict__.get("driver_id"),
        "document_type": getattr(doc, "type", ""),
    }


def _complaint_extra(c):
    return {
        "trip_id": c.__dict__.get("trip_id"),
        "category": getattr(c, "category", ""),
    }


_REGISTRY = [
    ("rides", "RideRequest", AuditEntity.RIDE, _ride_extra),
    ("matching", "RideOffer", AuditEntity.OFFER, _offer_extra),
    ("matching", "RideInvitation", AuditEntity.INVITATION, _invitation_extra),
    ("matching", "SharedJoinRequest", AuditEntity.SHARED_JOIN, _shared_join_extra),
    ("trips", "Trip", AuditEntity.TRIP, _trip_extra),
    ("payments", "Payment", AuditEntity.PAYMENT, _payment_extra),
    ("users", "DriverProfile", AuditEntity.DRIVER, _driver_extra),
    ("drivers", "DriverDocument", AuditEntity.DOCUMENT, _document_extra),
    ("feedback", "Complaint", AuditEntity.COMPLAINT, _complaint_extra),
]


def connect():
    """يُستدعى مرّة واحدة من `OpsConfig.ready()`."""
    from django.apps import apps

    for app_label, model_name, entity, extra in _REGISTRY:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            logger.warning("audit: لا يوجد نموذج %s.%s", app_label, model_name)
            continue

        if not any(f.name == "status" for f in model._meta.get_fields()):
            logger.warning(
                "audit: %s.%s بلا حقل status — تخطّي", app_label, model_name
            )
            continue

        _install_from_db(model)

        post_save.connect(
            _handler(entity, extra),
            sender=model,
            weak=False,
            dispatch_uid=f"audit_status_{app_label}_{model_name}",
        )
