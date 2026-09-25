import 'package:decimal/decimal.dart';
import 'package:equatable/equatable.dart';

import 'enums.dart';
import 'json.dart';
import 'money.dart';

class Payment extends Equatable {
  Payment({
    required this.id,
    required this.tripId,
    required this.rideId,
    required this.amount,
    Money? discountAmount,
    this.discountReason = '',
    required this.platformFee,
    required this.driverNet,
    required this.amountRefunded,
    required this.refundableAmount,
    required this.currency,
    required this.gatewayCode,
    required this.status,
    this.failureReason = '',
    this.paidAt,
  }) : discountAmount = discountAmount ?? Money(Decimal.zero, currency);

  final int id;
  final int tripId;
  final int rideId;
  /// ما يدفعه الزبون فعلًا = الأجرة المتّفق عليها - الخصم.
  final Money amount;

  /// الخصم الترويجيّ (أوّل مشوار، رصيد إحالة). صفر إن لم يكن.
  final Money discountAmount;

  /// `first_ride` أو `credit` أو فارغ.
  final String discountReason;

  final Money platformFee;
  final Money driverNet;
  final Money amountRefunded;
  final Money refundableAmount;
  final String currency;

  /// `cash` في النسخة الحالية. طبقة البوّابات مبنيّة كاملةً وتنتظر مزوّدًا.
  final String gatewayCode;

  final PaymentStatus status;
  final String failureReason;
  final DateTime? paidAt;

  bool get isCash => gatewayCode == 'cash';

  /// قيدٌ أمنيّ يصمّم الشاشة: في النقد، السائق وحده — أو الإدارة — من
  /// يؤكّد القبض. زرّ «دفعتُ» في تطبيق الزبون يردّ 403، فلا يوضع أصلًا.
  bool get awaitingDriverConfirmation =>
      isCash && status == PaymentStatus.pending;

  factory Payment.fromJson(Json json) {
    final currency = readString(json, 'currency', fallback: Money.defaultCurrency);
    return Payment(
      id: readInt(json, 'id'),
      tripId: readInt(json, 'trip_id'),
      rideId: readInt(json, 'ride_id'),
      amount: readMoney(json, 'amount', currency: currency),
      discountAmount: readMoney(json, 'discount_amount', currency: currency),
      discountReason: readString(json, 'discount_reason'),
      platformFee: readMoney(json, 'platform_fee', currency: currency),
      driverNet: readMoney(json, 'driver_net', currency: currency),
      amountRefunded: readMoney(json, 'amount_refunded', currency: currency),
      refundableAmount: readMoney(json, 'refundable_amount', currency: currency),
      currency: currency,
      gatewayCode: readString(json, 'gateway_code'),
      status: PaymentStatus.from(readStringOrNull(json, 'status')),
      failureReason: readString(json, 'failure_reason'),
      paidAt: readDateOrNull(json, 'paid_at'),
    );
  }

  @override
  List<Object?> get props => [id, status, amount, gatewayCode];
}
