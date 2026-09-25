/// تطبيع أرقام الهاتف السورية.
///
/// الخادم يتوقّع الصيغة الدولية `+963XXXXXXXXX`. والمستخدم يكتب ما اعتاده:
/// `0991234567` أو `991234567` أو `+963 99 123 4567` بمسافات. رفضُ أيّ
/// منها بـ«رقم غير صحيح» خطأٌ في الواجهة لا في المدخل — كلّها الرقم نفسه.
///
/// والتطبيع هنا لا في شاشة: الشاشتان في تطبيقين، ونسختان من هذا المنطق
/// تتباعدان عند أوّل تعديل.
library;

class SyrianPhone {
  static const countryCode = '+963';

  /// أرقام المحمول السورية تسعة أرقام تبدأ بـ9.
  static final _mobile = RegExp(r'^9\d{8}$');

  /// يعيد الصيغة الدولية، أو null إن لم يكن الرقم صالحًا.
  static String? normalize(String raw) {
    var digits = raw.replaceAll(RegExp(r'[^\d+]'), '');

    if (digits.startsWith('+963')) {
      digits = digits.substring(4);
    } else if (digits.startsWith('00963')) {
      digits = digits.substring(5);
    } else if (digits.startsWith('963') && digits.length > 9) {
      digits = digits.substring(3);
    }

    digits = digits.replaceAll('+', '');

    // صفر البادئة المحلّية.
    if (digits.startsWith('0')) digits = digits.substring(1);

    if (!_mobile.hasMatch(digits)) return null;
    return '$countryCode$digits';
  }

  static bool isValid(String raw) => normalize(raw) != null;

  /// للعرض: ‏`+963 991 234 567`.
  static String pretty(String international) {
    if (!international.startsWith(countryCode)) return international;
    final rest = international.substring(countryCode.length);
    if (rest.length != 9) return international;
    return '$countryCode ${rest.substring(0, 3)} '
        '${rest.substring(3, 6)} ${rest.substring(6)}';
  }
}
