import 'package:decimal/decimal.dart';
import 'package:equatable/equatable.dart';

import 'json.dart';
import 'money.dart';
import 'ride.dart';

/// قواعد «سوم» بنمط inDrive — نسخة العميل من `MatchingService.proposal_bounds`.
///
/// الخادم هو الحكم؛ هذه الحدود كي لا يضغط المستخدم زرًّا سيُرفض. وتُقرَّب
/// كلّها إلى `step` لأعلى، فتقع دائمًا داخل حدود الخادم لا على حافّتها.
class FareProposalRules extends Equatable {
  const FareProposalRules({
    required this.minRatio,
    required this.counterRatio,
    required this.step,
  });

  static final defaults = FareProposalRules(
    minRatio: Decimal.parse('0.70'),
    counterRatio: Decimal.parse('1.50'),
    step: Decimal.parse('500'),
  );

  /// بلا سقف في المنطقة: ثلاثة أضعاف التسعيرة (كالخادم) — يمنع صفرًا زائدًا.
  static final _sanityCap = Decimal.fromInt(3);

  /// أدنى سعر يعرضه الزبون كنسبة من تسعيرة المنصّة.
  final Decimal minRatio;

  /// أعلى عرض للسائق كنسبة من سعر الزبون.
  final Decimal counterRatio;

  /// خطوة زرّي − و+.
  final Decimal step;

  factory FareProposalRules.fromJson(Json json) {
    Decimal read(String key, Decimal fallback) =>
        Decimal.tryParse(readString(json, key)) ?? fallback;
    final step = read('customer_proposal_step', defaults.step);
    return FareProposalRules(
      minRatio: read('customer_proposal_min_ratio', defaults.minRatio),
      counterRatio: read('customer_proposal_counter_ratio', defaults.counterRatio),
      step: step > Decimal.zero ? step : defaults.step,
    );
  }

  Json toJson() => {
        'customer_proposal_min_ratio': minRatio.toString(),
        'customer_proposal_counter_ratio': counterRatio.toString(),
        'customer_proposal_step': step.toString(),
      };

  /// يقرّب لأعلى إلى أقرب مضاعف للخطوة.
  Money roundUp(Money value) {
    final steps = (value.amount / step).ceil();
    return Money(Decimal.fromBigInt(steps) * step, value.currency);
  }

  /// أدنى ما يعرضه الزبون الآن: أوّل مرّة نسبةٌ من التسعيرة، وبعدها خطوةٌ
  /// فوق سعره المعروض (يُرفع ولا يُخفض).
  Money minFor(RideRequest ride) {
    final current = ride.customerProposedFare;
    if (current != null) return roundUp(current + Money(step, current.currency));
    final gross = ride.fare.grossFare;
    return roundUp(Money(gross.amount * minRatio, gross.currency));
  }

  /// أعلى ما يعرضه الزبون.
  Money maxFor(RideRequest ride) {
    final gross = ride.fare.grossFare;
    return ride.fare.fareCap ?? Money(gross.amount * _sanityCap, gross.currency);
  }

  /// نقطة البداية في شاشة الزبون: سعره المعروض + خطوة، وإلّا التسعيرة.
  Money suggestedFor(RideRequest ride) {
    final floor = minFor(ride);
    final start = ride.customerProposedFare == null
        ? roundUp(ride.fare.grossFare)
        : floor;
    return start < floor ? floor : start;
  }

  /// أعلى عرض للسائق على سعر الزبون: نسبة المنطقة، ولا يتجاوز سقفها.
  Money counterCap(RideRequest ride) {
    final proposed = ride.customerProposedFare!;
    var cap = Money(proposed.amount * counterRatio, proposed.currency);
    final areaCap = ride.fare.fareCap;
    if (areaCap != null && areaCap < cap) cap = areaCap;
    return cap < proposed ? proposed : cap;
  }

  /// عروض السائق الجاهزة: بسعر الزبون، ثمّ +5٪ و+10٪ و+15٪ مقرَّبة لأعلى
  /// إلى الخطوة، ضمن السقف ومن غير تكرار.
  List<Money> quickCounters(RideRequest ride) {
    final proposed = ride.customerProposedFare!;
    final cap = counterCap(ride);
    final result = <Money>[proposed];
    for (final pct in const ['1.05', '1.10', '1.15']) {
      final raw = Money(proposed.amount * Decimal.parse(pct), proposed.currency);
      final rounded = roundUp(raw);
      if (rounded > cap) break;
      if (!result.contains(rounded)) result.add(rounded);
    }
    return result;
  }

  @override
  List<Object?> get props => [minRatio, counterRatio, step];
}
