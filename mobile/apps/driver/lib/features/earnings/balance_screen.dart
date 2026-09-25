/// الرصيد وتحصيل النقد.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

final balanceProvider = FutureProvider.autoDispose<DriverBalance>(
  (ref) => ref.read(soumProvider).driver.balance(),
);

/// الحوافز — تُطلب وحدها: فشلها لا يُخفي الرصيد.
final incentivesProvider = FutureProvider.autoDispose<List<IncentiveProgress>>(
  (ref) => ref.read(soumProvider).driver.incentives(),
);

class BalanceScreen extends ConsumerWidget {
  const BalanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final balance = ref.watch(balanceProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.balanceTitle)),
      body: balance.when(
        loading: () =>
            const Center(child: CircularProgressIndicator(strokeWidth: 2.4)),
        error: (error, _) => Center(
          child: ApiErrorView(
            failure: error is ApiException
                ? error
                : ApiException(
                    statusCode: 0,
                    code: ApiErrorCode.networkUnavailable,
                    detail: '$error',
                  ),
            onRetry: () => ref.invalidate(balanceProvider),
          ),
        ),
        data: (data) => ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(22),
                child: Column(
                  children: [
                    Text(
                      data.owesPlatform
                          ? strings.balanceYouOwe
                          : strings.balanceTotal,
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 8),
                    MoneyText(
                      data.owesPlatform ? data.amountOwedToPlatform : data.total,
                      style: theme.textTheme.displaySmall?.copyWith(
                        color: data.owesPlatform
                            ? theme.colorScheme.error
                            : theme.colorScheme.secondary,
                      ),
                    ),
                    const SizedBox(height: 8),
                    // الرصيد الموجب حالةٌ تحتاج شرحًا: سائقٌ رأى «3,000» بلا
                    // كلمة يظنّها خطأً أو عمولةً عليه.
                    Text(
                      data.total.isZero && !data.owesPlatform
                          ? strings.balanceZero
                          : data.owesPlatform
                              ? strings.balanceYouOwe
                              : strings.balanceOwedToYou,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    _Line(
                      label: strings.balanceLifetimeEarned,
                      value: data.lifetimeEarned,
                    ),
                    const SizedBox(height: 8),
                    _Line(
                      label: strings.balanceLifetimeCommission,
                      value: data.lifetimeCommission,
                    ),
                  ],
                ),
              ),
            ),
            ...ref.watch(incentivesProvider).maybeWhen(
                  data: (rows) => [
                    if (rows.isNotEmpty) ...[
                      const SizedBox(height: 20),
                      Text(strings.incentivesTitle,
                          style: theme.textTheme.titleLarge),
                      const SizedBox(height: 8),
                      for (final row in rows) _IncentiveCard(row: row),
                    ],
                  ],
                  orElse: () => const <Widget>[],
                ),
          ],
        ),
      ),
    );
  }
}

/// بطاقة تحصيل النقد بعد إنهاء الرحلة.
///
/// §6.3 — السائق وحده من يؤكّد القبض. زرّ التأكيد **هنا** لأنّ نظيره في
/// تطبيق الزبون يردّ 403، وهو قيدٌ أمنيّ لا تفصيل واجهة: الزبون لا
/// يستطيع تأكيد قبض مالٍ لم يُقبَض.
class CollectCard extends ConsumerWidget {
  const CollectCard({
    super.key,
    required this.payment,
    required this.isBusy,
    required this.onCollect,
  });

  final Payment payment;
  final bool isBusy;
  final VoidCallback onCollect;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(strings.collectTitle, style: theme.textTheme.titleLarge),
            const SizedBox(height: 14),
            Row(
              children: [
                Text(strings.paymentAmount, style: theme.textTheme.bodyMedium),
                const Spacer(),
                MoneyText(payment.amount, style: theme.textTheme.displaySmall),
              ],
            ),
            const SizedBox(height: 10),
            Text(strings.collectNote, style: theme.textTheme.bodySmall),
            // خصمٌ على الزبون لا على السائق: يقبض من الزبون أقلّ، ويبقى
            // الفرق دَينًا له على المنصّة. بلا هذا السطر يظنّ السائق أنّ
            // أجرته نقصت — وهو أوّل ما سيسأل عنه في المجموعة.
            if (!payment.discountAmount.isZero) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(11),
                decoration: BoxDecoration(
                  color: theme.colorScheme.secondary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  strings.collectDiscountNote(
                    payment.amount.format(),
                    payment.discountAmount.format(),
                    payment.driverNet.format(),
                  ),
                  style: theme.textTheme.bodySmall,
                ),
              ),
            ],
            const SizedBox(height: 18),
            FilledButton(
              onPressed: isBusy || payment.status.isSettled ? null : onCollect,
              child: Text(
                payment.status.isSettled
                    ? strings.collectDone
                    : strings.collectConfirm,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.label, required this.value});

  final String label;
  final Money value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Text(label, style: theme.textTheme.bodyMedium),
        const Spacer(),
        MoneyText(value, style: theme.textTheme.titleMedium),
      ],
    );
  }
}

/// حافزٌ واحد: الهدف، التقدّم، والمكافأة — شريطٌ يمتلئ بالأصفر.
class _IncentiveCard extends StatelessWidget {
  const _IncentiveCard({required this.row});

  final IncentiveProgress row;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    final status = row.earned
        ? (row.awardStatus == 'delivered'
            ? strings.incentiveDelivered
            : strings.incentiveEarned(row.rewardLabel))
        : strings.incentiveRemaining(row.remainingTrips, row.rewardLabel);

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(
                  row.earned
                      ? Icons.emoji_events_rounded
                      : Icons.local_gas_station_rounded,
                  color: theme.colorScheme.tertiary,
                ),
                const SizedBox(width: 8),
                Expanded(child: Text(row.name, style: theme.textTheme.titleMedium)),
                Text(
                  '${row.completedTrips}/${row.targetTrips}',
                  style: SoumTheme.tabular(theme.textTheme.titleMedium!),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: row.fraction,
                minHeight: 10,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
              ),
            ),
            const SizedBox(height: 8),
            Text(status, style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
