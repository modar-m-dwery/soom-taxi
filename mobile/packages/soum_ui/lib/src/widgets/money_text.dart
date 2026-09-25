import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';

import '../l10n/generated/soum_strings.dart';
import '../theme/soum_theme.dart';

/// مبلغ معروض — بأرقام جدولية ورمز العملة.
///
/// القيمة تبقى `Money` حتّى هنا. هذا الودجت هو «اللحظة الأخيرة» التي
/// يذكرها الدليل، وما قبله لا تقريب ولا تحويل إلى عائم.
class MoneyText extends StatelessWidget {
  const MoneyText(
    this.amount, {
    super.key,
    this.style,
    this.showCurrency = true,
  });

  final Money amount;
  final TextStyle? style;
  final bool showCurrency;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final base = style ?? Theme.of(context).textTheme.titleMedium!;
    final locale = Localizations.localeOf(context).languageCode;

    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: amount.format(locale: locale),
            style: SoumTheme.tabular(base),
          ),
          if (showCurrency)
            TextSpan(
              text: ' ${_symbol(strings, amount.currency)}',
              style: base.copyWith(
                fontSize: (base.fontSize ?? 16) * 0.72,
                fontWeight: FontWeight.w500,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }

  static String _symbol(SoumStrings strings, String currency) =>
      currency == 'SYP' ? strings.currencySyp : currency;
}
