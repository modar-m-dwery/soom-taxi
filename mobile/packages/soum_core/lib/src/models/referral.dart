/// «زبون يجلب زبونًا» — رمزي، ورصيدي، وهل ما زال خصم أوّل مشوار ينتظرني.
library;

import 'package:equatable/equatable.dart';

import 'json.dart';
import 'money.dart';

class Referral extends Equatable {
  const Referral({
    required this.referralCode,
    required this.referredByCode,
    required this.creditBalance,
    required this.firstRideDiscountAvailable,
  });

  final String referralCode;

  /// رمز من دعاني — `null` إن لم أُدخل رمزًا بعد.
  final String? referredByCode;
  final Money creditBalance;
  final bool firstRideDiscountAvailable;

  bool get hasReferrer => referredByCode != null;

  factory Referral.fromJson(Json json) {
    final currency = readString(json, 'currency', fallback: Money.defaultCurrency);
    return Referral(
      referralCode: readString(json, 'referral_code'),
      referredByCode: readStringOrNull(json, 'referred_by_code'),
      creditBalance: readMoney(json, 'credit_balance', currency: currency),
      firstRideDiscountAvailable:
          readBool(json, 'first_ride_discount_available'),
    );
  }

  @override
  List<Object?> get props =>
      [referralCode, referredByCode, creditBalance, firstRideDiscountAvailable];
}
