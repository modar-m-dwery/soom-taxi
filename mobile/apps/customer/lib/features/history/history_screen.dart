/// سجلّ الرحلات والمسار المسجَّل.
///
/// §12.4: «جرّب على `seed_scale` لا على ثلاثة حسابات — القوائم الطويلة
/// تكشف ما لا تكشفه القصيرة». لذلك القائمة كسولة (`ListView.builder`)
/// والصفوف ثابتة الارتفاع: قائمةٌ تبني كلّ صفوفها مرّة واحدة تتجمّد على
/// جهاز متوسّط عند بضع مئات.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../finish/complaint_sheet.dart';

final myTripsProvider = FutureProvider.autoDispose<List<Trip>>(
  (ref) => ref.read(soumProvider).rides.myTrips(),
);

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final trips = ref.watch(myTripsProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.historyTitle)),
      body: trips.when(
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
            onRetry: () => ref.invalidate(myTripsProvider),
          ),
        ),
        data: (rows) {
          if (rows.isEmpty) {
            return Center(
              child: Text(
                strings.historyEmpty,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            );
          }

          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: rows.length,
            separatorBuilder: (_, _) => const SizedBox(height: 8),
            itemBuilder: (context, index) => _TripRow(trip: rows[index]),
          );
        },
      ),
    );
  }
}

class _TripRow extends StatelessWidget {
  const _TripRow({required this.trip});

  final Trip trip;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();
    final when = trip.completedAt ?? trip.createdAt;

    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: trip.gpsPointsCount > 0
            ? () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => TripPathScreen(rideId: trip.rideId),
                  ),
                )
            : null,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(trip.driverName,
                              style: theme.textTheme.titleMedium,
                              overflow: TextOverflow.ellipsis),
                        ),
                        // الحالة رقاقةً لا لونًا وحده: الملغاة والقادمة
                        // تُقرآن من بعيد، والمكتملة لا تحتاج وسمًا.
                        if (trip.status != TripStatus.completed) ...[
                          const SizedBox(width: 8),
                          _StatusPill(status: trip.status),
                        ],
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      DateFormat.yMMMd(locale).add_jm().format(when),
                      style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                    ),
                    // الرحلة الموسومة للمراجعة تُعرض كما هي: إخفاء الوسم
                    // عن الزبون يجعل شكواه بلا سياق.
                    if (trip.needsReview)
                      Text(
                        trip.reviewReason,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.tertiary,
                        ),
                      ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  MoneyText(trip.finalFare, style: theme.textTheme.titleMedium),
                  if (trip.gpsPointsCount > 0)
                    Text(
                      strings.historyViewPath,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.tertiary,
                      ),
                    ),
                ],
              ),
              IconButton(
                tooltip: strings.complaintOpen,
                icon: const Icon(Icons.flag_outlined, size: 19),
                onPressed: () => showComplaintSheet(context, trip.rideId),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// المسار المسجَّل — نقاط GPS كما حفظها الخادم.
class TripPathScreen extends ConsumerWidget {
  const TripPathScreen({super.key, required this.rideId});

  final int rideId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = SoumStrings.of(context);
    final path = ref.watch(_pathProvider(rideId));

    return Scaffold(
      appBar: AppBar(title: Text(strings.historyViewPath)),
      body: path.when(
        loading: () => const Center(
          child: CircularProgressIndicator(strokeWidth: 2.4),
        ),
        error: (_, _) => Center(child: Text(strings.errorGeneric)),
        data: (points) {
          if (points.isEmpty) {
            return Center(child: Text(strings.historyEmpty));
          }

          final controller = OsmMapController();
          WidgetsBinding.instance.addPostFrameCallback(
            (_) => controller.fitPoints(points),
          );

          return SoumMap(
            controller: controller,
            initialCamera: MapStart(center: points.first, zoom: 14),
            polylines: [
              MapPolyline(
                points: points,
                color: Theme.of(context).colorScheme.primary,
                width: 4,
              ),
            ],
          );
        },
      ),
    );
  }
}

final _pathProvider =
    FutureProvider.autoDispose.family<List<GeoPoint>, int>(
  (ref, rideId) => ref.read(soumProvider).rides.tripPath(rideId),
);

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status});

  final TripStatus status;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final scheme = Theme.of(context).colorScheme;
    final (label, color) = switch (status) {
      TripStatus.cancelled => (strings.historyStatusCancelled, scheme.error),
      TripStatus.disputed => (strings.historyStatusDisputed, scheme.tertiary),
      TripStatus.completed => ('', scheme.secondary),
      _ => (strings.historyStatusUpcoming, scheme.secondary),
    };
    if (label.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context)
            .textTheme
            .labelSmall
            ?.copyWith(color: color, fontWeight: FontWeight.w700),
      ),
    );
  }
}
