// T1.5 — «اختبار يُسقط الشبكة ويثبت أنّ الشاشة تُرسم من النسخة المخزَّنة،
// وأنّ نسخةً أقدم من يوم تُرفض».
//
// الحمولة في هذا الملفّ هي ردّ `/config/?lat=35.3608&lng=35.9236` الحقيقي
// من خادم جبلة، بأرقامه كما هي: نصف قطر ٥ كم، ومهل دعوة ٢٠/٤٠/٦٠،
// ونطاق وصول ٢٠٠ مترًا.

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

const _jablehConfig = {
  'area_code': 'JAB',
  'area_name': 'جبلة',
  'country_code': '',
  'resolved_from': 'coordinates',
  'ride_modes': ['fast', 'express', 'standard', 'saving', 'shared'],
  'invitation_allowed_modes': ['fast', 'express'],
  'vehicle_categories': [
    {'code': 'sedan', 'name': 'سيدان', 'seats': 4, 'sort_order': 10},
    {'code': 'van', 'name': 'فان', 'seats': 8, 'sort_order': 40},
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
    'allowed_policies': ['platform_fixed', 'driver_bidding'],
    'surge_enabled': false,
    'surge_max_multiplier': null,
    'min_fare_absolute': null,
  },
  'server_time': '2026-09-14T20:04:15Z',
};

class FakeAdapter implements HttpClientAdapter {
  bool offline = false;
  int calls = 0;
  Map<String, dynamic> payload = Map<String, dynamic>.from(_jablehConfig);

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? stream,
      Future<void>? cancelFuture) async {
    calls++;
    if (offline) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
      );
    }
    return ResponseBody.fromString(
      jsonEncode(payload),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

class TestClock {
  DateTime now = DateTime.utc(2026, 9, 14, 20, 4, 15);
  DateTime call() => now;
  void advance(Duration by) => now = now.add(by);
}

Future<(ConfigRepository, FakeAdapter, TestClock, InMemoryStore)> build({
  InMemoryStore? disk,
  TestClock? clock,
}) async {
  final store = disk ?? InMemoryStore();
  final time = clock ?? TestClock();
  final adapter = FakeAdapter();

  final session = SessionStore(secure: store, prefs: store);
  await session.load();

  final client = ApiClient(
    baseUrl: 'http://test/api/v1',
    session: session,
    dio: Dio()..httpClientAdapter = adapter,
  );

  return (
    ConfigRepository(client: client, prefs: store, clock: time.call),
    adapter,
    time,
    store,
  );
}

void main() {
  test('يقرأ إعداد جبلة بأرقامه كما هي', () async {
    final (repo, _, _, _) = await build();
    final config = await repo.load(lat: 35.3608, lng: 35.9236);

    expect(config.areaCode, 'JAB');
    expect(config.areaName, 'جبلة');
    expect(config.resolution, AreaResolution.coordinates);
    expect(config.resolution.isTrustworthy, isTrue);

    expect(config.geometry.matchingRadiusKm, 5.0);
    expect(config.geometry.arrivalRadiusM, 200);
    expect(config.geometry.dropoffRadiusM, 300);

    expect(config.timings.invitationTtlOptions, [20, 40, 60]);
    expect(config.timings.invitationTtlDefault, 20);
    expect(config.timings.invitationMaxParallel, 1);

    expect(config.rideModes, hasLength(5));
    expect(config.vehicleCategories.first.code, 'sedan');
    expect(config.pricing.currencyCode, 'SYP');
  });

  test('الدعوة متاحة لـfast و express وحدهما', () async {
    final (repo, _, _, _) = await build();
    final config = await repo.load(lat: 35.3608, lng: 35.9236);

    expect(config.supportsInvitation('fast'), isTrue);
    expect(config.supportsInvitation('express'), isTrue);
    expect(config.supportsInvitation('standard'), isFalse);
    expect(config.supportsInvitation('saving'), isFalse);
  });

  test('وتيرة النبض أعلى من ثلث مهلة الانقطاع', () async {
    final (repo, _, _, _) = await build();
    final config = await repo.load();

    final interval = config.timings.heartbeatInterval;
    expect(interval.inSeconds * 3, lessThan(config.timings.presenceStaleSeconds));
    expect(interval.inSeconds, inInclusiveRange(3, 15));
  });

  test('انقطاع الشبكة يُرسم من النسخة المخزَّنة لا برسالة خطأ', () async {
    final disk = InMemoryStore();
    final clock = TestClock();

    final (repo1, adapter1, _, _) = await build(disk: disk, clock: clock);
    await repo1.load(lat: 35.3608, lng: 35.9236);
    expect(adapter1.calls, 1);

    // إقلاع ثانٍ بلا شبكة.
    final (repo2, adapter2, _, _) = await build(disk: disk, clock: clock);
    adapter2.offline = true;

    clock.advance(const Duration(hours: 3));
    final cached = await repo2.load(lat: 35.3608, lng: 35.9236);

    expect(cached.areaCode, 'JAB');
    expect(cached.geometry.matchingRadiusKm, 5.0);
    expect(cached.timings.invitationTtlOptions, [20, 40, 60]);
  });

  test('نسخة أقدم من يوم تُعدّ منتهية فلا تُستعمل', () async {
    final disk = InMemoryStore();
    final clock = TestClock();

    final (repo1, _, _, _) = await build(disk: disk, clock: clock);
    await repo1.load();

    final (repo2, adapter2, _, _) = await build(disk: disk, clock: clock);
    adapter2.offline = true;

    clock.advance(const Duration(hours: 25));

    await expectLater(repo2.load(), throwsA(isA<ConfigUnavailable>()));
  });

  test('الشبكة تُفضَّل على الخبيئة — الإعداد يسري فورًا بلا نشر', () async {
    final disk = InMemoryStore();
    final clock = TestClock();

    final (repo1, _, _, _) = await build(disk: disk, clock: clock);
    final before = await repo1.load();
    expect(before.timings.invitationTtlDefault, 20);

    // المشغّل غيّر المهلة الافتراضية من لوحة الإدارة.
    final (repo2, adapter2, _, _) = await build(disk: disk, clock: clock);
    adapter2.payload = {
      ..._jablehConfig,
      'timings': {
        ...(_jablehConfig['timings']! as Map<String, dynamic>),
        'invitation_ttl_default': 40,
      },
    };

    clock.advance(const Duration(minutes: 5));
    final after = await repo2.load();

    expect(after.timings.invitationTtlDefault, 40,
        reason: 'خبيئةٌ تُفضَّل على الشبكة تؤخّر التغيير يومًا');
  });

  test('خبيئة تالفة لا تمنع الإقلاع', () async {
    final disk = InMemoryStore();
    await disk.setString('soum.config.cache', '}{ليس JSON');
    await disk.setString(
        'soum.config.cached_at', DateTime.utc(2026, 9, 14, 20).toIso8601String());

    final (repo, adapter, _, _) = await build(disk: disk);
    adapter.offline = true;

    await expectLater(repo.load(), throwsA(isA<ConfigUnavailable>()));
  });

  test('خارج كلّ منطقة: أرقام عامّة وresolved_from صريح', () async {
    final (repo, adapter, _, _) = await build();
    adapter.payload = {
      ..._jablehConfig,
      'area_code': null,
      'area_name': null,
      'resolved_from': 'none',
    };

    final config = await repo.load(lat: 0, lng: 0);

    expect(config.areaCode, isNull);
    expect(config.resolution, AreaResolution.none);
    expect(config.resolution.isTrustworthy, isFalse,
        reason: 'لا يُعرض للمستخدم أنّه في مدينة ليس فيها');
    expect(config.geometry.matchingRadiusKm, greaterThan(0),
        reason: 'أرقام معقولة لا فراغ — الشاشة تُرسم');
  });

  test('حقل جديد في الخادم لا يكسر القراءة', () async {
    final (repo, adapter, _, _) = await build();
    adapter.payload = {
      ..._jablehConfig,
      'feature_we_have_not_seen_yet': {'x': 1},
      'timings': {
        ...(_jablehConfig['timings']! as Map<String, dynamic>),
        'brand_new_timing_seconds': 99,
      },
    };

    final config = await repo.load();
    expect(config.areaCode, 'JAB');
    expect(config.timings.offerTtlSeconds, 30);
  });
}
