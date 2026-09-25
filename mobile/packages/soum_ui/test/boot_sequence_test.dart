// T2.3 — «الترتيب مفروض: /config/ ← المصادقة ← /me/active-ride/ ← الشاشة».
//
// هذا الاختبار يقيس الترتيب نفسه لا النتيجة وحدها. السبب أنّ النتيجة تبدو
// صحيحة بترتيب خاطئ أيضًا: تطبيقٌ ينادي `/auth/me/` قبل `/config/` يعمل
// تمامًا — حتّى يفتحه مستخدم بلا شبكة، أو في مدينة أخرى، فيرسم شاشة بأرقام
// ليست أرقام مدينته.

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

const _config = {
  'area_code': 'JAB',
  'area_name': 'جبلة',
  'country_code': '',
  'resolved_from': 'default',
  'ride_modes': ['fast', 'express', 'standard', 'saving', 'shared'],
  'invitation_allowed_modes': ['fast', 'express'],
  'vehicle_categories': [
    {'code': 'sedan', 'name': 'سيدان', 'seats': 4, 'sort_order': 10}
  ],
  'timings': {
    'offer_ttl_seconds': 30,
    'ride_search_window_minutes': 10,
    'invitation_ttl_options': [20, 40, 60],
    'invitation_ttl_default': 20,
    'invitation_max_parallel': 1,
    'invitation_reject_cooldown_seconds': 60,
    'presence_stale_seconds': 60,
    'presence_fresh_seconds': 30,
    'location_max_age_seconds': 60,
  },
  'geometry': {
    'matching_radius_km': 5.0,
    'marketplace_radius_km': 10.0,
    'shared_join_radius_km': 3.0,
    'shared_scheduled_pickup_radius_km': 10.0,
    'shared_scheduled_dest_radius_km': 15.0,
    'shared_scheduled_time_window_minutes': 60,
    'arrival_radius_m': 200,
    'dropoff_radius_m': 300,
    'marketplace_cell_precision': 7,
  },
  'pricing': {
    'currency_code': 'SYP',
    'default_policy': 'platform_fixed',
    'allowed_policies': ['platform_fixed'],
    'surge_enabled': false,
    'surge_max_multiplier': null,
    'min_fare_absolute': null,
  },
  'server_time': '2026-09-14T20:04:15Z',
};

const _user = {
  'id': 1,
  'phone': '+963990000101',
  'name': 'Mobile Demo Customer',
  'role': 'customer',
  'is_verified': true,
  'is_active': true,
  'created_at': '2026-09-14T20:00:00Z',
};

const _idle = {
  'has_active_ride': false,
  'role': 'customer',
  'stage': 'idle',
  'ride': null,
  'trip': null,
  'pending_payment': null,
  'realtime': {'ride_room': null, 'driver_room': null},
};

/// يسجّل ترتيب النداءات كما غادرت الجهاز.
class RecordingAdapter implements HttpClientAdapter {
  RecordingAdapter();

  final calls = <String>[];
  final Map<String, Object> responses = {
    '/config/': _config,
    '/auth/me/': _user,
    '/me/active-ride/': _idle,
  };
  final Map<String, int> statuses = {};

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? stream,
      Future<void>? cancelFuture) async {
    final path = options.path;
    calls.add(path);

    final status = statuses[path] ?? 200;
    final body = status >= 400
        ? {'detail': 'خطأ', 'code': path == '/auth/me/' ? 'unauthenticated' : 'x'}
        : responses[path] ?? const <String, dynamic>{};

    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Future<(ProviderContainer, RecordingAdapter, InMemoryStore)> boot({
  String? token,
  Map<String, Object>? responses,
  Map<String, int>? statuses,
}) async {
  final store = InMemoryStore();
  if (token != null) await store.write('soum.auth.token', token);

  final adapter = RecordingAdapter();
  if (responses != null) adapter.responses.addAll(responses);
  if (statuses != null) adapter.statuses.addAll(statuses);

  final soum = await Soum.create(
    baseUrl: 'http://test/api/v1',
    secure: store,
    prefs: store,
    dio: Dio()..httpClientAdapter = adapter,
  );

  final container = ProviderContainer(
    overrides: [soumProvider.overrideWithValue(soum)],
  );
  addTearDown(container.dispose);

  return (container, adapter, store);
}

Future<void> settle(ProviderContainer container) async {
  container.listen(bootControllerProvider, (_, _) {});
  for (var i = 0; i < 40; i++) {
    await Future<void>.delayed(const Duration(milliseconds: 15));
    final state = container.read(bootControllerProvider);
    if (state is! BootLoading) return;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('بلا مفتاح: الإعداد يُقرأ ثمّ يُطلب تسجيل الدخول — ولا نداء موثَّق',
      () async {
    final (container, adapter, _) = await boot();
    await settle(container);

    expect(container.read(bootControllerProvider), isA<BootNeedsAuth>());
    expect(adapter.calls, ['/config/'],
        reason: 'لا نداء موثَّق قبل وجود مفتاح');

    final state = container.read(bootControllerProvider) as BootNeedsAuth;
    expect(state.config.areaCode, 'JAB',
        reason: 'شاشة الهاتف نفسها تحتاج الإعداد');
  });

  test('بمفتاح: الترتيب config ← me ← active-ride، وكلٌّ مرّة واحدة', () async {
    final (container, adapter, _) = await boot(token: 'abc');
    await settle(container);

    expect(adapter.calls, ['/config/', '/auth/me/', '/me/active-ride/']);

    final state = container.read(bootControllerProvider);
    expect(state, isA<BootReady>());
    expect((state as BootReady).snapshot.stage, ResumeStage.idle);
  });

  test('رحلة قائمة تفتح شاشة التتبّع في موضعها', () async {
    final (container, _, _) = await boot(
      token: 'abc',
      responses: {
        '/me/active-ride/': {
          'has_active_ride': true,
          'role': 'customer',
          'stage': 'driver_arriving',
          'ride': {'id': 2702, 'status': 'driver_arriving', 'currency': 'SYP'},
          'trip': {'id': 5, 'ride': 2702, 'status': 'driver_arriving',
                   'currency': 'SYP', 'final_fare': '5512.00'},
          'pending_payment': null,
          'realtime': {'ride_room': '/ws/rides/2702/', 'driver_room': null},
        },
      },
    );
    await settle(container);

    final state = container.read(bootControllerProvider) as BootReady;
    expect(state.snapshot.stage, ResumeStage.driverArriving);
    expect(state.snapshot.stage.isOnTrip, isTrue);
    expect(state.snapshot.rooms.rideRoom, '/ws/rides/2702/',
        reason: 'اسم الغرفة يأتي من الخادم لا يُبنى في التطبيق');
  });

  test('رحلة انتهت ولم تُدفع تفتح شاشة الدفع لا الرئيسية', () async {
    final (container, _, _) = await boot(
      token: 'abc',
      responses: {
        '/me/active-ride/': {
          'has_active_ride': false,
          'role': 'customer',
          'stage': 'awaiting_payment',
          'ride': null,
          'trip': null,
          'pending_payment': {
            'id': 9, 'trip_id': 5, 'ride_id': 2702,
            'amount': '5512.00', 'platform_fee': '0.00',
            'driver_net': '5512.00', 'amount_refunded': '0.00',
            'refundable_amount': '0.00', 'currency': 'SYP',
            'gateway_code': 'cash', 'status': 'pending', 'failure_reason': '',
          },
          'realtime': {'ride_room': null, 'driver_room': null},
        },
      },
    );
    await settle(container);

    final state = container.read(bootControllerProvider) as BootReady;
    expect(state.snapshot.stage, ResumeStage.awaitingPayment);
    expect(state.snapshot.needsPayment, isTrue);

    final payment = state.snapshot.pendingPayment!;
    expect(payment.amount.toApi(), '5512.00');
    expect(payment.awaitingDriverConfirmation, isTrue,
        reason: 'نقدًا: الزبون ينتظر تأكيد السائق — لا زرّ «دفعتُ» عنده');
  });

  test('مفتاح أُبطل من جهاز آخر يعود إلى شاشة الدخول لا إلى خطأ', () async {
    final (container, _, store) = await boot(
      token: 'stale',
      statuses: {'/auth/me/': 401},
    );
    await settle(container);

    expect(container.read(bootControllerProvider), isA<BootNeedsAuth>());
    expect(store.getString('soum.auth.token'), isNull,
        reason: 'المفتاح المُبطَل يُمحى وإلّا فشل كلّ نداء بلا مخرج');
  });

  test('انقطاع بلا خبيئة: خطأ قابل لإعادة المحاولة لا شاشة بيضاء', () async {
    final (container, _, _) = await boot(statuses: {'/config/': 503});
    await settle(container);

    final state = container.read(bootControllerProvider);
    expect(state, isA<BootFailed>());
    expect((state as BootFailed).failure.statusCode, 503);
  });

  test('الساعة تُصحَّح من server_time فتُبنى عليها العدّادات', () async {
    final (container, _, _) = await boot(token: 'abc');
    await settle(container);

    final state = container.read(bootControllerProvider) as BootReady;
    final clock = state.clock;

    // حمولة الاختبار تحمل وقت خادم في الماضي، فالانحراف سالب كبير —
    // والمهمّ أنّ الساعة تُبنى منه لا من DateTime.now() مباشرةً.
    expect(clock.skew, isNot(Duration.zero));
    expect(clock.secondsUntil(null), 0);
    expect(clock.hasPassed(clock.now().subtract(const Duration(minutes: 1))),
        isTrue);
  });
}
