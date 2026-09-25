import '../models/json.dart';
import '../network/api_client.dart';

/// قناة إيصال — §10.1.
class NotificationChannel {
  const NotificationChannel({
    required this.code,
    required this.label,
    required this.isConfigured,
    required this.requiresLinking,
    required this.isLinked,
    required this.isEnabled,
    required this.priority,
  });

  final String code;
  final String label;

  /// المشغّل اشترك بهذه القناة على الخادم. قناة `configured: false`
  /// **لا تظهر للمستخدم أصلًا** (§12.3) — لا معطَّلة ولا رمادية.
  final bool isConfigured;

  /// على المستخدم ربط عنوانه بنفسه — تليغرام مثلًا.
  final bool requiresLinking;

  final bool isLinked;
  final bool isEnabled;

  /// الأصغر يُجرَّب أوّلًا.
  final int priority;

  bool get isVisible => isConfigured;

  factory NotificationChannel.fromJson(Json json) => NotificationChannel(
        code: readString(json, 'code'),
        label: readString(json, 'label'),
        isConfigured: readBool(json, 'configured'),
        requiresLinking: readBool(json, 'requires_linking'),
        isLinked: readBool(json, 'linked'),
        isEnabled: readBool(json, 'enabled'),
        priority: readInt(json, 'priority', fallback: 100),
      );
}

class TelegramLink {
  const TelegramLink({
    required this.code,
    required this.deepLink,
    required this.expiresInSeconds,
  });

  final String code;

  /// يُفتح بـIntent / openURL. المستخدم يضغط «ابدأ» فيصل الخادمَ ويب هوك
  /// يربط المحادثة تلقائيًّا — البوت لا يستطيع بدء محادثة من طرفه.
  final String deepLink;

  final int expiresInSeconds;

  factory TelegramLink.fromJson(Json json) => TelegramLink(
        code: readString(json, 'code'),
        deepLink: readString(json, 'deep_link'),
        expiresInSeconds: readInt(json, 'expires_in_seconds', fallback: 600),
      );
}

class NotificationsApi {
  NotificationsApi(this._client);

  final ApiClient _client;

  /// §10 — «سجّل عند كلّ إقلاع لا مرّة واحدة: مفاتيح الدفع تتغيّر بلا إشعار».
  Future<void> registerDevice({
    required String token,
    required String platform,
    required String deviceId,
  }) =>
      _client.post<dynamic>('/push/devices/register/', body: {
        'token': token,
        'platform': platform,
        'device_id': deviceId,
      });

  /// عند تسجيل الخروج — وإلّا وصلت إشعارات المستخدم السابق إلى الجهاز نفسه.
  Future<void> unregisterDevice(String token) =>
      _client.post<dynamic>('/push/devices/unregister/', body: {'token': token});

  Future<List<Json>> inbox() async =>
      readResults(await _client.get<dynamic>('/me/notifications/'));

  Future<List<NotificationChannel>> channels() async {
    final body = asJson(await _client.get<dynamic>('/me/notification-channels/'));
    final raw = body['channels'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((e) => NotificationChannel.fromJson(e.cast<String, dynamic>()))
        .toList(growable: false);
  }

  Future<void> updateChannel(
    String code, {
    bool? isEnabled,
    int? priority,
  }) =>
      _client.patch<dynamic>('/me/notification-channels/$code/', body: {
        'is_enabled': ?isEnabled,
        'priority': ?priority,
      });

  /// 503 هنا ليست عطلًا: المشغّل لم يفعّل تليغرام على الخادم.
  /// أخفِ الخيار من الواجهة عندها.
  Future<TelegramLink> linkTelegram() async => TelegramLink.fromJson(
        asJson(await _client.post<dynamic>('/notifications/channels/telegram/link/')),
      );

  Future<void> unlinkTelegram() =>
      _client.delete<dynamic>('/notifications/channels/telegram/link/');
}
