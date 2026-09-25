/// المال — `Decimal` لا `double`، في كلّ الطبقة.
///
/// من §3.2 و§12.1 في دليل التكامل:
///
/// > الأرقام المالية كلّها نصوص عشرية لا أعداد عائمة — مرّرها كـ decimal
/// > في تطبيقك ولا تقربها للعرض إلّا في اللحظة الأخيرة.
///
/// الخادم يبني الأجرة من خمسة مكوّنات ثمّ يقيّدها بأرضية وسقف، ويحفظ
/// النتيجة في `DecimalField`. وتمثيل `5512.00` بـIEEE-754 يُدخل خطأً في
/// الخانة الأخيرة؛ خطأٌ لا يظهر في رحلة واحدة، لكنّه يظهر في رصيد سائق بعد
/// ثلاثمئة رحلة — وحينها يكون فرقُ رقمين في شكوى لا جواب لها.
///
/// `Money` هنا ليست غلافًا مزخرفًا: جعلُ النوع مختلفًا عن `double` هو ما
/// يجعل تمرير أجرة إلى دالّة تتوقّع عائمًا **خطأ ترجمة** لا عطلًا صامتًا.
library;

import 'package:decimal/decimal.dart';
import 'package:equatable/equatable.dart';
import 'package:intl/intl.dart';

class Money extends Equatable implements Comparable<Money> {
  const Money(this.amount, this.currency);

  final Decimal amount;

  /// رمز العملة كما يرسله الخادم — `SYP` في جبلة، وقد يختلف بمنطقة أخرى.
  final String currency;

  static const defaultCurrency = 'SYP';

  /// من نصّ الخادم. `null` و`""` تعنيان صفرًا لا خطأً: حقول مثل
  /// `platform_fee` تعود صفرًا في النسخة الحالية، و`counter_fare` تغيب.
  factory Money.parse(Object? raw, [String currency = defaultCurrency]) {
    if (raw == null) return Money(Decimal.zero, currency);

    if (raw is num) {
      // الخادم لا يرسل أرقامًا للحقول المالية، لكن حقلًا جديدًا قد يفعل.
      // نمرّ عبر النصّ لا عبر double حتّى لا نُدخل الخطأ الذي نتجنّبه.
      return Money(Decimal.parse(raw.toString()), currency);
    }

    final text = raw.toString().trim();
    if (text.isEmpty) return Money(Decimal.zero, currency);

    final parsed = Decimal.tryParse(text);
    if (parsed == null) {
      throw FormatException('قيمة مالية غير صالحة: "$text"');
    }
    return Money(parsed, currency);
  }

  /// كما تُرسل إلى الخادم: نصّ بخانتين عشريّتين.
  String toApi() => amount.toStringAsFixed(2);

  Money operator +(Money other) {
    _assertSameCurrency(other);
    return Money(amount + other.amount, currency);
  }

  Money operator -(Money other) {
    _assertSameCurrency(other);
    return Money(amount - other.amount, currency);
  }

  bool operator <(Money other) => compareTo(other) < 0;
  bool operator >(Money other) => compareTo(other) > 0;
  bool operator <=(Money other) => compareTo(other) <= 0;
  bool operator >=(Money other) => compareTo(other) >= 0;

  bool get isZero => amount == Decimal.zero;

  @override
  int compareTo(Money other) {
    _assertSameCurrency(other);
    return amount.compareTo(other.amount);
  }

  void _assertSameCurrency(Money other) {
    assert(
      currency == other.currency,
      'جمع عملتين مختلفتين: $currency و ${other.currency}',
    );
  }

  /// للعرض وحده — وهذه هي اللحظة الأخيرة المقصودة في الدليل.
  ///
  /// بلا كسور: الليرة السورية لا تُتداول بالقروش عمليًّا، وعرض `5512.00`
  /// يشغل مساحة ويقرأه المستخدم أبطأ بلا أن يضيف معلومة.
  String format({String locale = 'ar'}) {
    final formatter = NumberFormat.decimalPattern(locale)
      ..maximumFractionDigits = 0;
    return formatter.format(amount.toDouble());
  }

  @override
  List<Object?> get props => [amount, currency];

  @override
  String toString() => '${toApi()} $currency';
}
