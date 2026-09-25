"""
MarketplaceService: يدير عضوية السائقين داخل خلايا الماركت بليس (نواتج
locations.services.LocationService) ويبثّ vehicle.entered_area /
vehicle.updated / vehicle.left_area للعملاء المشتركين في تلك الخلية عبر
/ws/marketplace/{area_id}/.

كل البث هنا ephemeral (وليس عبر EventBus.publish المخصص لأحداث الأعمال)
لأن مواقع السيارات على الخريطة حية "آخر قيمة تفوز" - تمامًا كـ
driver.location في غرفة الرحلة (الجزء F) ولنفس السبب بالضبط: خلطها مع
سجل resync القصير كان سيُغرقه خلال ثوانٍ.

المرحلة 8ب أضافت طبقة لم تكن موجودة: الخليّة الواحدة لم تعد تبثّ الشيء
نفسه لكل مشتركيها. سيارة مشتركة بمقعد فارغ تخصّ راكبًا مشتركًا مسارُه
موافق ولا تخصّ سواه، والفلترة تجري عند كل مشاهد على حدة عبر
MarketplaceViewer - لا في البثّ.

لماذا عند المشاهد لا في البثّ؟ لأن البديل هو مجموعة Channels لكل توليفة
(نمط × وجهة × عدد ركّاب)، أي انفجار في عدد المجموعات مقابل فلترة رخيصة
جدًا: مقارنة زاوية ومسافتين لكل رسالة.
"""
from presence.constants import PresenceState, SHARED_MODE
from presence.services import PresenceService
from realtime.events import EventBus

CELL_MEMBERS_KEY = "marketplace:cell:{cell_id}"

# الحالات التي تُبقي السائق مرسومًا على الخريطة. SHARING منها - لكن
# لمن يوافقه فقط، وذلك ما يقرره MarketplaceViewer أدناه.
VISIBLE_STATES = (PresenceState.PRESENT, PresenceState.SHARING)


def group_name_for_cell(cell_id):
    """
    اسم مجموعة Channels آمن. Channels يمنع ':' في أسماء المجموعات، بينما
    area_id (القادم من LocationService) بصيغة "JAB:sy390vj". هذه الدالة
    هي المصدر الوحيد للتحويل - يجب أن يستخدمها كل من MarketplaceService
    و MarketplaceConsumer لضمان تطابق الاسم على الجانبين دائمًا.
    """
    return f"marketplace_{cell_id.replace(':', '_')}"


# =================================================================
# الفلترة لكل مشاهد على حدة
# =================================================================

class MarketplaceViewer:
    """
    سياق المشاهد الواحد. دالة خالصة عمليًا: تُبنى مرة عند الاتصال ثم
    تُسأل عن كل حمولة. لا تلمس Redis ولا القاعدة، فهي قابلة للاختبار
    بلا أي بنية تحتية - وهذا مقصود، لأن قاعدة "ماذا يرى هذا الزبون"
    أهم من أن تُختبر عبر WebSocket فقط.
    """

    def __init__(self, mode=None, pickup_lng=None, pickup_lat=None,
                 dest_lng=None, dest_lat=None, passenger_count=1, min_score=55):
        self.mode = mode
        self.pickup_lng = pickup_lng
        self.pickup_lat = pickup_lat
        self.dest_lng = dest_lng
        self.dest_lat = dest_lat
        self.passenger_count = passenger_count or 1
        self.min_score = min_score

    # -------------------------------------------------------------

    @classmethod
    def anonymous(cls):
        """
        مشاهد بلا طلب: يتصفّح الخريطة فقط. يرى السيارات الفارغة ولا يرى
        المشتركة - إخفاؤها عنه أصدق من عرض سيارة لا يستطيع ركوبها.
        """
        return cls()

    @classmethod
    def from_ride(cls, ride):
        if ride is None:
            return cls.anonymous()

        area = getattr(ride, "service_area", None)

        return cls(
            mode=getattr(ride, "mode", None),
            pickup_lng=ride.pickup.x if ride.pickup else None,
            pickup_lat=ride.pickup.y if ride.pickup else None,
            dest_lng=ride.destination.x if ride.destination else None,
            dest_lat=ride.destination.y if ride.destination else None,
            passenger_count=getattr(ride, "passenger_count", 1),
            min_score=int(
                getattr(area, "shared_min_compatibility_score", None) or 55
            ),
        )

    # -------------------------------------------------------------

    @property
    def wants_shared(self):
        return self.mode == SHARED_MODE

    def evaluate(self, payload):
        """
        يرجّع (هل يُعرض، درجة التوافق أو None).

        الحمولة غير المشتركة تمرّ دائمًا: السيارة الفارغة تصلح للجميع.
        """
        if not payload or not payload.get("is_sharing"):
            return True, None

        if not self.wants_shared:
            return False, None

        if self.dest_lng is None or payload.get("lng") is None:
            return False, None

        from matching.services.compat import SharedCompatibilityService

        result = SharedCompatibilityService.evaluate(
            driver_lng=float(payload["lng"]),
            driver_lat=float(payload["lat"]),
            driver_dest_cell=payload.get("dest_cell"),
            rider_pickup_lng=self.pickup_lng,
            rider_pickup_lat=self.pickup_lat,
            rider_dest_lng=self.dest_lng,
            rider_dest_lat=self.dest_lat,
            free_seats=payload.get("available_seats") or 0,
            passenger_count=self.passenger_count,
            min_score=self.min_score,
        )

        return result["eligible"], result["score"]

    def should_show(self, payload):
        return self.evaluate(payload)[0]


# =================================================================

class MarketplaceService:

    @staticmethod
    def _members_key(cell_id):
        return CELL_MEMBERS_KEY.format(cell_id=cell_id)

    @classmethod
    def _add_to_cell(cls, cell_id, driver_id):
        from presence.redis_client import get_redis
        get_redis().sadd(cls._members_key(cell_id), driver_id)

    @classmethod
    def _remove_from_cell(cls, cell_id, driver_id):
        from presence.redis_client import get_redis
        get_redis().srem(cls._members_key(cell_id), driver_id)

    @classmethod
    def get_cell_member_ids(cls, cell_id):
        from presence.redis_client import get_redis
        raw = get_redis().smembers(cls._members_key(cell_id))
        return [int(driver_id) for driver_id in raw]

    # -----------------------------------------------------------
    # بناء حمولة السيارة - مصدر واحد
    # -----------------------------------------------------------

    @classmethod
    def build_vehicle_payload(cls, driver_id, snapshot=None, driver=None,
                              lng=None, lat=None, heading=None):
        """
        كانت هذه الحمولة تُبنى في ثلاثة أماكن بصياغات متقاربة: نبضة
        الموقع، وسناب شوت الغرفة، والآن تغيّر الارتباط. ثلاث نسخ تعني
        حتمًا أن حقل is_sharing سيُنسى في إحداها يومًا.
        """
        from users.models import DriverProfile

        snapshot = snapshot if snapshot is not None else PresenceService.get_snapshot(driver_id)

        if driver is None:
            driver = (
                DriverProfile.objects
                .select_related("user")
                .prefetch_related("vehicles")
                .filter(id=driver_id)
                .first()
            )

        if lng is None:
            lng = float(snapshot["lng"]) if snapshot.get("lng") not in (None, "") else None
        if lat is None:
            lat = float(snapshot["lat"]) if snapshot.get("lat") not in (None, "") else None

        if heading is None:
            heading = snapshot.get("heading") or None

        vehicle = None
        if driver is not None:
            vehicle = next((v for v in driver.vehicles.all() if v.active), None)

        return {
            "driver_id": driver_id,
            # تقريب خصوصية (~110م) - نقطة #14 من خطة المرحلة 6
            "lng": round(lng, 3) if lng is not None else None,
            "lat": round(lat, 3) if lat is not None else None,
            "heading": heading,
            "available_seats": PresenceService.get_remaining_seats(
                driver_id, snapshot=snapshot
            ),
            "current_occupancy": driver.current_occupancy if driver else 0,
            "vehicle_type": vehicle.type_id if vehicle else None,
            # ما يحتاجه الزبون ليختار سيارته من الخريطة: الاسم الأوّل ونوع
            # السيارة ولونها — لا هاتف ولا لوحة قبل القبول.
            "driver_name": _first_name(driver),
            "vehicle_make": vehicle.make if vehicle else "",
            "vehicle_model": vehicle.model if vehicle else "",
            "vehicle_color": vehicle.color if vehicle else "",
            "seats": vehicle.seats if vehicle else 4,
            "onboard_passengers": (
                driver.current_occupancy
                if driver is not None and snapshot.get("sharing") == "1"
                else None
            ),
            "rating": (
                float(driver.rating)
                if driver is not None and driver.rating is not None
                else None
            ),
            # حقول المشاركة: خليّة خشنة لا وجهة دقيقة
            "is_sharing": snapshot.get("sharing") == "1",
            "trip_mode": snapshot.get("trip_mode") or None,
            "dest_cell": snapshot.get("dest_cell") or None,
        }

    # -----------------------------------------------------------
    # نقطة الدخول الوحيدة التي يناديها DriverRoomConsumer عند كل
    # location.update - تقرر بنفسها: دخول خلية جديدة / بقاء بنفس
    # الخلية / اختفاء (busy، offline، أو خارج كل مناطق الخدمة).
    # -----------------------------------------------------------

    @classmethod
    def handle_location_update(cls, driver_id, new_cell_id, vehicle_payload, is_available):
        old_cell = PresenceService.get_current_cell(driver_id)

        # غير متاح الآن (busy/unavailable) أو خارج كل مناطق الخدمة
        # (new_cell_id=None) -> يجب أن يختفي من أي خلية كان ظاهرًا فيها
        if not is_available or new_cell_id is None:
            if old_cell:
                cls._remove_from_cell(old_cell, driver_id)
                EventBus.publish_ephemeral(
                    group_name_for_cell(old_cell),
                    "vehicle.left_area",
                    {"driver_id": driver_id},
                )
                PresenceService.set_current_cell(driver_id, None)
            return

        # نفس الخلية - تحديث موقع فقط، لا تغيّر عضوية
        if old_cell == new_cell_id:
            EventBus.publish_ephemeral(
                group_name_for_cell(new_cell_id), "vehicle.updated", vehicle_payload
            )
            return

        # تغيّرت الخلية فعليًا (أو أول ظهور له في أي خلية)
        if old_cell:
            cls._remove_from_cell(old_cell, driver_id)
            EventBus.publish_ephemeral(
                group_name_for_cell(old_cell),
                "vehicle.left_area",
                {"driver_id": driver_id},
            )

        cls._add_to_cell(new_cell_id, driver_id)
        PresenceService.set_current_cell(driver_id, new_cell_id)
        EventBus.publish_ephemeral(
            group_name_for_cell(new_cell_id), "vehicle.entered_area", vehicle_payload
        )

    @classmethod
    def handle_offline(cls, driver_id):
        """تُستدعى عند go_offline الصريح، أو من presence.tasks.sweep_stale_driver_presence."""
        old_cell = PresenceService.get_current_cell(driver_id)

        if old_cell:
            cls._remove_from_cell(old_cell, driver_id)
            EventBus.publish_ephemeral(
                group_name_for_cell(old_cell),
                "vehicle.left_area",
                {"driver_id": driver_id},
            )
            PresenceService.set_current_cell(driver_id, None)

    # -----------------------------------------------------------
    # تغيّر الارتباط برحلة (المرحلة 8ب)
    # -----------------------------------------------------------

    @classmethod
    def handle_engagement_change(cls, driver_id):
        """
        تُستدعى لحظة تثبيت سائق أو تحريره، من EngagementResolver.sync.

        قبلها كان مسار العروض ينادي handle_offline مباشرة: أي أن كل تثبيت
        يعني اختفاءً فوريًا من الخريطة. هذا صحيح للرحلة الفردية وخاطئ
        تمامًا للمشتركة - السيارة يجب أن تبقى مرسومة، وتتغيّر فقط لمن
        تُعرض.

        وبلا هذه الدالة كانت الخريطة تكذب في الاتجاهين: تُبقي السائق
        المشغول ظاهرًا حتى نبضته التالية، وتُخفي المشتركة عمن ينتظرها.
        """
        snapshot = PresenceService.get_snapshot(driver_id)
        state = PresenceService._resolve_state_from_snapshot(snapshot)

        if state not in VISIBLE_STATES:
            cls.handle_offline(driver_id)
            return

        payload = cls.build_vehicle_payload(driver_id, snapshot=snapshot)

        if payload["lng"] is None or payload["lat"] is None:
            cls.handle_offline(driver_id)
            return

        cell_id = PresenceService.get_current_cell(driver_id)

        if cell_id is None:
            from locations.services import LocationService

            cell_id = LocationService.compute_marketplace_cell_id(
                payload["lng"], payload["lat"]
            )

            if cell_id is None:
                return

            cls._add_to_cell(cell_id, driver_id)
            PresenceService.set_current_cell(driver_id, cell_id)

            EventBus.publish_ephemeral(
                group_name_for_cell(cell_id), "vehicle.entered_area", payload
            )
            return

        # موجود في خليّة بالفعل: تحديث يحمل is_sharing الجديد. المشاهدون
        # غير المتوافقين سيحوّلونه إلى vehicle.left_area عند أنفسهم.
        EventBus.publish_ephemeral(
            group_name_for_cell(cell_id), "vehicle.updated", payload
        )


def _first_name(driver):
    """الاسم الأوّل وحده: يكفي لـ«أبو علي قادم» ولا يكشف هويّة كاملة."""
    user = getattr(driver, "user", None) if driver is not None else None
    name = (getattr(user, "name", "") or "").strip()
    if not name:
        return ""
    # «أبو علي» اسمٌ واحد في العامّية، لا يُقصّ إلى «أبو».
    parts = name.split()
    if parts[0] in ("أبو", "ابو", "أم", "ام") and len(parts) > 1:
        return " ".join(parts[:2])
    return parts[0]
