/// التخزين — واجهتان وتنفيذان لكلٍّ.
///
/// الفصل هنا ليس تجريدًا لأجل التجريد: ‏`flutter_secure_storage` و
/// `shared_preferences` كلاهما يحتاج قناة منصّة لا تعمل في اختبار وحدة.
/// الواجهة تعني أنّ كلّ ما فوقها — المفتاح، معرّف الجهاز، خبيئة الإعداد —
/// يُختبر كاملًا بلا محاكي ولا جهاز.
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// تخزين محميّ — للمفتاح وحده. لا يوضع فيه شيء يُقرأ في كلّ إقلاع:
/// القراءة منه تمرّ بسلسلة المفاتيح وهي أبطأ بمراتب من الخيارات.
abstract interface class SecureStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

/// تخزين عاديّ — للإعداد ومعرّف الجهاز وما ليس سرًّا.
abstract interface class PrefsStore {
  String? getString(String key);
  Future<void> setString(String key, String value);
  Future<void> remove(String key);
}

// ---------------------------------------------------------------
// تنفيذ المنصّة
// ---------------------------------------------------------------

class PlatformSecureStore implements SecureStore {
  PlatformSecureStore([FlutterSecureStorage? storage])
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock,
              ),
            );

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class PlatformPrefsStore implements PrefsStore {
  PlatformPrefsStore(this._prefs);

  final SharedPreferences _prefs;

  static Future<PlatformPrefsStore> open() async =>
      PlatformPrefsStore(await SharedPreferences.getInstance());

  @override
  String? getString(String key) => _prefs.getString(key);

  @override
  Future<void> setString(String key, String value) =>
      _prefs.setString(key, value);

  @override
  Future<void> remove(String key) => _prefs.remove(key).then((_) {});
}

// ---------------------------------------------------------------
// تنفيذ الذاكرة — للاختبارات
// ---------------------------------------------------------------

class InMemoryStore implements SecureStore, PrefsStore {
  final Map<String, String> _data = {};

  Map<String, String> get snapshot => Map.unmodifiable(_data);

  @override
  Future<String?> read(String key) async => _data[key];

  @override
  Future<void> write(String key, String value) async => _data[key] = value;

  @override
  Future<void> delete(String key) async => _data.remove(key);

  @override
  String? getString(String key) => _data[key];

  @override
  Future<void> setString(String key, String value) async => _data[key] = value;

  @override
  Future<void> remove(String key) async => _data.remove(key);
}
