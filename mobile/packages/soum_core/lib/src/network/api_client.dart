/// عميل الشبكة — المكان الوحيد الذي يعرف Dio.
///
/// كلّ ما فوق هذه الطبقة يرى `ApiException` فقط. الفائدة ليست ذوقًا
/// معماريًّا: ‏`DioException` يحمل أربعة أشكال مختلفة للخطأ (استجابة،
/// مهلة، إلغاء، خطأ غير معروف)، ومعالجتها في كلّ مستودع تعني أربع فروع
/// مكرّرة في كلّ ملفّ — وثلاثة منها لن تُختبر أبدًا.
library;

// ignore_for_file: prefer_initializing_formals
// السبب: Dart يمنع معاملًا مسمّى يبدأ بشرطة سفلية، فلا سبيل لكتابة
// this._x في معامل مسمّى، ولا بديل عن الإسناد في قائمة التهيئة.

import 'package:dio/dio.dart';

import '../storage/session.dart';
import 'api_exception.dart';
import 'throttle_guard.dart';

class ApiClient {
  ApiClient({
    required String baseUrl,
    required SessionStore session,
    Dio? dio,
    ThrottleGuard? throttleGuard,
    void Function()? onUnauthenticated,
  })  : _session = session,
        throttle = throttleGuard ?? ThrottleGuard(),
        dio = dio ?? Dio() {
    this.dio.options
      ..baseUrl = baseUrl
      ..connectTimeout = const Duration(seconds: 12)
      ..receiveTimeout = const Duration(seconds: 20)
      ..sendTimeout = const Duration(seconds: 20)
      ..headers['Accept'] = 'application/json'
      // اللغة تُرسل في كلّ نداء: رسائل الخطأ تعود من الخادم جاهزة للعرض،
      // وهي ما يقرأه المستخدم فعلًا.
      ..headers['Accept-Language'] = 'ar'
      // 4xx ليست استثناءً في منطق الأعمال — 409 عند اختيار سائق حدثٌ
      // متوقَّع. لكنّنا نُبقي التحويل إلى استثناء ليكون للمسار الفاشل شكل
      // واحد، ونتفرّع على `code` في الشاشة.
      ..validateStatus = (status) => status != null && status < 400;

    this.dio.interceptors.add(throttle);
    this.dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              final token = _session.token;
              if (token != null && token.isNotEmpty) {
                options.headers['Authorization'] = 'Token $token';
              }
              handler.next(options);
            },
            onError: (error, handler) {
              if (error.response?.statusCode == 401) {
                // المفتاح لا ينتهي في هذا الخادم إلّا بخروج صريح، فـ401
                // تعني أنّه أُبطل من جهاز آخر. إبقاؤه محفوظًا يجعل كلّ
                // نداء لاحق يفشل بالطريقة نفسها بلا مخرج.
                _session.clearToken();
                onUnauthenticated?.call();
              }
              handler.next(error);
            },
          ),
        );
  }

  final Dio dio;
  final SessionStore _session;

  /// مكشوف لتقرأ الواجهة المدّة المتبقّية وترسم عدّادًا بلا نداء.
  final ThrottleGuard throttle;

  // ---------------------------------------------------------------
  // الأفعال
  // ---------------------------------------------------------------

  Future<T> get<T>(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) =>
      _send<T>(() => dio.get<T>(path, queryParameters: query, cancelToken: cancelToken));

  Future<T> post<T>(
    String path, {
    Object? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) =>
      _send<T>(() => dio.post<T>(
            path,
            data: body,
            queryParameters: query,
            cancelToken: cancelToken,
          ));

  Future<T> patch<T>(String path, {Object? body}) =>
      _send<T>(() => dio.patch<T>(path, data: body));

  Future<T> delete<T>(String path, {Object? body}) =>
      _send<T>(() => dio.delete<T>(path, data: body));

  /// رفع ملفّ متعدّد الأجزاء — وثائق السائق الأربع.
  Future<T> upload<T>(String path, FormData form) => _send<T>(
        () => dio.post<T>(
          path,
          data: form,
          options: Options(contentType: 'multipart/form-data'),
          // الوثائق صور من الكاميرا: مهلة الرفع الافتراضية قصيرة عليها
          // على شبكة بطيئة، والفشل هنا يعني سائقًا لا يستطيع التسجيل.
          onSendProgress: null,
        ),
      );

  Future<T> _send<T>(Future<Response<T>> Function() request) async {
    try {
      final response = await request();
      return response.data as T;
    } on DioException catch (error) {
      // الرفض المحلّي من حارس الحدود يحمل استثناءنا جاهزًا.
      final local = error.error;
      if (local is ApiException) throw local;
      throw ApiException.fromDio(error);
    }
  }
}
