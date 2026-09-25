// حدود تطبيق السائق — ما يجب ألّا يكون فيه.
//
// المرآة المقابلة لاختبار الزبون: هناك منعنا أفعال السائق، وهنا نمنع
// افتراضات الزبون. وكلاهما يُفحص آليًّا لأنّ المراجعة البشرية تمرّ عليها.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

Iterable<File> dartFiles() => Directory('lib')
    .listSync(recursive: true)
    .whereType<File>()
    .where((f) => f.path.endsWith('.dart'));

void main() {
  test('لا شاشة تستورد مزوّد الخرائط مباشرةً', () {
    final offenders = dartFiles()
        .where((f) =>
            f.readAsStringSync().contains('package:flutter_map/') ||
            f.readAsStringSync().contains('package:latlong2/'))
        .map((f) => f.path)
        .toList();

    expect(offenders, isEmpty, reason: 'الشاشات تتكلّم SoumMap: $offenders');
  });

  test('لا رقم مهلة أو نصف قطر مثبَّت في الشيفرة', () {
    // §12.1 و§12.3: كلّ رقم من `/config/`. الفحص يمسك الأرقام الشهيرة
    // التي تُكتب بالخطأ — 200 و300 مترًا، و60 ثانية، و5 كم.
    final suspicious = RegExp(
      r'(arrivalRadius|dropoffRadius|presenceStale|matchingRadius|'
      r'invitationTtl|offerTtl)\w*\s*[=:]\s*\d+',
    );
    final offenders = <String>[];

    for (final file in dartFiles()) {
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trimLeft().startsWith('//')) continue;
        if (suspicious.hasMatch(lines[i])) {
          offenders.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }

    expect(offenders, isEmpty,
        reason: 'قيمة إعداد مثبَّتة في الشيفرة: $offenders');
  });

  test('الحضور يقرأ وتيرة النبض من الإعداد', () {
    final source = File(
      'lib/features/presence/presence_controller.dart',
    ).readAsStringSync();

    expect(source, contains('heartbeatInterval'),
        reason: 'الوتيرة من الإعداد لا من الرقم 3 أو 5');
    expect(source, contains('presenceStaleSeconds'));
  });

  test('النبض الدوريّ يرسل heartbeat لا location.update وحدها', () {
    // الخادم لا يردّ `presence.ack` إلّا على `heartbeat`. و`matchable`
    // لا يُبلَغ إلّا بذلك الإقرار، والقائمة محجوبة خلفه. عُثر عليه على
    // خادم يعمل: خمسون ثانية «بانتظار أوّل نبضة» وقائمة طلبات فارغة.
    final source = File(
      'lib/features/presence/presence_controller.dart',
    ).readAsStringSync();

    final start = source.indexOf('void _sendHeartbeat()');
    expect(start, greaterThan(-1));
    final end = source.indexOf(RegExp(r'\n  \}\n'), start);
    final body = source.substring(start, end);

    expect(body, contains("'type': 'location.update'"));
    expect(body, contains("'type': 'heartbeat'"),
        reason: 'بلا heartbeat لا إقرار، وبلا إقرار لا مطابقة في الواجهة');
  });

  test('العودة من الخلفية تعيد go-online لا فتح المقبس فقط', () {
    // §6.2 حرفيًّا. الفحص على البنية لا على النيّة: `resumed` يجب أن
    // ينادي `goOnline` لا `connect`.
    final source = File(
      'lib/features/presence/presence_controller.dart',
    ).readAsStringSync();

    final resumedBlock = source.substring(
      source.indexOf('AppLifecycleState.resumed'),
      source.indexOf('AppLifecycleState.paused'),
    );

    expect(resumedBlock, contains('goOnline'),
        reason: 'إعادة فتح المقبس وحدها لا تُعيد السائق إلى الأسطول');
  });

  test('لا إعادة محاولة تلقائية لأفعال دورة حياة الرحلة', () {
    // §12.3: «ولا تعِد المحاولة تلقائيًّا» عند 400 الجغرافيّ.
    final source = File(
      'lib/features/work/work_controller.dart',
    ).readAsStringSync();

    expect(source, isNot(contains('retry')),
        reason: 'حلقة إعادة محاولة على حارس جغرافيّ لا تتحقّق أبدًا');
  });
}
