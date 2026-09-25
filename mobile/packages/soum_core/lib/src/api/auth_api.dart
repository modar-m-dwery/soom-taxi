import '../models/json.dart';
import '../models/user.dart';
import '../network/api_client.dart';
import '../storage/session.dart';

/// نتيجة طلب الرمز.
class OtpChallenge {
  const OtpChallenge({required this.expiresAt, this.developmentCode});

  final DateTime? expiresAt;

  /// §1.1: يعود في الجسم في وضع التطوير وحده، ويختفي تمامًا حين
  /// `DEBUG=False`. اقرأه اختياريًّا ولا تبنِ عليه منطقًا دائمًا —
  /// وجودُه هو ما يوفّر اشتراك الرسائل أثناء البناء.
  final String? developmentCode;

  bool get hasDevelopmentCode => developmentCode != null;

  factory OtpChallenge.fromJson(Json json) => OtpChallenge(
        expiresAt: readDateOrNull(json, 'expires_at'),
        developmentCode: readStringOrNull(json, 'development_code'),
      );
}

class AuthApi {
  AuthApi(this._client, this._session);

  final ApiClient _client;
  final SessionStore _session;

  /// §1.2: `device_id` ليس اختياريًّا — الحدّ يُحسب على الهاتف والجهاز
  /// والعنوان معًا.
  Future<OtpChallenge> requestOtp(String phone) async {
    final body = await _client.post<dynamic>('/auth/request-otp/', body: {
      'phone': phone,
      'device_id': await _session.deviceId(),
    });
    return OtpChallenge.fromJson(asJson(body));
  }

  /// يحفظ المفتاح عند النجاح ويعيد المستخدم.
  Future<AppUser> verifyOtp(String phone, String code) async {
    final body = await _client.post<dynamic>('/auth/verify-otp/', body: {
      'phone': phone,
      'device_id': await _session.deviceId(),
      'code': code,
    });

    final json = asJson(body);
    final token = readString(json, 'token');
    if (token.isNotEmpty) await _session.saveToken(token);

    return AppUser.fromJson(asJson(json['user']));
  }

  Future<AppUser> me() async =>
      AppUser.fromJson(asJson(await _client.get<dynamic>('/auth/me/')));

  Future<AppUser> becomeDriver() async =>
      AppUser.fromJson(asJson(await _client.post<dynamic>('/auth/become-driver/')));

  /// يُبطل المفتاح على الخادم ثمّ يمحوه محلّيًّا.
  ///
  /// الترتيب مقصود: محوُه أوّلًا يعني أنّ النداء يخرج بلا مصادقة فيفشل،
  /// ويبقى المفتاح صالحًا على الخادم إلى الأبد.
  Future<void> logout() async {
    try {
      await _client.post<dynamic>('/auth/logout/');
    } finally {
      await _session.clearToken();
    }
  }
}
