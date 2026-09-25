// T2.1 — تطبيع الرقم.
//
// المستخدم يكتب ما اعتاده. رفضُ `0991234567` بـ«رقم غير صحيح» خطأٌ في
// الواجهة لا في المدخل.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_ui/soum_ui.dart';

void main() {
  group('الصيغ التي يكتبها الناس فعلًا', () {
    const expected = '+963991234567';

    for (final input in [
      '0991234567',
      '991234567',
      '+963991234567',
      '00963991234567',
      '963991234567',
      '+963 99 123 4567',
      '0991 234 567',
      ' 0991234567 ',
    ]) {
      test('«$input» ← $expected', () {
        expect(SyrianPhone.normalize(input), expected);
      });
    }
  });

  group('ما يجب أن يُرفض', () {
    for (final input in [
      '',
      '099123456',    // ناقص رقمًا
      '09912345678',  // زائد رقمًا
      '0891234567',   // لا يبدأ بـ9 بعد الصفر
      'أبجد',
      '+9613456789',  // لبنان
    ]) {
      test('«$input» مرفوض', () {
        expect(SyrianPhone.normalize(input), isNull);
        expect(SyrianPhone.isValid(input), isFalse);
      });
    }
  });

  test('العرض يجزّئ الرقم ولا يغيّره', () {
    expect(SyrianPhone.pretty('+963991234567'), '+963 991 234 567');
    expect(SyrianPhone.pretty('غير صالح'), 'غير صالح');
  });
}
