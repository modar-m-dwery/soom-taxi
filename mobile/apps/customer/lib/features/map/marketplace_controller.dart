/// الخريطة الحيّة — الاشتراك في خليّة السوق ومتابعتها.
///
/// §9.1: «الخريطة الحيّة لا تبثّ كلّ سائق في المدينة إلى كلّ جهاز — بل
/// تُقسَّم إلى خلايا geohash. تشترك في الخليّة التي يراها المستخدم، وتنتقل
/// حين ينتقل».
///
/// وثلاثة قيود تجعل هذا أصعب ممّا يبدو:
///
/// **١. التبديل يتبع الاستقرار لا الحركة.** سحبةُ إصبع واحدة تعبر ثلاث
/// خلايا. التبديل مع كلّ إطار يعني ثلاثة اشتراكات وثلاثة إلغاءات وثلاث
/// لقطات في ثانية — على شبكة هاتف.
///
/// **٢. الخليّة القديمة تبقى حتّى تصل لقطة الجديدة.** الإغلاق أوّلًا يُفرغ
/// الخريطة لجزء من ثانية مع كلّ تمرير، وهو ارتعاشٌ مرئيّ.
///
/// **٣. السيارات تُخزَّن بمعرّف السائق لا بموضعها.** `vehicle.updated`
/// يصل كلّ ثلاث ثوانٍ لكلّ سيارة مرئيّة؛ إعادة بناء القائمة كاملةً مع كلّ
/// واحد تُعيد رسم الخريطة عشرات المرّات في الثانية.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';

import '../../providers.dart';

class MarketplaceState {
  const MarketplaceState({
    this.cellId,
    this.vehicles = const {},
    this.isConnected = false,
  });

  final String? cellId;

  /// معرّف السائق ← سيارته. خريطة لا قائمة: التحديث نقطيّ لا كامل.
  final Map<int, NearbyVehicle> vehicles;

  final bool isConnected;

  List<NearbyVehicle> get visible => vehicles.values.toList(growable: false);
  bool get isEmpty => vehicles.isEmpty;

  MarketplaceState copyWith({
    String? cellId,
    Map<int, NearbyVehicle>? vehicles,
    bool? isConnected,
  }) =>
      MarketplaceState(
        cellId: cellId ?? this.cellId,
        vehicles: vehicles ?? this.vehicles,
        isConnected: isConnected ?? this.isConnected,
      );
}

final marketplaceControllerProvider =
    NotifierProvider<MarketplaceController, MarketplaceState>(
        MarketplaceController.new);

class MarketplaceController extends Notifier<MarketplaceState> {
  RealtimeRoom? _room;
  StreamSubscription<GuardedEvent>? _events;
  StreamSubscription<RoomState>? _states;
  Timer? _settleTimer;

  /// مهلة استقرار الكاميرا قبل التبديل.
  static const _settle = Duration(milliseconds: 600);

  @override
  MarketplaceState build() {
    ref.onDispose(_close);
    return const MarketplaceState();
  }

  Soum get _soum => ref.read(soumProvider);
  AppConfig get _config => ref.read(configProvider);

  /// تُنادى عند استقرار الكاميرا. التبديل يحدث بعد صمت [_settle].
  void followCamera(GeoPoint center) {
    final cellId = _config.cellIdFor(center);

    // خارج مناطق الخدمة: لا خليّة. الاشتراك بغرفة مخترَعة يصمت بلا خطأ،
    // فالخريطة تبقى فارغة ولا أحد يعرف لماذا.
    if (cellId == null) {
      _settleTimer?.cancel();
      _close();
      state = const MarketplaceState();
      return;
    }

    if (cellId == state.cellId) return;

    _settleTimer?.cancel();
    _settleTimer = Timer(_settle, () => _subscribe(cellId));
  }

  void _subscribe(String cellId) {
    if (cellId == state.cellId) return;

    final previous = _room;
    final previousEvents = _events;
    final previousStates = _states;

    final room = _soum.marketplaceRoom(cellId);
    _room = room;
    _events = room.events.listen(_onEvent);
    _states = room.states.listen(
      (roomState) => state = state.copyWith(
        isConnected: roomState == RoomState.connected,
      ),
    );

    // الخليّة القديمة تُغلق بعد أن تصل لقطة الجديدة — لا قبلها.
    unawaited(room.connect().then((_) {
      previousEvents?.cancel();
      previousStates?.cancel();
      unawaited(previous?.close());
    }));

    state = state.copyWith(cellId: cellId);
  }

  void _onEvent(GuardedEvent guarded) {
    if (guarded.isStale) return;

    final event = guarded.event;
    final data = event.data;

    switch (event.type) {
      case RealtimeEventType.marketplaceSnapshot:
        final raw = data['vehicles'];
        if (raw is! List) return;

        final fleet = raw
            .whereType<Map>()
            .map((e) => NearbyVehicle.fromJson(e.cast<String, dynamic>()));

        state = state.copyWith(
          vehicles: {for (final vehicle in fleet) vehicle.driverId: vehicle},
        );

      case RealtimeEventType.vehicleEnteredArea:
      case RealtimeEventType.vehicleUpdated:
        final vehicle = NearbyVehicle.fromJson(data);
        state = state.copyWith(
          vehicles: {...state.vehicles, vehicle.driverId: vehicle},
        );

      case RealtimeEventType.vehicleLeftArea:
        final driverId = readIntOrNull(data, 'driver_id');
        if (driverId == null) return;
        state = state.copyWith(
          vehicles: {...state.vehicles}..remove(driverId),
        );
    }
  }

  void _close() {
    _settleTimer?.cancel();
    _settleTimer = null;
    _events?.cancel();
    _events = null;
    _states?.cancel();
    _states = null;
    unawaited(_room?.close());
    _room = null;
  }
}
