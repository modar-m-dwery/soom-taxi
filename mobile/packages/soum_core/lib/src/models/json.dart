/// قارئات JSON آمنة.
///
/// السبب في وجودها مذكور في آخر §0.1 من دليل التكامل:
///
/// > وأيّ حقل جديد سيُضاف هنا مستقبلًا — اقرأه بـoptional ولا تنهر عند غيابه.
///
/// وهذا ليس احتياطًا نظريًّا: الخادم يضيف حقولًا بلا إصدار جديد من الـAPI،
/// و`json['x'] as int` على حقل غائب يرمي `TypeError` يُسقط الشاشة كلّها —
/// لا الحقل وحده. القارئات هنا تُعيد قيمة افتراضية وتُبقي الشاشة قائمة.
library;

import 'money.dart';

typedef Json = Map<String, dynamic>;

Json asJson(Object? raw) =>
    raw is Map ? raw.cast<String, dynamic>() : const <String, dynamic>{};

Json? asJsonOrNull(Object? raw) =>
    raw is Map ? raw.cast<String, dynamic>() : null;

int readInt(Json json, String key, {int fallback = 0}) {
  final raw = json[key];
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  if (raw is String) return int.tryParse(raw) ?? fallback;
  return fallback;
}

int? readIntOrNull(Json json, String key) {
  final raw = json[key];
  if (raw == null) return null;
  if (raw is int) return raw;
  if (raw is num) return raw.toInt();
  if (raw is String) return int.tryParse(raw);
  return null;
}

double readDouble(Json json, String key, {double fallback = 0}) {
  final raw = json[key];
  if (raw is num) return raw.toDouble();
  if (raw is String) return double.tryParse(raw) ?? fallback;
  return fallback;
}

double? readDoubleOrNull(Json json, String key) {
  final raw = json[key];
  if (raw == null) return null;
  if (raw is num) return raw.toDouble();
  if (raw is String) return double.tryParse(raw);
  return null;
}

String readString(Json json, String key, {String fallback = ''}) {
  final raw = json[key];
  if (raw == null) return fallback;
  return raw is String ? raw : '$raw';
}

String? readStringOrNull(Json json, String key) {
  final raw = json[key];
  if (raw == null) return null;
  final text = raw is String ? raw : '$raw';
  return text.isEmpty ? null : text;
}

bool readBool(Json json, String key, {bool fallback = false}) {
  final raw = json[key];
  if (raw is bool) return raw;
  if (raw is String) return raw.toLowerCase() == 'true';
  if (raw is num) return raw != 0;
  return fallback;
}

/// التواريخ تعود دائمًا بـUTC من DRF. التحويل إلى محلّي هنا لا في كلّ شاشة:
/// عدّادٌ يُحسب على تاريخ UTC وساعة محلّية يخطئ بفارق المنطقة كاملًا.
DateTime? readDateOrNull(Json json, String key) {
  final raw = json[key];
  if (raw is! String || raw.isEmpty) return null;
  return DateTime.tryParse(raw)?.toLocal();
}

DateTime readDate(Json json, String key) =>
    readDateOrNull(json, key) ?? DateTime.fromMillisecondsSinceEpoch(0);

Money readMoney(Json json, String key, {String currency = Money.defaultCurrency}) =>
    Money.parse(json[key], currency);

Money? readMoneyOrNull(Json json, String key,
    {String currency = Money.defaultCurrency}) {
  final raw = json[key];
  if (raw == null || (raw is String && raw.isEmpty)) return null;
  return Money.parse(raw, currency);
}

List<T> readList<T>(Json json, String key, T Function(Json) item) {
  final raw = json[key];
  if (raw is! List) return const [];
  return raw
      .whereType<Map>()
      .map((e) => item(e.cast<String, dynamic>()))
      .toList(growable: false);
}

List<String> readStringList(Json json, String key) {
  final raw = json[key];
  if (raw is! List) return const [];
  return raw.map((e) => '$e').toList(growable: false);
}

List<int> readIntList(Json json, String key) {
  final raw = json[key];
  if (raw is! List) return const [];
  return raw
      .map((e) => e is int ? e : int.tryParse('$e'))
      .whereType<int>()
      .toList(growable: false);
}

/// القوائم المرقَّمة في DRF تأتي بشكلين: كائن فيه `results`، أو مصفوفة
/// عارية. الخلط بينهما يعني شاشة فارغة بلا خطأ — وهو أسوأ من عطل مرئيّ.
List<Json> readResults(Object? body) {
  if (body is List) {
    return body.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
  }
  final json = asJson(body);
  final results = json['results'];
  if (results is List) {
    return results.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
  }
  return const [];
}
