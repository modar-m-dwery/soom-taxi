/// شاشة البحث والمزاد.
///
/// العدّاد يُبنى على `ride.expires_at` لا على مدّة محسوبة محلّيًّا (§3.2)،
/// ودائرة البحث نصفُ قطرها `matching_radius_km` — نفس الرقم الذي يفلتر به
/// الخادم (§12.3). الرقمان معًا يجعلان الشاشة صادقة مع الخادم: العدّاد
/// ينتهي حين ينتهي الطلب فعلًا، والدائرة تَعِد بما يفي به.
library;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../map/marketplace_controller.dart';
import '../map/vehicle_marker.dart';
import '../invite/invite_sheet.dart';
import '../shared/shared_sheet.dart';
import '../ride/ride_controller.dart';
import '../ride/ride_state.dart';

class AuctionScreen extends ConsumerStatefulWidget {
  const AuctionScreen({super.key});

  @override
  ConsumerState<AuctionScreen> createState() => _AuctionScreenState();
}

class _AuctionScreenState extends ConsumerState<AuctionScreen> {
  final _map = OsmMapController();

  @override
  Widget build(BuildContext context) {
    final config = ref.watch(configProvider);
    final clock = ref.watch(clockProvider);
    final arc = ref.watch(rideControllerProvider);
    final ride = arc.ride;
    // السيارات الحيّة تبقى مرسومة أثناء البحث: زبونٌ يرى ثلاث سيارات تقترب
    // ينتظر، وزبونٌ يرى بياضًا يلغي. الاشتراك نفسه الذي فتحته الرئيسية.
    final market = ref.watch(marketplaceControllerProvider);

    if (ride == null) return const SizedBox.shrink();

    final pickup = ride.pickup;
    final canInvite = config.supportsInvitation(ride.mode.code);
    // المشاركة مدخلٌ آخر للنمط `shared` وحده: الخادم يبحث عن مجموعات
    // قائمة أو مجدولة متوافقة مع هذا الطلب تحديدًا.
    final canShare = ride.mode == RideMode.shared;
    // نطاق الزبون إن اختار واحدًا — هو ما يفلتر به الخادم هذا الطلب.
    final radiusKm = ride.searchRadiusKm ?? config.geometry.matchingRadiusKm;

    return Scaffold(
      body: Stack(
        children: [
          if (pickup != null)
            SoumMap(
              controller: _map,
              initialCamera: MapStart(center: pickup, zoom: 14),
              circles: [
                searchRadius(context, pickup, radiusKm),
              ],
              markers: [
                pointMarker(
                  id: 'pickup',
                  position: pickup,
                  icon: Icons.trip_origin_rounded,
                  color: Theme.of(context).colorScheme.secondary,
                ),
                if (ride.destination != null)
                  pointMarker(
                    id: 'destination',
                    position: ride.destination!,
                    icon: Icons.place_rounded,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                for (final vehicle in market.visible)
                  vehicleMarker(vehicle, isSelected: false, onTap: () {}),
              ],
            ),

          SafeArea(
            child: _SearchHeader(
              ride: ride,
              arc: arc,
              clock: clock,
              radiusKm: radiusKm,
              onCancel: () => ref
                  .read(rideControllerProvider.notifier)
                  .cancelRide(),
            ),
          ),

          Align(
            alignment: Alignment.bottomCenter,
            child: _OffersSheet(
              arc: arc,
              clock: clock,
              canInvite: canInvite,
              canShare: canShare,
              onSelect: _select,
              onInvite: () => showInviteSheet(context, ref),
              onShare: () => showSharedSheet(context, ride.id),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _select(int offerId) async {
    final ok = await ref.read(rideControllerProvider.notifier).selectOffer(offerId);
    if (ok || !mounted) return;

    final error = ref.read(rideControllerProvider).lastError;
    if (error == null) return;

    // §4.4 — «هذا سلوك متوقَّع لا عطل: اعرض «هذه السيارة لم تعد متاحة»
    // وأعد الزبون إلى القائمة محدَّثةً».
    //
    // والنصّ من التطبيق لا من الخادم هنا وحده: الخادم يردّ على هذا المسار
    // بنصّ إنجليزيّ («Driver has just been assigned to another ride.»)
    // لأنّ النقطة تلتقط الاستثناء قبل معالج الأخطاء الذي يعرّبه.
    final message = error.isDriverTaken
        ? SoumStrings.of(context).offerTaken
        : error.detail;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _SearchHeader extends StatelessWidget {
  const _SearchHeader({
    required this.ride,
    required this.arc,
    required this.clock,
    required this.radiusKm,
    required this.onCancel,
  });

  final RideRequest ride;
  final RideArc arc;
  final ServerClock clock;
  final double radiusKm;
  final VoidCallback onCancel;

  String _subtitle(SoumStrings strings) {
    if (ride.isScheduled) return strings.upcomingWaiting;
    if (arc.driverRequeued) return strings.driverCancelledRequeued;
    if (arc.isAutoDispatching) {
      return arc.invitation == null
          ? strings.nearestLooking
          : strings.nearestAsking;
    }
    if (arc.autoDispatchExhausted) return strings.nearestExhausted;
    return strings.searchingSubtitle(_km(radiusKm));
  }

  /// «0.5» لا «1» ولا «0»: نطاقٌ دون الكيلومتر حقيقيّ داخل المدينة.
  static String _km(double km) =>
      km < 1 ? km.toStringAsFixed(1) : km.toStringAsFixed(0);

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              // المجدول لا مهلة له: أيقونة موعد بدل حلقةٍ تعدّ من صفر.
              if (ride.isScheduled)
                Icon(Icons.event_available_rounded,
                    size: 40, color: theme.colorScheme.tertiary)
              else
                SoumCountdown(
                  deadline: ride.expiresAt,
                  clock: clock,
                  builder: (context, seconds) => CountdownRing(
                    secondsRemaining: seconds,
                    totalSeconds: _window(ride),
                    size: 46,
                  ),
                ),
              const SizedBox(width: 14),
              Expanded(
                // mainAxisSize.min: عمودٌ داخل صفٍّ داخل Stack يأخذ أقصى
                // ارتفاعٍ متاح — فكانت البطاقة تغطّي الخريطة كلّها والزبون
                // لا يرى السيارات التي يبحث بينها (العيب #8).
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      ride.isScheduled
                          ? strings.upcomingTitle(DateFormat(
                                  strings.scheduleFormat,
                                  Localizations.localeOf(context).toString())
                              .format(ride.scheduledAt!))
                          : arc.isAutoDispatching
                              ? strings.nearestTitle
                              : strings.searchingTitle,
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(_subtitle(strings), style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
              TextButton(onPressed: onCancel, child: Text(strings.actionCancel)),
            ],
          ),
        ),
      ),
    );
  }

  /// نافذة البحث الكاملة، لرسم الحلقة بنسبة صحيحة.
  ///
  /// تُحسب من الطلب نفسه لا من الإعداد: طلبٌ أُنشئ قبل أن يغيّر المشغّل
  /// النافذة يحمل مهلته هو، ورسمُه بنافذة جديدة يجعل الحلقة تبدأ ناقصة.
  static int _window(RideRequest ride) {
    final expires = ride.expiresAt;
    if (expires == null) return 600;
    final total = expires.difference(ride.createdAt).inSeconds;
    return total > 0 ? total : 600;
  }
}

class _OffersSheet extends StatelessWidget {
  const _OffersSheet({
    required this.arc,
    required this.clock,
    required this.canInvite,
    required this.canShare,
    required this.onSelect,
    required this.onInvite,
    required this.onShare,
  });

  final RideArc arc;
  final ServerClock clock;
  final bool canInvite;
  final bool canShare;
  final Future<void> Function(int) onSelect;
  final VoidCallback onInvite;
  final VoidCallback onShare;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.5,
      ),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.13),
            blurRadius: 14,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      arc.hasOffers
                          ? strings.offersTitle(arc.offers.length)
                          : strings.offersEmpty,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  // §5: الدعوة المباشرة تعمل مع fast و express وحدهما —
                  // من `invitation_allowed_modes` لا من افتراض.
                  if (canInvite)
                    TextButton.icon(
                      onPressed: onInvite,
                      icon: const Icon(Icons.touch_app_rounded, size: 18),
                      label: Text(strings.inviteTitle),
                    ),
                  if (canShare)
                    TextButton.icon(
                      onPressed: onShare,
                      icon: const Icon(Icons.groups_rounded, size: 18),
                      label: Text(strings.sharedTitle),
                    ),
                ],
              ),
            ),
            if (!arc.hasOffers)
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 4, 16, 22),
                child: LinearProgressIndicator(minHeight: 2),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: arc.offers.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, index) => OfferCard(
                    offer: arc.offers[index],
                    clock: clock,
                    isBusy: arc.isBusy,
                    onSelect: () => onSelect(arc.offers[index].id),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class OfferCard extends StatelessWidget {
  const OfferCard({
    super.key,
    required this.offer,
    required this.clock,
    required this.onSelect,
    this.isBusy = false,
  });

  final RideOffer offer;
  final ServerClock clock;
  final VoidCallback onSelect;
  final bool isBusy;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            // العدّاد على `expires_at` الخاصّ بالعرض: عرضٌ وصل متأخّرًا
            // مهلته المتبقّية أقلّ من مهلته الكاملة.
            SoumCountdown(
              deadline: offer.expiresAt,
              clock: clock,
              builder: (context, seconds) => CountdownRing(
                secondsRemaining: seconds,
                totalSeconds: offer.expiresAt
                    .difference(offer.expiresAt
                        .subtract(const Duration(seconds: 30)))
                    .inSeconds,
                size: 38,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(offer.driverName, style: theme.textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      if (offer.vehicle != null) ...[
                        Text(offer.vehicle!.label,
                            style: theme.textTheme.bodySmall),
                        const SizedBox(width: 8),
                      ],
                      Text(
                        strings.offerEta(offer.etaMinutes),
                        style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                      ),
                      if (offer.driverRating != null) ...[
                        const SizedBox(width: 8),
                        Icon(Icons.star_rounded,
                            size: 13, color: theme.colorScheme.tertiary),
                        Text(
                          offer.driverRating!.toStringAsFixed(1),
                          style: SoumTheme.tabular(theme.textTheme.bodySmall!),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                MoneyText(offer.grossFare, style: theme.textTheme.titleLarge),
                const SizedBox(height: 4),
                FilledButton(
                  onPressed: isBusy ? null : onSelect,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(80, 34),
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                  ),
                  child: Text(strings.offerChoose),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
