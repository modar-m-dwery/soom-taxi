/// بطاقة «لماذا هذا السعر».
///
/// §4.1 في وثيقة المنتج: «كلّ مكوّن يعود في الاستجابة منفصلًا. الزبون يرى
/// لماذا هذا السعر لا رقمًا نهائيًّا فقط — وهذه هي الشفافية التي تمنع نصف
/// الشكاوى قبل وقوعها».
///
/// و`route_source` يظهر هنا لا في مكان آخر: «سعر تقريبي» تعني أنّ الخادم
/// لم يصل إلى مزوّد الخرائط فحسب المسافة بخطّ مستقيم مضروبًا في معامل
/// التفاف. إخفاء ذلك يجعل فرق السعر عن الواقع شكوى بلا جواب.
library;

import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';

import '../l10n/generated/soum_strings.dart';
import 'money_text.dart';

class FareCard extends StatelessWidget {
  const FareCard({
    super.key,
    required this.fare,
    required this.routeSource,
    this.distanceKm,
    this.durationMinutes,
  });

  final FareBreakdown fare;
  final RouteSource routeSource;
  final String? distanceKm;
  final int? durationMinutes;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final isApproximate = routeSource.isApproximate;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    strings.fareBreakdownTitle,
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                _SourceChip(isApproximate: isApproximate),
              ],
            ),
            const SizedBox(height: 14),
            _Line(label: strings.fareBase, amount: fare.baseFare),
            _Line(label: strings.fareDistance, amount: fare.distanceFare),
            _Line(label: strings.fareTime, amount: fare.timeFare),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Divider(height: 1),
            ),
            _Line(
              label: strings.fareCustomerTotal,
              amount: fare.customerTotal,
              emphasize: true,
            ),
            // العمولة صفر في النسخة الحالية. عرض سطر بصفر يثير سؤالًا بلا
            // داعٍ، وإخفاؤه يوم تُفعَّل يخفي اقتطاعًا حقيقيًّا — فالشرط
            // على القيمة لا على النسخة.
            if (!fare.platformFee.isZero) ...[
              const SizedBox(height: 6),
              _Line(label: strings.farePlatformFee, amount: fare.platformFee),
              const SizedBox(height: 6),
              _Line(label: strings.fareDriverNet, amount: fare.driverNet),
            ],
            if (isApproximate) ...[
              const SizedBox(height: 12),
              Text(
                strings.fareApproximateNote,
                style: theme.textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SourceChip extends StatelessWidget {
  const _SourceChip({required this.isApproximate});

  final bool isApproximate;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final scheme = Theme.of(context).colorScheme;

    final color = isApproximate ? scheme.tertiary : scheme.secondary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        isApproximate ? strings.fareApproximate : strings.fareRouted,
        style: Theme.of(context)
            .textTheme
            .labelSmall
            ?.copyWith(color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.label, required this.amount, this.emphasize = false});

  final String label;
  final Money amount;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: emphasize
                  ? theme.textTheme.titleMedium
                  : theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
            ),
          ),
          MoneyText(
            amount,
            style: emphasize
                ? theme.textTheme.titleLarge
                : theme.textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}
