// T3.8 — «لا زرّ تأكيد قبض في تطبيق الزبون إطلاقًا».
//
// §6.3: «قيدٌ أمنيّ يعني تصميم شاشتك: في الدفع النقدي، السائق وحده — أو
// الإدارة — من يؤكّد القبض. زر «دفعت» في تطبيق الزبون يردّ 403».
//
// الفحص آليّ لا بصريّ: زرٌّ يُضاف بعد سنة في مراجعة سريعة يمرّ من عين
// المراجع ولا يمرّ من هنا. والمقياس هو النداء نفسه — `payments.charge` —
// لا نصّ الزرّ، لأنّ الزرّ قد يُسمّى أيّ شيء.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('تطبيق الزبون لا ينادي charge في أيّ موضع', () {
    final offenders = <String>[];

    for (final file in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        if (line.trimLeft().startsWith('//')) continue;
        if (line.contains('payments.charge') || line.contains('.charge(')) {
          offenders.add('${file.path}:${i + 1}');
        }
      }
    }

    expect(offenders, isEmpty,
        reason: 'الزبون لا يستطيع تأكيد قبض مالٍ لم يُقبَض: $offenders');
  });

  test('ولا ينادي أفعال السائق في دورة حياة الرحلة', () {
    // `arrived` و`start` و`complete` أفعالُ سائق. نداؤها من تطبيق الزبون
    // يعود 403، ووجودُها في الشيفرة يعني شاشةً تَعِد بما سيُرفض.
    final offenders = <String>[];
    final forbidden = RegExp(r'driver\.(arrived|start|complete|goOnline|submitOffer)\(');

    for (final file in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trimLeft().startsWith('//')) continue;
        if (forbidden.hasMatch(lines[i])) {
          offenders.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }

    expect(offenders, isEmpty, reason: 'أفعال سائق في تطبيق الزبون: $offenders');
  });

  test('لا شاشة تستورد flutter_map مباشرةً', () {
    // T1.8 — الشاشات تتكلّم SoumMap وحدها، فاستبدال المزوّد يبقى تنفيذًا
    // ثانيًا خلف الواجهة لا إعادةَ كتابة لعشر شاشات.
    final offenders = <String>[];

    for (final file in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final source = file.readAsStringSync();
      if (source.contains('package:flutter_map/') ||
          source.contains('package:latlong2/')) {
        offenders.add(file.path);
      }
    }

    expect(offenders, isEmpty,
        reason: 'استيراد مزوّد الخرائط مباشرةً: $offenders');
  });
}
