import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:soum_core/soum_core.dart';

import 'boot_state.dart';

/// يُحقَن من كلّ تطبيق عند الإقلاع.
final soumProvider = Provider<Soum>(
  (ref) => throw UnimplementedError('override soumProvider in main()'),
);

final bootControllerProvider =
    NotifierProvider<BootController, BootState>(BootController.new);

class BootController extends Notifier<BootState> {
  @override
  BootState build() {
    // الإقلاع يبدأ فور بناء المزوّد — لا ننتظر أن تطلبه شاشة، فالشاشة
    // الأولى نفسها تُرسم من نتيجته.
    Future.microtask(start);
    return const BootLoading(BootStep.config);
  }

  Soum get _soum => ref.read(soumProvider);

  Future<void> start() async {
    state = const BootLoading(BootStep.config);

    try {
      // ١ — الإعداد. بالإحداثيات إن أذن المستخدم، وإلّا بلا شيء:
      // `resolved_from: default` يقول للتطبيق إنّ المدينة افتراض، فيُعاد
      // النداء بعد الإذن بدل أن تُعرض للمستخدم مدينة ليس فيها.
      final position = await _currentPosition();
      final config = await _soum.config.load(
        lat: position?.latitude,
        lng: position?.longitude,
      );

      if (!_soum.isAuthenticated) {
        state = BootNeedsAuth(config);
        return;
      }

      // ٢ — هويّة المستخدم.
      state = const BootLoading(BootStep.session);
      final user = await _soum.auth.me();

      // ٣ — الرحلة القائمة. نداءٌ واحد يقرّر الشاشة.
      state = const BootLoading(BootStep.activeRide);
      final snapshot = await _soum.rides.activeRide();

      state = BootReady(
        config: await _configForRide(config, snapshot),
        user: user,
        snapshot: snapshot,
      );

      // ٤ — تسجيل الجهاز للإشعارات، بعد أن تصير الشاشة جاهزة.
      //
      // §10: «سجّل عند كلّ إقلاع لا مرّة واحدة: مفاتيح الدفع تتغيّر بلا
      // إشعار». وبعد الشاشة لا قبلها: التسجيل يمرّ بمزوّد خارجيّ قد
      // يتأخّر ثوانيَ، وحبسُ الإقلاع عليه يعني شاشة بيضاء بلا سبب.
      unawaited(_registerPushDevice());
    } on ConfigUnavailable catch (error) {
      state = BootFailed(error.cause);
    } on ApiException catch (error) {
      // المفتاح أُبطل من جهاز آخر: العميل محا المفتاح أصلًا عند 401،
      // فنكمل إلى شاشة الدخول بدل أن نعرض خطأً لا فعل له.
      if (error.code == ApiErrorCode.unauthenticated) {
        final config = _soum.config.current;
        state = config == null ? BootFailed(error) : BootNeedsAuth(config);
        return;
      }
      state = BootFailed(error);
    }
  }

  /// رحلةٌ قائمة تحمل نقطة انطلاقها: المدينة منها لا من الافتراض.
  ///
  /// الإقلاع كثيرًا ما يمرّ بلا موقع، فتأتي المدينة الافتراضية. وشاشة
  /// البحث أو الرحلة بعد إعادة فتح التطبيق لا تمرّ بالرئيسية التي تصحّح
  /// المدينة من الموقع — فكانت تعمل بنصف قطر مدينة أخرى ومهلها، وبلا
  /// سيارات على الخريطة. وُجد بتصوير التطبيق: «ضمن 7 كم» بدل 5 بعد إعادة
  /// الفتح وسط البحث.
  Future<AppConfig> _configForRide(
    AppConfig config,
    ActiveRideSnapshot snapshot,
  ) async {
    final pickup = snapshot.ride?.pickup;
    if (pickup == null || config.resolution == AreaResolution.coordinates) {
      return config;
    }
    try {
      return await _soum.config.load(lat: pickup.lat, lng: pickup.lng);
    } on Object {
      return config;
    }
  }

  /// يُنادى بعد نجاح تسجيل الدخول.
  Future<void> resumeAfterLogin() => start();

  Future<void> logout() async {
    // إلغاء التسجيل قبل محو المفتاح: §10 — «ألغِ التسجيل عند تسجيل
    // الخروج، وإلّا وصلت إشعارات المستخدم السابق إلى الجهاز نفسه».
    // والترتيب مهمّ: النداء يحتاج مصادقة.
    final token = pushToken;
    if (token != null) {
      try {
        await _soum.notifications.unregisterDevice(token);
      } on ApiException {
        // فشلُ الإلغاء لا يمنع الخروج. الخادم سيفشل في التسليم لاحقًا
        // ويُسقط المفتاح من تلقائه.
      }
    }

    await _soum.logout();
    await start();
  }

  /// مفتاح الدفع من مزوّد الإشعارات.
  ///
  /// يُحقَن من التطبيق: هذه الحزمة لا تعتمد على Firebase ولا على أيّ
  /// مزوّد بعينه — إضافةُ مزوّد لا يجب أن تمسّ تسلسل الإقلاع.
  static String? pushToken;

  /// يُضبط من التطبيق قبل الإقلاع.
  static Future<String?> Function()? pushTokenProvider;

  /// مفاتيح جديدة يصدرها المزوّد بعد الإقلاع — تُسجَّل كما تصل.
  static Stream<String>? pushTokenRefresh;
  StreamSubscription<String>? _refreshSub;

  Future<void> _registerPushDevice() async {
    final provider = pushTokenProvider;
    if (provider == null) return;

    try {
      final token = await provider();
      if (token == null || token.isEmpty) return;

      await _register(token);
      _refreshSub ??= pushTokenRefresh?.listen(
        (fresh) => unawaited(_register(fresh).catchError((Object _) {})),
      );
    } on ApiException {
      // الإشعارات تحسينٌ لا شرط: §10.2 — «لا تبنِ منطق حالة على وصول
      // إشعار». فشلُ التسجيل لا يمنع التطبيق من العمل بالمقبس.
    } on Object {
      // مزوّدٌ غير مهيَّأ في هذه البيئة — وهو الوضع اليوم حتّى يُشترى
      // ملفّ حساب الخدمة.
    }
  }

  Future<void> _register(String token) async {
    pushToken = token;
    await _soum.notifications.registerDevice(
      token: token,
      platform: defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android',
      deviceId: await _soum.session.deviceId(),
    );
  }

  /// يعيد حلّ المدينة من موقعٍ حقيقيّ — الوعد الذي في رأس `start`.
  ///
  /// الإقلاع كثيرًا ما يمرّ بلا موقع (إذنٌ لم يُمنح بعد، أو مهلة GPS)،
  /// فيردّ الخادم `resolved_from: default` = أوّل مدينة فعّالة. قِيس:
  /// زبونٌ في جبلة أُعطي إعداد اللاذقية — نصف قطر المطابقة ومهل العروض
  /// وخليّة السوق كلّها لمدينة أخرى، فلا يرى سيارةً واحدة على خريطته.
  ///
  /// تُنادى من أوّل شاشة تحصل على موقع. لا تفعل شيئًا إن كانت المدينة
  /// محلولة بالإحداثيات أصلًا، أو إن فشل النداء — الإعداد القائم يبقى.
  Future<void> resolveArea(GeoPoint point) async {
    final current = state;
    final config = switch (current) {
      BootReady(:final config) => config,
      BootNeedsAuth(:final config) => config,
      _ => null,
    };
    if (config == null) return;
    if (config.resolution == AreaResolution.coordinates) return;

    try {
      final resolved = await _soum.config.load(lat: point.lat, lng: point.lng);
      if (resolved.areaCode == config.areaCode &&
          resolved.resolution == config.resolution) {
        return;
      }
      switch (state) {
        case BootReady(:final user, :final snapshot):
          state = BootReady(config: resolved, user: user, snapshot: snapshot);
        case BootNeedsAuth():
          state = BootNeedsAuth(resolved);
        default:
          break;
      }
    } on ConfigUnavailable {
      // الإعداد الحاليّ يبقى — مدينةٌ افتراضية خيرٌ من شاشة خطأ.
    } on ApiException {
      // كذلك.
    }
  }

  /// يُعاد بعد كلّ رجوع من الخلفية، ومع كلّ حدث ينهي رحلة.
  Future<void> refreshActiveRide() async {
    final current = state;
    if (current is! BootReady) return;

    try {
      final snapshot = await _soum.rides.activeRide();
      state = BootReady(
        config: current.config,
        user: current.user,
        snapshot: snapshot,
      );
    } on ApiException {
      // فشلُ تحديثٍ ليس سببًا لإفراغ شاشة قائمة. الحالة السابقة تبقى،
      // والمقبس الحيّ سيصحّحها عند أوّل حدث.
    }
  }

  /// الموقع إن كان مأذونًا — وإلّا null، لا خطأ.
  ///
  /// تطبيقٌ يمنع الإقلاع حتّى يُمنح إذن الموقع يخسر مستخدمًا قبل أن يريه
  /// شيئًا. نقرأ الإعداد بلا إحداثيات، ونعيد قراءته بعد الإذن.
  Future<Position?> _currentPosition() async {
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

      // آخر موقع معروف أوّلًا: فوريّ، ويكفي لتسمية المدينة. الطلب الطازج
      // احتياطٌ لجهازٍ لم يحدّد موقعه قطّ — وبمهلة، فالإقلاع لا ينتظر GPS.
      final lastKnown = await Geolocator.getLastKnownPosition();
      if (lastKnown != null) return lastKnown;

      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 8),
        ),
      );
    } on Object {
      // مهلة، أو جهاز بلا GPS، أو منصّة لا تدعم النداء. لا شيء منها
      // يبرّر إسقاط الإقلاع.
      return null;
    }
  }
}
