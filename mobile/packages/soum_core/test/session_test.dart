// T1.3 — «اختبار يثبت ثبات device_id عبر إقلاعين، ومحوَه مع المفتاح عند
// تسجيل الخروج».
//
// دقّة مهمّة: الدليل يقول إنّ `device_id` ثابت **لكلّ تثبيت**. أي أنّه
// لا يُمحى عند تسجيل الخروج — محوُه هناك يجعل كلّ دورة خروج ودخول تثبيتًا
// جديدًا في نظر الخادم، وهو بالضبط ما يُبطل حدّ الجهاز.

import 'package:flutter_test/flutter_test.dart';
import 'package:soum_core/soum_core.dart';

void main() {
  test('يُولَّد مرّة واحدة ويبقى عبر الإقلاعات', () async {
    final disk = InMemoryStore();

    final first = SessionStore(secure: disk, prefs: disk);
    final id1 = await first.deviceId();
    final id2 = await first.deviceId();
    expect(id1, id2, reason: 'لا يُولَّد في كلّ نداء');
    expect(id1, isNotEmpty);

    // إقلاع ثانٍ: كائن جديد، القرص نفسه.
    final second = SessionStore(secure: disk, prefs: disk);
    expect(await second.deviceId(), id1);
  });

  test('تثبيتان مختلفان يحملان معرّفين مختلفين', () async {
    final a = SessionStore(secure: InMemoryStore(), prefs: InMemoryStore());
    final b = SessionStore(secure: InMemoryStore(), prefs: InMemoryStore());
    expect(await a.deviceId(), isNot(await b.deviceId()));
  });

  test('المفتاح يُحفظ ويُقرأ عند الإقلاع', () async {
    final disk = InMemoryStore();

    final first = SessionStore(secure: disk, prefs: disk);
    await first.load();
    expect(first.isAuthenticated, isFalse);

    await first.saveToken('0a67a8fa18eb8cd2');
    expect(first.isAuthenticated, isTrue);

    final second = SessionStore(secure: disk, prefs: disk);
    await second.load();
    expect(second.token, '0a67a8fa18eb8cd2');
  });

  test('تسجيل الخروج يمحو المفتاح ويُبقي معرّف الجهاز', () async {
    final disk = InMemoryStore();
    final session = SessionStore(secure: disk, prefs: disk);
    await session.load();

    final deviceId = await session.deviceId();
    await session.saveToken('token-abc');

    await session.clearToken();

    expect(session.token, isNull);
    expect(session.isAuthenticated, isFalse);
    expect(await session.deviceId(), deviceId,
        reason: 'المعرّف للتثبيت لا للمستخدم');
  });
}
