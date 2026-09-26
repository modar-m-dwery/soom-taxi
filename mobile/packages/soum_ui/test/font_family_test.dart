// خطّ الهويّة مُعلَن في هذه الحزمة — فاسمه يجب أن يطابق ما يسجّله Flutter.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_ui/soum_ui.dart';

void main() {
  test('اسم الخطّ في السمة يطابق تسجيله من الحزمة', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    final family = RegExp(r'-\s*family:\s*(\S+)').firstMatch(pubspec)!.group(1)!;
    expect(SoumTheme.fontFamily, 'packages/soum_ui/$family',
        reason: 'بالاسم المجرّد لا يُعثر على الخطّ فيسقط إلى خطّ النظام');
    expect(SoumTheme.light().textTheme.bodyMedium!.fontFamily, SoumTheme.fontFamily);
  });
}
