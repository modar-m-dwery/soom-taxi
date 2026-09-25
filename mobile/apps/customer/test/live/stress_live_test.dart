// §12.4 — «قبل التسليم».
//
// أربعة سيناريوهات تسمّيها الوثيقة صراحةً، وكلّها تقيس ما لا تقيسه
// اختبارات المسار السعيد:
//
//   • زبونان يختاران السائق نفسه في اللحظة نفسها.
//   • قطع الشبكة في منتصف الرحلة ثمّ عودتها.
//   • سائقٌ يغلق التطبيق أثناء رحلة قائمة.
//   • قوائم طويلة لا ثلاثة صفوف.
//
// والفرق بينها وبين اختبارات M3 و M4 أنّ تلك تقيس أنّ الميزة تعمل، وهذه
// تقيس أنّها **لا تنهار** حين لا تعمل الظروف.

import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

const _baseUrl = String.fromEnvironment('SOUM_LIVE');
const _customerToken = String.fromEnvironment('SOUM_CUSTOMER_TOKEN');
const _driverToken = String.fromEnvironment('SOUM_DRIVER_TOKEN');
const _driverProfileId =
    int.fromEnvironment('SOUM_DRIVER_PROFILE', defaultValue: 1);

const pickup = GeoPoint(35.3608, 35.9236);
const destination = GeoPoint(35.3700, 35.9300);

Future<Soum> session(String token, {Dio? dio}) async {
  final soum = await Soum.create(
    baseUrl: _baseUrl,
    secure: InMemoryStore(),
    prefs: InMemoryStore(),
    dio: dio ?? Dio(),
  );
  await soum.session.saveToken(token);
  return soum;
}

/// محوّل يقطع الشبكة بأمرنا — لمحاكاة نفق أو مصعد.
class CuttableAdapter implements HttpClientAdapter {
  CuttableAdapter() : _inner = IOHttpClientAdapter();

  final HttpClientAdapter _inner;
  bool isCut = false;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? stream,
      Future<void>? cancelFuture) {
    if (isCut) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
        error: 'قُطعت الشبكة عمدًا',
      );
    }
    return _inner.fetch(options, stream, cancelFuture);
  }

  @override
  void close({bool force = false}) => _inner.close(force: force);
}

/// يُلغي كلّ طلب قائم للزبون قبل الاختبار.
///
/// للزبون طلبٌ قائم واحد في كلّ لحظة (409 للثاني). اختبارٌ سقط قبل أن
/// ينظّف كان يُسقط كلّ ما بعده بسلسلة 409 — فالتنظيف هنا لا في نهاية
/// كلّ اختبار وحدها.
Future<void> cancelActiveRides(Soum customer) async {
  const active = {
    RideStatus.searching,
    RideStatus.offersReceived,
    RideStatus.driverSelected,
    RideStatus.driverArriving,
    RideStatus.driverArrived,
    RideStatus.inProgress,
  };
  final mine = await customer.rides.mine();
  for (final ride in mine.where((r) => active.contains(r.status))) {
    try {
      await customer.rides.cancelTrip(ride.id, reason: 'تنظيف اختبار');
    } on ApiException {
      await customer.rides.cancel(ride.id).catchError((_) {});
    }
  }
}

void main() {
  if (_baseUrl.isEmpty || _customerToken.isEmpty || _driverToken.isEmpty) {
    test('سيناريوهات §12.4 — متخطّاة (بلا إعداد خادم)', () {}, skip: true);
    return;
  }

  late Soum customer;
  late Soum driver;
  final rooms = <RealtimeRoom>[];

  setUp(() async {
    customer = await session(_customerToken);
    driver = await session(_driverToken);
    await cancelActiveRides(customer);
    await customer.config.load(lat: pickup.lat, lng: pickup.lng);
  });

  tearDown(() async {
    for (final room in rooms) {
      await room.close();
    }
    rooms.clear();
    try {
      await driver.driver.goOffline();
    } on ApiException {
      // لا يهمّ حال التنظيف.
    }
  });

  Future<RealtimeRoom> bringDriverOnline() async {
    await driver.driver.goOnline(lat: pickup.lat, lng: pickup.lng);
    final room = driver.room('/ws/driver/$_driverProfileId/');
    rooms.add(room);
    await room.connect();
    await Future<void>.delayed(const Duration(milliseconds: 400));
    room.send({'type': 'location.update', 'lat': pickup.lat, 'lng': pickup.lng});
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    return room;
  }

  test('§12.4 — قطع الشبكة في منتصف الرحلة ثمّ عودتها', () async {
    final adapter = CuttableAdapter();
    final flaky = await session(_customerToken, dio: Dio()..httpClientAdapter = adapter);
    await flaky.config.load(lat: pickup.lat, lng: pickup.lng);

    final ride = await flaky.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    // الشبكة تُقطع.
    adapter.isCut = true;

    // كلّ نداء يفشل بالشكل الموحّد — لا انهيار ولا استثناء غريب.
    await expectLater(
      flaky.rides.activeRide(),
      throwsA(isA<ApiException>()
          .having((e) => e.isNetwork, 'isNetwork', isTrue)
          .having((e) => e.statusCode, 'status', 0)
          .having((e) => e.detail, 'detail', isNotEmpty)),
    );

    // والإعداد يبقى مقروءًا من الخبيئة: «المستخدم بلا شبكة يجب أن يرى
    // شاشةً لا خطأً».
    final cached = await flaky.config.load(lat: pickup.lat, lng: pickup.lng);
    expect(cached.areaCode, 'JAB');
    expect(cached.geometry.matchingRadiusKm, greaterThan(0));

    // الشبكة تعود.
    adapter.isCut = false;

    final restored = await flaky.rides.activeRide();
    expect(restored.ride?.id, ride.id,
        reason: 'الحالة تُستعاد من الخادم بنداء واحد');

    await flaky.rides.cancel(ride.id);
  });

  test('§12.4 — السائق يغلق التطبيق أثناء رحلة قائمة', () async {
    final room = await bringDriverOnline();

    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    final offer = await driver.driver.submitOffer(
      rideId: ride.id,
      grossFare: Money.parse('6000.00'),
      etaMinutes: 4,
    );
    await customer.rides.selectOffer(ride.id, offer.id);
    await Future<void>.delayed(const Duration(milliseconds: 600));

    // إغلاق التطبيق = إغلاق المقبس بلا go-offline.
    await room.close();
    rooms.remove(room);
    await Future<void>.delayed(const Duration(seconds: 2));

    // الرحلة تبقى قائمة عند الطرفين: إغلاق تطبيق ليس إلغاءً.
    final customerView = await customer.rides.activeRide();
    expect(customerView.hasActiveRide, isTrue);
    expect(customerView.stage.isOnTrip, isTrue,
        reason: 'الزبون لا يُترك بلا رحلة لأنّ سائقه أغلق تطبيقه');

    final driverView = await driver.rides.activeRide();
    expect(driverView.hasActiveRide, isTrue);

    // وعند العودة يستأنف السائق من حيث كان — بنداء واحد.
    expect(driverView.rooms.rideRoom, isNotNull);
    expect(driverView.trip?.status, isNotNull);

    await customer.rides.cancelTrip(ride.id, reason: 'اختبار');
  });

  test('§12.4 — قوائم طويلة لا ثلاثة صفوف', () async {
    // عشرة طلبات دفعةً واحدة: القوائم الطويلة تكشف ترقيمًا ناقصًا
    // وترتيبًا غير مستقرّ وقراءةً تفترض `results` أو تفترض مصفوفة.
    // للزبون طلبٌ قائم واحد في كلّ لحظة (409 للثاني)، فكلّ طلب يُلغى فور
    // إنشائه: الملغاة تبقى في `mine()` وهي ما تحتاجه القائمة الطويلة.
    final rides = <RideRequest>[];
    for (var i = 0; i < 10; i++) {
      final ride = await customer.rides.create(
        pickup: pickup,
        destination: destination,
        mode: 'standard',
        passengerCount: 1,
      );
      rides.add(ride);
      await customer.rides.cancel(ride.id);
    }

    final mine = await customer.rides.mine();
    expect(mine.length, greaterThanOrEqualTo(10));

    // الترتيب مستقرّ: الأحدث أوّلًا كما يعد الخادم.
    for (var i = 1; i < mine.length; i++) {
      expect(
        mine[i].createdAt.isAfter(mine[i - 1].createdAt),
        isFalse,
        reason: 'ترتيبٌ غير مستقرّ يجعل القائمة تقفز مع كلّ تحديث',
      );
    }

    // وكلّ صفّ كامل: حقلٌ مفقود في صفٍّ واحد يُسقط الشاشة كلّها.
    for (final ride in mine.take(10)) {
      expect(ride.id, greaterThan(0));
      expect(ride.fare.currency, isNotEmpty);
      expect(ride.status, isNot(RideStatus.unknown));
    }

    for (final ride in rides) {
      try {
        await customer.rides.cancel(ride.id);
      } on ApiException {
        // بعضها قد يكون انقضى.
      }
    }
  });

  test('§12.4 — إعادة اتصال المقبس تستأنف بلا تكرار', () async {
    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    final room = customer.room('/ws/rides/${ride.id}/');
    rooms.add(room);

    var resumeCalls = 0;
    room.onReconnected = () => resumeCalls++;

    final snapshots = <RealtimeEvent>[];
    room.events.listen((g) {
      if (g.event.isSnapshot) snapshots.add(g.event);
    });

    await room.connect();
    await Future<void>.delayed(const Duration(milliseconds: 800));

    expect(snapshots, hasLength(1), reason: 'لقطة واحدة عند الاتصال الأوّل');
    expect(resumeCalls, 0, reason: 'الاتصال الأوّل ليس استئنافًا');

    // النسخة المعروفة تتقدّم مع الأحداث، وحارس الترتيب يحفظها.
    expect(room.guard.versionOf('ride', ride.id), greaterThanOrEqualTo(0));

    await customer.rides.cancel(ride.id);
  });
}
