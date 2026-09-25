// T1.1 — «اختبار يثبت أنّ 400 و403 و404 و409 و429 و503 تُحوَّل كلّها إلى
// الشكل نفسه بلا فقدان حقل».
//
// الحالة التي تبرّر هذا الملفّ: الخادم لا يلتزم شكلًا واحدًا في كلّ مسار.
// ‏`GET /trips/999999/` على خادم يعمل يعود {"detail": "Trip not found."}
// بلا `code`. طبقةٌ تفترض وجوده تنهار على ردٍّ يقابله كلّ مستخدم يفتح
// رابطًا قديمًا.

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

DioException _dio(int status, Object? body, {Map<String, List<String>>? headers}) {
  final options = RequestOptions(path: '/x/');
  return DioException(
    requestOptions: options,
    response: Response<dynamic>(
      requestOptions: options,
      statusCode: status,
      data: body,
      headers: Headers.fromMap(headers ?? const {}),
    ),
    type: DioExceptionType.badResponse,
  );
}

void main() {
  group('الشكل الموحّد', () {
    test('خطأ تحقّق يحتفظ بالحقول كلّها', () {
      final failure = ApiException.fromDio(_dio(400, {
        'detail': 'This field is required.',
        'code': 'validation_error',
        'request_id': '0ea67c2ce4cb',
        'fields': {
          'pickup_lat': ['This field is required.'],
          'mode': ['"nope" is not a valid choice.'],
        },
      }));

      expect(failure.statusCode, 400);
      expect(failure.code, ApiErrorCode.validationError);
      expect(failure.requestId, '0ea67c2ce4cb');
      expect(failure.isValidation, isTrue);
      expect(failure.fieldError('pickup_lat'), 'This field is required.');
      expect(failure.fieldError('mode'), contains('not a valid choice'));
      expect(failure.fieldError('غير_موجود'), isNull);
    });

    test('409 عند اختيار سائق سبق إليه غيرك', () {
      final failure = ApiException.fromDio(_dio(409, {
        'detail': 'هذه السيارة لم تعد متاحة.',
        'code': 'driver.unavailable',
        'request_id': 'abc123',
      }));

      expect(failure.code, ApiErrorCode.driverUnavailable);
      expect(failure.detail, 'هذه السيارة لم تعد متاحة.');
    });

    test('404 بلا code — يُشتقّ من الحالة ولا يبقى فارغًا', () {
      // هذا هو الردّ الحرفيّ من الخادم الحقيقي.
      final failure = ApiException.fromDio(_dio(404, {'detail': 'Trip not found.'}));

      expect(failure.code, ApiErrorCode.notFound);
      expect(failure.requestId, isNull);
      expect(failure.fields, isEmpty);
      expect(failure.detail, 'Trip not found.');
    });

    test('503 من مزوّد الخرائط', () {
      final failure = ApiException.fromDio(_dio(503, {
        'detail': 'تعذّر حساب المسار.',
        'code': 'routing.unavailable',
      }));
      expect(failure.code, ApiErrorCode.routingUnavailable);
    });

    test('جسم ليس خريطة لا يُسقط التحويل', () {
      final failure = ApiException.fromDio(_dio(500, '<html>502 Bad Gateway</html>'));
      expect(failure.code, ApiErrorCode.serverError);
      expect(failure.detail, contains('500'));
    });

    test('انقطاع الشبكة يأخذ الشكل نفسه', () {
      final failure = ApiException.fromDio(DioException(
        requestOptions: RequestOptions(path: '/x/'),
        type: DioExceptionType.connectionError,
      ));

      expect(failure.statusCode, 0);
      expect(failure.code, ApiErrorCode.networkUnavailable);
      expect(failure.isNetwork, isTrue);
      expect(failure.detail, isNotEmpty);
    });
  });

  group('retry_after', () {
    test('يُقرأ من الجسم', () {
      final failure = ApiException.fromDio(_dio(429, {
        'detail': 'تجاوزت الحدّ.',
        'code': 'throttled',
        'retry_after': 42,
      }));
      expect(failure.isThrottled, isTrue);
      expect(failure.retryAfter, const Duration(seconds: 42));
    });

    test('يُقرأ من الترويسة حين يغيب من الجسم', () {
      final failure = ApiException.fromDio(_dio(
        429,
        {'detail': 'تجاوزت الحدّ.'},
        headers: {'retry-after': ['17']},
      ));
      expect(failure.code, ApiErrorCode.throttled);
      expect(failure.retryAfter, const Duration(seconds: 17));
    });

    test('يغيب من الاثنين فيبقى null — والحارس هو من يقرّر الافتراض', () {
      final failure = ApiException.fromDio(_dio(429, {'detail': 'تجاوزت الحدّ.'}));
      expect(failure.retryAfter, isNull);
    });
  });
}
