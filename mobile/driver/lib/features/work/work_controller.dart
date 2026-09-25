/// عمل السائق — الطلبات والعروض والدعوات وتنفيذ الرحلة.
///
/// السائق طرفٌ يعرض ويقبل ويرفض، لا منفّذ لأمر. وهذا يعني أنّ شاشاته
/// أقسى من شاشات الزبون في ثلاثة مواضع:
///
/// **المهل بالثواني.** الدعوة مهلتها عشرون ثانية افتراضًا، والعرض ثلاثون.
/// عدّادٌ يخطئ بثانيتين هنا يعني دعوةً تُقبَل بعد انقضائها فتردّ 400.
///
/// **الترتيب مفروض من الخادم.** `start` قبل `arrived` يردّ
/// `trip.not_arrived`، و`complete` قبل `start` يردّ `trip.not_started`.
/// فالأزرار تُعطَّل بالترتيب نفسه لا لتجميل الواجهة بل لأنّ الضغط عليها
/// خارج الترتيب ينتهي بخطأ لا يفهمه السائق.
///
/// **الحارس الجغرافيّ.** «وصلت» تُرفض خارج `arrival_radius_m`. §12.3:
/// «عندما يظهر لك هذا الردّ فالسائق لم يصل فعلًا — اعرض له المسافة
/// المتبقّية، ولا تعِد المحاولة تلقائيًّا».
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../../providers.dart';
import '../presence/presence_controller.dart';
import '../presence/presence_state.dart';

class WorkState {
  const WorkState({
    this.candidates = const [],
    this.invitation,
    this.ride,
    this.trip,
    this.payment,
    this.isBusy = false,
    this.failure,
    this.trips = const [],
  });

  /// كلّ رحلات السائق النشطة. أكثر من واحدة = رحلة مشتركة: لكلّ راكب
  /// التقاطه وإنزاله وأجرته. `ride`/`trip` أدناه هما الراكب المعروض الآن.
  final List<DriverTripEntry> trips;

  /// الطلبات المؤهَّلة لهذا السائق وحده.
  final List<RideRequest> candidates;

  /// دعوة واردة معلّقة — تصل عبر غرفة السائق.
  final RideInvitation? invitation;

  final RideRequest? ride;
  final Trip? trip;
  final Payment? payment;

  final bool isBusy;
  final ApiException? failure;

  bool get hasRunningTrip => trip != null && trip!.isRunning;
  bool get hasIncomingInvitation => invitation != null && invitation!.isPending;

  /// المرحلة التي يعرضها التطبيق، مشتقّة من الحالات الواصلة.
  ResumeStage get stage {
    final currentTrip = trip;
    if (currentTrip != null) {
      final fromTrip = switch (currentTrip.status) {
        TripStatus.created => ResumeStage.driverAssigned,
        TripStatus.driverArriving => ResumeStage.driverArriving,
        TripStatus.driverArrived => ResumeStage.driverArrived,
        TripStatus.inProgress => ResumeStage.inProgress,
        _ => null,
      };
      if (fromTrip != null) return fromTrip;
    }
    return payment != null ? ResumeStage.awaitingPayment : ResumeStage.idle;
  }

  WorkState copyWith({
    List<RideRequest>? candidates,
    RideInvitation? invitation,
    RideRequest? ride,
    Trip? trip,
    Payment? payment,
    bool? isBusy,
    ApiException? failure,
    bool clearInvitation = false,
    bool clearTrip = false,
    bool clearPayment = false,
    bool clearFailure = true,
    List<DriverTripEntry>? trips,
  }) =>
      WorkState(
        trips: trips ?? this.trips,
        candidates: candidates ?? this.candidates,
        invitation: clearInvitation ? null : (invitation ?? this.invitation),
        ride: clearTrip ? null : (ride ?? this.ride),
        trip: clearTrip ? null : (trip ?? this.trip),
        payment: clearPayment ? null : (payment ?? this.payment),
        isBusy: isBusy ?? this.isBusy,
        failure: clearFailure ? failure : (failure ?? this.failure),
      );
}

final workControllerProvider =
    NotifierProvider<WorkController, WorkState>(WorkController.new);

class WorkController extends Notifier<WorkState> {
  StreamSubscription<GuardedEvent>? _driverEvents;
  /// غرفةٌ لكلّ راكب: حدث أيّ منهم (ألغى، دفع) يجب أن يصل ولو لم يكن
  /// المعروض الآن.
  final Map<int, RealtimeRoom> _rideRooms = {};
  final Map<int, StreamSubscription<GuardedEvent>> _rideEvents = {};
  Timer? _poll;

  @override
  WorkState build() {
    ref.onDispose(_teardown);

    final snapshot = ref.watch(bootSnapshotProvider);

    // الاشتراك في غرفة السائق يتبع الحضور: الغرفة تُفتح مع `go-online`،
    // وهي نفسها التي تحمل الدعوات الواردة.
    ref.listen(presenceControllerProvider, (previous, next) {
      final cameOnline = next.isOnline && previous?.isOnline != true;
      // غرفةٌ جديدة والحضور مستمرّ (عودة من الخلفية): نعيد الاشتراك،
      // وإلّا بقينا نسمع غرفةً أُغلقت.
      final newRoom = next.isOnline &&
          previous != null &&
          previous.roomGeneration != next.roomGeneration;
      if (cameOnline || newRoom) {
        _attachDriverRoom();
        if (cameOnline) {
          unawaited(refreshCandidates());
          _startPolling();
        }
      } else if (!next.isOnline) {
        _driverEvents?.cancel();
        _driverEvents = null;
        _poll?.cancel();
        _poll = null;
        state = state.copyWith(candidates: const []);
      }
    });

    if (snapshot != null) {
      Future.microtask(() => _adoptSnapshot(snapshot));
    }

    return WorkState(
      ride: snapshot?.ride,
      trip: snapshot?.trip,
      payment: snapshot?.pendingPayment,
      trips: snapshot?.allTrips ?? const [],
    );
  }

  Soum get _soum => ref.read(soumProvider);
  AppConfig get _config => ref.read(configProvider);

  // =================================================================
  // الطلبات المؤهَّلة
  // =================================================================

  /// استقصاءٌ مقصود هنا وحده.
  ///
  /// `/driver/rides/candidates/` لا تُقابلها غرفةُ بثّ: الطلب الجديد
  /// يُبثّ إلى غرفة الرحلة لا إلى السائقين، والخادم يُخطر السائقين
  /// بالإشعارات لا بالمقبس. فالاستقصاء هو السبيل الوحيد — والفاصل
  /// يُقرأ من الإعداد لا يُخمَّن.
  void _startPolling() {
    _poll?.cancel();
    _poll = Timer.periodic(
      Duration(seconds: math.max(_config.timings.offerTtlSeconds ~/ 3, 5)),
      (_) => unawaited(refreshCandidates()),
    );
  }

  /// الرحلات التي قدّمنا عليها عرضًا ولم تُحسم بعد.
  final _offeredRideIds = <int>{};

  Future<void> refreshCandidates() async {
    // سائقٌ على رحلة لا يرى طلبات: الخادم يستبعده أصلًا، والاستقصاء
    // هنا إزعاجٌ بلا نتيجة.
    if (state.hasRunningTrip) return;

    try {
      final candidates = await _soum.driver.candidates();
      state = state.copyWith(candidates: candidates);

      // احتياط الحدث: رحلةٌ قدّمنا عليها عرضًا واختفت من المرشّحين إمّا
      // قُبل عرضنا أو أُغلقت. اللقطة تقول أيّهما — بلا انتظار مقبسٍ قد
      // يكون فوّت الحدث.
      final stillOpen = candidates.map((ride) => ride.id).toSet();
      if (_offeredRideIds.any((id) => !stillOpen.contains(id))) {
        _offeredRideIds.removeWhere((id) => !stillOpen.contains(id));
        await _resync();
      }
    } on ApiException {
      // فشل تحديثٍ لا يُفرغ قائمة قائمة.
    }
  }

  /// §4.2 — تقديم عرض.
  ///
  /// الممرّ `fare_floor…fare_cap` يُفحص محلّيًّا قبل الإرسال: الخادم يرفض
  /// ما خرج عنه، ورسالةٌ بعد الإرسال أسوأ من حقلٍ يقول الحدّ سلفًا.
  Future<bool> submitOffer({
    required int rideId,
    required Money fare,
    required int etaMinutes,
  }) async {
    state = state.copyWith(isBusy: true);

    try {
      await _soum.driver.submitOffer(
        rideId: rideId,
        grossFare: fare,
        etaMinutes: etaMinutes,
      );
      _offeredRideIds.add(rideId);
      await refreshCandidates();
      state = state.copyWith(isBusy: false);
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }

  // =================================================================
  // الدعوات
  // =================================================================

  Future<bool> acceptInvitation() async {
    final invitation = state.invitation;
    if (invitation == null) return false;

    state = state.copyWith(isBusy: true);

    try {
      await _soum.invitations.accept(invitation.id);
      state = state.copyWith(isBusy: false, clearInvitation: true);
      // الرحلة أُنشئت في الخادم. اللقطة تحسم شكلها بلا تخمين.
      await _resync();
      return true;
    } on ApiException catch (error) {
      // المهلة انقضت بين العرض والضغط: نُخفي الدعوة ولا نُبقيها معلّقة.
      state = state.copyWith(
        isBusy: false,
        failure: error,
        clearInvitation: true,
      );
      return false;
    }
  }

  Future<void> rejectInvitation({String? reason}) async {
    final invitation = state.invitation;
    if (invitation == null) return;

    state = state.copyWith(isBusy: true, clearInvitation: true);

    try {
      await _soum.invitations.reject(invitation.id, reason: reason);
    } on ApiException {
      // الرفض محلّيًّا تمّ. الدعوة ستنقضي على الخادم على أيّ حال.
    } finally {
      state = state.copyWith(isBusy: false);
    }
  }

  // =================================================================
  // تنفيذ الرحلة — الترتيب مفروض
  // =================================================================

  /// المسافة إلى نقطة الالتقاء بالأمتار، أو null حين لا موقع.
  ///
  /// تُحسب محلّيًّا لتُعرض قبل النداء. القرار للخادم دائمًا — هذا تقدير
  /// يُجنّب السائق ضغطةً سترتدّ بخطأ.
  int? metersToPickup() {
    final position = ref.read(presenceControllerProvider).lastPosition;
    final pickup = state.ride?.pickup;
    if (position == null || pickup == null) return null;
    return _haversineMeters(position, pickup);
  }

  int? metersToDestination() {
    final position = ref.read(presenceControllerProvider).lastPosition;
    final destination = state.ride?.destination;
    if (position == null || destination == null) return null;
    return _haversineMeters(position, destination);
  }

  bool get canMarkArrived {
    final meters = metersToPickup();
    if (meters == null) return true; // لا موقع: نترك القرار للخادم.
    return meters <= _config.geometry.arrivalRadiusM;
  }

  bool get canComplete {
    final meters = metersToDestination();
    if (meters == null) return true;
    return meters <= _config.geometry.dropoffRadiusM;
  }

  Future<bool> markArrived() async {
    final ride = state.ride;
    if (ride == null) return false;

    // النبضة أوّلًا: الحارس يُقاس على آخر نبضة لا على جسم الطلب.
    //
    // ولا ننتظر نافذة المزامنة هنا: النبض الدوري كلّ خمس ثوانٍ يُبقي
    // موقع القاعدة حديثًا أصلًا، وحجزُ الزرّ خمس ثوانٍ إضافية عند كلّ
    // ضغطة ثمنٌ يدفعه السائق في كلّ رحلة لحالةٍ نادرة. وإن رفض الخادم
    // فرسالته تحمل المسافة الدقيقة — وهي ما يُعرض.
    await ref.read(presenceControllerProvider.notifier).pushLocationNow();

    final position = ref.read(presenceControllerProvider).lastPosition;
    return _act(() => _soum.driver.arrived(
          ride.id,
          lat: position?.lat,
          lng: position?.lng,
        ));
  }

  Future<bool> startTrip() async {
    final ride = state.ride;
    if (ride == null) return false;
    return _act(() => _soum.driver.start(ride.id));
  }

  Future<bool> completeTrip() async {
    final ride = state.ride;
    if (ride == null) return false;

    // كما في «وصلت»: نطاق الإنزال يُقاس على آخر نبضة.
    await ref.read(presenceControllerProvider.notifier).pushLocationNow();

    final position = ref.read(presenceControllerProvider).lastPosition;
    if (position == null) return false;

    final ok = await _act(
      () => _soum.driver.complete(ride.id, lat: position.lat, lng: position.lng),
    );
    if (ok) await _loadPayment(ride.id);
    return ok;
  }

  /// §6.3 — تأكيد قبض النقد. حقّ السائق وحده.
  Future<bool> collectCash() async {
    final rideId = state.ride?.id ?? state.payment?.rideId;
    if (rideId == null) return false;

    state = state.copyWith(isBusy: true);

    try {
      final payment = await _soum.payments.charge(rideId);
      state = state.copyWith(isBusy: false, payment: payment);
      // الرحلة انتهت ودُفعت: نعود إلى شاشة العمل.
      if (payment.status.isSettled) {
        // راكبٌ دفع ونزل؛ الباقون (رحلة مشتركة) يبقون. اللقطة تقرّر.
        state = state.copyWith(clearTrip: true, clearPayment: true);
        await _resync();
      }
      return true;
    } on ApiException catch (error) {
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }

  /// السائق يبدّل الراكب المعروض في رحلة مشتركة.
  void focus(int rideId) {
    final entry = state.trips.where((e) => e.ride.id == rideId).firstOrNull;
    if (entry == null) return;
    state = state.copyWith(ride: entry.ride, trip: entry.trip);
  }

  /// تراجعٌ بعد القبول. الطلب يعود للبحث عند الزبون.
  Future<bool> cancelTrip(String reason) async {
    final ride = state.ride;
    if (ride == null) return false;
    return _act(() => _soum.driver.cancelTrip(ride.id, reason: reason));
  }

  Future<bool> _act(Future<void> Function() action) async {
    state = state.copyWith(isBusy: true);
    try {
      await action();
      await _resync();
      state = state.copyWith(isBusy: false);
      return true;
    } on ApiException catch (error) {
      // لا إعادة محاولة تلقائية: `trip.not_arrived` و400 الجغرافيّ
      // كلاهما يعني أنّ الشرط لم يتحقّق بعد، وتكرار النداء لا يحقّقه.
      state = state.copyWith(isBusy: false, failure: error);
      return false;
    }
  }

  // =================================================================
  // البثّ الحيّ
  // =================================================================

  void _attachDriverRoom() {
    final room = ref.read(presenceControllerProvider.notifier).room;
    if (room == null) return;

    _driverEvents?.cancel();
    _driverEvents = room.events.listen(_onDriverEvent);
  }

  void _onDriverEvent(GuardedEvent guarded) {
    if (guarded.isStale) return;

    final event = guarded.event;
    switch (event.type) {
      case RealtimeEventType.invitationCreated:
        if (event.data.containsKey('status')) {
          state = state.copyWith(
            invitation: RideInvitation.fromJson(event.data),
          );
        }

      case RealtimeEventType.invitationExpired:
      case RealtimeEventType.invitationCancelled:
        state = state.copyWith(clearInvitation: true);

      // الزبون اختار عرضنا. الرحلة موجودة في الخادم واللقطة تجلبها مع
      // غرفتها. قبل هذا لم يكن السائق يعرف أنّه اختير إلّا بإعادة تشغيل.
      case RealtimeEventType.offerAccepted:
        unawaited(_resync());
    }
  }

  /// اللقطة ← الحالة. الراكب المعروض يبقى هو نفسه إن بقيت رحلته، وإلّا
  /// الأوّل — فلا تقفز الشاشة إلى راكبٍ آخر مع كلّ مزامنة.
  void _applySnapshot(ActiveRideSnapshot snapshot) {
    final all = snapshot.allTrips;
    final focused = all
            .where((entry) => entry.ride.id == state.ride?.id)
            .firstOrNull ??
        all.firstOrNull;

    state = state.copyWith(
      trips: all,
      ride: focused?.ride,
      trip: focused?.trip,
      payment: snapshot.pendingPayment,
      clearTrip: focused == null,
      clearPayment: snapshot.pendingPayment == null,
    );

    _syncRideRooms(all);
  }

  void _adoptSnapshot(ActiveRideSnapshot snapshot) {
    _applySnapshot(snapshot);

    // رحلةٌ قائمة بلا حضور: التطبيق أُعيد تشغيله أثناءها. الشاشة تستأنف
    // من اللقطة، لكنّ النبض لا يستأنف نفسه — فيكنس الخادمُ السائقَ بعد
    // `presence_stale_seconds`، ويردّ كلّ «وصلت» بـ«موقعك غير محدَّث»،
    // ولا يرى الزبون السيارة تتحرّك. قِيس بإعادة تشغيل أثناء رحلة.
    final presence = ref.read(presenceControllerProvider);
    if (snapshot.trip != null &&
        !presence.isOnline &&
        presence.stage != PresenceStage.connecting) {
      unawaited(ref.read(presenceControllerProvider.notifier).goOnline());
    }
  }

  /// غرفٌ مفتوحة = رحلاتٌ نشطة، لا أكثر ولا أقلّ. المسارات من اللقطة.
  void _syncRideRooms(List<DriverTripEntry> trips) {
    final paths = {
      for (final entry in trips)
        if (entry.rideRoom != null) entry.ride.id: entry.rideRoom!,
    };
    final live = paths.keys.toSet();

    for (final id in _rideRooms.keys.toList()) {
      if (live.contains(id)) continue;
      unawaited(_rideEvents.remove(id)?.cancel());
      unawaited(_rideRooms.remove(id)?.close());
    }

    for (final id in live) {
      if (_rideRooms.containsKey(id)) continue;
      final room = _soum.room(paths[id]!);
      _rideRooms[id] = room;
      room.onReconnected = () => unawaited(_resync());
      _rideEvents[id] = room.events.listen(_onRideEvent);
      unawaited(room.connect());
    }
  }

  void _onRideEvent(GuardedEvent guarded) {
    if (guarded.isStale) return;

    switch (guarded.event.type) {
      case RealtimeEventType.tripCompleted:
      case RealtimeEventType.tripCancelled:
      case RealtimeEventType.rideCancelled:
      case RealtimeEventType.rideCancelledByDriver:
        unawaited(_resync());

      case RealtimeEventType.driverArrived:
      case RealtimeEventType.tripStarted:
        unawaited(_resync());
    }
  }

  Future<void> _resync() async {
    try {
      final snapshot = await _soum.rides.activeRide();
      _applySnapshot(snapshot);
      if (snapshot.allTrips.isEmpty) await refreshCandidates();
    } on ApiException {
      // الحالة السابقة تبقى. الحدث التالي أو الاستقصاء سيصحّحها.
    }
  }

  Future<void> _loadPayment(int rideId) async {
    try {
      final payment = await _soum.payments.forTrip(rideId);
      state = state.copyWith(payment: payment);
    } on ApiException {
      // بلا دفعة تبقى شاشة النهاية بلا قسم تحصيل.
    }
  }

  void _teardown() {
    _poll?.cancel();
    _poll = null;
    _driverEvents?.cancel();
    _driverEvents = null;
    for (final sub in _rideEvents.values) {
      unawaited(sub.cancel());
    }
    _rideEvents.clear();
    for (final room in _rideRooms.values) {
      unawaited(room.close());
    }
    _rideRooms.clear();
  }

  /// مسافة هافرساين بالأمتار — نفس الصيغة التي يستعملها الخادم.
  static int _haversineMeters(GeoPoint a, GeoPoint b) {
    const earthRadius = 6371008.8;

    final lat1 = a.lat * math.pi / 180;
    final lat2 = b.lat * math.pi / 180;
    final dLat = (b.lat - a.lat) * math.pi / 180;
    final dLng = (b.lng - a.lng) * math.pi / 180;

    final h = math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(lat1) * math.cos(lat2) * math.sin(dLng / 2) * math.sin(dLng / 2);

    return (2 * earthRadius * math.asin(math.sqrt(h))).round();
  }
}
