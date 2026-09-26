import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('التقييم يُقتطع لا يُقرَّب', () {
    expect(formatRating(4.95), '4.9', reason: '4.95 ليست خمس نجوم');
    expect(formatRating(4.99), '4.9');
    expect(formatRating(5), '5.0');
    expect(formatRating(4.3), '4.3', reason: 'بلا خطأ الفاصلة العائمة');
    expect(formatRating(4.8), '4.8');
  });

  test('العدّاد بالدقائق والثواني', () {
    expect(formatClock(598), '9:58');
    expect(formatClock(59), '0:59');
    expect(formatClock(3725), '1:02:05');
    expect(formatClock(-3), '0:00');
  });
}
