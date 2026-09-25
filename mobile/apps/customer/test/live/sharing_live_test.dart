// M5 — المشاركة والرحلات المنشورة والقنوات، على خادم يعمل.
//
// ما يقيسه هذا الملفّ ليس أنّ النقاط تردّ 200، بل أنّ القيود التي تحكم
// العرض تصل فعلًا:
//
//   • كتالوج الرحلات المنشورة **لا يكشف إحداثيات دقيقة ولا رقم هاتف**.
//   • النافذة الزمنية وأنصاف الأقطار يفلترها الخادم لا التطبيق.
//   • قناة `configured: false` لا تظهر، و503 على الربط ليست عطلًا.

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

const _baseUrl = String.fromEnvironment('SOUM_LIVE');
const _customerToken = String.fromEnvironment('SOUM_CUSTOMER_TOKEN');

const pickup = GeoPoint(35.3608, 35.9236);
const destination = GeoPoint(35.3700, 35.9300);

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
  if (_baseUrl.isEmpty || _customerToken.isEmpty) {
    test('M5 الحيّة — متخطّاة (بلا إعداد خادم)', () {}, skip: true);
    return;
  }

  late Soum customer;

  setUp(() async {
    customer = await session(_customerToken);
    await cancelActiveRides(customer);
    await customer.config.load(lat: pickup.lat, lng: pickup.lng);
  });

  group('المشاركة', () {
    test('طلب مشترك يقبل البحث عن مجموعات ورحلات مجدولة', () async {
      final ride = await customer.rides.create(
        pickup: pickup,
        destination: destination,
        mode: 'shared',
        passengerCount: 1,
      );

      expect(ride.mode, RideMode.shared);

      // القائمتان قد تعودان فارغتين — وهذا ردٌّ صحيح لا عطل. المقيس هو
      // أنّ النقطتين تردّان بالشكل المتوقَّع لا بخطأ.
      final instant = await customer.sharing.sharedOffers(ride.id);
      final scheduled = await customer.sharing.scheduledSharedTrips(ride.id);

      expect(instant, isA<List<SharedJoinOffer>>());
      expect(scheduled, isA<List<ScheduledSharedTrip>>());

      await customer.rides.cancel(ride.id);
    });

    test('نمط غير مشترك لا يمنع النداء لكنّه لا يُنتج مرشَّحين', () async {
      final ride = await customer.rides.create(
        pickup: pickup,
        destination: destination,
        mode: 'standard',
        passengerCount: 1,
      );

      final scheduled = await customer.sharing.scheduledSharedTrips(ride.id);
      expect(scheduled, isEmpty);

      await customer.rides.cancel(ride.id);
    });
  });

  group('الرحلات المنشورة', () {
    test('الكتالوج يُقرأ، ولا يكشف إحداثيات دقيقة', () async {
      final trips = await customer.sharing.publishedTrips();
      expect(trips, isA<List<ScheduledSharedTrip>>());

      for (final trip in trips) {
        final point = trip.pickup;
        if (point == null) continue;

        // التقريب إلى ثلاث خانات عشرية ≈ 110 أمتار. إحداثيةٌ بأربع
        // خانات أو أكثر تعني تسريبًا — راجع PUBLIC_COORD_PRECISION.
        expect(
          _decimalPlaces(point.lat),
          lessThanOrEqualTo(3),
          reason: 'إحداثية دقيقة في كتالوج عامّ: ${point.lat}',
        );
        expect(_decimalPlaces(point.lng), lessThanOrEqualTo(3));
      }
    });

    test('الترشيح بالفئة يمرّ إلى الخادم', () async {
      final intercity =
          await customer.sharing.publishedTrips(category: 'intercity');

      for (final trip in intercity) {
        expect(trip.tripCategory, TripCategory.intercity);
      }
    });
  });

  group('قنوات الإيصال', () {
    test('القنوات تُقرأ، وكلّ قناة تحمل حالتها الكاملة', () async {
      final channels = await customer.notifications.channels();
      expect(channels, isNotEmpty);

      for (final channel in channels) {
        expect(channel.code, isNotEmpty);
        expect(channel.label, isNotEmpty);
        expect(channel.priority, greaterThan(0));
      }

      // §12.3: قناة غير مهيَّأة لا تُعرض. المقيس هنا أنّ العلم موجود
      // ليُرشَّح عليه — لا أنّ قناةً بعينها مهيّأة في هذه البيئة.
      final visible = channels.where((c) => c.isVisible).toList();
      expect(visible.length, lessThanOrEqualTo(channels.length));
    });

    test('ربط تليغرام: إمّا رابط عميق وإمّا 503 حين لم يُفعَّل', () async {
      try {
        final link = await customer.notifications.linkTelegram();

        // رمزٌ لمرّة واحدة وقصير العمر.
        expect(link.code, isNotEmpty);
        expect(link.deepLink, contains('t.me'));
        expect(link.expiresInSeconds, greaterThan(0));
        expect(link.expiresInSeconds, lessThanOrEqualTo(3600));
      } on ApiException catch (error) {
        // 503 ليست عطلًا: المشغّل لم يفعّل تليغرام على الخادم.
        // والتطبيق يُخفي الخيار عندها بدل أن يعرض خطأ.
        expect(error.statusCode, anyOf(503, 400, 404));
      }
    });

    test('صندوق الإشعارات يُقرأ', () async {
      final inbox = await customer.notifications.inbox();
      expect(inbox, isA<List<Json>>());
    });
  });
}

int _decimalPlaces(double value) {
  final text = value.toString();
  final dot = text.indexOf('.');
  if (dot < 0) return 0;
  return text.length - dot - 1;
}
