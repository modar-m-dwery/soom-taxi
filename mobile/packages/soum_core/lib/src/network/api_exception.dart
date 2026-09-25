/// شكل الخطأ الموحّد.
///
/// دليل التكامل يَعِد بأنّ لكلّ خطأ في المنصّة شكلًا واحدًا:
///
///     {"detail": "...", "code": "...", "request_id": "...", "fields": {...}}
///
/// والوعد صحيح في معظم المسارات، لكن ليس فيها كلّها: ‏`GET /trips/999999/`
/// على خادم يعمل يعود `{"detail": "Trip not found."}` بلا `code` ولا
/// `request_id`. طُبقةٌ تفترض وجود `code` دائمًا تنهار على هذا الردّ
/// تحديدًا — وهو ردٌّ سيقابله كلّ مستخدم يفتح رابطًا قديمًا.
///
/// لذلك: الرمز يُقرأ من الجسم إن وُجد، ويُشتقّ من حالة HTTP إن غاب. النتيجة
/// أنّ الشيفرة أعلى هذه الطبقة تتفرّع على `code` دائمًا ولا تفحص `null`.
library;

import 'dart:io';

import 'package:dio/dio.dart';

/// الرموز التي تغيّر شاشةً فعلًا.
///
/// ليست كلّ رموز الخادم — بل ما يقابله سلوك مرئيّ محدّد في التطبيق. وما
/// عداها يُعرض بـ`detail` كما هو.
abstract final class ApiErrorCode {
  // تحقّق
  static const validationError = 'validation_error';

  // الطلب
  static const rideInvalid = 'ride.invalid';
  static const rideNotSearching = 'ride.not_searching';

  // المزاد
  static const offerExpired = 'offer.expired';
  static const driverUnavailable = 'driver.unavailable';

  // السائق
  static const driverNotEligible = 'driver.not_eligible';

  // الدعوة
  static const invitationExpired = 'invitation.expired';
  static const invitationParallelLimit = 'invitation.parallel_limit';
  static const invitationCooldown = 'invitation.cooldown';

  // الرحلة
  static const tripNotArrived = 'trip.not_arrived';
  static const tripNotStarted = 'trip.not_started';
  static const tripForbidden = 'trip.forbidden';

  // التقييم
  static const ratingDuplicate = 'rating.duplicate';

  // الخرائط
  static const routingUnavailable = 'routing.unavailable';

  // عامّة
  static const unauthenticated = 'unauthenticated';
  static const forbidden = 'forbidden';
  static const notFound = 'not_found';
  static const conflict = 'conflict';
  static const throttled = 'throttled';
  static const serverError = 'server_error';

  /// ليس من الخادم: انقطاع شبكة أو مهلة. مذكور هنا ليتفرّع عليه التطبيق
  /// كما يتفرّع على أيّ رمز آخر، فلا يصير للانقطاع مسارُ معالجة ثانٍ.
  static const networkUnavailable = 'network.unavailable';
}

/// خطأٌ من الخادم أو من الشبكة، بشكل واحد في الحالتين.
class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    required this.code,
    required this.detail,
    this.requestId,
    this.fields = const {},
    this.retryAfter,
  });

  /// حالة HTTP. صفر يعني أنّ الطلب لم يصل إلى الخادم أصلًا.
  final int statusCode;

  /// الرمز الذي تتفرّع عليه الشيفرة. لا يكون فارغًا أبدًا: يُشتقّ من الحالة
  /// حين لا يرسله الخادم.
  final String code;

  /// النصّ المعروض للمستخدم — بالعربية كما يرسله الخادم.
  final String detail;

  /// للدعم الفنّي. غائب في بعض الردود.
  final String? requestId;

  /// أخطاء الحقول في `validation_error`: اسم الحقل ← رسائله.
  final Map<String, List<String>> fields;

  /// ثوانٍ يجب انتظارها قبل إعادة المحاولة. تأتي مع 429 وحدها.
  final Duration? retryAfter;

  bool get isNetwork => code == ApiErrorCode.networkUnavailable;

  bool get isThrottled => code == ApiErrorCode.throttled;

  bool get isValidation => code == ApiErrorCode.validationError;

  /// سائقٌ سبق إليه غيرك — §4.4.
  ///
  /// الفحص على الحالة لا على الرمز وحده. السبب مقيس على خادم يعمل:
  /// ‏`CustomerSelectOfferView` تلتقط `MatchingError` بنفسها وتعيد
  /// `{"detail": str(exc)}` مباشرةً، فتتجاوز معالج الأخطاء الذي كان
  /// سيُلحق `code` و`request_id`. والنتيجة أنّ 409 على هذا المسار يصل
  /// بلا رمز — بينما §4.4 و§8.1 يَعِدان بـ`driver.unavailable`.
  ///
  /// تطبيقٌ يتفرّع على الرمز وحده هنا يسقط في `else` العامّ، فيعرض شاشة
  /// خطأ بدل قائمة محدَّثة — وهو بالضبط ما تحذّر منه الوثيقة.
  bool get isDriverTaken =>
      statusCode == 409 || code == ApiErrorCode.driverUnavailable;

  /// أوّل رسالة لحقل بعينه — لعرضها تحت الحقل في النموذج.
  String? fieldError(String name) {
    final messages = fields[name];
    if (messages == null || messages.isEmpty) return null;
    return messages.first;
  }

  // ---------------------------------------------------------------
  // البناء من استجابة
  // ---------------------------------------------------------------

  factory ApiException.fromDio(DioException error) {
    final response = error.response;

    if (response == null) {
      return ApiException(
        statusCode: 0,
        code: ApiErrorCode.networkUnavailable,
        detail: _networkDetail(error.type),
      );
    }

    final status = response.statusCode ?? 0;
    final body = response.data;
    final map = body is Map ? body.cast<String, dynamic>() : const <String, dynamic>{};

    return ApiException(
      statusCode: status,
      code: _readCode(map, status),
      detail: _readDetail(map, status),
      requestId: map['request_id'] as String?,
      fields: _readFields(map),
      retryAfter: _readRetryAfter(map, response.headers),
    );
  }

  /// الرمز من الجسم، وإلّا مشتقًّا من الحالة.
  ///
  /// الاشتقاق ليس تجميلًا: ردّ 404 بلا `code` هو ردٌّ حقيقيّ من هذا الخادم،
  /// وتركُ الرمز فارغًا يعني أنّ كلّ موضع تفرّع في التطبيق يحتاج فحص null.
  static String _readCode(Map<String, dynamic> body, int status) {
    final raw = body['code'];
    if (raw is String && raw.isNotEmpty) return raw;

    return switch (status) {
      400 => ApiErrorCode.validationError,
      401 => ApiErrorCode.unauthenticated,
      403 => ApiErrorCode.forbidden,
      404 => ApiErrorCode.notFound,
      409 => ApiErrorCode.conflict,
      429 => ApiErrorCode.throttled,
      >= 500 => ApiErrorCode.serverError,
      _ => 'http_$status',
    };
  }

  static String _readDetail(Map<String, dynamic> body, int status) {
    final raw = body['detail'];
    if (raw is String && raw.isNotEmpty) return raw;
    return 'تعذّر إتمام الطلب (رمز $status).';
  }

  static Map<String, List<String>> _readFields(Map<String, dynamic> body) {
    final raw = body['fields'];
    if (raw is! Map) return const {};

    final out = <String, List<String>>{};
    raw.forEach((key, value) {
      if (value is List) {
        out['$key'] = value.map((e) => '$e').toList(growable: false);
      } else if (value != null) {
        out['$key'] = ['$value'];
      }
    });
    return out;
  }

  /// المدّة من الجسم أوّلًا ثمّ من الترويسة.
  ///
  /// الخادم يضعها في `retry_after` داخل الجسم، وDRF يضع `Retry-After` في
  /// الترويسة. قراءة الاثنتين تعني أنّ عدّاد الواجهة يعمل أيًّا كان المصدر.
  static Duration? _readRetryAfter(Map<String, dynamic> body, Headers headers) {
    final fromBody = body['retry_after'];
    final seconds = switch (fromBody) {
      final int value => value,
      final double value => value.ceil(),
      final String value => int.tryParse(value),
      _ => null,
    };
    if (seconds != null && seconds > 0) return Duration(seconds: seconds);

    final header = headers.value(HttpHeaders.retryAfterHeader);
    final parsed = header == null ? null : int.tryParse(header.trim());
    if (parsed != null && parsed > 0) return Duration(seconds: parsed);

    return null;
  }

  static String _networkDetail(DioExceptionType type) => switch (type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.sendTimeout ||
        DioExceptionType.receiveTimeout =>
          'الخادم لم يستجب. تحقّق من اتصالك ثمّ أعد المحاولة.',
        DioExceptionType.cancel => 'أُلغي الطلب.',
        _ => 'لا اتصال بالإنترنت.',
      };

  @override
  String toString() =>
      'ApiException($statusCode, $code, "$detail"'
      '${requestId == null ? '' : ', req=$requestId'})';
}
