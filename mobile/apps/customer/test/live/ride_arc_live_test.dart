// T3.3 و T3.4 و T3.5 — قوس المزاد كاملًا على خادم يعمل.
//
// الاختبار يلعب الطرفين بالطبقة نفسها التي يستعملها التطبيقان: زبونٌ
// ينشئ طلبًا ويشترك في غرفته، وسائقٌ يتّصل وينبض بموقعه ويقدّم عرضًا.
// ما يقيسه ليس أنّ النداءات تنجح — بل أنّ **الأحداث تصل عبر المقبس**
// فتتغيّر الحالة بلا نداء استقصاء واحد.
//
// وفيه سيناريو السباق الذي يفرضه §4.4: زبونان يختاران السائق نفسه في
// اللحظة نفسها — واحدٌ يفوز، والآخر يقرأ 409 لا شاشة خطأ.

import 'dart:async';

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

Future<Soum> session(String token) async {
  final store = InMemoryStore();
  final soum = await Soum.create(
    baseUrl: _baseUrl,
    secure: store,
    prefs: InMemoryStore(),
    dio: Dio(),
  );
  await soum.session.saveToken(token);
  return soum;
}

/// زبونٌ ثانٍ مسجَّل برمز التطوير — الخادم في وضع DEBUG يعيده في الردّ.
Future<Soum> secondCustomer() async {
  final soum = await Soum.create(
    baseUrl: _baseUrl,
    secure: InMemoryStore(),
    prefs: InMemoryStore(),
    dio: Dio(),
  );
  const phone = '+963990000104';
  final challenge = await soum.auth.requestOtp(phone);
  final code = challenge.developmentCode;
  if (code == null) {
    fail('الخادم لا يعيد رمز التطوير — الاختبار يحتاج DEBUG=True');
  }
  await soum.auth.verifyOtp(phone, code);
  return soum;
}

/// السائق حاضر فعلًا في المطابقة.
///
/// `go-online` وحده لا يكفي — أثبتناه على خادم يعمل: المطابقة تشترط
/// `last_location_at` حديثًا، ولا يتحدّث إلّا بنبض `location.update` في
/// غرفة السائق. سائقٌ «متّصل» بلا نبض لا يرى طلبًا واحدًا.
Future<RealtimeRoom> bringDriverOnline(Soum driver) async {
  await driver.driver.goOnline(lat: pickup.lat, lng: pickup.lng);

  final room = driver.room('/ws/driver/$_driverProfileId/');
  await room.connect();
  await Future<void>.delayed(const Duration(milliseconds: 400));

  room.send({'type': 'location.update', 'lat': pickup.lat, 'lng': pickup.lng});
  await Future<void>.delayed(const Duration(milliseconds: 900));

  return room;
}

/// مسجّل أحداث يبدأ من لحظة الاتصال.
///
/// ‏`room.events` تدفّق بثّي: الاشتراك عليه **بعد** إطلاق الفعل يُفوّت ما
/// وصل في ما بينهما. هذا ليس تفصيلًا اختباريًّا — الشاشة التي تشترك عند
/// أوّل بناء بدل عند فتح الغرفة تفقد أوّل عرض بالطريقة نفسها.
class EventLog {
  EventLog(RealtimeRoom room) {
    _subscription = room.events.listen((guarded) {
      if (!guarded.isStale) events.add(guarded.event);
    });
  }

  final events = <RealtimeEvent>[];
  late final StreamSubscription<GuardedEvent> _subscription;

  Future<void> close() => _subscription.cancel();

  /// ينتظر حتّى يظهر حدث مطابق في السجلّ.
  Future<RealtimeEvent> waitFor(
    String type, {
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final deadline = DateTime.now().add(timeout);

    while (DateTime.now().isBefore(deadline)) {
      final found = events.where((e) => e.type == type);
      if (found.isNotEmpty) return found.first;
      await Future<void>.delayed(const Duration(milliseconds: 120));
    }

    throw TimeoutException(
      'لم يصل $type خلال ${timeout.inSeconds} ثانية. '
      'ما وصل: ${events.map((e) => e.type).toSet()}',
    );
  }
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
    test('قوس الرحلة الحيّ — متخطّى (بلا إعداد خادم)', () {}, skip: true);
    return;
  }

  late Soum customer;
  late Soum driver;
  RealtimeRoom? driverRoom;
  final openRooms = <RealtimeRoom>[];

  setUp(() async {
    customer = await session(_customerToken);
    driver = await session(_driverToken);
    await cancelActiveRides(customer);
    await customer.config.load(lat: pickup.lat, lng: pickup.lng);
  });

  tearDown(() async {
    for (final room in openRooms) {
      await room.close();
    }
    openRooms.clear();
    await driverRoom?.close();
    driverRoom = null;
    try {
      await driver.driver.goOffline();
    } on ApiException {
      // لا يهمّ حال التنظيف.
    }
  });

  test('اللقطة تصل عند الاشتراك، وفيها الطلب بتفصيل أجرته', () async {
    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    expect(ride.status, RideStatus.searching);
    expect(ride.expiresAt, isNotNull, reason: 'العدّاد يُبنى على هذا');

    // الأجرة تعود مفصَّلة، والمجموع يطابق الإجمالي خانةً بخانة.
    final fare = ride.fare;
    final parts = fare.baseFare + fare.distanceFare + fare.timeFare;
    expect(parts.toApi(), fare.grossFare.toApi());
    expect(fare.customerTotal, fare.driverNet,
        reason: 'عمولة صفر: ما يدفعه الزبون = ما يقبضه السائق');

    final room = customer.room('/ws/rides/${ride.id}/');
    openRooms.add(room);
    await room.connect();

    final log = EventLog(room);
    final snapshot = await log.waitFor(RealtimeEventType.rideSnapshot);

    expect(snapshot.version, isNotNull);
    expect(snapshot.entityId, ride.id);
    expect(asJson(snapshot.data['ride'])['id'], ride.id);

    await customer.rides.cancel(ride.id);
  });

  test('عرض السائق يصل إلى الزبون عبر المقبس بلا استقصاء', () async {
    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    final room = customer.room('/ws/rides/${ride.id}/');
    openRooms.add(room);
    await room.connect();
    final log = EventLog(room);
    await Future<void>.delayed(const Duration(milliseconds: 400));

    driverRoom = await bringDriverOnline(driver);

    final candidates = await driver.driver.candidates();
    expect(candidates.map((r) => r.id), contains(ride.id),
        reason: 'السائق مؤهَّل ويرى الطلب');

    await driver.driver.submitOffer(
      rideId: ride.id,
      grossFare: Money.parse('6000.00'),
      etaMinutes: 4,
    );

    final offer = RideOffer.fromJson(
      (await log.waitFor(RealtimeEventType.offerCreated)).data,
    );

    expect(offer.rideId, ride.id);
    expect(offer.grossFare.toApi(), '6000.00');
    expect(offer.etaMinutes, 4);
    expect(offer.status.isLive, isTrue);
    expect(offer.vehicle, isNotNull);
    expect(offer.expiresAt.isAfter(DateTime.now()), isTrue,
        reason: 'العدّاد يُبنى على expires_at لا على offer_ttl_seconds');

    await customer.rides.cancel(ride.id);
  });

  test('اختيار عرض يُنشئ رحلة، والحدث يحمل النسخة التالية', () async {
    final ride = await customer.rides.create(
      pickup: pickup,
      destination: destination,
      mode: 'standard',
      passengerCount: 1,
    );

    final room = customer.room('/ws/rides/${ride.id}/');
    openRooms.add(room);
    await room.connect();
    final log = EventLog(room);
    await Future<void>.delayed(const Duration(milliseconds: 400));

    driverRoom = await bringDriverOnline(driver);

    final offer = await driver.driver.submitOffer(
      rideId: ride.id,
      grossFare: Money.parse('6000.00'),
      etaMinutes: 4,
    );

    await customer.rides.selectOffer(ride.id, offer.id);
    await Future<void>.delayed(const Duration(seconds: 2));

    final versions = log.events
        .where((e) => e.version != null && !e.isSnapshot)
        .map((e) => e.version!)
        .toList();

    // النسخ متصاعدة بلا فجوة — وهو ما يعتمد عليه حارس الترتيب.
    expect(versions, isNotEmpty);
    for (var i = 1; i < versions.length; i++) {
      expect(versions[i], greaterThan(versions[i - 1]));
    }

    final snapshot = await customer.rides.activeRide();
    expect(snapshot.hasActiveRide, isTrue);
    expect(snapshot.stage.isOnTrip, isTrue);
    expect(snapshot.rooms.rideRoom, '/ws/rides/${ride.id}/');

    await customer.rides.cancelTrip(ride.id, reason: 'اختبار');
  });

  test('طلبٌ ثانٍ من الزبون نفسه يُردّ 409 بنصّ عربيّ', () async {
    // كان الخادم يقبل طلبات متوازية للزبون الواحد — ثلاثة «searching» في
    // دقيقة — فأُضيف الحارس. الاختبار يثبّته.
    final first = await customer.rides.create(
      pickup: pickup, destination: destination,
      mode: 'standard', passengerCount: 1,
    );
    try {
      await expectLater(
        customer.rides.create(
          pickup: pickup, destination: destination,
          mode: 'standard', passengerCount: 1,
        ),
        throwsA(isA<ApiException>()
            .having((e) => e.statusCode, 'status', 409)
            .having((e) => e.detail, 'detail', contains('قائم'))),
      );
    } finally {
      await customer.rides.cancel(first.id).catchError((_) {});
    }
  });

  test('§4.4 — زبونان على السائق نفسه: واحد يفوز والآخر يقرأ 409', () async {
    // القفل على **السائق** لا على الزبون. ولأنّ للزبون الواحد طلبًا قائمًا
    // واحدًا، الطلب الثاني من زبونٍ ثانٍ يُسجَّل برمز التطوير.
    final other = await secondCustomer();

    final first = await customer.rides.create(
      pickup: pickup, destination: destination,
      mode: 'standard', passengerCount: 1,
    );
    final second = await other.rides.create(
      pickup: pickup, destination: destination,
      mode: 'standard', passengerCount: 1,
    );

    driverRoom = await bringDriverOnline(driver);

    final offerOne = await driver.driver.submitOffer(
      rideId: first.id, grossFare: Money.parse('6000.00'), etaMinutes: 4,
    );
    final offerTwo = await driver.driver.submitOffer(
      rideId: second.id, grossFare: Money.parse('6000.00'), etaMinutes: 4,
    );

    // الاختياران في اللحظة نفسها.
    final results = await Future.wait([
      customer.rides.selectOffer(first.id, offerOne.id)
          .then<Object>((o) => o).catchError((Object e) => e),
      other.rides.selectOffer(second.id, offerTwo.id)
          .then<Object>((o) => o).catchError((Object e) => e),
    ]);

    final winners = results.whereType<RideOffer>().toList();
    final losers = results.whereType<ApiException>().toList();

    expect(winners, hasLength(1), reason: 'سائق واحد لرحلة واحدة');
    expect(losers, hasLength(1));
    expect(losers.single.statusCode, 409);
    expect(losers.single.isDriverTaken, isTrue);
    expect(losers.single.detail, isNotEmpty);

    // عيبٌ مقيس في الباك إند لا في التطبيق: ‏CustomerSelectOfferView تلتقط
    // MatchingError بنفسها وتعيد {"detail": str(exc)} مباشرةً، فتتجاوز
    // معالج الأخطاء. النتيجة أنّ الرمز الموعود في §4.4 و§8.1 لا يصل،
    // وأنّ النصّ إنجليزيّ بينما كلّ رسائل المنصّة عربية.
    //
    // الاختبار يوثّق الواقع لا الوعد: يوم يُصلَح الخادم يسقط هذان السطران
    // فيُنبَّه من يقرأ — وهو أفضل من اختبار يمرّ على الحالتين بلا أن يقول.
    expect(losers.single.code, ApiErrorCode.conflict,
        reason: 'الخادم لا يرسل code على هذا المسار — راجع ApiException');
    expect(losers.single.requestId, isNull,
        reason: 'ولا request_id، للسبب نفسه');

    for (final (owner, ride) in [(customer, first), (other, second)]) {
      try {
        await owner.rides.cancelTrip(ride.id, reason: 'اختبار');
      } on ApiException {
        await owner.rides.cancel(ride.id).catchError((_) {});
      }
    }
  });
}
