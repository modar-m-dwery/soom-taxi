// T1.4 — «اختبار يثبت أنّ "5512.00" تعود كما هي بلا فقدان خانة».
//
// الخطأ الذي يقيسه هذا الملفّ لا يظهر في رحلة واحدة. يظهر في رصيد سائق
// بعد ثلاثمئة رحلة، وحينها يكون فرقُ رقمين في شكوى لا جواب لها.

import 'package:decimal/decimal.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  group('الدقّة', () {
    test('نصّ الخادم يعود كما هو', () {
      expect(Money.parse('5512.00').toApi(), '5512.00');
      expect(Money.parse('0.01').toApi(), '0.01');
      expect(Money.parse('999999.99').toApi(), '999999.99');
    });

    test('الجمع المتكرّر لا ينحرف — وهذا ما يفشل فيه double', () {
      var total = Money(Decimal.zero, 'SYP');
      for (var i = 0; i < 300; i++) {
        total = total + Money.parse('0.10');
      }
      expect(total.toApi(), '30.00');

      // البرهان المقابل: نفس العملية بأعداد عائمة.
      var drift = 0.0;
      for (var i = 0; i < 300; i++) {
        drift += 0.10;
      }
      expect(drift, isNot(30.0));
    });

    test('الطرح دقيق عند الحافة', () {
      final gross = Money.parse('5512.00');
      final fee = Money.parse('0.00');
      expect((gross - fee).toApi(), '5512.00');
    });
  });

  group('القراءة المتساهلة', () {
    test('null وفراغ يعنيان صفرًا لا خطأً', () {
      expect(Money.parse(null).isZero, isTrue);
      expect(Money.parse('').isZero, isTrue);
      expect(Money.parse('   ').isZero, isTrue);
    });

    test('رقم لا نصّ يمرّ عبر النصّ لا عبر double', () {
      expect(Money.parse(12.5).toApi(), '12.50');
    });

    test('نصّ غير صالح يرمي بوضوح لا يُعيد صفرًا صامتًا', () {
      expect(() => Money.parse('غير رقم'), throwsFormatException);
    });
  });

  group('المقارنة والعرض', () {
    test('المقارنة تعمل على الحدّ تمامًا', () {
      final floor = Money.parse('4000.00');
      final offer = Money.parse('4000.00');
      expect(offer >= floor, isTrue);
      expect(offer > floor, isFalse);
      expect(Money.parse('3999.99') < floor, isTrue);
    });

    test('العرض بلا كسور، والقيمة المخزَّنة تبقى كاملة', () {
      final fare = Money.parse('5512.00');
      expect(fare.format(locale: 'en'), '5,512');
      expect(fare.toApi(), '5512.00');
    });

    test('المساواة على القيمة لا على المرجع', () {
      expect(Money.parse('100.00'), Money.parse('100.0'));
      expect(Money.parse('100.00'), isNot(Money.parse('100.01')));
    });
  });
}
