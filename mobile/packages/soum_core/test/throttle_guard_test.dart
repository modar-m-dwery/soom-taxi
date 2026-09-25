// T1.2 — «اختبار يُرجع 429 بـretry_after: 30 ويثبت أنّ النداء الثاني لم
// يُرسل قبل الثلاثين».
//
// السطر الذي يقيسه، §8.2: «حلقة إعادة محاولة بلا انتظار تُبقي المستخدم
// محظورًا إلى ما لا نهاية». الخنق يُحتسب على نافذة زمنية، فكلّ محاولة
// داخلها تجدّدها — والتطبيق الذي «يعيد حتى ينجح» يحبس نفسه.

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

class _Clock {
  DateTime now = DateTime(2026, 9, 14, 12, 0, 0);
  DateTime call() => now;
  void advance(Duration by) => now = now.add(by);
}

/// يعدّ كم نداءً غادر فعلًا نحو الشبكة.
class _CountingAdapter implements HttpClientAdapter {
  int calls = 0;
  int status = 429;
  Map<String, dynamic> body = const {
    'detail': 'تجاوزت الحدّ.',
    'code': 'throttled',
    'retry_after': 30,
  };

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? stream,
      Future<void>? cancelFuture) async {
    calls++;
    return ResponseBody.fromString(
      '{"detail":"${body['detail']}","code":"${body['code']}"'
      '${body.containsKey('retry_after') ? ',"retry_after":${body['retry_after']}' : ''}}',
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late _Clock clock;
  late _CountingAdapter adapter;
  late ThrottleGuard guard;
  late ApiClient client;

  setUp(() async {
    clock = _Clock();
    adapter = _CountingAdapter();
    guard = ThrottleGuard(clock: clock.call);

    final store = InMemoryStore();
    final session = SessionStore(secure: store, prefs: store);
    await session.load();

    final dio = Dio()..httpClientAdapter = adapter;
    client = ApiClient(
      baseUrl: 'http://test/api/v1',
      session: session,
      dio: dio,
      throttleGuard: guard,
    );
  });

  test('النداء الثاني لا يغادر الجهاز قبل انقضاء المدّة', () async {
    // الأوّل يصل إلى الخادم ويعود بـ429.
    await expectLater(
      client.get<dynamic>('/auth/request-otp/'),
      throwsA(isA<ApiException>()
          .having((e) => e.code, 'code', ApiErrorCode.throttled)
          .having((e) => e.retryAfter, 'retryAfter', const Duration(seconds: 30))),
    );
    expect(adapter.calls, 1);

    // الثاني يُرفض محلّيًّا — ولا يُحتسب على النافذة فيجدّدها.
    clock.advance(const Duration(seconds: 5));
    await expectLater(
      client.get<dynamic>('/auth/request-otp/'),
      throwsA(isA<ApiException>()
          .having((e) => e.code, 'code', ApiErrorCode.throttled)),
    );
    expect(adapter.calls, 1, reason: 'لم يغادر نداء ثانٍ');

    // والمدّة المتبقّية صادقة — عليها يُبنى العدّاد المرئي.
    expect(guard.remainingFor('/auth/request-otp/'), const Duration(seconds: 25));
  });

  test('بعد انقضاء المدّة يمرّ النداء', () async {
    await expectLater(client.get<dynamic>('/auth/request-otp/'),
        throwsA(isA<ApiException>()));
    expect(adapter.calls, 1);

    clock.advance(const Duration(seconds: 31));
    expect(guard.remainingFor('/auth/request-otp/'), isNull);

    adapter.status = 200;
    adapter.body = const {'detail': 'ok', 'code': 'ok'};
    await client.get<dynamic>('/auth/request-otp/');
    expect(adapter.calls, 2);
  });

  test('الحظر يخصّ النقطة لا التطبيق كلّه', () async {
    await expectLater(client.get<dynamic>('/auth/request-otp/'),
        throwsA(isA<ApiException>()));

    adapter.status = 200;
    adapter.body = const {'detail': 'ok', 'code': 'ok'};

    // نقطة أخرى لا علاقة لها بحدّ الرموز.
    await client.get<dynamic>('/auth/me/');
    expect(adapter.calls, 2);
    expect(guard.remainingFor('/auth/me/'), isNull);
  });

  test('المعرّفات في المسار لا تشقّ الحدّ إلى حدود منفصلة', () async {
    await expectLater(client.get<dynamic>('/customer/rides/2702/offers/'),
        throwsA(isA<ApiException>()));
    expect(adapter.calls, 1);

    // رحلة أخرى، النقطة نفسها: الحدّ يخصّ النقطة.
    await expectLater(client.get<dynamic>('/customer/rides/9999/offers/'),
        throwsA(isA<ApiException>()));
    expect(adapter.calls, 1, reason: 'المسار طُبِّع فصار الحدّ واحدًا');
  });

  test('429 بلا retry_after يأخذ افتراضًا لا صفرًا', () async {
    adapter.body = const {'detail': 'تجاوزت الحدّ.', 'code': 'throttled'};

    await expectLater(client.get<dynamic>('/maps/route/'),
        throwsA(isA<ApiException>()));

    final left = guard.remainingFor('/maps/route/');
    expect(left, isNotNull);
    expect(left!.inSeconds, greaterThan(0),
        reason: 'صفرٌ هنا يعيدنا إلى الحلقة التي يحذّر منها الدليل');
  });
}
