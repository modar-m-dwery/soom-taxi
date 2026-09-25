// T1.4 — «فحص آليّ يسقط البناء إن ظهر double في أيّ حقل ماليّ».
//
// وأكثر منه: هذا الملفّ يقارن النماذج المكتوبة يدويًّا بمخطّط OpenAPI
// المسحوب من الخادم نفسه. الفائدة ليست التوثيق بل الإنذار: حقلٌ يُعاد
// تسميته في الخادم يصير **فشلَ اختبار** هنا، لا شاشةً فارغة عند مستخدم
// بعد أسبوعين.
//
// المخطّط في contract/openapi.json يُحدَّث بنداء واحد:
//   curl -s http://<host>/api/schema/?format=json -o openapi.json

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

/// الحقول المالية في هذا الخادم: ‏`DecimalField` يخرج نصًّا عشريًّا.
const _moneyFields = {
  'base_fare',
  'distance_fare',
  'time_fare',
  'gross_fare',
  'platform_fee',
  'customer_total',
  'driver_net',
  'fare_floor',
  'fare_cap',
  'final_fare',
  'quoted_fare',
  'counter_fare',
  'amount',
  'amount_refunded',
  'refundable_amount',
  'price_per_seat',
};

Map<String, dynamic> _schema(Map<String, dynamic> spec, String name) {
  final schemas = spec['components']['schemas'] as Map<String, dynamic>;
  expect(schemas.containsKey(name), isTrue,
      reason: 'المخطّط لا يحوي $name — تغيّر اسمه في الخادم؟');
  return (schemas[name] as Map<String, dynamic>)['properties']
      as Map<String, dynamic>;
}

/// الحقول التي يقرأها النموذج فعلًا — تُستخرج من مصدره.
Set<String> _readKeys(String modelPath) {
  final source = File('lib/src/models/$modelPath').readAsStringSync();
  final pattern = RegExp(r"""read\w+\(\s*json\s*,\s*'([^']+)'""");
  return pattern.allMatches(source).map((m) => m.group(1)!).toSet()
    ..addAll(RegExp(r"""fromFields\(json,\s*'([^']+)'\)""")
        .allMatches(source)
        .expand((m) => ['${m.group(1)}_lat', '${m.group(1)}_lng']));
}

void main() {
  late Map<String, dynamic> spec;

  setUpAll(() {
    final file = File('test/contract/openapi.json');
    expect(file.existsSync(), isTrue,
        reason: 'المخطّط مفقود — اسحبه من /api/schema/');
    spec = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
  });

  // 82 نقطة في التسليم، ثمّ خمس أُضيفت في 2026-09-20: الإحالة (2)،
  // اشتراكات الصباح (3). الرقم يُحدَّث عمدًا لا آليًّا: نقطة تختفي يجب أن تُرى.
  test('المخطّط يحمل النقاط الاثنتين والتسعين (+ إلغاء السائق، الحوافز، الإعلانات)', () {
    final paths = spec['paths'] as Map<String, dynamic>;
    final operations = paths.values
        .cast<Map<String, dynamic>>()
        .expand((p) => p.keys)
        .where((m) => const {'get', 'post', 'put', 'patch', 'delete'}.contains(m))
        .length;

    expect(operations, 92);
  });

  group('النماذج تطابق المخطّط', () {
    void check(String schemaName, String modelPath, {Set<String> skip = const {}}) {
      test(schemaName, () {
        final properties = _schema(spec, schemaName);
        final read = _readKeys(modelPath);
        final missing = read.difference(properties.keys.toSet()).difference(skip);

        expect(missing, isEmpty,
            reason: 'النموذج يقرأ حقولًا لا وجود لها في $schemaName: $missing');
      });
    }

    check('RideRequest', 'ride.dart');
    check('RideOffer', 'offer.dart');
    // `invitation_id` مفتاح حدث المقبس لا مخطّط REST — مقروءٌ عمدًا (العيب #34).
    check('RideInvitation', 'invitation.dart', skip: {'invitation_id'});
    check('Trip', 'trip.dart');
    check('Payment', 'payment.dart');
    check('NearbyVehicle', 'nearby_vehicle.dart', skip: {'lat', 'lng'});
    check('User', 'user.dart');
    check('Vehicle', 'vehicle.dart', skip: {'plate_number'});
    check('ActiveRideSnapshot', 'active_ride.dart',
        skip: {'ride_room', 'driver_room'});
    check('RideSubscription', 'subscription.dart');
    check('Referral', 'referral.dart');
  });

  group('رموز التعدادات موجودة في المخطّط', () {
    // كلّ رمز يرسله التطبيق أو يقرؤه يجب أن يكون قيمةً يعرفها الخادم.
    // `unknown` احتياطُ العميل لقيمةٍ جديدة، و`expired` للوثائق يحسبه
    // العميل من expires_at — فلا يُطلبان من المخطّط.
    void check(String schemaName, List<Enum> values, String Function(Enum) code,
        {Set<String> clientOnly = const {'unknown'}}) {
      test(schemaName, () {
        final schemas = spec['components']['schemas'] as Map<String, dynamic>;
        expect(schemas.containsKey(schemaName), isTrue,
            reason: 'المخطّط لا يحوي $schemaName — تغيّر اسمه في الخادم؟');
        final schema = schemas[schemaName] as Map<String, dynamic>;
        final allowed = (schema['enum'] as List).cast<String>().toSet();
        final ours = values.map(code).toSet().difference(clientOnly);
        final bogus = ours.difference(allowed);

        expect(bogus, isEmpty,
            reason: 'التطبيق يستعمل رموزًا لا يعرفها $schemaName: $bogus');
      });
    }

    check('RideModeEnum', RideMode.values, (e) => (e as RideMode).code);
    check('TripCategoryEnum', TripCategory.values,
        (e) => (e as TripCategory).code);
    check('RideStatusEnum', RideStatus.values, (e) => (e as RideStatus).code);
    check('OfferStatusEnum', OfferStatus.values,
        (e) => (e as OfferStatus).code);
    check('InvitationStatusEnum', InvitationStatus.values,
        (e) => (e as InvitationStatus).code);
    check('TripStatusEnum', TripStatus.values, (e) => (e as TripStatus).code);
    check('PaymentStatusEnum', PaymentStatus.values,
        (e) => (e as PaymentStatus).code);
    check('UserRoleEnum', UserRole.values, (e) => (e as UserRole).code);
    check('DocumentTypeEnum', DriverDocumentType.values,
        (e) => (e as DriverDocumentType).code, clientOnly: const {});
    check('DocumentStatusEnum', DocumentStatus.values,
        (e) => (e as DocumentStatus).code,
        clientOnly: const {'unknown', 'expired'});
    check('CancelReasonEnum', CancelReason.values,
        (e) => (e as CancelReason).code, clientOnly: const {});

    // الاتجاه المعاكس لأسباب الإلغاء وحدها: التطبيق يعرض قائمةً ثابتة،
    // فسببٌ يضيفه الخادم ولا يعرفه التطبيق لا يختاره زبونٌ أبدًا.
    test('CancelReasonEnum ← كلّ رموز الخادم معروضة', () {
      final schemas = spec['components']['schemas'] as Map<String, dynamic>;
      final allowed = ((schemas['CancelReasonEnum'] as Map<String, dynamic>)
              ['enum'] as List)
          .cast<String>()
          .toSet();
      final ours = CancelReason.values.map((e) => e.code).toSet();
      expect(allowed.difference(ours), isEmpty,
          reason: 'أسبابٌ في الخادم لا يعرضها التطبيق');
    });
  });

  group('أجسام الطلبات تطابق المخطّط', () {
    // ما يُرسَل لا ما يُقرأ: مفتاحٌ خاطئ في جسم POST يردّه الخادم بـ400
    // ولا يلتقطه فحص النماذج أعلاه. عُثر عليه في التقييم: `rating` بدل
    // `score`، فكان كلّ تقييم يفشل بصمت.
    Set<String> bodyKeys(String apiPath, String route) {
      final source = File('lib/src/api/$apiPath').readAsStringSync();
      final start = source.indexOf(route);
      expect(start, greaterThan(-1), reason: 'المسار $route غير موجود في $apiPath');
      final open = source.indexOf('body: {', start);
      final close = source.indexOf('})', open);
      final body = source.substring(open, close);
      return RegExp(r"'([a-z_]+)':")
          .allMatches(body)
          .map((m) => m.group(1)!)
          .toSet();
    }

    void check(String schemaName, String apiPath, String route) {
      test('$route ← $schemaName', () {
        final schemas = spec['components']['schemas'] as Map<String, dynamic>;
        expect(schemas.containsKey(schemaName), isTrue,
            reason: 'المخطّط لا يحوي $schemaName');
        final allowed =
            ((schemas[schemaName] as Map<String, dynamic>)['properties']
                    as Map<String, dynamic>)
                .keys
                .toSet();
        final bogus = bodyKeys(apiPath, route).difference(allowed);
        expect(bogus, isEmpty,
            reason: 'الجسم يحمل مفاتيح لا يعرفها $schemaName: $bogus');
      });
    }

    check('SubmitRatingRequest', 'feedback_api.dart', '/rate/');
    check('OpenComplaintRequest', 'feedback_api.dart', "'/complaints/', body");
    check('RideSubscriptionRequest', 'rides_api.dart', "'/rides/subscriptions/', body");
    check('ApplyReferralCodeRequest', 'payments_api.dart', 'applyReferralCode');

    // الإلغاءان يبنيان جسمهما في دالّة واحدة — `_cancelBody`.
    test('_cancelBody ← CancelTripRequest', () {
      final source = File('lib/src/api/rides_api.dart').readAsStringSync();
      final start = source.indexOf('static Json _cancelBody(');
      expect(start, greaterThan(-1));
      final body = source.substring(start, source.indexOf('};', start));
      final keys = RegExp(r"'([a-z_]+)':")
          .allMatches(body)
          .map((m) => m.group(1)!)
          .toSet();
      expect(keys, containsAll(['reason', 'reason_code']));

      final schemas = spec['components']['schemas'] as Map<String, dynamic>;
      final allowed =
          ((schemas['CancelTripRequest'] as Map<String, dynamic>)['properties']
                  as Map<String, dynamic>)
              .keys
              .toSet();
      expect(keys.difference(allowed), isEmpty);
    });
  });

  group('معاملات الاستعلام تطابق المخطّط', () {
    // GET بمعاملات باسمٍ خاطئ يُردّ 400 مثل جسم POST الخاطئ. عُثر عليه في
    // `/maps/route/`: `origin_*` بدل `pickup_*`، فلا مسار يُرسم قبل الطلب.
    void check(String path, String apiPath, String route) {
      test(route, () {
        final paths = spec['paths'] as Map<String, dynamic>;
        expect(paths.containsKey(path), isTrue, reason: 'المسار $path غائب');
        final params = ((paths[path] as Map<String, dynamic>)['get']
                as Map<String, dynamic>)['parameters'] as List? ?? const [];
        final allowed = params
            .cast<Map<String, dynamic>>()
            .where((p) => p['in'] == 'query')
            .map((p) => p['name'] as String)
            .toSet();

        final source = File('lib/src/api/$apiPath').readAsStringSync();
        final start = source.indexOf(route);
        expect(start, greaterThan(-1));
        final open = source.indexOf('query: {', start);
        final close = source.indexOf('}', open);
        final used = RegExp(r"'([a-z_]+)':")
            .allMatches(source.substring(open, close))
            .map((m) => m.group(1)!)
            .toSet();

        expect(used.difference(allowed), isEmpty,
            reason: 'معاملات لا يعرفها $path: ${used.difference(allowed)}');
      });
    }

    check('/api/v1/maps/route/', 'maps_api.dart', "'/maps/route/'");
  });

  group('حقول الأجرة المطلوبة موجودة كلّها', () {
    test('RideRequest يحمل تفصيل الأجرة الكامل', () {
      final properties = _schema(spec, 'RideRequest');
      for (final field in [
        'base_fare',
        'distance_fare',
        'time_fare',
        'gross_fare',
        'platform_fee',
        'customer_total',
        'driver_net',
        'currency',
        'surge_multiplier',
        'route_source',
      ]) {
        expect(properties.containsKey(field), isTrue, reason: 'ينقص $field');
      }
    });
  });

  group('المال ليس عائمًا', () {
    test('كلّ حقل ماليّ في المخطّط نصّ عشريّ لا رقم', () {
      final schemas = spec['components']['schemas'] as Map<String, dynamic>;
      final offenders = <String>[];

      schemas.forEach((name, schema) {
        final properties =
            (schema as Map<String, dynamic>)['properties'] as Map<String, dynamic>?;
        if (properties == null) return;

        properties.forEach((field, definition) {
          if (!_moneyFields.contains(field)) return;
          final type = (definition as Map<String, dynamic>)['type'];
          if (type == 'number' || type == 'integer') {
            offenders.add('$name.$field ($type)');
          }
        });
      });

      expect(offenders, isEmpty,
          reason: 'حقول مالية رقمية في المخطّط: $offenders');
    });

    test('لا حقل ماليّ في الشيفرة نوعه double', () {
      final offenders = <String>[];

      for (final file in Directory('lib/src')
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'))) {
        for (final line in file.readAsLinesSync()) {
          final match = RegExp(r'final\s+(double|num)\??\s+(\w+);').firstMatch(line);
          if (match == null) continue;

          final name = match.group(2)!.toLowerCase();
          if (name.contains('fare') ||
              name.contains('amount') ||
              name.contains('price') ||
              name.contains('total') ||
              name.contains('balance')) {
            offenders.add('${file.path}: ${line.trim()}');
          }
        }
      }

      expect(offenders, isEmpty, reason: 'حقول مالية عائمة: $offenders');
    });

    test('نموذج الأجرة يبني كلّ مكوّناته Money', () {
      final fare = FareBreakdown.fromJson(const {
        'base_fare': '4000.00',
        'distance_fare': '1272.00',
        'time_fare': '240.00',
        'gross_fare': '5512.00',
        'platform_fee': '0.00',
        'customer_total': '5512.00',
        'driver_net': '5512.00',
        'currency': 'SYP',
        'surge_multiplier': '1.00',
      });

      // المجموع يطابق الإجمالي خانةً بخانة — وهذا ما يفشل بـdouble.
      final sum = fare.baseFare + fare.distanceFare + fare.timeFare;
      expect(sum.toApi(), fare.grossFare.toApi());

      // عمولة صفر: ما يدفعه الزبون = ما يقبضه السائق.
      expect(fare.platformFee.isZero, isTrue);
      expect(fare.customerTotal, fare.driverNet);
      expect(fare.hasSurge, isFalse);
    });
  });

  group('حدود معمارية', () {
    test('الطبقة المشتركة لا ترسم شيئًا', () {
      final offenders = <String>[];

      for (final file in Directory('lib/src')
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'))) {
        final source = file.readAsStringSync();
        if (source.contains("package:flutter/material.dart") ||
            source.contains("package:flutter/widgets.dart") ||
            source.contains("package:flutter/cupertino.dart")) {
          offenders.add(file.path);
        }
      }

      expect(offenders, isEmpty,
          reason: 'استيراد واجهة في حزمة العقد — خطأ معماريّ: $offenders');
    });

    test('غرف البثّ لا تُبنى في العميل', () {
      // المسارات تأتي من /me/active-ride/ تحت realtime. بناؤها هنا يعني
      // أنّ تغييرًا في مسارات الخادم يتطلّب إصدارًا على المتجر.
      final source = File('lib/src/soum.dart').readAsStringSync();
      expect(source.contains("'/ws/rides/"), isFalse,
          reason: 'مسار غرفة رحلة مبنيّ في العميل');
      expect(source.contains("'/ws/driver/"), isFalse,
          reason: 'مسار غرفة سائق مبنيّ في العميل');
    });
  });
}
