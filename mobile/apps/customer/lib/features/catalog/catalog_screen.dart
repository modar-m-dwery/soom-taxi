/// كتالوج الرحلات المنشورة — سفريات وسرفيس ورحلات ترفيهية.
///
/// لا مطابقة هنا: العرض موجود قبل الطلب. السائق نشر مقاعد بسعر وموعد،
/// والزبون يحجز.
///
/// وما لا يُعرض هنا مقصود: الكتالوج عامّ، فإحداثيات الانطلاق مقرَّبة إلى
/// ~110 أمتار ولا رقم هاتف فيه. إحداثيةٌ دقيقة مربوطة باسم سائق وموعدٍ
/// معلن هي عنوانٌ وموعد.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

final _catalogProvider = FutureProvider.autoDispose
    .family<List<ScheduledSharedTrip>, String?>(
  (ref, category) =>
      ref.read(soumProvider).sharing.publishedTrips(category: category),
);

class CatalogScreen extends ConsumerStatefulWidget {
  const CatalogScreen({super.key});

  @override
  ConsumerState<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends ConsumerState<CatalogScreen> {
  String? _category;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final trips = ref.watch(_catalogProvider(_category));

    return Scaffold(
      appBar: AppBar(title: Text(strings.catalogTitle)),
      body: Column(
        children: [
          // شريطٌ يُمرَّر أفقيًّا: أربع رقائق عربية لا تتّسع في 360 نقطة
          // (فاضت 101 نقطة على المحاكي)، والقصّ يُخفي «الكلّ».
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(
              children: [
                for (final entry in <(String?, String)>[
                  (null, strings.catalogFilterAll),
                  ('intercity', strings.categoryIntercity),
                  ('service_line', strings.categoryServiceLine),
                  ('recreational', strings.categoryRecreational),
                ]) ...[
                  ChoiceChip(
                    label: Text(entry.$2),
                    visualDensity: VisualDensity.compact,
                    selected: _category == entry.$1,
                    onSelected: (_) => setState(() => _category = entry.$1),
                  ),
                  const SizedBox(width: 6),
                ],
              ],
            ),
          ),
          Expanded(
            child: trips.when(
              loading: () => const Center(
                child: CircularProgressIndicator(strokeWidth: 2.4),
              ),
              error: (error, _) => Center(
                child: ApiErrorView(
                  failure: error is ApiException
                      ? error
                      : ApiException(
                          statusCode: 0,
                          code: ApiErrorCode.networkUnavailable,
                          detail: '$error',
                        ),
                  onRetry: () => ref.invalidate(_catalogProvider(_category)),
                ),
              ),
              data: (rows) => rows.isEmpty
                  ? Center(
                      child: Text(
                        strings.catalogEmpty,
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: rows.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 8),
                      itemBuilder: (context, index) => _TripCard(
                        trip: rows[index],
                        onBook: () => _book(rows[index]),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _book(ScheduledSharedTrip trip) async {
    try {
      await ref.read(soumProvider).sharing.bookPublishedTrip(tripId: trip.id);
      if (!mounted) return;

      final strings = SoumStrings.of(context);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(strings.catalogBooked)));

      ref.invalidate(_catalogProvider(_category));
      await ref.read(bootControllerProvider.notifier).refreshActiveRide();
    } on ApiException catch (error) {
      if (!mounted) return;
      final strings = SoumStrings.of(context);
      // امتلاء المقاعد بين العرض والحجز — السباق نفسه.
      final message =
          error.statusCode == 409 ? strings.sharedFull : error.detail;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(message)));
      ref.invalidate(_catalogProvider(_category));
    }
  }
}

class _TripCard extends StatelessWidget {
  const _TripCard({required this.trip, required this.onBook});

  final ScheduledSharedTrip trip;
  final VoidCallback onBook;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();

    final route = [trip.originCity, trip.destinationCity]
        .where((city) => city != null && city.isNotEmpty)
        .join(' ← ');

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        trip.title?.isNotEmpty == true ? trip.title! : route,
                        style: theme.textTheme.titleMedium,
                      ),
                      if (route.isNotEmpty && trip.title?.isNotEmpty == true)
                        Text(route, style: theme.textTheme.bodySmall),
                      const SizedBox(height: 2),
                      Text(
                        strings.catalogDeparts(
                          DateFormat.MMMEd(locale)
                              .add_jm()
                              .format(trip.scheduledAt),
                        ),
                        style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                      ),
                    ],
                  ),
                ),
                if (trip.pricePerSeat != null)
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      MoneyText(trip.pricePerSeat!,
                          style: theme.textTheme.titleLarge),
                      Text(strings.catalogPricePerSeat,
                          style: theme.textTheme.labelSmall),
                    ],
                  ),
              ],
            ),

            if (trip.features.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final feature in trip.features)
                    Chip(
                      label: Text(feature),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                ],
              ),
            ],

            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(trip.driverName, style: theme.textTheme.bodySmall),
                      Text(
                        strings.sharedSeatsLeft(trip.remainingCapacity),
                        style: theme.textTheme.labelSmall,
                      ),
                    ],
                  ),
                ),
                FilledButton(
                  onPressed: trip.hasRoom ? onBook : null,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(110, 38),
                  ),
                  child: Text(strings.catalogBook),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
