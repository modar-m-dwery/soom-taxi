/// نقطة التجميع — كلّ ما يحتاجه تطبيق من الطبقة المشتركة، في كائن واحد.
///
/// وجودها يمنع نمطًا يتكرّر في تطبيقات هذا الحجم: كلّ شاشة تبني عميلها
/// ومستودعاتها، فتتعدّد مخازن الجلسة، ويصير تسجيل الخروج يمحو مفتاحًا
/// لا تزال نسخة أخرى منه في الذاكرة.
library;

import 'package:dio/dio.dart';

import 'api/ads_api.dart';
import 'api/auth_api.dart';
import 'api/driver_api.dart';
import 'api/feedback_api.dart';
import 'api/invitations_api.dart';
import 'api/maps_api.dart';
import 'api/notifications_api.dart';
import 'api/payments_api.dart';
import 'api/rides_api.dart';
import 'api/sharing_api.dart';
import 'config/config_repository.dart';
import 'network/api_client.dart';
import 'realtime/realtime_room.dart';
import 'realtime/version_guard.dart';
import 'storage/session.dart';
import 'storage/stores.dart';

class Soum {
  Soum._({
    required this.client,
    required this.session,
    required this.config,
    required this.baseWsUrl,
    required this.auth,
    required this.rides,
    required this.invitations,
    required this.driver,
    required this.payments,
    required this.feedback,
    required this.maps,
    required this.notifications,
    required this.sharing,
    required this.ads,
  });

  /// يبني كلّ شيء ويحمّل المفتاح المحفوظ.
  ///
  /// [baseUrl] مثل `http://10.0.2.2:8000/api/v1` — عنوان المضيف كما يراه
  /// الجهاز لا كما يراه الحاسوب.
  static Future<Soum> create({
    required String baseUrl,
    required SecureStore secure,
    required PrefsStore prefs,
    Dio? dio,
    void Function()? onUnauthenticated,
  }) async {
    final session = SessionStore(secure: secure, prefs: prefs);
    await session.load();

    final client = ApiClient(
      baseUrl: baseUrl,
      session: session,
      dio: dio,
      onUnauthenticated: onUnauthenticated,
    );

    return Soum._(
      client: client,
      session: session,
      config: ConfigRepository(client: client, prefs: prefs),
      baseWsUrl: _deriveWsUrl(baseUrl),
      auth: AuthApi(client, session),
      rides: RidesApi(client),
      invitations: InvitationsApi(client),
      driver: DriverApi(client),
      payments: PaymentsApi(client),
      feedback: FeedbackApi(client),
      maps: MapsApi(client),
      notifications: NotificationsApi(client),
      sharing: SharingApi(client),
      ads: AdsApi(client, _origin(baseUrl)),
    );
  }

  final ApiClient client;
  final SessionStore session;
  final ConfigRepository config;

  /// جذر المقابس — `ws://host` أو `wss://host` بلا `/api/v1`.
  final String baseWsUrl;

  final AuthApi auth;
  final RidesApi rides;
  final InvitationsApi invitations;
  final DriverApi driver;
  final PaymentsApi payments;
  final FeedbackApi feedback;
  final MapsApi maps;
  final NotificationsApi notifications;
  final SharingApi sharing;
  final AdsApi ads;

  static String _origin(String baseUrl) {
    final uri = Uri.parse(baseUrl);
    return uri.replace(path: '', query: null, fragment: null).toString().replaceAll(RegExp(r'/$'), '');
  }

  bool get isAuthenticated => session.isAuthenticated;

  /// غرفة بثّ على مسار يعطيه الخادم.
  ///
  /// المسار يأتي من `/me/active-ride/` تحت `realtime`، ولا يُبنى هنا:
  /// أيّ تغيير في مسارات البثّ غدًا كان سيتطلّب إصدارًا على المتجر لو
  /// كانت مبنيّة في العميل.
  RealtimeRoom room(String path, {VersionGuard? guard}) {
    final token = session.token;
    if (token == null || token.isEmpty) {
      throw StateError('لا يمكن فتح غرفة بثّ بلا مصادقة.');
    }
    return RealtimeRoom(
      baseWsUrl: baseWsUrl,
      path: path,
      token: token,
      guard: guard,
    );
  }

  /// غرفة خليّة السوق. `cellId` يأتي جاهزًا في ردود الخادم — مثل
  /// `JAB:sy390vj` — ولا يُحسب في التطبيق.
  RealtimeRoom marketplaceRoom(String cellId) =>
      room('/ws/marketplace/$cellId/');

  Future<void> logout() async {
    await auth.logout();
    await config.clearCache();
  }

  /// `https://x/api/v1` ← `wss://x` ، و`http://x:8000/api/v1` ← `ws://x:8000`.
  static String _deriveWsUrl(String baseUrl) {
    final uri = Uri.parse(baseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    final port = uri.hasPort ? ':${uri.port}' : '';
    return '$scheme://${uri.host}$port';
  }
}
