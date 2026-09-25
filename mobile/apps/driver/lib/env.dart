/// عنوان الخادم.
///
/// يُمرَّر عند البناء لا يُكتب في الشيفرة:
///
///     flutter run --dart-define=SOUM_API=http://10.0.2.2:8000/api/v1
///
/// والافتراض `10.0.2.2` لا `localhost`: داخل محاكي أندرويد، `localhost`
/// هو المحاكي نفسه لا الحاسوب المضيف. هذا أوّل ما يوقف مبرمجًا يشغّل
/// التطبيق أوّل مرّة على خادم محلّي.
library;

import 'package:flutter/foundation.dart';

abstract final class Env {
  static const _api = String.fromEnvironment(
    'SOUM_API',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

  /// بناء الإصدار يرفض خادمًا بلا HTTPS بدل أن يرسل التوكن نصًّا مكشوفًا.
  /// الخطأ عند الإقلاع أوضح من اتّصالٍ يفشل بصمت بسبب منع أندرويد له.
  static String get apiBaseUrl {
    if (kReleaseMode && !_api.startsWith('https://')) {
      throw StateError('SOUM_API must be https:// in release builds: $_api');
    }
    return _api;
  }
}
