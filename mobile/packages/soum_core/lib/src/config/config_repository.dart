/// مستودع الإعداد — القراءة والخبيئة.
///
/// §0.1 في دليل التكامل يصف السلوك المطلوب حرفيًّا:
///
/// > اقرأها عند كلّ إقلاع واخزنها محلّيًّا مع الطابع الزمني. استعمل النسخة
/// > المخزَّنة إن فشل النداء (المستخدم بلا شبكة يجب أن يرى شاشةً لا خطأً)،
/// > وأعد القراءة عند تغيّر مدينة المستخدم. وضع سقفًا: نسخة أقدم من يوم
/// > تُعدّ منتهية.
///
/// والسقف هو الشرط الذي ينساه الجميع: نسخةٌ بلا انتهاء تعني أنّ جهازًا بقي
/// شهرًا بلا شبكة يعمل بمهل وأنصاف أقطار قد تكون تغيّرت — فيرسل قيمًا
/// يرفضها الخادم، وهو بالضبط العطل الذي وُجد `/config/` لمنعه.
library;

import 'dart:convert';

import '../models/json.dart';
import '../network/api_client.dart';
import '../network/api_exception.dart';
import '../storage/stores.dart';
import 'app_config.dart';

class ConfigUnavailable implements Exception {
  const ConfigUnavailable(this.cause);
  final ApiException cause;

  @override
  String toString() => 'ConfigUnavailable(${cause.code})';
}

class ConfigRepository {
  ConfigRepository({
    required ApiClient client,
    required PrefsStore prefs,
    DateTime Function()? clock,
    this.maxAge = const Duration(hours: 24),
  })  : _client = client,
        _prefs = prefs,
        _now = clock ?? DateTime.now;
  // ignore_for_file: prefer_initializing_formals

  static const _cacheKey = 'soum.config.cache';
  static const _cacheAtKey = 'soum.config.cached_at';

  final ApiClient _client;
  final PrefsStore _prefs;
  final DateTime Function() _now;

  /// السقف الذي تُعدّ بعده النسخة المخزَّنة منتهية.
  final Duration maxAge;

  AppConfig? _current;

  AppConfig? get current => _current;

  /// يُنادى عند كلّ إقلاع، وعند تغيّر مدينة المستخدم.
  ///
  /// الترتيب مقصود: نحاول الشبكة أوّلًا دائمًا — الإعداد يتغيّر من لوحة
  /// الإدارة ويسري فورًا، فخبيئةٌ تُفضَّل على الشبكة تؤخّر التغيير يومًا.
  /// الخبيئة احتياطٌ للانقطاع لا مصدرٌ أوّل.
  Future<AppConfig> load({double? lat, double? lng, String? areaCode}) async {
    try {
      final body = await _client.get<dynamic>(
        '/config/',
        query: {
          'lat': ?lat,
          'lng': ?lng,
          if (areaCode != null && areaCode.isNotEmpty) 'area': areaCode,
        },
      );

      final json = asJson(body);
      final config = AppConfig.fromJson(json, fetchedAt: _now());

      await _persist(json);
      _current = config;
      return config;
    } on ApiException catch (error) {
      final cached = _readCache();
      if (cached != null) {
        _current = cached;
        return cached;
      }
      throw ConfigUnavailable(error);
    }
  }

  /// النسخة المخزَّنة إن كانت صالحة، وإلّا null.
  AppConfig? _readCache() {
    final raw = _prefs.getString(_cacheKey);
    final at = _prefs.getString(_cacheAtKey);
    if (raw == null || at == null) return null;

    final cachedAt = DateTime.tryParse(at);
    if (cachedAt == null) return null;

    if (_now().difference(cachedAt) > maxAge) return null;

    try {
      final json = asJson(jsonDecode(raw));
      if (json.isEmpty) return null;
      return AppConfig.fromJson(json, fetchedAt: cachedAt);
    } on FormatException {
      // خبيئة تالفة ليست سببًا لمنع الإقلاع — نتجاهلها ونمضي.
      return null;
    }
  }

  Future<void> _persist(Json json) async {
    await _prefs.setString(_cacheKey, jsonEncode(json));
    await _prefs.setString(_cacheAtKey, _now().toIso8601String());
  }

  Future<void> clearCache() async {
    await _prefs.remove(_cacheKey);
    await _prefs.remove(_cacheAtKey);
    _current = null;
  }
}
