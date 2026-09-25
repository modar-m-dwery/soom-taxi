/// وحدة تحكّم قوس الرحلة.
///
/// هي الموضع الوحيد الذي يتكلّم غرفة الرحلة، والموضع الوحيد الذي يغيّر
/// حالة القوس. السبب أنّ التوزيع هنا مكلف: ثلاث شاشات تشترك بالغرفة
/// نفسها تعني ثلاثة اشتراكات وثلاثة حرّاس ترتيب وثلاث نسخ من الحالة —
/// وواحدةٌ منها ستتأخّر عن الأخريات في لحظة ما.
///
/// القواعد المنفَّذة هنا، وكلّ واحدة منها بندٌ في §12:
///
///  • كلّ حدث يمرّ بحارس الترتيب. المتأخّر يُهمَل، والفجوة تُطلق `resync`.
///  • إعادة الاتصال تُطلق `/me/active-ride/` **مرّة واحدة**.
///  • 409 عند اختيار عرض ليست شاشة خطأ بل قائمة محدَّثة.
///  • مهلة الدعوة من `invitation_ttl_options` حصرًا.
///  • التهدئة بعد الرفض تُخفي السائق محلّيًّا قبل أن يردّ الخادم 400.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../../providers.dart';
import 'ride_state.dart';

final rideControllerProvider =
    NotifierProvider<RideController, RideArc>(RideController.new);

class RideController extends Notifier<RideArc> {
  RealtimeRoom? _room;
  StreamSubscription<GuardedEvent>? _events;
  Timer? _cooldownTimer;

  /// الخادم لا يبثّ حدثًا حين يؤكّد السائق قبض النقد، فشاشة النهاية
  /// كانت تبقى على «بانتظار تأكيد السائق» إلى أن يُعاد فتح التطبيق.
  /// نستطلع الدفعة ما دامت معلّقة، ونتوقّف فور حسمها.
  Timer? _paymentWatch;

  @override
  RideArc build() {
    ref.onDispose(_teardown);

    // اللقطة من الإقلاع هي نقطة البدء: مستخدمٌ أغلق التطبيق والسائق في
    // الطريق يعود إلى شاشة التتبّع لا إلى شاشة طلب جديد.
    final snapshot = ref.watch(bootSnapshotProvider);
    if (snapshot == null) return const RideArc();

    Future.microtask(() => _adoptSnapshot(snapshot));

    return RideArc(
      ride: snapshot.ride,
      trip: snapshot.trip,
      pendingPayment: snapshot.pendingPayment,
    );
  }

  Soum get _soum => ref.read(soumProvider);
  AppConfig get _config => ref.read(configProvider);

  // =================================================================
  // إنشاء الطلب
  // =================================================================

  Future<RideRequest?> createRide({
    required GeoPoint pickup,
    required GeoPoint destination,
    required String mode,
    required int passengerCount,
    String? vehicleType,
    DateTime? scheduledAt,
    TripCategory tripCategory = TripCategory.city,
    String? originCity,
    String? destinationCity,
    double? searchRadiusKm,
    bool autoDispatch = false,
  }) async {
    state = state.copyWith(isBusy: true);

    try {
      final ride = await _soum.rides.create(
        pickup: pickup,
        destination: destination,
        mode: mode,
        passengerCount: passengerCount,
        requestedVehicleType: vehicleType,
        scheduledAt: scheduledAt,
        tripCategory: tripCategory,
        originCity: originCity,
        destinationCity: destinationCity,
        searchRadiusKm: searchRadiusKm,
        autoDispatch: autoDispatch,
      );

      state = RideArc(ride: ride);
      _openRoom(ride.id);
      return ride;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, lastError: error, clearError: false);
      return null;
    }
  }

  /// `reasonCode` يُرسل مع إلغاء رحلةٍ لها سائق: «السائق طلب منّي أن ألغي»
  /// بالذات إشارةٌ على سائقٍ يُكمل المشوار خارج التطبيق.
  Future<void> cancelRide({String? reason, CancelReason? reasonCode}) async {
    final ride = state.ride;
    if (ride == null) return;

    state = state.copyWith(isBusy: true);
    try {
      await _soum.rides.cancel(ride.id, reason: reason, reasonCode: reasonCode);
      // لا نصفّر محلّيًّا: الخادم يبثّ `ride.cancelled` فتُصفّر من الحدث.
      // التصفير هنا يجعل الشاشة تسبق الخادم، فيختلفان إن فشل الإلغاء.
      state = state.copyWith(isBusy: false);
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, lastError: error, clearError: false);
    }
  }

  // =================================================================
  // المزاد
  // =================================================================

  Future<void> refreshOffers() async {
    final ride = state.ride;
    if (ride == null) return;

    try {
      final offers = await _soum.rides.offers(ride.id);
      state = state.copyWith(offers: _sorted(offers));
    } on ApiException {
      // فشل تحديثٍ لا يُفرغ قائمة قائمة. الغرفة ستصحّحها.
    }
  }

  /// §4.4 — السباق الذي سيقابلك.
  ///
  /// 409 هنا **ليست عطلًا**: زبون آخر اختار السائق نفسه في اللحظة نفسها،
  /// والخادم أقفل الصفّ فردّ على الثاني. المطلوب رسالة لطيفة وقائمة
  /// محدَّثة — لا شاشة خطأ تُخرج الزبون من التدفّق.
  /// «سوم» بنمط inDrive: يعرض الزبون سعره أو يرفعه وهو ينتظر العروض.
  Future<bool> proposeFare(Money fare) async {
    final ride = state.ride;
    if (ride == null) return false;

    state = state.copyWith(isBusy: true);
    try {
      final updated = await _soum.rides.proposeFare(ride.id, fare);
      state = state.copyWith(isBusy: false, ride: updated);
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, lastError: error, clearError: false);
      return false;
    }
  }

  Future<bool> selectOffer(int offerId) async {
    final ride = state.ride;
    if (ride == null) return false;

    state = state.copyWith(isBusy: true);

    try {
      await _soum.rides.selectOffer(ride.id, offerId);
      // الرحلة أُنشئت في الخادم. `offer.accepted` سيصل عبر الغرفة، لكنّ
      // اللقطة الآن تحسم الشاشة بلا انتظار حدثٍ قد يسبقه انقطاع.
      await _resyncFromServer();
      state = state.copyWith(isBusy: false);
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, lastError: error, clearError: false);

      // الفحص على `isDriverTaken` لا على الرمز: الخادم لا يرسل رمزًا
      // على هذا المسار — راجع التعليق في ApiException.
      if (error.isDriverTaken || error.code == ApiErrorCode.offerExpired) {
        await refreshOffers();
      }
      return false;
    }
  }

  // =================================================================
  // الدعوة المباشرة
  // =================================================================

  Future<List<NearbyVehicle>> nearbyVehicles() async {
    final ride = state.ride;
    if (ride == null) return const [];

    try {
      final vehicles = await _soum.invitations.nearbyVehicles(ride.id);
      // السائقون في التهدئة يُخفَون هنا لا في الشاشة: إخفاؤهم في موضع
      // واحد يعني أنّ كلّ شاشة تعرض القائمة تحترم القيد.
      return vehicles
          .where((v) => !state.cooldownDrivers.contains(v.driverId))
          .toList(growable: false);
    } on ApiException catch (error) {
      state = state.copyWith(lastError: error, clearError: false);
      return const [];
    }
  }

  /// [ttlSeconds] يجب أن تكون من `timings.invitationTtlOptions`.
  /// أيّ قيمة أخرى يرفضها الخادم بـ400، فنمنعها هنا قبل النداء.
  Future<bool> inviteDriver(int driverId, {int? ttlSeconds}) async {
    final ride = state.ride;
    if (ride == null) return false;

    final timings = _config.timings;
    final ttl = ttlSeconds ?? timings.invitationTtlDefault;

    if (!timings.invitationTtlOptions.contains(ttl)) {
      assert(false, 'مهلة دعوة خارج الخيارات المسموح بها: $ttl');
      return false;
    }

    state = state.copyWith(isBusy: true);

    try {
      final invitation = await _soum.invitations.invite(
        rideId: ride.id,
        driverId: driverId,
        ttlSeconds: ttl,
      );
      state = state.copyWith(invitation: invitation, isBusy: false);
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, lastError: error, clearError: false);

      if (error.code == ApiErrorCode.invitationCooldown) {
        _startCooldown(driverId);
      }
      return false;
    }
  }

  /// يُخفي السائق مدّة التهدئة ثمّ يعيده تلقائيًّا.
  ///
  /// الإعادة التلقائية مقصودة: الإخفاء الدائم يجعل الزبون يظنّ أنّ السيارة
  /// غادرت المنطقة، بينما هي واقفة أمامه.
  void _startCooldown(int driverId) {
    state = state.copyWith(
      cooldownDrivers: {...state.cooldownDrivers, driverId},
    );

    _cooldownTimer?.cancel();
    _cooldownTimer = Timer(
      Duration(seconds: _config.timings.invitationRejectCooldownSeconds),
      () {
        final next = {...state.cooldownDrivers}..remove(driverId);
        state = state.copyWith(cooldownDrivers: next);
      },
    );
  }

  // =================================================================
  // غرفة الرحلة
  // =================================================================

  void _adoptSnapshot(ActiveRideSnapshot snapshot) {
    state = RideArc(
      ride: snapshot.ride,
      trip: snapshot.trip,
      pendingPayment: snapshot.pendingPayment,
    );

    // اسم الغرفة من الخادم لا مبنيًّا هنا.
    final room = snapshot.rooms.rideRoom;
    if (room != null) _openRoomPath(room);
  }

  /// الموضع **الوحيد** في المشروع الذي يُبنى فيه مسار غرفة.
  ///
  /// القاعدة العامّة أنّ المسارات تأتي من `/me/active-ride/` تحت
  /// `realtime` — يبنيها الخادم «لأنّ أي تغيير في مسارات
  /// `realtime/routing.py` غدًا كان سيتطلّب إصدار تطبيق جديد لو كانت
  /// مبنيّة في العميل».
  ///
  /// والاستثناء هنا مقصود ومحصور: بعد `POST /rides/` مباشرةً لا تحمل
  /// الاستجابةُ مسارَ غرفة، ونداء `/me/active-ride/` لقراءته يفتح نافذةً
  /// من مئات الميلي ثانية قد يصل فيها أوّل عرض قبل الاشتراك — فيضيع.
  /// والمسار نفسه موثَّق حرفيًّا في §4.1 و§7.1 من دليل التكامل.
  ///
  /// وأثر هذا الاقتران محدود: إعادة الاتصال والاستئناف يقرآن المسار من
  /// الخادم، فتغييرٌ في مسارات البثّ يكسر أوّل اشتراك وحده ويُصحَّح عند
  /// أوّل إعادة اتصال.
  ///
  /// **التوصية للباك إند:** إضافة `realtime.ride_room` إلى استجابة
  /// `POST /rides/` تُلغي هذا الاستثناء كاملًا.
  void _openRoom(int rideId) => _openRoomPath('/ws/rides/$rideId/');

  void _openRoomPath(String path) {
    _teardown();

    final room = _soum.room(path);
    _room = room;

    // الخطوة الثالثة من قاعدة إعادة الاتصال (§7.3): نداء واحد بعد عودة
    // المقبس. الغرفة تُطلقها بعد **نجاح** الاتصال لا عند كلّ محاولة.
    room.onReconnected = _resyncFromServer;

    _events = room.events.listen(_onEvent);
    unawaited(room.connect());
  }

  Future<void> _resyncFromServer() async {
    try {
      final snapshot = await _soum.rides.activeRide();
      state = state.copyWith(
        ride: snapshot.ride,
        trip: snapshot.trip,
        pendingPayment: snapshot.pendingPayment,
        clearRide: snapshot.ride == null,
        clearTrip: snapshot.trip == null,
        // الدفعة أيضًا: بلا هذا كانت تبقى بعد أن يقول الخادم «لا شيء
        // قائم»، فتبقى شاشة النهاية إلى الأبد.
        clearPayment: snapshot.pendingPayment == null,
      );
      await refreshOffers();
    } on ApiException {
      // الحالة السابقة تبقى؛ اللقطة القادمة من الغرفة ستصحّحها.
    }
  }

  /// مغادرة شاشة النهاية — بعد التقييم أو بتخطّيه.
  ///
  /// لماذا لا يكفي `refreshActiveRide` في الإقلاع: لقطة الإقلاع بعد
  /// الرحلة تساوي لقطة ما قبلها («لا شيء قائم»)، و`ActiveRideSnapshot`
  /// يقارن بالقيمة — فلا يُبلَّغ أحد، ويبقى الزبون على «شكرًا لتقييمك»
  /// وزرّ التخطّي لا يفعل شيئًا. قِيس على المحاكي.
  Future<void> leaveFinished() async {
    _paymentWatch?.cancel();
    _paymentWatch = null;
    await _resyncFromServer();
    if (state.ride == null && state.trip == null) {
      _teardown();
      state = RideArc(pendingPayment: state.pendingPayment);
    }
  }

  void _onEvent(GuardedEvent guarded) {
    // المتأخّر يُهمَل — لا يُطبَّق ولا يُحسب.
    if (guarded.isStale) return;

    // الفجوة: نطبّق الحدث **و**نطلب اللحاق. لا نخمّن ما فات.
    if (guarded.needsResync) {
      final entityId = guarded.event.entityId;
      if (entityId != null) {
        _room?.requestResync(guarded.event.entityType ?? 'ride', entityId);
      }
    }

    final event = guarded.event;
    final data = event.data;

    switch (event.type) {
      case RealtimeEventType.rideSnapshot:
        _applySnapshot(data);

      case RealtimeEventType.offerCreated:
        _upsertOffer(RideOffer.fromJson(data));

      case RealtimeEventType.offerExpired:
        _removeOffer(readInt(data, 'id'));

      // `offer.accepted` هو ما يصل غرفةَ الرحلة العادية فعلًا؛ أمّا
      // `ride.driver_selected` فلا يبثّه الخادم إلّا لأعضاء الرحلة
      // المشتركة. الاكتفاء بالثاني ترك الزبون على شاشة البحث بعد أن
      // اختار سائقه — قِيس على خادم يعمل.
      case RealtimeEventType.offerAccepted:
      case RealtimeEventType.rideDriverSelected:
        _applyDriverSelected(data);

      case RealtimeEventType.driverLocation:
        final point = GeoPoint.fromJson(data);
        if (point != null) state = state.copyWith(driverLocation: point);

      case RealtimeEventType.driverArrived:
      case RealtimeEventType.tripStarted:
        _applyTrip(data);

      case RealtimeEventType.tripCompleted:
        _applyCompleted(data);

      case RealtimeEventType.tripCancelled:
      case RealtimeEventType.rideCancelled:
      case RealtimeEventType.rideCancelledByDriver:
      case RealtimeEventType.rideExpired:
        _applyEnded(event.type, data);

      case RealtimeEventType.invitationSent:
        _applyInvitation(data);

      // السائق قبل الدعوة = الرحلة صارت له. الحدث يحمل الدعوة لا الرحلة،
      // فاللقطة من الخادم تحسم الشكل (سائق، مركبة، أجرة). بلا هذا بقي
      // الزبون على شاشة البحث والسائق في طريقه إليه — قِيس بهاتف حقيقيّ
      // (العيب #35).
      case RealtimeEventType.invitationAccepted:
        state = state.copyWith(clearInvitation: true);
        unawaited(_resyncFromServer());

      case RealtimeEventType.invitationRejected:
        _applyInvitationRejected(data);

      case RealtimeEventType.invitationExpired:
      case RealtimeEventType.invitationCancelled:
        // §5.1: «أعد الزبون للخريطة تلقائيًّا».
        state = state.copyWith(clearInvitation: true);

      case RealtimeEventType.autoDispatchExhausted:
        state = state.copyWith(
          clearInvitation: true,
          autoDispatchExhausted: true,
        );
    }
  }

  void _applySnapshot(Json data) {
    final rideJson = asJsonOrNull(data['ride']);
    final offersRaw = data['offers'];

    state = state.copyWith(
      ride: rideJson == null ? null : RideRequest.fromJson(rideJson),
      clearRide: rideJson == null,
      offers: offersRaw is List
          ? _sorted(offersRaw
              .whereType<Map>()
              .map((e) => RideOffer.fromJson(e.cast<String, dynamic>()))
              .toList())
          : state.offers,
    );
  }

  void _upsertOffer(RideOffer offer) {
    final next = [...state.offers.where((o) => o.id != offer.id)];
    if (offer.status.isLive) next.add(offer);
    state = state.copyWith(offers: _sorted(next));
  }

  void _removeOffer(int offerId) {
    state = state.copyWith(
      offers: state.offers.where((o) => o.id != offerId).toList(growable: false),
    );
  }

  void _applyDriverSelected(Json data) {
    final trip = asJsonOrNull(data['trip']);
    final ride = asJsonOrNull(data['ride']);

    state = state.copyWith(
      ride: ride == null ? null : RideRequest.fromJson(ride),
      trip: trip == null ? null : Trip.fromJson(trip),
      offers: const [],
      clearInvitation: true,
    );

    // الحمولة قد تحمل الرحلة وقد لا تحملها بحسب المسار الذي أنشأها
    // (مزاد أو دعوة). القراءة من الخادم تحسم الأمر بلا تخمين.
    if (trip == null) unawaited(_resyncFromServer());
  }

  void _applyTrip(Json data) {
    final trip = asJsonOrNull(data['trip']) ?? data;

    // أحداث الرحلة (`driver.arrived`، `trip.started`…) تحمل حمولةً
    // مختصرة: `trip_id` والحالة والأجرة — بلا اسم السائق ولا مركبته.
    // بناءُ Trip منها كان يمحو الاسم واللوحة من البطاقة لحظة الوصول.
    // الحمولة الكاملة (فيها `driver_name`) تُطبَّق كما هي؛ المختصرة
    // تُستكمل من الخادم.
    if (trip.containsKey('status') && trip.containsKey('driver_name')) {
      state = state.copyWith(trip: Trip.fromJson(trip));
    } else {
      unawaited(_resyncFromServer());
    }
  }

  void _applyCompleted(Json data) {
    final tripJson = asJsonOrNull(data['trip']) ?? data;
    final paymentJson = asJsonOrNull(data['payment']);

    // حمولة `trip.completed` مختصرة (بلا اسم السائق) ولا تحمل الطلب.
    // والمرحلة تُشتقّ من حالة **الطلب** بعد انتهاء الرحلة — فبقاؤه على
    // `in_progress` كان يُبقي الزبون على «في الطريق إلى وجهتك» إلى الأبد
    // بعد أن أنهى السائق. اللقطة تجلب الطلب والرحلة والدفعة معًا.
    if (tripJson.containsKey('driver_name')) {
      state = state.copyWith(
        trip: Trip.fromJson(tripJson),
        pendingPayment:
            paymentJson == null ? null : Payment.fromJson(paymentJson),
      );
      if (paymentJson == null) unawaited(_loadPayment());
      return;
    }

    unawaited(_resyncFromServer().then((_) => _loadPayment()));
  }

  Future<void> _loadPayment() async {
    // بعد الاكتمال تعود اللقطة بلا طلب ولا رحلة — الدفعة وحدها تبقى،
    // وهي تحمل رقم الطلب. بدونها كان الاستطلاع يتوقّف بعد أوّل قراءة.
    final rideId = state.ride?.id ??
        state.trip?.rideId ??
        state.pendingPayment?.rideId;
    if (rideId == null) return;

    try {
      final payment = await _soum.payments.forTrip(rideId);
      state = state.copyWith(pendingPayment: payment);
      _watchPayment(payment);
    } on ApiException {
      // بلا دفعة نُبقي شاشة النهاية بلا قسم دفع — لا شاشة خطأ.
    }
  }

  void _watchPayment(Payment payment) {
    final settled = payment.status != PaymentStatus.pending;
    if (settled) {
      _paymentWatch?.cancel();
      _paymentWatch = null;
      return;
    }
    _paymentWatch ??= Timer.periodic(
      const Duration(seconds: 8),
      (_) => unawaited(_loadPayment()),
    );
  }

  void _applyEnded(String type, Json data) {
    // السائق اعتذر والطلب عاد إلى البحث: لا نهاية، بل شاشة العروض من جديد
    // ورسالةٌ تقول ما حدث.
    if (type == RealtimeEventType.rideCancelledByDriver &&
        readBool(data, 'requeued')) {
      state = state.copyWith(
        clearInvitation: true,
        clearTrip: true,
        driverRequeued: true,
      );
      unawaited(_resyncFromServer());
      return;
    }

    _teardown();

    state = RideArc(
      pendingPayment: state.pendingPayment,
      endedReason: readStringOrNull(data, 'reason') ??
          readStringOrNull(data, 'cancel_reason') ??
          type,
      ended: rideEndFor(type, data),
    );
  }

  void _applyInvitation(Json data) {
    if (!data.containsKey('status')) return;
    state = state.copyWith(invitation: RideInvitation.fromJson(data));
  }

  void _applyInvitationRejected(Json data) {
    final driverId = readIntOrNull(data, 'driver');
    state = state.copyWith(clearInvitation: true);
    // §5.1: «أخفِ سيارته مؤقّتًا واقترح غيرها».
    if (driverId != null) _startCooldown(driverId);
  }

  /// الأرخص أوّلًا، وعند تساوي السعر الأسرع وصولًا — نفس ترتيب الخادم في
  /// اللقطة، فلا تقفز القائمة حين تُستبدل بلقطة بعد إعادة اتصال.
  static List<RideOffer> _sorted(List<RideOffer> offers) {
    final next = [...offers];
    next.sort((a, b) {
      final byFare = a.grossFare.compareTo(b.grossFare);
      return byFare != 0 ? byFare : a.etaMinutes.compareTo(b.etaMinutes);
    });
    return List.unmodifiable(next);
  }

  void _teardown() {
    _cooldownTimer?.cancel();
    _cooldownTimer = null;
    _paymentWatch?.cancel();
    _paymentWatch = null;
    _events?.cancel();
    _events = null;
    unawaited(_room?.close());
    _room = null;
  }
}

/// كيف انتهى الطلب، من حدث النهاية — null إن ألغاه الزبون بيده.
RideEnd? rideEndFor(String type, Json data) {
  if (type == RealtimeEventType.rideExpired) return RideEnd.expired;
  if (readStringOrNull(data, 'kind') == 'no_show') return RideEnd.noShow;
  // الزبون ألغى بيده: يعرف ما حدث، فلا رسالة.
  if (readStringOrNull(data, 'cancelled_by') == 'customer') return null;
  return RideEnd.cancelledByOther;
}
