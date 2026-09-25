"""
طبقة الاتصال اللحظي.

القاعدة المعمارية الملتزم بها: Consumer لا يحوي Business Logic أبدًا،
فقط يستقبل/يبث. أي منطق حقيقي يذهب إلى Services.

هيكل الأصناف — انتبه له عند أي تعديل مستقبلي، فقد كلّفنا خلطُه ساعتين:

    BaseAuthenticatedConsumer     أساس عام: توثيق، مجموعة، ping، بثّ
    ├── DriverConnectionConsumer  اختبار اتصال
    ├── CustomerConnectionConsumer اختبار اتصال
    ├── RideConsumer              غرفة الرحلة  (له snapshot خاص به)
    ├── DriverRoomConsumer        القناة الشخصية للسائق
    └── MarketplaceConsumer       خليّة الخريطة (له snapshot وفلتر خاصان)

كل صنف يملك connect و_build_snapshot الخاصين به. نقل أيّهما إلى الأساس
أو إلى أخيه يكسر الاتصال كله بلا رسالة مفهومة.
"""
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from config.observability.safety import guarded


class BaseAuthenticatedConsumer(AsyncJsonWebsocketConsumer):
    """
    مسؤولياته فقط:
        - رفض الاتصال غير الموثّق (close code 4401)
        - تحديد اسم المجموعة (override في الأبناء)
        - الانضمام/المغادرة الصحيحة للمجموعة
        - ping/pong
        - بثّ عام إلى العميل

    مهم: لا تضع هنا أي منطق خاص بنوع اتصال واحد (فلترة الخريطة، snapshot
    الرحلة...). هذا الصنف يرث من AsyncJsonWebsocketConsumer التي لا تملك
    broadcast_event، فأي override هنا يستدعي super() سينهار — وينهار معه
    كل بثّ على كل غرفة في المشروع.
    """

    group_name = None  # يحدَّد في subclass عبر get_group_name()

    async def connect(self):
        # نقبل الاتصال أولاً عمدًا (حتى لو سيُرفض بعد قليل). السبب: لو رفضنا
        # *قبل* accept()، الـASGI server (Daphne) يرفض الـhandshake نفسه على
        # مستوى HTTP (403) والعميل لا يرى أي رسالة أو كود مفهوم - فقط
        # "connection failed" غامض. بعد accept()، نقدر نرسل سبب الرفض
        # كرسالة JSON واضحة قبل الإغلاق.
        await self.accept()

        user = self.scope.get("user")

        if user is None or not user.is_authenticated:
            await self.send_json({"event_type": "error", "detail": "Unauthorized"})
            await self.close(code=4401)
            return

        self.group_name = await self.get_group_name()

        if self.group_name is None:
            await self.send_json({"event_type": "error", "detail": "Forbidden"})
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)

        await self.send_json(
            {
                "event_type": "connection.established",
                "group": self.group_name,
            }
        )

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def get_group_name(self):
        raise NotImplementedError("subclasses must implement get_group_name()")

    # -----------------------------------------------------------
    # استقبال من العميل — عام فقط (ping)
    # -----------------------------------------------------------

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")

        if message_type == "ping":
            await self.send_json({"event_type": "pong"})
            return

        await self.send_json(
            {
                "event_type": "error",
                "detail": f"Unsupported message type: {message_type}",
            }
        )

    # -----------------------------------------------------------
    # استقبال من channel layer
    # -----------------------------------------------------------

    async def broadcast_event(self, event):
        """
        Handler عام لأي حدث يُبث عبر group_send بالشكل:
            {"type": "broadcast.event", "event_type": "...", "payload": {...}}
        (Channels يحوّل النقطة تلقائيًا: broadcast.event -> broadcast_event)

        هذا هو الجذر. الصنف الذي يريد فلترة يُعرّف نسخته الخاصة ويستدعي
        super().broadcast_event(event) — وهو ما يعمل من الأبناء فقط.
        """
        await self.send_json(
            {
                "event_type": event.get("event_type"),
                "payload": event.get("payload"),
            }
        )


class DriverConnectionConsumer(BaseAuthenticatedConsumer):
    """
    /ws/connection-test/driver/{driver_id}/
    اختبار اتصال فقط - يتحقق أن السائق الموثّق هو صاحب driver_id فعلاً.
    """

    async def get_group_name(self):
        user = self.scope["user"]
        url_driver_id = int(self.scope["url_route"]["kwargs"]["driver_id"])

        @database_sync_to_async
        def _get_driver_profile():
            # user.driver_profile هو reverse OneToOne accessor - أي وصول له
            # يشغّل استعلام DB. لازم يُغلَّف بـdatabase_sync_to_async وإلا
            # Django يرمي SynchronousOnlyOperation داخل الـconsumer الـasync.
            return getattr(user, "driver_profile", None)

        driver_profile = await _get_driver_profile()

        if driver_profile is None or driver_profile.id != url_driver_id:
            return None

        return f"driver_{url_driver_id}"


class CustomerConnectionConsumer(BaseAuthenticatedConsumer):
    """
    /ws/connection-test/customer/{ride_id}/
    اختبار اتصال فقط - يتحقق أن العميل الموثّق هو صاحب الرحلة فعلاً.
    """

    async def get_group_name(self):
        from rides.models import RideRequest

        user = self.scope["user"]
        ride_id = int(self.scope["url_route"]["kwargs"]["ride_id"])

        @database_sync_to_async
        def _ride_belongs_to_user():
            return RideRequest.objects.filter(id=ride_id, customer=user).exists()

        if not await _ride_belongs_to_user():
            return None

        return f"ride_{ride_id}"


# =================================================================
# غرفة الرحلة
# =================================================================

class RideConsumer(BaseAuthenticatedConsumer):
    """
    /ws/rides/{ride_id}/

    يخدم العميل صاحب الرحلة، وأيضًا السائق المُعيَّن عليها فعليًا (عرض
    مقبول). كل منطق resync/snapshot الخاص بالرحلة يعيش هنا حصرًا.
    """

    entity_type = "ride"

    async def get_group_name(self):
        self.ride_id = int(self.scope["url_route"]["kwargs"]["ride_id"])
        user = self.scope["user"]

        allowed = await self._user_can_access_ride(user, self.ride_id)

        if not allowed:
            return None

        return f"ride_{self.ride_id}"

    @staticmethod
    async def _user_can_access_ride(user, ride_id):

        @database_sync_to_async
        def _check(user_id, ride_id):
            from rides.models import RideRequest
            from matching.models import RideOffer, OfferStatus
            from users.models import DriverProfile

            if RideRequest.objects.filter(id=ride_id, customer_id=user_id).exists():
                return True

            driver_profile = (
                DriverProfile.objects
                .filter(user_id=user_id)
                .only("id")
                .first()
            )

            if driver_profile is None:
                return False

            return RideOffer.objects.filter(
                ride_id=ride_id,
                driver_id=driver_profile.id,
                status=OfferStatus.ACCEPTED,
            ).exists()

        return await _check(user.id, ride_id)

    async def connect(self):
        await super().connect()

        if self.group_name is None:
            # تم الرفض والرسالة والإغلاق تمّا بالفعل في connect() الأساسية.
            return

        snapshot = await self._build_snapshot(self.ride_id)
        await self.send_json(snapshot)

    @staticmethod
    async def _build_snapshot(ride_id):
        from realtime.events import EventBus

        @database_sync_to_async
        def _fetch():
            from rides.models import RideRequest
            from matching.models import RideOffer
            from rides.serializers import RideRequestSerializer
            from matching.serializers import RideOfferSerializer

            ride = RideRequest.objects.select_related("customer").get(id=ride_id)

            offers = (
                RideOffer.objects
                .filter(ride=ride)
                .exclude(status="withdrawn")
                .select_related("driver", "driver__user")
                .order_by("gross_fare", "eta_minutes")
            )

            return {
                "ride": RideRequestSerializer(ride).data,
                "offers": RideOfferSerializer(offers, many=True).data,
            }

        payload = await _fetch()

        # استدعاء متزامن (Redis) داخل async def -> يجب لفّه بـsync_to_async
        # حتى لا يحجب event loop عند Daphne.
        version = await sync_to_async(EventBus.get_current_version)("ride", ride_id)

        return {
            "event_type": "ride.snapshot",
            "entity_type": "ride",
            "entity_id": ride_id,
            "version": version,
            "payload": payload,
        }

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")

        if message_type == "resync":
            from realtime.events import EventBus

            since_version = int(content.get("since_version", 0))

            events = await sync_to_async(EventBus.get_events_since)(
                "ride", self.ride_id, since_version
            )

            if events:
                await self.send_json({"event_type": "ride.resync", "events": events})
            else:
                snapshot = await self._build_snapshot(self.ride_id)
                await self.send_json(snapshot)
            return

        await super().receive_json(content, **kwargs)


# =================================================================
# القناة الشخصية للسائق
# =================================================================

class DriverRoomConsumer(BaseAuthenticatedConsumer):
    """
    /ws/driver/{driver_id}/

    مسؤولياتها:
        - go_online / go_offline / heartbeat / location.update
        - تحديث PresenceService (Redis)
        - تحديث DriverProfile في DB بمعدل مخفَّف فقط
        - بثّ driver.location لغرف الرحلات النشطة
        - أفعال الدعوة ودورة حياة الرحلة
    """

    # لا نكتب لقاعدة البيانات عند كل نبضة GPS - نكتفي بتحديث Redis فورًا،
    # ونزامن DB كل DB_SYNC_MIN_INTERVAL_SECONDS على الأكثر.
    DB_SYNC_MIN_INTERVAL_SECONDS = 5

    async def get_group_name(self):
        user = self.scope["user"]
        self.driver_id = int(self.scope["url_route"]["kwargs"]["driver_id"])

        @database_sync_to_async
        def _get_driver_profile():
            return getattr(user, "driver_profile", None)

        driver_profile = await _get_driver_profile()

        if driver_profile is None or driver_profile.id != self.driver_id:
            return None

        return f"driver_{self.driver_id}"

    async def connect(self):
        await super().connect()
        self._last_db_sync = 0.0

    async def receive_json(self, content, **kwargs):
        message_type = content.get("type")

        handler = {
            "go_online": self._handle_go_online,
            "go_offline": self._handle_go_offline,
            "heartbeat": self._handle_heartbeat,
            "location.update": self._handle_location_update,
            "invitation.accept": self._handle_invitation_accept,
            "invitation.reject": self._handle_invitation_reject,
            "trip.arrived": self._handle_trip_arrived,
            "trip.start": self._handle_trip_start,
            "trip.complete": self._handle_trip_complete,
        }.get(message_type)

        if handler is None:
            await super().receive_json(content, **kwargs)
            return

        await handler(content)

    # -----------------------------------------------------------
    # GO ONLINE / OFFLINE
    # -----------------------------------------------------------
    @guarded(event="_handle_go_online")
    async def _handle_go_online(self, content):
        from presence.services import PresenceService

        driver = await self._get_driver_row()

        driver.online = True
        await database_sync_to_async(driver.save)(update_fields=["online", "updated_at"])

        # PresenceService.go_online متزامنة (Redis) - يجب لفّها، وإلا تحجب
        # event loop بأكمله.
        await sync_to_async(PresenceService.go_online)(driver)

        await self.send_json({"event_type": "presence.ack", "payload": {"status": "online"}})
    @guarded(event="_handle_go_offline")
    async def _handle_go_offline(self, content):
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService

        driver = await self._get_driver_row()

        driver.online = False
        await database_sync_to_async(driver.save)(update_fields=["online", "updated_at"])

        await sync_to_async(PresenceService.go_offline)(self.driver_id)
        await sync_to_async(MarketplaceService.handle_offline)(self.driver_id)

        await self.send_json({"event_type": "presence.ack", "payload": {"status": "offline"}})

    # -----------------------------------------------------------
    # HEARTBEAT
    # -----------------------------------------------------------
    @guarded(event="_handle_heartbeat")
    async def _handle_heartbeat(self, content):
        from presence.services import PresenceService, PresenceError

        try:
            await sync_to_async(PresenceService.heartbeat)(self.driver_id)
        except PresenceError:
            # نبضة بدون go_online سابق - نعامله كـgo_online ضمني بدل رفضه
            await self._handle_go_online(content)
            return

        await self.send_json({"event_type": "presence.ack", "payload": {"status": "heartbeat"}})

    # -----------------------------------------------------------
    # LOCATION UPDATE
    # -----------------------------------------------------------
    @guarded(event="_handle_location_update")
    async def _handle_location_update(self, content):
        import time

        from presence.services import PresenceService

        try:
            lng = float(content["lng"])
            lat = float(content["lat"])
        except (KeyError, TypeError, ValueError):
            await self.send_json(
                {"event_type": "error", "detail": "location.update requires numeric lng/lat"}
            )
            return

        from config.security import location_rejection

        now_epoch = time.time()
        reason = location_rejection(
            lng, lat, getattr(self, "_last_point", None), now_epoch
        )
        if reason is not None:
            # لا يُكتب ولا يُبثّ: موقعٌ مزيَّف يضع السائق قرب طلباتٍ ليس قربها.
            await self.send_json(
                {"event_type": "location.rejected", "payload": {"reason": reason}}
            )
            return
        self._last_point = (lng, lat, now_epoch)

        speed = content.get("speed")
        heading = content.get("heading")
        accuracy = content.get("accuracy")

        # 1) Redis أولاً وعلى كل نبضة - هذا هو الـhot path
        await sync_to_async(PresenceService.update_location)(
            self.driver_id, lng, lat, speed=speed, heading=heading, accuracy=accuracy
        )

        # 2) DB بمعدل مُخفَّف فقط
        now = time.time()
        if now - self._last_db_sync >= self.DB_SYNC_MIN_INTERVAL_SECONDS:
            await self._sync_location_to_db(lng, lat)
            self._last_db_sync = now

        # 3) بثّ ephemeral لكل غرفة رحلة نشطة.
        #
        # الجمع لا المفرد: سائق مشترك يحمل راكبين له رحلتان نشطتان، وكلاهما
        # ينتظر رؤية السيارة تتحرك. الصيغة المفردة كانت تُجمّد خريطة الأول
        # لحظة صعود الثاني.
        ride_ids = await self._get_active_ride_ids()

        if ride_ids:
            from realtime.events import EventBus

            location_payload = {
                "driver_id": self.driver_id,
                "lng": lng,
                "lat": lat,
                "speed": speed,
                "heading": heading,
                "accuracy": accuracy,
            }

            # غرفة لكل راكب. البثّ ephemeral فالتكرار رخيص، والبديل (غرفة
            # واحدة للسائق) يكشف لكل راكب وجود الآخرين.
            for ride_id in ride_ids:
                await sync_to_async(EventBus.publish_ephemeral)(
                    group_name=f"ride_{ride_id}",
                    event_type="driver.location",
                    payload=location_payload,
                )

        # تسجيل المسار — الخدمة تتجاهل ما ليس أثناء IN_PROGRESS، وتخنق
        # النقاط المتقاربة زمنيًا ومكانيًا.
        await self._record_trip_location(lng, lat, speed, heading, accuracy)

        # لوحة التشغيل ترى الحركة نفسها لحظيًّا بدل استطلاع دوري.
        try:
            from realtime.ops_live import OpsLiveBroadcaster

            await sync_to_async(OpsLiveBroadcaster.driver_moved)(
                self.driver_id, lng, lat
            )
        except Exception:  # noqa: BLE001 — اللوحة لا تُسقط تحديث الموقع
            pass

        # 4) عضوية الماركت بليس: خلية جديدة/نفس الخلية/اختفاء.
        from locations.services import LocationService
        from realtime.marketplace import MarketplaceService, VISIBLE_STATES

        cell_id = await sync_to_async(LocationService.compute_marketplace_cell_id)(lng, lat)

        snapshot = await sync_to_async(PresenceService.get_snapshot)(self.driver_id)
        state = await sync_to_async(PresenceService._resolve_state_from_snapshot)(snapshot)

        # SHARING مرئية أيضًا - لمن يوافق مسارها فقط، والفلترة تجري عند كل
        # مشاهد في MarketplaceConsumer لا هنا.
        is_available = state in VISIBLE_STATES

        payload = await sync_to_async(MarketplaceService.build_vehicle_payload)(
            self.driver_id, snapshot, None, lng, lat, heading,
        )

        await sync_to_async(MarketplaceService.handle_location_update)(
            self.driver_id, cell_id, payload, is_available,
        )

    # -----------------------------------------------------------
    # دورة حياة الرحلة
    # -----------------------------------------------------------
    @guarded(event="_handle_trip_arrived")
    async def _handle_trip_arrived(self, content):
        await self.send_json(await self._trip_action("arrived", content))

    @guarded(event="_handle_trip_start")
    async def _handle_trip_start(self, content):
        await self.send_json(await self._trip_action("start", content))

    @guarded(event="_handle_trip_complete")
    async def _handle_trip_complete(self, content):
        await self.send_json(await self._trip_action("complete", content))

    @database_sync_to_async
    def _trip_action(self, action, content):
        from trips.serializers import TripSerializer
        from trips.services.trip import TripError, TripService
        from users.models import DriverProfile

        ride_id = content.get("ride_id")

        if not ride_id:
            return {"event_type": "error", "detail": "ride_id is required"}

        driver = DriverProfile.objects.get(id=self.driver_id)

        try:
            trip = getattr(TripService, action)(ride_id=ride_id, driver=driver)
        except TripError as exc:
            return {"event_type": "trip.error", "detail": str(exc)}
        except Exception as exc:
            return {"event_type": "trip.error", "detail": str(exc)}

        return {"event_type": "trip.ack", "payload": TripSerializer(trip).data}

    @database_sync_to_async
    def _record_trip_location(self, lng, lat, speed, heading, accuracy):
        from trips.services.trip import TripService

        TripService.record_location_for_driver(
            self.driver_id, lng, lat,
            speed=speed, heading=heading, accuracy=accuracy, source="app",
        )

    # -----------------------------------------------------------
    # DB HELPERS
    # -----------------------------------------------------------

    @database_sync_to_async
    def _sync_location_to_db(self, lng, lat):
        from django.contrib.gis.geos import Point
        from django.utils import timezone
        from users.models import DriverProfile

        DriverProfile.objects.filter(id=self.driver_id).update(
            current_location=Point(lng, lat, srid=4326),
            last_location_at=timezone.now(),
        )

    @database_sync_to_async
    def _get_driver_row(self):
        from users.models import DriverProfile
        return DriverProfile.objects.get(id=self.driver_id)

    @database_sync_to_async
    def _get_vehicle_info(self):
        from users.models import DriverProfile

        driver = (
            DriverProfile.objects
            .prefetch_related("vehicles")
            .get(id=self.driver_id)
        )

        vehicle = next(
            (v for v in driver.vehicles.all() if v.active), None
        )

        return {
            "vehicle_type": vehicle.type_id if vehicle else None,
            "rating": float(driver.rating) if driver.rating is not None else None,
            "occupancy": driver.current_occupancy,
        }

    @database_sync_to_async
    def _get_active_ride_id(self):
        """
        نفس تعريف "مشغول" المستخدم في MatchingService.get_busy_driver_ids،
        لكن باتجاه معاكس: من سائق -> أحدث رحلة نشطة.

        أُبقيت للتوافق. المسارات الجديدة تستعمل الصيغة الجمعية أدناه.
        """
        ride_ids = self._active_ride_ids_sync()
        return ride_ids[0] if ride_ids else None

    @database_sync_to_async
    def _get_active_ride_ids(self):
        """كل رحلات السائق النشطة — رحلة لكل راكب في السيارة المشتركة."""
        return self._active_ride_ids_sync()

    def _active_ride_ids_sync(self):
        from matching.models import RideOffer, OfferStatus
        from rides.models import RideStatus

        active_statuses = [
            RideStatus.DRIVER_SELECTED,
            RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED,
            RideStatus.IN_PROGRESS,
        ]

        return list(
            RideOffer.objects
            .filter(
                driver_id=self.driver_id,
                status=OfferStatus.ACCEPTED,
                ride__status__in=active_statuses,
            )
            .order_by("-accepted_at")
            .values_list("ride_id", flat=True)
        )

    # -----------------------------------------------------------
    # الدعوة المباشرة
    # -----------------------------------------------------------
    @guarded(event="_handle_invitation_accept")
    async def _handle_invitation_accept(self, content):
        invitation_id = content.get("invitation_id")

        if not invitation_id:
            await self.send_json(
                {"event_type": "error", "detail": "invitation_id is required"}
            )
            return

        result = await self._respond_to_invitation(invitation_id, "accept", None)
        await self.send_json(result)
    @guarded(event="_handle_invitation_reject")
    async def _handle_invitation_reject(self, content):
        invitation_id = content.get("invitation_id")

        if not invitation_id:
            await self.send_json(
                {"event_type": "error", "detail": "invitation_id is required"}
            )
            return

        result = await self._respond_to_invitation(
            invitation_id, "reject", content.get("reason", "")
        )
        await self.send_json(result)

    @database_sync_to_async
    def _respond_to_invitation(self, invitation_id, action, reason):
        from matching.models import RideInvitation
        from matching.services.invitation import InvitationError, InvitationService
        from users.models import DriverProfile

        driver = DriverProfile.objects.get(id=self.driver_id)

        try:
            if action == "accept":
                invitation = InvitationService.accept(
                    invitation_id=invitation_id, driver=driver
                )
            else:
                invitation = InvitationService.reject(
                    invitation_id=invitation_id, driver=driver, reason=reason
                )
        except RideInvitation.DoesNotExist:
            return {"event_type": "invitation.error", "detail": "الدعوة غير موجودة."}
        except InvitationError as exc:
            return {"event_type": "invitation.error", "detail": str(exc)}

        return {
            "event_type": "invitation.ack",
            "payload": {
                "invitation_id": invitation.id,
                "ride_id": invitation.ride_id,
                "status": invitation.status,
            },
        }


# =================================================================
# خليّة الخريطة الحيّة
# =================================================================

class MarketplaceConsumer(BaseAuthenticatedConsumer):
    """
    /ws/marketplace/{area_id}/?ride_id=123

    قراءة فقط - أي مستخدم موثّق يمكنه الانضمام، بلا فحص ملكية، لأن
    البيانات المعروضة تقريبية أصلًا.

    ride_id اختياري. بوجوده يعرف الخادم ما الذي يبحث عنه هذا المشاهد،
    فيُظهر له السيارات المشتركة الموافقة لمساره ويُخفي ما لا يوافقه.
    بدونه يرى السيارات الفارغة فقط.
    """

    async def get_group_name(self):
        from realtime.marketplace import group_name_for_cell

        self.area_id = self.scope["url_route"]["kwargs"]["area_id"]
        self.viewer = await self._build_viewer()

        return group_name_for_cell(self.area_id)

    @database_sync_to_async
    def _build_viewer(self):
        from urllib.parse import parse_qs

        from realtime.marketplace import MarketplaceViewer
        from rides.models import RideRequest

        query = parse_qs((self.scope.get("query_string") or b"").decode())
        raw_ride_id = (query.get("ride_id") or [None])[0]

        if not raw_ride_id:
            return MarketplaceViewer.anonymous()

        user = self.scope["user"]

        ride = (
            RideRequest.objects
            .select_related("service_area")
            .filter(id=raw_ride_id, customer=user)
            .first()
        )

        # طلب ليس له: نعامله كمتصفّح بلا سياق، لا نرفض الاتصال. الرفض هنا
        # يعني شاشة خريطة فارغة بلا تفسير عند أول خطأ في العميل.
        return MarketplaceViewer.from_ride(ride)

    async def connect(self):
        await super().connect()

        if self.group_name is None:
            return

        snapshot = await self._build_snapshot(self.area_id, self.viewer)
        await self.send_json(snapshot)

    @staticmethod
    @database_sync_to_async
    def _build_snapshot(area_id, viewer):
        from presence.services import PresenceService
        from realtime.marketplace import MarketplaceService, VISIBLE_STATES
        from users.models import DriverProfile

        driver_ids = MarketplaceService.get_cell_member_ids(area_id)
        vehicles = []

        if driver_ids:
            snapshots = PresenceService.get_snapshots_bulk(driver_ids)

            drivers_by_id = {
                driver.id: driver
                for driver in (
                    DriverProfile.objects
                    .filter(id__in=driver_ids)
                    .select_related("user")
                    .prefetch_related("vehicles")
                )
            }

            for driver_id in driver_ids:
                data = snapshots.get(driver_id) or {}
                driver = drivers_by_id.get(driver_id)

                if driver is None or data.get("lng") in (None, ""):
                    continue

                if PresenceService._resolve_state_from_snapshot(data) not in VISIBLE_STATES:
                    continue

                payload = MarketplaceService.build_vehicle_payload(
                    driver_id, snapshot=data, driver=driver
                )

                visible, score = viewer.evaluate(payload)

                if not visible:
                    continue

                if score is not None:
                    payload["compatibility_score"] = score

                vehicles.append(payload)

        return {
            "event_type": "marketplace.snapshot",
            "entity_type": "marketplace_cell",
            "entity_id": area_id,
            "payload": {"vehicles": vehicles},
        }

    async def broadcast_event(self, event):
        """
        الخليّة الواحدة تبثّ للجميع، وكل مشاهد يقرر ما يعنيه.

        الحالة اللطيفة هنا: مشاهد كانت السيارة مرسومة عنده ثم صارت مشتركة
        بمسار لا يوافقه. لا يكفي أن نتجاهل التحديث - السيارة ستبقى مرسومة
        على شاشته إلى الأبد. فنحوّل التحديث عنده إلى vehicle.left_area،
        وهذا هو الفرق بين خريطة صحيحة وخريطة تكذب بالصمت.

        ملاحظة: هذا override يخصّ هذا الصنف وحده. نقله إلى
        BaseAuthenticatedConsumer يجعل super() بلا هدف وينهار كل بثّ في
        المشروع — وقد حدث ذلك فعلًا مرة.
        """
        event_type = event.get("event_type")
        payload = event.get("payload") or {}

        if event_type in ("vehicle.entered_area", "vehicle.updated"):
            visible, score = self.viewer.evaluate(payload)

            if not visible:
                if payload.get("driver_id") is not None:
                    await self.send_json({
                        "event_type": "vehicle.left_area",
                        "payload": {"driver_id": payload["driver_id"]},
                    })
                return

            if score is not None:
                payload = {**payload, "compatibility_score": score}

            await self.send_json({"event_type": event_type, "payload": payload})
            return

        await super().broadcast_event(event)

# =====================================================================
# غرفة لوحة التشغيل — /ws/admin/live/
# =====================================================================


ADMIN_LIVE_GROUP = "admin_live"


class AdminLiveConsumer(BaseAuthenticatedConsumer):
    """
    /ws/admin/live/

    الغرفة التي تشترطها الوثيقة (§7) وكانت غائبة: لوحة التشغيل كانت
    تستطلع `/ops/drivers/live/` كلّ بضع ثوانٍ. الفرق ليس أناقةً — مشغّل
    يبحث عن سائق مفقود يرى موقعه متأخّرًا بمقدار دورة الاستطلاع كاملة،
    وعشر لوحات مفتوحة تعني عشرة استعلامات جغرافية كاملة كلّ ثانيتين.

    ما يصل إليها
    ------------
    كلّ ما يحتاج إنسانًا: رحلة عالقة، سائق تعذّر تحريره، دفعة متوقّفة،
    تدخّل إداري وقع، وتحديثات مواقع السائقين. البثّ إليها يتمّ عبر
    `OpsLiveBroadcaster` أدناه لا مباشرةً، فتبقى أسماء الأحداث في مكان
    واحد.

    الصلاحية
    --------
    `is_staff` فقط، ويُفحص داخل `get_group_name` — إعادة None هناك تُغلق
    الاتصال بـ4403 برسالة مفهومة. وهذه ليست شكليّة: الغرفة تبثّ إحداثيات
    دقيقة وأرقام هواتف، وهي بالضبط ما تخفيه الخريطة العامّة عن الزبائن.
    """

    async def get_group_name(self):
        user = self.scope.get("user")

        # نفس تعريف `IsStaffOrSupport` حرفًا بحرف — لا نسخة ثالثة.
        # اختلاف التعريف بين REST وWebSocket هو ما جعل حساب دعم يُمنع
        # من نقطة REST ويقرأ البيانات نفسها بثًّا حيًّا.
        from users.models import UserRole

        allowed = bool(
            getattr(user, "is_staff", False)
            or getattr(user, "role", "") in (UserRole.ADMIN, UserRole.SUPPORT)
        )

        if not allowed:
            return None

        return ADMIN_LIVE_GROUP

    async def connect(self):
        await super().connect()

        if self.group_name is None:
            return

        snapshot = await self._build_snapshot()
        await self.send_json(snapshot)

    @database_sync_to_async
    def _build_snapshot(self):
        """
        لقطة أولى فور الاتصال: اللوحة يجب أن تُظهر الحالة الحاضرة قبل أن
        يصلها أوّل حدث. اتصالٌ يفتح على شاشة فارغة ينتظر حدثًا قد لا يأتي
        لدقائق هو ما يجعل المشغّل يعيد التحميل ويشكّ في الأداة.
        """
        from ops.services.health import OpsHealthService

        try:
            return {
                "event_type": "admin.snapshot",
                "entity_type": "admin_live",
                "entity_id": 0,
                "payload": {
                    "overview": OpsHealthService.overview(),
                    "attention": OpsHealthService.attention(),
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "event_type": "admin.snapshot",
                "entity_type": "admin_live",
                "entity_id": 0,
                "payload": {"error": str(exc)[:200]},
            }

    async def receive_json(self, content, **kwargs):
        """`refresh` يعيد بناء اللقطة عند الطلب — بلا إعادة اتصال."""
        if content.get("type") == "refresh":
            await self.send_json(await self._build_snapshot())
            return

        await super().receive_json(content, **kwargs)
