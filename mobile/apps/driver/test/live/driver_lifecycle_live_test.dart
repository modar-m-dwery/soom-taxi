// T4.3 و T4.4 و T4.7 — دورة حياة السائق كاملة على خادم يعمل.
//
// هذا الملفّ هو الدليل على أهمّ ما اكتشفناه في هذا المشروع، ويقيسه
// صراحةً بدل أن يفترضه:
//
//   ١. نقاط السائق تتجاهل جسم الطلب: `go-online` و`arrived` و`complete`
//      كلّها `request=None` في الخادم. قناة الموقع واحدة: النبضة.
//   ٢. الإقرار يأتي على `heartbeat` لا على `location.update`.
//   ٣. الحارس الجغرافيّ يقرأ من القاعدة، والقاعدة تُزامَن كلّ خمس ثوانٍ
//      على الأكثر — فالفحص يتأخّر عن النبضة بهذه النافذة.
//   ٤. الترتيب مفروض: `start` قبل `arrived` يُرفض، و`complete` قبل
//      `start` يُرفض.
//
// وكلّها تمرّ بالطبقة نفسها التي يستعملها التطبيق، لا بنداءات خام.


import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

const _baseUrl = String.fromEnvironment('SOUM_LIVE');
const _customerToken = String.fromEnvironment('SOUM_CUSTOMER_TOKEN');
const _driverToken = String.fromEnvironment('SOUM_DRIVER_TOKEN');
const _driverProfileId =
    int.fromEnvironment('SOUM_DRIVER_PROFILE', defaultValue: 1);

const pickup = GeoPoint(35.3608, 35.9236);
const destination = GeoPoint(35.3700, 35.9300);

/// نقطة بعيدة عمدًا — خارج نطاق الوصول بكثير.
const farAway = GeoPoint(35.5300, 35.7800);

Future<Soum> session(String token) async {
  final soum = await Soum.create(
    baseUrl: _baseUrl,
    secure: InMemoryStore(),
    prefs: InMemoryStore(),
    dio: Dio(),
  );
  await soum.session.saveToken(token);
  return soum;
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
    test('دورة السائق الحيّة — متخطّاة (بلا إعداد خادم)', () {}, skip: true);
    return;
  }

  late Soum customer;
  late Soum driver;
  RealtimeRoom? driverRoom;

  setUp(() async {
    customer = await session(_customerToken);
    driver = await session(_driverToken);
    await cancelActiveRides(customer);
    await driver.config.load(lat: pickup.lat, lng: pickup.lng);
  });

  tearDown(() async {
    await driverRoom?.close();
    driverRoom = null;
    try {
      await driver.driver.goOffline();
    } on ApiException {
      // لا يهمّ حال التنظيف.
    }
  });

  test('قناة موقع السائق واحدة: النبضة، لا جسم go-online', () async {
    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    // الاتّصال ينجح — لكنّ الإحداثيات في الجسم لا تصل إلى الخادم أصلًا:
    // `DriverGoOnlineView.post` لا يقرأ جسم الطلب (مخطّطها request=None).
    // نرسل هنا إحداثيات بعيدة عمدًا لنُثبت أنّها بلا أثر.
    final response = await driver.driver.goOnline(
      lat: farAway.lat,
      lng: farAway.lng,
    );
    expect(readBool(response, 'online'), isTrue);
    expect(readString(response, 'status'), 'active');

    // النبضة — القناة الفعلية.
    final room = driver.room('/ws/driver/$_driverProfileId/');
    driverRoom = room;

    final acks = <RealtimeEvent>[];
    room.events.listen((g) {
      if (g.event.type == RealtimeEventType.presenceAck) acks.add(g.event);
    });

    await room.connect();
    await Future<void>.delayed(const Duration(milliseconds: 400));

    room.send({
      'type': 'location.update',
      'lat': pickup.lat,
      'lng': pickup.lng,
    });
    // الإقرار لا يأتي على `location.update` — بل على `heartbeat` وحده.
    room.send({'type': 'heartbeat'});
    await Future<void>.delayed(const Duration(milliseconds: 1500));

    expect(acks, isNotEmpty,
        reason: 'presence.ack يأتي على heartbeat لا على location.update');

    // وهو الآن في المطابقة، عند **نقطة النبضة** لا عند إحداثيات الجسم.
    final matched = await driver.driver.candidates();
    expect(matched.map((r) => r.id), contains(ride.id));

    // والبرهان الحاسم: الحارس الجغرافيّ يُقاس على النبضة. نُثبت السائق
    // على الطلب ثمّ نطلب «وصلت» بإحداثيات بعيدة في الجسم — فتنجح، لأنّ
    // الجسم يُتجاهَل والموقع المحفوظ هو نقطة الالتقاء.
    final offer = await driver.driver.submitOffer(
      rideId: ride.id,
      grossFare: Money.parse('6000.00'),
      etaMinutes: 4,
    );
    await customer.rides.selectOffer(ride.id, offer.id);
    await Future<void>.delayed(const Duration(milliseconds: 600));

    await driver.driver.arrived(ride.id, lat: farAway.lat, lng: farAway.lng);

    final snapshot = await driver.rides.activeRide();
    expect(
      snapshot.trip?.status,
      TripStatus.driverArrived,
      reason: 'نجحت رغم إحداثيات بعيدة في الجسم — الجسم يُتجاهَل، '
          'والحارس يُقاس على آخر نبضة',
    );

    await customer.rides.cancelTrip(ride.id, reason: 'اختبار');
  });

  test('الترتيب مفروض: start قبل arrived، وcomplete قبل start', () async {
    final (ride, room) = await _matchedRide(customer, driver);
    driverRoom = room;

    // `start` قبل `arrived`.
    await expectLater(
      driver.driver.start(ride.id),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 400)
          .having((e) => e.detail, 'detail', isNotEmpty)),
      reason: 'trip.not_arrived',
    );

    // `complete` قبل `start`.
    await expectLater(
      driver.driver.complete(ride.id, lat: destination.lat, lng: destination.lng),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 400)),
      reason: 'trip.not_started',
    );

    await customer.rides.cancelTrip(ride.id, reason: 'اختبار');
  });

  test('الحارس الجغرافيّ يُقاس على النبضة: نبضةٌ بعيدة تُرفض «وصلت»',
      () async {
    final (ride, room) = await _matchedRide(customer, driver);
    driverRoom = room;

    // ننبض من نقطة بعيدة — وهي القناة التي يقرأ منها الحارس فعلًا.
    //
    // والانتظار ستّ ثوانٍ لا واحدة: الخادم يكتب الموقع إلى القاعدة كلّ
    // خمس ثوانٍ على الأكثر (`DB_SYNC_MIN_INTERVAL_SECONDS`)، والحارس
    // يقرأ من القاعدة. انتظارٌ أقصر يقيس Redis لا ما يقيسه الحارس.
    // مرّتان عبر النافذة: الخانق يُقاس عند **الإرسال** لا عند القراءة،
    // فإرسالةٌ واحدة بعد أخرى قريبة تُكتب في Redis وحده. الثانية بعد
    // ستّ ثوانٍ تتجاوز الخانق فتصل القاعدة.
    for (var i = 0; i < 2; i++) {
      room.send({
        'type': 'location.update',
        'lat': farAway.lat,
        'lng': farAway.lng,
      });
      await Future<void>.delayed(const Duration(seconds: 6));
    }

    late ApiException failure;
    try {
      await driver.driver.arrived(ride.id, lat: pickup.lat, lng: pickup.lng);
      fail('كان يجب أن تُرفض: السائق بعيد بحسب آخر نبضة');
    } on ApiException catch (error) {
      failure = error;
    }

    expect(failure.statusCode, 400);
    // الخادم يرسل المسافة الدقيقة بالعربية جاهزةً للعرض.
    expect(failure.detail, contains('متر'),
        reason: '§12.3: اعرض له المسافة المتبقّية');

    // ثمّ نعود وننبض من نقطة الالتقاء فتنجح — وهو ما يفعله التطبيق:
    // نبضة، ثمّ نافذة المزامنة، ثمّ الفحص.
    for (var i = 0; i < 2; i++) {
      room.send({
        'type': 'location.update',
        'lat': pickup.lat,
        'lng': pickup.lng,
      });
      await Future<void>.delayed(const Duration(seconds: 6));
    }

    await driver.driver.arrived(ride.id, lat: pickup.lat, lng: pickup.lng);

    final snapshot = await driver.rides.activeRide();
    expect(snapshot.trip?.status, TripStatus.driverArrived);

    await customer.rides.cancelTrip(ride.id, reason: 'اختبار');
  });

  test('الدورة الكاملة: وصلت ← ابدأ ← أنهِ ← حصّل', () async {
    final (ride, room) = await _matchedRide(customer, driver);
    driverRoom = room;

    await driver.driver.arrived(ride.id, lat: pickup.lat, lng: pickup.lng);
    var snapshot = await driver.rides.activeRide();
    expect(snapshot.trip?.status, TripStatus.driverArrived);

    await driver.driver.start(ride.id);
    snapshot = await driver.rides.activeRide();
    expect(snapshot.trip?.status, TripStatus.inProgress);

    // السائق وصل الوجهة: ننبض من هناك قبل الإنهاء — وهو بالضبط ما
    // يفعله `WorkController.completeTrip` عبر `pushLocationNow`.
    for (var i = 0; i < 2; i++) {
      room.send({
        'type': 'location.update',
        'lat': destination.lat,
        'lng': destination.lng,
      });
      await Future<void>.delayed(const Duration(seconds: 6));
    }

    final completion = await driver.driver.complete(
      ride.id,
      lat: destination.lat,
      lng: destination.lng,
    );
    expect(completion, isNotEmpty);

    // الأجرة النهائية والدفعة.
    final payment = await driver.payments.forTrip(ride.id);
    expect(payment.gatewayCode, 'cash');
    expect(payment.status, PaymentStatus.pending);
    expect(payment.amount.amount.toDouble(), greaterThan(0));

    // §6.3 — الزبون لا يستطيع تأكيد القبض.
    await expectLater(
      customer.payments.charge(ride.id),
      throwsA(isA<ApiException>()
          .having((e) => e.statusCode, 'status', 403)),
      reason: 'الزبون لا يؤكّد قبض مالٍ لم يُقبَض',
    );

    // والسائق يستطيع.
    final charged = await driver.payments.charge(ride.id);
    expect(charged.status.isSettled, isTrue);

    // وبعد الدفع لا رحلة قائمة.
    final after = await driver.rides.activeRide();
    expect(after.hasActiveRide, isFalse);
    expect(after.pendingPayment, isNull);
  });

  test('رصيد السائق يقرأ بعد رحلة', () async {
    final balance = await driver.driver.balance();
    expect(balance.currency, isNotEmpty);
    expect(balance.total.amount.toDouble(), greaterThanOrEqualTo(0));
  });
}

/// رحلة مثبَّتة بسائق — المقدّمة المشتركة لاختبارات التنفيذ.
///
/// تُعيد الغرفة مع الطلب: النبض هو قناة الموقع الوحيدة، فكلّ اختبار
/// تنفيذ يحتاجها ليضع السائق حيث يريد.
Future<(RideRequest, RealtimeRoom)> _matchedRide(
  Soum customer,
  Soum driver,
) async {
  final ride = await customer.rides.create(
    pickup: pickup,
    destination: destination,
    mode: 'standard',
    passengerCount: 1,
  );

  await driver.driver.goOnline(lat: pickup.lat, lng: pickup.lng);

  final room = driver.room('/ws/driver/$_driverProfileId/');
  await room.connect();
  await Future<void>.delayed(const Duration(milliseconds: 400));
  room.send({'type': 'location.update', 'lat': pickup.lat, 'lng': pickup.lng});
  await Future<void>.delayed(const Duration(milliseconds: 1200));

  final offer = await driver.driver.submitOffer(
    rideId: ride.id,
    grossFare: Money.parse('6000.00'),
    etaMinutes: 4,
  );
  await customer.rides.selectOffer(ride.id, offer.id);
  await Future<void>.delayed(const Duration(milliseconds: 600));

  addTearDown(room.close);
  return (ride, room);
}
