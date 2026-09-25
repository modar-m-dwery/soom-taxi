/// حارس الحدود — §8.2 في دليل التكامل.
///
/// > الردّ 429 يحمل `retry_after` بالثواني. لا تعِد المحاولة فورًا — انتظر
/// > المدّة، واعرض عدّادًا. حلقة إعادة محاولة بلا انتظار تُبقي المستخدم
/// > محظورًا إلى ما لا نهاية.
///
/// السطر الأخير هو المهمّ: الخنق في هذا الخادم يُحتسب على نافذة زمنية، فكلّ
/// محاولة داخل النافذة تجدّدها. تطبيقٌ «يعيد المحاولة حتى ينجح» لا يتعافى
/// أبدًا — يحبس نفسه.
///
/// الحلّ هنا أنّ النداء الثاني لا يغادر الجهاز أصلًا: يُرفض محلّيًّا بالخطأ
/// نفسه وبالمدّة المتبقّية، فتبني الواجهة عدّادها من رقم صادق ولا تلمس
/// الخادم أثناء عقوبته.
///
/// والمدّة تُحفظ لكلّ مسار لا عالميًّا: حدّ طلب رمز OTP لا علاقة له بحدّ
/// حساب المسار، وخلطهما يقفل شاشةً بسبب أخرى.
library;

import 'package:dio/dio.dart';

import 'api_exception.dart';

class ThrottleGuard extends Interceptor {
  ThrottleGuard({DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final DateTime Function() _now;

  /// المسار ← أوّل لحظة يُسمح فيها بنداء جديد.
  final Map<String, DateTime> _blockedUntil = {};

  /// المدّة المتبقّية على مسار، أو null إن لم يكن محظورًا.
  /// تقرأها الواجهة لترسم عدّادًا بلا نداء.
  Duration? remainingFor(String path) {
    final until = _blockedUntil[_key(path)];
    if (until == null) return null;

    final left = until.difference(_now());
    if (left <= Duration.zero) {
      _blockedUntil.remove(_key(path));
      return null;
    }
    return left;
  }

  void clear() => _blockedUntil.clear();

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final left = remainingFor(options.path);

    if (left == null) {
      handler.next(options);
      return;
    }

    // نرفض محلّيًّا بالشكل نفسه الذي يرسله الخادم، فلا تحتاج الواجهة مسار
    // معالجة ثانيًا للحظر المحلّي.
    handler.reject(
      DioException(
        requestOptions: options,
        type: DioExceptionType.cancel,
        error: ApiException(
          statusCode: 429,
          code: ApiErrorCode.throttled,
          detail: 'تجاوزتَ الحدّ المسموح. أعد المحاولة بعد '
              '${left.inSeconds} ثانية.',
          retryAfter: left,
        ),
      ),
      true,
    );
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 429) {
      final failure = ApiException.fromDio(err);
      // بلا `retry_after` نفترض دقيقة: الخادم يخنق على نوافذ بالدقائق،
      // وصفرٌ هنا يعيدنا إلى الحلقة التي يحذّر منها الدليل.
      final wait = failure.retryAfter ?? const Duration(seconds: 60);
      _blockedUntil[_key(err.requestOptions.path)] = _now().add(wait);
    }
    handler.next(err);
  }

  /// المسار بلا معاملات استعلام ولا معرّفات — الحدّ يخصّ النقطة لا الصفّ.
  static String _key(String path) {
    final withoutQuery = path.split('?').first;
    return withoutQuery
        .split('/')
        .map((segment) => int.tryParse(segment) == null ? segment : '{id}')
        .join('/');
  }
}
