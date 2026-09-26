import 'package:flutter/services.dart';

/// إبقاء الشاشة مضاءة ما دام السائق «يعمل الآن».
///
/// النبض يتوقّف حين يذهب التطبيق للخلفية — قرارٌ مقصود (البيان بلا موقع
/// خلفيّ). لكنّ قفل الشاشة التلقائيّ يعدّ «خلفيّة»: شاشة ريدمي تُقفل بعد
/// نصف دقيقة، فيتوقّف النبض ويكنس الخادمُ السائقَ بعد دقيقة دون أن يدري.
/// على أندرويد نداءٌ لـ`FLAG_KEEP_SCREEN_ON`، وعلى غيره لا شيء.
abstract final class ScreenAwake {
  static const _channel = MethodChannel('sy.soum/screen');

  static Future<void> set(bool on) async {
    try {
      await _channel.invokeMethod<void>('keepOn', on);
    } on MissingPluginException {
      // ويب/آي أو إس/اختبار: لا قناة — والسائق يضبط قفل الشاشة يدويًّا.
    } on PlatformException {
      // فشلٌ هنا لا يمسّ العمل نفسه.
    }
  }
}
