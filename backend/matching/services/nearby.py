"""
NearbyVehiclesService — خريطة السيارات الحيّة عبر REST.

الوثيقة §21 تُدرج GET /rides/{id}/nearby-vehicles/ ضمن الواجهات المطلوبة،
ولم تكن مبنية: كان الماركت بليس متاحًا عبر WebSocket فقط. هذا يعني أن أول
فتح للشاشة كان يعتمد على snapshot الغرفة، وأن أي عميل بلا WebSocket (اختبار،
لوحة إدارة، تطبيق في وضع ضعيف الشبكة) لا يرى شيئًا.

المصدر هنا هو Presence نفسه لا استعلام جديد على PostGIS: نفس تعريف
"السائق المتاح" الذي تستخدمه المطابقة والخريطة الحيّة، بلا اجتهاد ثالث.
"""
from math import radians, sin, cos, sqrt, atan2

from django.conf import settings

from matching.models import InvitationStatus, RideInvitation
from matching.services.compat import SharedCompatibilityService
from matching.services.eta import MatchingETAService
from presence.constants import SHARED_MODE
from presence.services import PresenceService
from users.models import DriverProfile


def _haversine_km(lng1, lat1, lng2, lat2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


class NearbyVehiclesService:

    @classmethod
    def for_ride(cls, ride, limit=None):
        """
        يرجّع قائمة السيارات الصالحة لهذا الطلب تحديدًا، مرتّبة بالأقرب.

        ملاحظة خصوصية مقصودة: الحساب يجري بالإحداثيات الدقيقة على الخادم،
        لكن ما يُرجَع للعميل مُقرَّب إلى ~110م. الزبون يحصل على مسافة وETA
        دقيقين دون أن يحصل على موقع دقيق - وهي نقطة #14 في خطة المرحلة 6.
        """
        area = getattr(ride, "service_area", None)

        # نفس القارئ الذي يستعمله محرّك المطابقة، لا نسخة ثانية من المنطق:
        # نسختان تتباعدان عند أوّل تعديل، فتُظهر الخريطة سيارةً لا تُطابَق
        # أو تُخفي سيارةً تُطابَق — وكلاهما يجعل الزبون لا يثق بما يراه.
        radius_km = (
            area.effective_instant_radius_km
            if area is not None
            else float(getattr(settings, "MATCHING_NORMAL_RADIUS_KM", 5))
        )
        if ride.search_radius_km:
            radius_km = min(radius_km, float(ride.search_radius_km))

        limit = limit or getattr(settings, "MATCHING_MARKETPLACE_DRIVER_LIMIT", 40)

        pickup_lng, pickup_lat = ride.pickup.x, ride.pickup.y

        mode = getattr(ride, "mode", None)

        # هنا يدخل الفرق كله: طلب مشترك يرى السيارات المشتركة ذات المقعد
        # الفارغ أيضًا، والطلب الفردي لا يراها. نفس الاستدعاء، جواب مختلف
        # بحسب مَن يسأل.
        candidates = PresenceService.get_available_nearby_with_snapshots(
            pickup_lng, pickup_lat, radius_km=radius_km, limit=limit,
            for_mode=mode,
        )

        if not candidates:
            return []

        driver_ids = [c["driver_id"] for c in candidates]

        drivers = {
            d.id: d
            for d in (
                DriverProfile.objects
                .filter(id__in=driver_ids)
                .select_related("user")
                .prefetch_related("vehicles")
            )
        }

        # السائقون الذين لديهم دعوة معلّقة على هذا الطلب: يُعرضون لكن
        # مع علامة، حتى لا يظن الزبون أن ضغطه لم يصل.
        already_invited = set(
            RideInvitation.objects
            .filter(ride=ride, status=InvitationStatus.PENDING)
            .values_list("driver_id", flat=True)
        )

        min_score = int(
            getattr(area, "shared_min_compatibility_score", None) or 55
        )

        results = []

        for item in candidates:
            driver = drivers.get(item["driver_id"])

            if driver is None or item["lng"] is None or item["lat"] is None:
                continue

            if driver.available_seats - driver.current_occupancy < ride.passenger_count:
                continue

            vehicle = next(
                (v for v in driver.vehicles.all() if v.active), None
            )

            if vehicle is None or vehicle.seats < ride.passenger_count:
                continue

            if ride.requested_vehicle_type and vehicle.type_id != ride.requested_vehicle_type:
                continue

            # -------------------------------------------------------
            # سيارة مشتركة على الطريق: تمرّ من بوّابة التوافق أولًا
            # -------------------------------------------------------
            compatibility = None

            if item.get("is_sharing"):
                if mode != SHARED_MODE or ride.destination is None:
                    continue

                compatibility = SharedCompatibilityService.evaluate(
                    driver_lng=item["lng"],
                    driver_lat=item["lat"],
                    driver_dest_cell=item.get("dest_cell"),
                    rider_pickup_lng=pickup_lng,
                    rider_pickup_lat=pickup_lat,
                    rider_dest_lng=ride.destination.x,
                    rider_dest_lat=ride.destination.y,
                    free_seats=item.get("available_seats") or 0,
                    passenger_count=ride.passenger_count,
                    min_score=min_score,
                )

                if not compatibility["eligible"]:
                    continue

            distance_km = _haversine_km(
                item["lng"], item["lat"], pickup_lng, pickup_lat
            )

            results.append(
                {
                    "driver_id": driver.id,
                    "driver_name": driver.user.name or "",
                    "rating": float(driver.rating) if driver.rating is not None else None,
                    "vehicle_type": vehicle.type_id,
                    "vehicle_make": vehicle.make,
                    "vehicle_model": vehicle.model,
                    "vehicle_color": vehicle.color,
                    "seats": vehicle.seats,
                    "available_seats": max(
                        driver.available_seats - driver.current_occupancy, 0
                    ),
                    "current_occupancy": driver.current_occupancy,
                    # تقريب الخصوصية - لا يُرسَل الموقع الدقيق قبل القبول
                    "lng": round(item["lng"], 3),
                    "lat": round(item["lat"], 3),
                    "heading": item.get("heading"),
                    "approximate_distance_m": int(round(distance_km * 1000)),
                    "eta_minutes": MatchingETAService.calculate_eta_minutes(distance_km),
                    "quoted_fare": str(ride.gross_fare),
                    "currency": getattr(ride, "currency", None) or "SYP",
                    "is_invited": driver.id in already_invited,
                    # حقول المشاركة — None لسيارة فارغة عادية
                    "is_sharing": bool(item.get("is_sharing")),
                    "onboard_passengers": (
                        driver.current_occupancy if item.get("is_sharing") else None
                    ),
                    "compatibility_score": (
                        compatibility["score"] if compatibility else None
                    ),
                    "route_bearing": (
                        compatibility["route_bearing"] if compatibility else None
                    ),
                    "extra_detour_m": (
                        int(compatibility["detour_km"] * 1000) if compatibility else None
                    ),
                    "_sort_km": distance_km,
                    "_score": compatibility["score"] if compatibility else None,
                }
            )

        # الطلب المشترك يُرتَّب بالتوافق أولًا ثم بالقرب: أقرب سيارة بمسار
        # مخالف أسوأ خيارًا من سيارة أبعد قليلًا تسير في طريقك.
        if mode == SHARED_MODE:
            results.sort(key=lambda r: (-(r["_score"] or 0), r["_sort_km"]))
        else:
            results.sort(key=lambda r: r["_sort_km"])

        for r in results:
            r.pop("_sort_km", None)
            r.pop("_score", None)

        return results
