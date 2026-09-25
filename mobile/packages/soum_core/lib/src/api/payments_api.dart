import '../models/json.dart';
import '../models/payment.dart';
import '../models/referral.dart';
import '../network/api_client.dart';

class PaymentGateway {
  const PaymentGateway({
    required this.code,
    required this.name,
    required this.isEnabled,
  });

  final String code;
  final String name;
  final bool isEnabled;

  factory PaymentGateway.fromJson(Json json) => PaymentGateway(
        code: readString(json, 'code'),
        name: readString(json, 'name'),
        isEnabled: readBool(json, 'is_enabled', fallback: true),
      );
}

class PaymentsApi {
  PaymentsApi(this._client);

  final ApiClient _client;

  Future<List<PaymentGateway>> gateways() async {
    final body = await _client.get<dynamic>('/payments/gateways/');
    return readResults(body).map(PaymentGateway.fromJson).toList(growable: false);
  }

  Future<Payment> forTrip(int rideId) async =>
      Payment.fromJson(asJson(await _client.get<dynamic>('/trips/$rideId/payment/')));

  /// §6.3 — قيدٌ أمنيّ يصمّم الشاشة: في الدفع النقدي، السائق وحده — أو
  /// الإدارة — من يؤكّد القبض. نداؤها من تطبيق الزبون يردّ 403، ولذلك
  /// لا يوضع زرّها في تطبيق الزبون أصلًا.
  Future<Payment> charge(int rideId, {String? gatewayCode}) async =>
      Payment.fromJson(asJson(await _client.post<dynamic>(
        '/trips/$rideId/payment/charge/',
        body: {'gateway_code': ?gatewayCode},
      )));

  /// «زبون يجلب زبونًا»: رمزي ورصيدي.
  Future<Referral> myReferral() async =>
      Referral.fromJson(asJson(await _client.get<dynamic>('/me/referral/')));

  /// المدعوّ يُدخل رمز صديقه مرّةً واحدة قبل رحلته الأولى. الخادم يردّ
  /// 400 بنصّ عربيّ جاهز للعرض حين يخالف ذلك.
  Future<Referral> applyReferralCode(String code) async {
    final body = await _client.post<dynamic>('/me/referral/', body: {
      'code': code.trim().toUpperCase(),
    });
    return Referral.fromJson(asJson(body));
  }
}
