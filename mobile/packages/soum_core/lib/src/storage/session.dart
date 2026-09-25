/// جلسة المستخدم: المفتاح ومعرّف الجهاز.
///
/// البند الذي يفسّر هذا الملفّ، من §1.2 في دليل التكامل:
///
/// > الحدّ يُحسب على ثلاثة محاور مستقلّة: الهاتف، الجهاز، وعنوان الشبكة.
/// > `device_id` ثابت لكلّ تثبيت — ولّده مرّة واحدة عند أوّل إقلاع واحفظه.
///
/// والخطآن اللذان يحذّر منهما صريحان، ولكلٍّ ثمنه:
///
///   توليده في كلّ نداء   → حدّ الجهاز بلا معنى، فيصير محور الحماية الثالث
///                          عدّادًا لا يُبلَغ أبدًا.
///   تثبيته لكلّ المستخدمين → مستخدم واحد يستهلك الحصّة فيقفل الآخرين عن
///                          تسجيل الدخول على الجهاز نفسه.
///
/// لذلك: يُولَّد مرّة، ويُحفظ في التخزين العاديّ لا المحميّ (ليس سرًّا،
/// وقراءته تحدث في كلّ إقلاع)، **ولا يُمحى عند تسجيل الخروج** — فهو معرّف
/// التثبيت لا معرّف المستخدم.
library;

// ignore_for_file: prefer_initializing_formals
// السبب: Dart يمنع معاملًا مسمّى يبدأ بشرطة سفلية، فلا سبيل لكتابة
// this._x في معامل مسمّى، ولا بديل عن الإسناد في قائمة التهيئة.

import 'package:uuid/uuid.dart';

import 'stores.dart';

class SessionStore {
  SessionStore({
    required SecureStore secure,
    required PrefsStore prefs,
    Uuid? uuid,
  })  : _secure = secure,
        _prefs = prefs,
        _uuid = uuid ?? const Uuid();

  static const _tokenKey = 'soum.auth.token';
  static const _deviceKey = 'soum.device.id';

  final SecureStore _secure;
  final PrefsStore _prefs;
  final Uuid _uuid;

  String? _token;

  /// المفتاح المحمَّل. يُقرأ من الذاكرة بعد أوّل تحميل حتّى لا تمرّ كلّ
  /// نداءة على سلسلة المفاتيح.
  String? get token => _token;

  bool get isAuthenticated => _token != null && _token!.isNotEmpty;

  /// يُستدعى مرّة عند الإقلاع، قبل أوّل نداء موثَّق.
  Future<void> load() async {
    _token = await _secure.read(_tokenKey);
  }

  Future<void> saveToken(String token) async {
    _token = token;
    await _secure.write(_tokenKey, token);
  }

  /// تسجيل الخروج: يمحو المفتاح ويُبقي معرّف الجهاز.
  ///
  /// محوُ المعرّف هنا يجعل كلّ تسجيل خروج ودخول تثبيتًا جديدًا في نظر
  /// الخادم — وهو بالضبط ما يُبطل حدّ الجهاز.
  Future<void> clearToken() async {
    _token = null;
    await _secure.delete(_tokenKey);
  }

  /// معرّف التثبيت. يُولَّد عند أوّل طلب له ويبقى.
  Future<String> deviceId() async {
    final existing = _prefs.getString(_deviceKey);
    if (existing != null && existing.isNotEmpty) return existing;

    final generated = _uuid.v4();
    await _prefs.setString(_deviceKey, generated);
    return generated;
  }
}
