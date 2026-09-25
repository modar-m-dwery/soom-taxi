// T2.4 — «فحص آليّ يسقط البناء عند أيّ نصّ عربيّ مكتوب داخل شيفرة واجهة».
//
// لماذا فحصٌ آليّ لا مراجعة: نصٌّ واحد منسيّ في الشيفرة يعني سطرًا لا
// يُترجَم أبدًا. ولن يظهر في اختبار — الشاشة تعمل، والنصّ عربيّ، وكلّ شيء
// يبدو سليمًا حتّى يُفتح التطبيق بالإنجليزية فيظهر سطر عربيّ وحيد وسطه.
//
// والفحص يقيس النصوص المعروضة وحدها: التعليقات ووثائق الشيفرة عربية عمدًا
// في هذا المشروع، وهي ليست معروضة لأحد.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

final _arabic = RegExp(r'[؀-ۿ]');

/// الأسطر التي لا تُعدّ نصًّا معروضًا.
///
/// ثلاث فئات معفاة، وكلّها لا تصل إلى مستخدم:
///
///   التعليقات      — عربية عمدًا في هذا المشروع، ويقرأها المبرمج وحده.
///   `assert`       — تُحذف كاملةً في بناء الإصدار.
///   استثناءات البرمجة (`StateError` و`ArgumentError`) — تصف خطأً في
///   الشيفرة لا حالةً يقابلها المستخدم؛ وصولها إلى شاشة عطلٌ بذاته.
///
/// وما عدا ذلك نصٌّ معروض، ويجب أن يكون في ملفّ الترجمة.
bool _isExempt(String line) {
  final trimmed = line.trimLeft();

  if (trimmed.startsWith('//') ||
      trimmed.startsWith('///') ||
      trimmed.startsWith('*') ||
      trimmed.startsWith('/*')) {
    return true;
  }

  return trimmed.contains('assert(') ||
      trimmed.contains('StateError(') ||
      trimmed.contains('ArgumentError(') ||
      trimmed.contains('UnimplementedError(');
}

/// نصّ عربيّ داخل علامات اقتباس — وهو ما يصل إلى الشاشة.
final _quotedArabic = RegExp(
  r"""(?<!\/\/.*)(['"])([^'"\n]*[؀-ۿ][^'"\n]*)\1""",
);

void main() {
  test('لا نصّ عربيّ معروض خارج ملفّات الترجمة', () {
    final offenders = <String>[];

    final roots = [
      Directory('lib/src/auth'),
      Directory('lib/src/boot'),
      Directory('lib/src/widgets'),
      Directory('lib/src/theme'),
      Directory('../../apps/customer/lib'),
      Directory('../../apps/driver/lib'),
    ];

    for (final root in roots) {
      if (!root.existsSync()) continue;

      for (final file in root
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'))) {
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (_isExempt(line)) continue;
          if (!_arabic.hasMatch(line)) continue;
          if (!_quotedArabic.hasMatch(line)) continue;

          offenders.add('${file.path}:${i + 1}: ${line.trim()}');
        }
      }
    }

    expect(
      offenders,
      isEmpty,
      reason: 'نصوص عربية في شيفرة الواجهة — انقلها إلى app_ar.arb:\n'
          '${offenders.join('\n')}',
    );
  });

  test('العربية والإنجليزية متطابقتان في المفاتيح', () {
    final ar = File('lib/src/l10n/app_ar.arb').readAsStringSync();
    final en = File('lib/src/l10n/app_en.arb').readAsStringSync();

    // المستوى الأعلى وحده: مفاتيح placeholders متداخلة وليست نصوصًا.
    Set<String> keys(String source) => (jsonDecode(source) as Map)
        .keys
        .cast<String>()
        .where((k) => !k.startsWith('@'))
        .toSet();

    final arabicKeys = keys(ar);
    final englishKeys = keys(en);

    expect(arabicKeys.difference(englishKeys), isEmpty,
        reason: 'مفاتيح بلا ترجمة إنجليزية');
    expect(englishKeys.difference(arabicKeys), isEmpty,
        reason: 'مفاتيح إنجليزية بلا مقابل عربيّ');
    expect(arabicKeys.length, greaterThan(40));
  });
}
