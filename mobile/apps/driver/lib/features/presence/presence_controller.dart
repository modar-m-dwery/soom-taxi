/// الحضور ونبض الموقع — أهمّ ملفّ في تطبيق السائق.
///
/// §6.2 في دليل التكامل:
///
/// > انقطاع النبض ستّين ثانية يُخرج السائق من الأسطول المرئي تلقائيًّا —
/// > مهمّة مجدولة تكنس كلّ خامل كلّ خمس عشرة ثانية. أرسل النبض ما دام
/// > التطبيق في المقدّمة، **وأعد `go-online` عند العودة من الخلفية: مجرّد
/// > إعادة فتح المقبس لا تكفي**.
///
/// والجملة الأخيرة هي التي تكلّف من يتجاهلها يومًا كاملًا من التشخيص.
/// السبب أنّ الحضور يعيش في مكانين: ‏Redis يحمل مفتاح الحضور، والقاعدة
/// تحمل `online` و`last_location_at`. وإعادة فتح المقبس لا تلمس أيًّا
/// منهما — هي تفتح قناةً لا أكثر.
///
/// **وقاعدة ثانية اكتشفناها بالتشغيل ولم تذكرها الوثيقة:** ‏`go-online`
/// وحده لا يُدخل السائق في المطابقة. الفلتر يقرأ `last_location_at`، وهو
/// لا يتحدّث إلّا بنبضة `location.update`. لذلك هذا الملفّ يرسل نبضة
/// **فور** نجاح `go-online` ولا ينتظر أوّل دورة مؤقّت: انتظارٌ من خمس
/// ثوانٍ هنا يعني خمس ثوانٍ يرى فيها السائق «متّصل» وهو غير موجود في
/// المطابقة.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:soum_core/soum_core.dart';

import '../../providers.dart';
import 'location_fix.dart';
import 'presence_state.dart';

final presenceControllerProvider =
    NotifierProvider<PresenceController, PresenceState>(PresenceController.new);

class PresenceController extends Notifier<PresenceState>
    with WidgetsBindingObserver {
  RealtimeRoom? _room;
  StreamSubscription<GuardedEvent>? _events;
  StreamSubscription<Position>? _positions;
  Timer? _heartbeat;
  Timer? _staleWatch;

  int? _profileId;
  LocationFix? _latest;

  /// الخادم رفض آخر موقع لأنّه مزيّف. ما دام قائمًا لا يُعدّ `presence.ack`
  /// دخولًا في المطابقة: الإقرار يصل على `heartbeat` حتّى والموقع مرفوض،
  /// و`last_location_at` لم يتحدّث — فالسائق غير مرئيّ للزبائن.
  bool _mockRejected = false;

  @override
  PresenceState build() {
    WidgetsBinding.instance.addObserver(this);
    ref.onDispose(() {
      WidgetsBinding.instance.removeObserver(this);
      _teardown();
    });
    return const PresenceState();
  }

  Soum get _soum => ref.read(soumProvider);
  AppConfig get _config => ref.read(configProvider);

  // =================================================================
  // التشغيل والإيقاف
  // =================================================================

  Future<void> goOnline() async {
    state = state.copyWith(
      stage: PresenceStage.connecting,
      clearFailure: true,
    );

    final fix = await _readPosition();
    if (fix == null) {
      // سببٌ مصنَّف لا نصّ: وحدة التحكّم لا تعرف لغة المستخدم، والنصّ
      // المكتوب هنا يخرج من ملفّ الترجمة فلا يُترجَم أبدًا.
      state = state.copyWith(
        stage: PresenceStage.offline,
        blocker: PresenceBlocker.locationUnavailable,
      );
      return;
    }

    final position = fix.point;
    try {
      await _soum.driver.goOnline(lat: position.lat, lng: position.lng);
    } on ApiException catch (error) {
      // `driver.not_eligible` يصل هنا بنصّه الصريح: وثيقة ناقصة أو
      // منتهية أو حساب موقوف. §12.3: «اعرض السبب من detail لا رسالة
      // عامّة» — والنصّ من الخادم يقول أيّ وثيقة بالضبط.
      state = state.copyWith(
        stage: PresenceStage.offline,
        failure: error,
        blocker: PresenceBlocker.serverRefused,
      );
      return;
    }

    _latest = fix;

    // الغرفة تُنشأ **قبل** إعلان الاتّصال. وحدة العمل تشترك في غرفة السائق
    // لحظة انقلاب `isOnline`، فإن أُعلن قبل وجود الغرفة اشتركت في لا شيء
    // ولم يصلها «قُبل عرضك» أبدًا — وُجد بهاتفٍ حقيقيّ: الزبون اختار العرض
    // وبقي السائق على شاشة الطلبات.
    final room = _createRoom(await _profileIdOrNull());

    state = state.copyWith(
      stage: PresenceStage.onlineNoHeartbeat,
      lastPosition: position,
      clearFailure: true,
      roomGeneration: room == null ? null : state.roomGeneration + 1,
    );

    // أوّل موقع مؤكَّد: مدينة الإعداد قد تكون افتراضًا (§0.1) فنعيد حلّها،
    // وإلّا قِيست أنصاف الأقطار والمهل على مدينةٍ أخرى.
    unawaited(ref.read(bootControllerProvider.notifier).resolveArea(position));

    if (room != null) await room.connect();
    // نبضة فورية لا بعد أوّل دورة مؤقّت — راجع رأس الملفّ.
    _sendHeartbeat();
    _startHeartbeat();
    _watchPosition();
  }

  Future<void> goOffline() async {
    _teardown();
    state = const PresenceState();

    try {
      await _soum.driver.goOffline();
    } on ApiException {
      // الإيقاف المحلّي تمّ. فشلُ النداء يعني أنّ الخادم سيكنسه بعد
      // `presence_stale_seconds` على أيّ حال، فلا نُبقي الزرّ معلّقًا.
    }
  }

  // =================================================================
  // دورة حياة التطبيق — §6.2
  // =================================================================

  // الاسم `state` في التوقيع الأصلي يحجب `state` الخاصّ بـNotifier —
  // وهو ما نقرؤه ونكتبه في هذا التابع نفسه.
  @override
  // ignore: avoid_renaming_method_parameters
  void didChangeAppLifecycleState(AppLifecycleState lifecycle) {
    switch (lifecycle) {
      case AppLifecycleState.resumed:
        // العودة من الخلفية: **`go-online` كاملًا** لا إعادة فتح مقبس.
        // نظام التشغيل جمّد المؤقّتات وقطع المقبس وربّما كنس الخادمُ
        // السائقَ من الأسطول أثناء ذلك.
        if (state.isOnline) unawaited(goOnline());

      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        // النبض يتوقّف في الخلفية عمدًا: نبضٌ من تطبيق مغلق يجعل الخريطة
        // تعرض سيارةً لا أحد فيها، والزبون يدعو سائقًا نائمًا.
        _heartbeat?.cancel();
        _heartbeat = null;

      case AppLifecycleState.inactive:
        break;
    }
  }

  // =================================================================
  // الغرفة والنبض
  // =================================================================

  Future<int?> _profileIdOrNull() async =>
      _profileId ??= await ref.read(driverProfileIdProvider.future);

  /// تُنشئ الغرفة وتشترك في أحداثها بلا اتّصال: الاتّصال يُنتظر لاحقًا،
  /// أمّا وجود الغرفة فيلزم قبل أن يرى الآخرون `isOnline`.
  RealtimeRoom? _createRoom(int? profileId) {
    if (profileId == null) return null;

    unawaited(_room?.close());
    unawaited(_events?.cancel());

    final room = _soum.room('/ws/driver/$profileId/');
    _room = room;

    // إعادة الاتصال ليست كافية وحدها — راجع §6.2 ورأس الملفّ.
    room.onReconnected = () => unawaited(goOnline());

    _events = room.events.listen(_onEvent);
    return room;
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();

    // الوتيرة من الإعداد لا من الرقم 3 أو 5: `presence_stale_seconds`
    // يضبطه المشغّل لكلّ مدينة، ووتيرةٌ ثابتة تصير خاطئة حين يغيّره.
    _heartbeat = Timer.periodic(
      _config.timings.heartbeatInterval,
      (_) => _sendHeartbeat(),
    );

    _staleWatch?.cancel();
    _staleWatch = Timer.periodic(const Duration(seconds: 5), (_) => _checkStale());
  }

  /// يدفع الموقع **وينتظر إقرار الخادم** — قبل كلّ فعل يُقاس جغرافيًّا.
  ///
  /// ثلاث حقائق مقيسة على خادم يعمل تشرح كلّ سطر هنا:
  ///
  /// **١. الحارس يقرأ من القاعدة لا من Redis.** `TripService.arrived`
  /// يقرأ `driver.current_location` و`last_location_at` من صفّ السائق.
  ///
  /// **٢. `location.update` يكتب Redis في كلّ نبضة، والقاعدةَ كلّ خمس
  /// ثوانٍ على الأكثر** — `DB_SYNC_MIN_INTERVAL_SECONDS = 5` في
  /// `DriverRoomConsumer`. فالحارس قد يُقاس على موقع أقدم بخمس ثوانٍ من
  /// آخر نبضة: نحو سبعين مترًا على سرعة خمسين كم/سا.
  ///
  /// **٣. `location.update` لا يردّ بإقرار.** الإقرار يأتي على
  /// `heartbeat` و`go_online` و`go_offline` وحدها. فانتظار إقرارٍ بعد
  /// `location.update` وحده ينتظر ما لا يأتي.
  ///
  /// لذلك: نرسل الموقع، ثمّ `heartbeat` لننتزع إقرارًا يثبت أنّ القناة
  /// حيّة، ثمّ نمهل قدر نافذة المزامنة. وإن رفض الخادم بعدها فرسالته
  /// تحمل المسافة الدقيقة — وهي ما يُعرض للسائق.
  Future<bool> pushLocationNow({
    Duration timeout = const Duration(seconds: 5),
  }) async {
    final room = _room;
    if (room == null || !room.isConnected) return false;

    // موقعٌ طازج لا آخر ما وصل من التدفّق: التدفّق مرشَّح بعشرة أمتار،
    // وسيارةٌ توقّفت قبل قليل قد لا تكون بعثت تحديثًا منذ ذلك.
    // مهلةٌ قصيرة: السائق ضغط «وصلتُ» وينتظر، وآخر موقع من التدفّق حديثٌ
    // أصلًا — الطازج تحسينٌ لا شرط.
    final fresh = await _readPosition(timeout: const Duration(seconds: 4));
    if (fresh != null) {
      _latest = fresh;
      state = state.copyWith(lastPosition: fresh.point);
    }

    final before = state.lastAck;
    // `_sendHeartbeat` يرسل الموقع ثمّ `heartbeat` الذي يحمل الإقرار.
    _sendHeartbeat();

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 120));
      final ack = state.lastAck;
      if (ack != null && ack != before) return true;
    }
    return false;
  }

  /// نافذة مزامنة القاعدة في الخادم.
  ///
  /// ليست إعدادًا يُقرأ من `/config/` بل ثابتٌ في `DriverRoomConsumer`.
  /// نذكرها هنا صراحةً لأنّها تحكم دقّة كلّ فحص جغرافيّ، ولأنّ تغييرها
  /// في الخادم يوجب تغييرها هنا.
  static const serverDbSyncWindow = Duration(seconds: 5);

  void _sendHeartbeat() {
    final fix = _latest;
    final room = _room;
    if (fix == null || room == null || !room.isConnected) return;

    // موقعٌ حقيقيّ بعد رفضٍ سابق يُقبل: نرفع المانع متفائلين، وإن بقي
    // الخادم يرفض فحدثه يصل قبل إقرار `heartbeat` التالي فيعيده.
    if (!fix.mocked) _mockRejected = false;
    room.send(fix.toFrame());

    // `location.update` لا يردّ بإقرار — انظر رأس `pushLocationNow`. ولأنّ
    // `PresenceStage.matchable` لا يُبلَغ إلّا بـ`presence.ack`، فنبضٌ
    // بلا `heartbeat` يُبقي الواجهة على «بانتظار أوّل نبضة» إلى الأبد
    // ويحجب قائمة الطلبات خلفها — مع أنّ الخادم يرى السائق متاحًا.
    // قِيس على خادم يعمل: خمسون ثانية متّصلًا بلا إقرار واحد.
    room.send({'type': 'heartbeat'});
  }

  /// النبض يُرسَل، والخادم يردّ `presence.ack`. الفرق بينهما مهمّ:
  /// إرسالٌ بلا ردّ يعني مقبسًا مفتوحًا ظاهريًّا وميّتًا فعليًّا — وهو ما
  /// يحدث خلف بوّابات NAT التي تُسقط الجلسات الصامتة بلا إشعار.
  void _checkStale() {
    final ack = state.lastAck;
    if (ack == null || !state.isOnline) return;

    final age = DateTime.now().difference(ack).inSeconds;
    final limit = _config.timings.presenceStaleSeconds;

    if (age >= limit && state.stage != PresenceStage.stale) {
      state = state.copyWith(stage: PresenceStage.stale);
    }
  }

  void _onEvent(GuardedEvent guarded) {
    if (guarded.isStale) return;

    switch (guarded.event.type) {
      case RealtimeEventType.presenceAck:
        if (_mockRejected) {
          // القناة حيّة لكنّ الموقع مرفوض: متّصل وخارج المطابقة.
          state = state.copyWith(
            stage: PresenceStage.onlineNoHeartbeat,
            lastAck: DateTime.now(),
            blocker: PresenceBlocker.mockLocation,
          );
          return;
        }
        // أوّل ack هو لحظة دخول المطابقة فعلًا — لا لحظة نجاح go-online.
        state = state.copyWith(
          stage: PresenceStage.matchable,
          lastAck: DateTime.now(),
          clearFailure: true,
        );

      case RealtimeEventType.locationRejected:
        // بقيّة الأسباب (قفزة مستحيلة، إحداثيّات خارج النطاق) نقطةٌ واحدة
        // سيئة تصحّحها النقطة التالية — لا تستحقّ إزعاج السائق.
        if (readString(guarded.event.data, 'reason') != 'mock_location') return;
        _mockRejected = true;
        state = state.copyWith(
          stage: PresenceStage.onlineNoHeartbeat,
          blocker: PresenceBlocker.mockLocation,
        );

      case RealtimeEventType.presenceOffline:
        // الخادم كنسه. إعادة `go-online` كاملة لا إعادة نبض: الكنس
        // غيّر القاعدة وRedis معًا.
        state = state.copyWith(stage: PresenceStage.stale);
        unawaited(goOnline());
    }
  }

  // =================================================================
  // الموقع
  // =================================================================

  void _watchPosition() {
    _positions?.cancel();

    // مرشّح المسافة يمنع نبضًا لسيارة واقفة: §5 في وثيقة المنتج يذكر أنّ
    // «سائقًا واقفًا في زحام عشر دقائق يكتب 120 صفًّا لنقطة واحدة».
    // المرشّح هنا يخفّف المصدر نفسه لا الأثر.
    _positions = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 10,
      ),
    ).listen(
      (position) {
        final fix = LocationFix.fromPosition(position);
        _latest = fix;
        state = state.copyWith(lastPosition: fix.point);
      },
      onError: (Object _) {
        // فقدان إشارة GPS لا يُخرج السائق: آخر موقع معروف يبقى صالحًا
        // حتّى `location_max_age_seconds`، والخادم هو من يقرّر.
      },
    );
  }

  Future<LocationFix?> _readPosition({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      // المهلة من `Future.timeout` لا من `timeLimit` وحده: `timeLimit` لا
      // يُحترم على كلّ جهاز (قِيس على شاشة الزبون الرئيسية)، ونداءٌ معلّق هنا
      // يعلّق «وصلتُ» و«أنهِ» إلى الأبد بلا أيّ رسالة — وُجد بالتصوير.
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      ).timeout(timeout);
      return LocationFix.fromPosition(position);
    } on Object {
      return null;
    }
  }

  void _teardown() {
    _mockRejected = false;
    _heartbeat?.cancel();
    _heartbeat = null;
    _staleWatch?.cancel();
    _staleWatch = null;
    _positions?.cancel();
    _positions = null;
    _events?.cancel();
    _events = null;
    unawaited(_room?.close());
    _room = null;
  }

  /// غرفة السائق — تتشاركها الدعوات الواردة.
  RealtimeRoom? get room => _room;
}
