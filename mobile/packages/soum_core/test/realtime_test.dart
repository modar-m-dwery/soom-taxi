// T1.6 و T1.7 — الأشكال الثلاثة وحارس الترتيب.
//
// الأشكال في هذا الملفّ ليست مخترَعة: كلّ إطار هنا منسوخ حرفيًّا من جلسة
// حقيقية على الخادم — طلبٌ أُنشئ، وغرفة اشتُرك بها، وسائقٌ قدّم عرضًا
// فقُبل. الاختبار الذي يقيس شكلًا متخيَّلًا يمرّ ولا يثبت شيئًا.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  group('الأشكال الثلاثة على السلك', () {
    test('اللقطة — النسخة في المستوى الأعلى', () {
      final events = RealtimeEvent.parse({
        'event_type': 'ride.snapshot',
        'entity_type': 'ride',
        'entity_id': 2,
        'version': 0,
        'payload': {
          'ride': {'id': 2, 'status': 'searching'},
          'offers': <dynamic>[],
        },
      });

      expect(events, hasLength(1));
      final event = events.single;
      expect(event.type, RealtimeEventType.rideSnapshot);
      expect(event.isSnapshot, isTrue);
      expect(event.version, 0);
      expect(event.entityType, 'ride');
      expect(event.entityId, 2);
      expect(event.data['ride'], isA<Map>());
    });

    test('حدث أعمال — النسخة داخل payload، والبيانات تحت data', () {
      final events = RealtimeEvent.parse({
        'event_type': 'offer.created',
        'payload': {
          'event_id': '58d7b4ec-519d-4b7d-b4db-aa8516a3555f',
          'entity_type': 'ride',
          'entity_id': 2,
          'version': 1,
          'timestamp': 1789419137.7851727,
          'data': {
            'id': 1,
            'ride': 2,
            'gross_fare': '6000.00',
            'eta_minutes': 4,
            'status': 'pending',
          },
        },
      });

      final event = events.single;
      expect(event.type, RealtimeEventType.offerCreated);
      expect(event.version, 1, reason: 'قراءتها من المستوى الأعلى تعطي null');
      expect(event.entityId, 2);
      expect(event.eventId, isNotNull);
      expect(event.timestamp, isNotNull);

      // البيانات وصلت بعد فكّ المستوى الإضافي.
      final offer = RideOffer.fromJson(event.data);
      expect(offer.id, 1);
      expect(offer.grossFare.toApi(), '6000.00');
      expect(offer.etaMinutes, 4);
    });

    test('حدث زائل — بلا نسخة، ولا يُفترض له صفر', () {
      final event = RealtimeEvent.parse({
        'event_type': 'driver.location',
        'payload': {'lat': 35.361, 'lng': 35.924, 'driver_id': 1},
      }).single;

      expect(event.type, RealtimeEventType.driverLocation);
      expect(event.version, isNull);
      expect(event.isVersioned, isFalse);
      expect(event.data['lat'], 35.361);
    });

    test('رسالة تحكّم تحتفظ بحقولها في المستوى الأعلى', () {
      final event = RealtimeEvent.parse({
        'event_type': 'connection.established',
        'group': 'ride_2',
      }).single;

      expect(event.isConnectionEstablished, isTrue);
      expect(event.data['group'], 'ride_2');
    });

    test('ردّ اللحاق يُفكّ إلى أحداث، ومفتاح بياناتها payload لا data', () {
      final events = RealtimeEvent.parse({
        'event_type': 'ride.resync',
        'events': [
          {
            'event_id': 'a',
            'event_type': 'offer.created',
            'entity_type': 'ride',
            'entity_id': 2,
            'version': 3,
            'timestamp': 1789419137.0,
            'payload': {'id': 7, 'gross_fare': '5000.00'},
          },
          {
            'event_id': 'b',
            'event_type': 'offer.expired',
            'entity_type': 'ride',
            'entity_id': 2,
            'version': 4,
            'timestamp': 1789419140.0,
            'payload': {'id': 7},
          },
        ],
      });

      expect(events, hasLength(2));
      expect(events[0].version, 3);
      expect(events[0].data['gross_fare'], '5000.00');
      expect(events[1].type, RealtimeEventType.offerExpired);
      expect(events[1].version, 4);
    });

    test('إطار بلا event_type يُهمَل بلا انهيار', () {
      expect(RealtimeEvent.parse({'payload': {}}), isEmpty);
    });
  });

  group('حارس الترتيب', () {
    RealtimeEvent versioned(String type, int version) => RealtimeEvent.parse({
          'event_type': type,
          'payload': {
            'entity_type': 'ride',
            'entity_id': 2,
            'version': version,
            'data': <String, dynamic>{},
          },
        }).single;

    test('1‑3‑2‑5: يتجاهل المتأخّر، ويطلب اللحاق مرّتين بالضبط', () {
      final guard = VersionGuard();
      final verdicts = <VersionVerdict>[];

      for (final version in [1, 3, 2, 5]) {
        verdicts.add(guard.inspect(versioned('offer.created', version)));
      }

      expect(verdicts, [
        VersionVerdict.accept, // 1 — أوّل حدث لهذا الكيان
        VersionVerdict.gap,    // 3 — فاتنا 2
        VersionVerdict.stale,  // 2 — وصل متأخّرًا بعد 3
        VersionVerdict.gap,    // 5 — فاتنا 4
      ]);

      expect(verdicts.where((v) => v == VersionVerdict.gap).length, 2);
      expect(guard.versionOf('ride', 2), 5);
    });

    test('التتابع الصحيح يُقبل كلّه', () {
      final guard = VersionGuard();
      for (final version in [1, 2, 3, 4]) {
        expect(guard.inspect(versioned('offer.created', version)),
            VersionVerdict.accept);
      }
    });

    test('اللقطة تعيد ضبط العدّاد مهما كانت قيمتها', () {
      final guard = VersionGuard();
      guard.inspect(versioned('offer.created', 40));
      expect(guard.versionOf('ride', 2), 40);

      // انقطاع طويل ثمّ عودة: Redis أُفرغ فعادت اللقطة برقم أقلّ.
      final snapshot = RealtimeEvent.parse({
        'event_type': 'ride.snapshot',
        'entity_type': 'ride',
        'entity_id': 2,
        'version': 3,
        'payload': <String, dynamic>{},
      }).single;

      expect(guard.inspect(snapshot), VersionVerdict.accept);
      expect(guard.versionOf('ride', 2), 3,
          reason: 'اللقطة مضمونة دائمًا، واللحاق ليس كذلك');
    });

    test('الأحداث الزائلة تمرّ دائمًا ولا تلمس العدّاد', () {
      final guard = VersionGuard();
      guard.inspect(versioned('offer.created', 5));

      final location = RealtimeEvent.parse({
        'event_type': 'driver.location',
        'payload': {'lat': 1.0, 'lng': 2.0},
      }).single;

      expect(guard.inspect(location), VersionVerdict.unversioned);
      expect(guard.versionOf('ride', 2), 5);
    });

    test('الكيانات مستقلّة — عدّاد لكلّ رحلة', () {
      final guard = VersionGuard();

      RealtimeEvent forRide(int rideId, int version) => RealtimeEvent.parse({
            'event_type': 'offer.created',
            'payload': {
              'entity_type': 'ride',
              'entity_id': rideId,
              'version': version,
              'data': <String, dynamic>{},
            },
          }).single;

      expect(guard.inspect(forRide(1, 9)), VersionVerdict.accept);
      expect(guard.inspect(forRide(2, 1)), VersionVerdict.accept,
          reason: 'رحلة أخرى، عدّاد آخر — لا فجوة');
      expect(guard.versionOf('ride', 1), 9);
      expect(guard.versionOf('ride', 2), 1);
    });

    test('reset يمحو كلّ العدّادات — عند تبديل المستخدم', () {
      final guard = VersionGuard();
      guard.inspect(versioned('offer.created', 7));
      guard.reset();
      expect(guard.versionOf('ride', 2), 0);
    });
  });
}
