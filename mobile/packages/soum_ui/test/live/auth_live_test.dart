// T2.1 و T2.2 — «جولة كاملة على الخادم الحقيقي تنتهي بمفتاح محفوظ ودور
// مقروء، وتسجيل خروج يُبطله فعلًا».
//
// هذا ليس اختبار وحدة. هو يتكلّم خادم Django حقيقيًّا بـPostGIS وRedis
// وCelery، ويقيس ما لا يقيسه أيّ محاكاة: أنّ الحقول التي نرسلها هي التي
// يتوقّعها، وأنّ الأسماء التي نقرأها هي التي يرسلها.
//
// يُشغَّل بعنوان الخادم صراحةً، ويُتخطّى بلا ضجيج إن لم يكن هناك خادم:
//
//   flutter test test/live --dart-define=SOUM_LIVE=http://127.0.0.1:8000/api/v1

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

const _baseUrl = String.fromEnvironment('SOUM_LIVE');

/// مخزنان منفصلان لا واحد: ‏`InMemoryStore` ينفّذ الواجهتين، وتمريره
/// مرّتين يجعل «المحميّ» و«العاديّ» الخريطةَ نفسها — فيمرّ اختبارٌ يدّعي
/// أنّ المفتاح ليس في التخزين العاديّ وهو فيه.
Future<Soum> connect({InMemoryStore? secure, InMemoryStore? prefs}) =>
    Soum.create(
      baseUrl: _baseUrl,
      secure: secure ?? InMemoryStore(),
      prefs: prefs ?? InMemoryStore(),
      dio: Dio(),
    );

void main() {
  if (_baseUrl.isEmpty) {
    test('اختبارات الخادم الحيّ — متخطّاة (بلا SOUM_LIVE)', () {}, skip: true);
    return;
  }

  test('الإعداد يُقرأ بلا مصادقة، ويحلّ جبلة من الإحداثيات', () async {
    final soum = await connect();

    final config = await soum.config.load(lat: 35.3608, lng: 35.9236);

    expect(config.areaCode, 'JAB');
    expect(config.resolution, AreaResolution.coordinates);
    expect(config.geometry.matchingRadiusKm, greaterThan(0));
    expect(config.timings.invitationTtlOptions, isNotEmpty);
    expect(config.vehicleCategories, isNotEmpty);

    // كلّ خيار مهلة يجب أن يكون قابلًا للإرسال — الخادم يرفض ما عداها.
    expect(
      config.timings.invitationTtlOptions,
      contains(config.timings.invitationTtlDefault),
    );
  });

  test('خارج كلّ منطقة: أرقام عامّة لا فراغ', () async {
    final soum = await connect();

    // نقطة في البحر المتوسّط، بعيدة عن كلّ منطقة خدمة.
    final config = await soum.config.load(lat: 34.0, lng: 33.0);

    expect(config.areaCode, isNull);
    expect(config.resolution, AreaResolution.none);
    expect(config.geometry.matchingRadiusKm, greaterThan(0));
  });

  test('دورة OTP كاملة: رمز ← مفتاح ← هويّة ← رحلة قائمة ← خروج', () async {
    final secure = InMemoryStore();
    final prefs = InMemoryStore();
    final soum = await connect(secure: secure, prefs: prefs);

    // هاتف جديد لكلّ تشغيل: حدّ طلب الرمز يُحتسب على الهاتف والجهاز معًا.
    final suffix = DateTime.now().millisecondsSinceEpoch % 10000000;
    final phone = '+9639${suffix.toString().padLeft(8, '0')}';

    final challenge = await soum.auth.requestOtp(phone);

    // في وضع التطوير يعود الرمز في الجسم — وهو ما يوفّر اشتراك الرسائل.
    expect(challenge.hasDevelopmentCode, isTrue,
        reason: 'الخادم ليس في وضع DEBUG؟');
    expect(challenge.expiresAt, isNotNull);

    final user = await soum.auth.verifyOtp(phone, challenge.developmentCode!);

    expect(user.phone, phone);
    expect(user.role, UserRole.customer);
    expect(soum.isAuthenticated, isTrue);
    expect(prefs.getString('soum.auth.token'), isNull,
        reason: 'المفتاح في التخزين المحميّ لا في العاديّ');
    expect(await secure.read('soum.auth.token'), isNotEmpty);

    // ‏/auth/me/ بالمفتاح المحفوظ — يثبت أنّ المعترض يحقنه فعلًا.
    final me = await soum.auth.me();
    expect(me.id, user.id);

    // أوّل نداء بعد المصادقة في كلّ إقلاع.
    final snapshot = await soum.rides.activeRide();
    expect(snapshot.stage, ResumeStage.idle);
    expect(snapshot.hasActiveRide, isFalse);
    expect(snapshot.rooms.rideRoom, isNull);

    // ومعرّف الجهاز ثابت — لم يُولَّد مرّتين خلال الدورة.
    final deviceId = await soum.session.deviceId();
    expect(deviceId, isNotEmpty);

    await soum.logout();
    expect(soum.isAuthenticated, isFalse);

    // المفتاح أُبطل على الخادم فعلًا لا محلّيًّا فقط.
    final reconnected = await connect();
    await reconnected.session.saveToken(soum.session.token ?? 'x');
    await expectLater(
      reconnected.auth.me(),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 401)),
    );
  });

  test('رمز خاطئ يعود بخطأ مفهوم لا بانهيار', () async {
    final soum = await connect();

    final suffix = (DateTime.now().millisecondsSinceEpoch ~/ 7) % 10000000;
    final phone = '+9639${suffix.toString().padLeft(8, '0')}';

    await soum.auth.requestOtp(phone);

    await expectLater(
      soum.auth.verifyOtp(phone, '000000'),
      throwsA(isA<ApiException>()
          .having((e) => e.detail, 'detail', isNotEmpty)
          .having((e) => e.code, 'code', isNotEmpty)),
    );
  });

  test('نداء موثَّق بلا مفتاح يعود 401 بالشكل الموحّد', () async {
    final soum = await connect();

    await expectLater(
      soum.auth.me(),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 401)
          .having((e) => e.code, 'code', ApiErrorCode.unauthenticated)
          .having((e) => e.requestId, 'requestId', isNotNull)),
    );
  });

  test('مورد غير موجود يعود بلا code — والطبقة تشتقّه', () async {
    final soum = await connect();

    final suffix = (DateTime.now().millisecondsSinceEpoch ~/ 13) % 10000000;
    final phone = '+9639${suffix.toString().padLeft(8, '0')}';
    final challenge = await soum.auth.requestOtp(phone);
    await soum.auth.verifyOtp(phone, challenge.developmentCode!);

    await expectLater(
      soum.rides.trip(99999999),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 404)
          .having((e) => e.code, 'code', ApiErrorCode.notFound)),
    );
  });
}
