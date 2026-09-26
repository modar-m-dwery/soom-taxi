/// الشاشة الرئيسية — خريطة حيّة وطلب رحلة.
///
/// الترتيب على الشاشة يتبع ما يفعله الزبون فعلًا: يرى السيارات حوله،
/// يحدّد وجهته، يختار درجة الخدمة، يطلب. وهذا هو ترتيب البطاقة السفلية.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' hide TextDirection;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

import '../../providers.dart';
import '../auction/auction_screen.dart';
import '../catalog/catalog_screen.dart';
import '../trip/trip_screen.dart';
import '../history/history_screen.dart';
import '../map/marketplace_controller.dart';
import '../notifications/channels_screen.dart';
import '../perks/perks_screen.dart';
import '../map/vehicle_marker.dart';
import '../ride/ride_controller.dart';
import 'ad_banner.dart';
import 'request_sheet.dart';
import 'services_strip.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _map = OsmMapController();

  GeoPoint? _pickup;
  GeoPoint? _destination;
  bool _pickingDestination = false;

  DispatchStyle _style = DispatchStyle.offers;
  double? _radiusKm;

  /// «اختر سيارتك»: السائق الذي لمسه الزبون.
  int? _pickedDriverId;

  /// الخدمة المختارة من الشريط، وعدّادٌ يجعل كلّ لمسة تُطبَّق.
  String _service = 'taxi';
  int _presetTick = 0;

  void _onService(ServiceInfo service) {
    if (service.isComingSoon) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          SnackBar(
            content: Text(
              SoumStrings.of(context).serviceComingSoon(service.name),
            ),
          ),
        );
      return;
    }
    switch (service.code) {
      case 'published_trips':
        _open(const CatalogScreen());
      case 'morning_subscription':
        final pickup = _pickup;
        if (pickup != null) _open(PerksScreen(pickup: pickup));
      default:
        setState(() {
          _service = service.code;
          _presetTick++;
        });
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _locate());
  }

  Future<void> _locate() async {
    final config = ref.read(configProvider);

    // موقع المستخدم إن أذن، وإلّا مركز المدينة من الإعداد. شاشةٌ فارغة
    // بانتظار إذنٍ قد لا يُمنح ليست خيارًا.
    //
    // آخر موقع معروف أوّلًا: فوريّ، والشاشة تُرسم بلا انتظار. ثمّ موقعٌ حيّ
    // يصحّحه إن اختلف. انتظارُ الحيّ وحده علّق الشاشة على «نحدّد موقعك»
    // أكثر من مهلته عند كلّ عودة للرئيسية — `timeLimit` لا يُحترم على كلّ
    // جهاز، فالمهلة هنا من `Future.timeout` لا من الإعداد (قِيس على المحاكي).
    GeoPoint? here;
    var permitted = false;
    try {
      final permission = await Geolocator.checkPermission();
      permitted =
          permission == LocationPermission.always ||
          permission == LocationPermission.whileInUse;
      if (permitted) {
        final last = await Geolocator.getLastKnownPosition().timeout(
          const Duration(seconds: 2),
          onTimeout: () => null,
        );
        if (last != null) here = GeoPoint(last.latitude, last.longitude);
      }
    } on Object {
      here = null;
    }

    if (permitted) {
      final cached = here;
      if (cached == null) {
        here = await _liveFix();
      } else {
        unawaited(_refine(cached));
      }
    }

    final center = here ?? _fallbackCenter(config);
    if (!mounted) return;

    setState(() => _pickup = center);
    _map.moveTo(_aboveSheet(center), zoom: 15);
    ref.read(marketplaceControllerProvider.notifier).followCamera(center);

    // مدينة الإعداد قد تكون افتراضًا لا موقعًا (§0.1). بموقعٍ حقيقيّ نعيد
    // حلّها، فتتبعها خليّة السوق ونصف القطر والمهل.
    if (here != null) {
      unawaited(ref.read(bootControllerProvider.notifier).resolveArea(here));
    }
  }

  /// جبلة حين لا موقع. ليس رقمًا سحريًّا: المنطقة الأولى الفعّالة في
  /// الخادم، والإعداد لا يرسل مركزها اليوم — فنبدأ منها ونصحّح فور
  /// وصول الموقع.
  GeoPoint _fallbackCenter(AppConfig config) =>
      const GeoPoint(35.3608, 35.9236);

  Future<GeoPoint?> _liveFix() async {
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      ).timeout(const Duration(seconds: 8));
      return GeoPoint(position.latitude, position.longitude);
    } on Object {
      return null;
    }
  }

  /// الموقع المخزَّن قديمٌ ربّما: الحيّ يصحّحه إن ابتعد أكثر من 50 مترًا.
  Future<void> _refine(GeoPoint cached) async {
    final live = await _liveFix();
    if (live == null || !mounted) return;
    if (distanceMeters(cached, live) < 50) return;
    setState(() => _pickup = live);
    _map.moveTo(_aboveSheet(live), zoom: 15);
    ref.read(marketplaceControllerProvider.notifier).followCamera(live);
  }

  /// بطاقة الطلب تغطّي نصف الشاشة السفليّ. مركزُ الكاميرا على الزبون يُخفيه
  /// ويُخفي السيارات الأقرب إليه تحتها — فنُنزل المركز قليلًا ليظهر الزبون
  /// في الثلث العلويّ. ~700 م عند زوم 15 تقارب ربع ارتفاع الشاشة.
  GeoPoint _aboveSheet(GeoPoint point) =>
      GeoPoint(point.lat - 0.0065, point.lng);

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final config = ref.watch(configProvider);
    final market = ref.watch(marketplaceControllerProvider);
    final pickup = _pickup;

    // النطاق المختار يحكم ما يُرسم: سيارةٌ خارج النطاق لن تصلها الرحلة،
    // فعرضُها وعدٌ كاذب — والخادم يفلتر بالرقم نفسه.
    final radiusKm = _radiusKm ?? config.geometry.matchingRadiusKm;
    final fleet = pickup == null
        ? const <NearbyVehicle>[]
        : market.visible
              .where(
                (v) =>
                    distanceMeters(pickup, v.position) <= radiusKm * 1000 + 150,
              )
              .toList(growable: false);
    final picking = _style == DispatchStyle.pick;
    final picked = picking
        ? fleet.where((v) => v.driverId == _pickedDriverId).firstOrNull
        : null;

    return Scaffold(
      body: Stack(
        children: [
          if (pickup != null)
            SoumMap(
              controller: _map,
              initialCamera: MapStart(center: pickup, zoom: 15),
              circles: [searchRadius(context, pickup, radiusKm)],
              markers: [
                pointMarker(
                  id: 'pickup',
                  position: pickup,
                  icon: Icons.trip_origin_rounded,
                  color: Theme.of(context).colorScheme.secondary,
                ),
                if (_destination != null)
                  pointMarker(
                    id: 'destination',
                    position: _destination!,
                    icon: Icons.place_rounded,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                for (final vehicle in fleet)
                  vehicleMarker(
                    vehicle,
                    isSelected: vehicle.driverId == picked?.driverId,
                    // البطاقات كلّها حين يختار الزبون سيارة؛ وإلّا تزدحم
                    // الخريطة بعشرين بطاقة لا يحتاجها.
                    showLabel: picking || fleet.length <= 6,
                    onTap: () => setState(() {
                      // في وضع «حدّد على الخريطة» اللمسة وجهةٌ حتّى فوق
                      // سيارة: السيارات تتحرّك تحت إصبع الزبون، ولمسةٌ
                      // تصيب إحداها كانت تحوّله إلى «اختر سيارتك» بلا قصد.
                      if (_pickingDestination) {
                        _destination = vehicle.position;
                        _pickingDestination = false;
                        return;
                      }
                      if (!picking) _style = DispatchStyle.pick;
                      _pickedDriverId = vehicle.driverId;
                    }),
                  ),
              ],
              onTap: _pickingDestination
                  ? (point) => setState(() {
                      _destination = point;
                      _pickingDestination = false;
                    })
                  : null,
              onCameraIdle: (viewport) => ref
                  .read(marketplaceControllerProvider.notifier)
                  .followCamera(viewport.center),
            )
          else
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(strokeWidth: 2.4),
                  const SizedBox(height: 14),
                  Text(
                    strings.homeLocating,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),

          SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // الأزرار صفٌّ وحده، والشريط تحته: أربعة أزرار وشريط
                // «لا سيارات ضمن ٥ كم» لا يتّسعان معًا على شاشة ضيّقة.
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    _RoundAction(
                      icon: Icons.receipt_long_rounded,
                      tooltip: strings.historyTitle,
                      onTap: () => _open(const HistoryScreen()),
                    ),
                    // الدعوة والرصيد هنا، والاشتراك في شريط الخدمات.
                    if (pickup != null && config.feature('referral'))
                      _RoundAction(
                        icon: Icons.card_giftcard_rounded,
                        tooltip: strings.perksTitle,
                        onTap: () => _open(PerksScreen(pickup: pickup)),
                      ),
                    _RoundAction(
                      icon: Icons.notifications_none_rounded,
                      tooltip: strings.notificationsTitle,
                      onTap: () => _open(const NotificationsScreen()),
                    ),
                    const SizedBox(width: 8),
                  ],
                ),
                _FleetBanner(
                  config: config,
                  count: fleet.length,
                  isConnected: market.isConnected,
                  radiusKm: radiusKm,
                ),
                if (ref.watch(rideControllerProvider).ride?.isScheduled == true)
                  _UpcomingCard(
                    ride: ref.watch(rideControllerProvider).ride!,
                    offers: ref.watch(rideControllerProvider).offers.length,
                    confirmed:
                        ref.watch(rideControllerProvider).stage !=
                            ResumeStage.searching &&
                        ref.watch(rideControllerProvider).stage !=
                            ResumeStage.choosingOffer,
                    onOpen: () => _open(
                      ref.read(rideControllerProvider).stage ==
                                  ResumeStage.searching ||
                              ref.read(rideControllerProvider).stage ==
                                  ResumeStage.choosingOffer
                          ? const AuctionScreen()
                          : const TripScreen(),
                    ),
                    onCancel: () =>
                        ref.read(rideControllerProvider.notifier).cancelRide(),
                  ),
              ],
            ),
          ),

          if (pickup != null)
            Align(
              alignment: Alignment.bottomCenter,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: AdBanner(
                      placement: 'customer_home',
                      height: 72,
                      onOpenService: (code) {
                        final service = config.services
                            .where((s) => s.code == code)
                            .firstOrNull;
                        if (service != null) _onService(service);
                      },
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
                    child: ServicesStrip(
                      services: config.services,
                      selected: _service,
                      onSelect: _onService,
                    ),
                  ),
                  RequestSheet(
                    preset: (_service, _presetTick),
                    style: _style,
                    pickup: pickup,
                    destination: _destination,
                    selectedVehicle: picked,
                    onPickDestination: () =>
                        setState(() => _pickingDestination = true),
                    onStyleChanged: (style) => setState(() => _style = style),
                    onRadiusChanged: (km) => setState(() => _radiusKm = km),
                    onSubmit: _submit,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  void _open(Widget screen) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
  }

  Future<void> _submit(RideRequestDraft draft) async {
    final ride = await ref
        .read(rideControllerProvider.notifier)
        .createRide(
          pickup: draft.pickup,
          destination: draft.destination,
          mode: draft.mode,
          passengerCount: draft.passengerCount,
          vehicleType: draft.vehicleType,
          scheduledAt: draft.scheduledAt,
          tripCategory: draft.category,
          originCity: draft.originCity,
          destinationCity: draft.destinationCity,
          searchRadiusKm: draft.searchRadiusKm,
          autoDispatch: draft.autoDispatch,
        );

    if (!mounted) return;

    if (ride == null) {
      final error = ref.read(rideControllerProvider).lastError;
      if (error != null) showApiError(context, error);
      return;
    }

    // «اختر سيارتك»: الطلب أُنشئ، والدعوة للسائق المختار فورًا. إن فشلت
    // (انشغل السائق بين اللمس والطلب) يبقى الزبون على شاشة العروض ويدعو
    // غيره — لا يضيع طلبه.
    final driverId = draft.inviteDriverId;
    if (driverId != null) {
      final invited = await ref
          .read(rideControllerProvider.notifier)
          .inviteDriver(driverId);
      if (!invited && mounted) {
        final error = ref.read(rideControllerProvider).lastError;
        if (error != null) showApiError(context, error);
      }
    }
    if (mounted) setState(() => _pickedDriverId = null);
    // النجاح لا يحتاج تنقّلًا: القشرة تتبع `stage`، والحالة تغيّرت.
  }
}

/// شريط يقول ما تقوله الخريطة بالأرقام.
///
/// «لا سيارات ضمن ٥ كم» أصدق من خريطة فارغة: الرقم من
/// `matching_radius_km` نفسه الذي يفلتر به الخادم، فالرسالة والواقع
/// متطابقان بلا تخمين.
class _RoundAction extends StatelessWidget {
  const _RoundAction({
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsetsDirectional.only(start: 6, top: 12),
      child: Material(
        color: theme.colorScheme.surface,
        shape: const CircleBorder(),
        elevation: 1.5,
        child: IconButton(
          icon: Icon(icon, size: 20),
          tooltip: tooltip,
          onPressed: onTap,
        ),
      ),
    );
  }
}

class _FleetBanner extends StatelessWidget {
  const _FleetBanner({
    required this.config,
    required this.count,
    required this.isConnected,
    required this.radiusKm,
  });

  final AppConfig config;
  final int count;
  final bool isConnected;
  final double radiusKm;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);

    final label = config.areaCode == null
        ? strings.homeOutsideArea
        : count == 0
        ? strings.homeNoCarsInRange(radiusLabelNumber(radiusKm))
        : strings.homeCarsNearby(count);

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      child: Align(
        alignment: AlignmentDirectional.topStart,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.1),
                blurRadius: 6,
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isConnected
                      ? theme.colorScheme.secondary
                      : theme.colorScheme.outline,
                ),
              ),
              const SizedBox(width: 8),
              Text(label, style: theme.textTheme.labelMedium),
            ],
          ),
        ),
      ),
    );
  }
}

/// موعدٌ محجوز: بطاقة صغيرة تحت شريط الأسطول. تقول متى، وكم عرضًا وصل،
/// وتفتح شاشة العروض بضغطة — والرئيسية تبقى للمشوار الفوريّ.
class _UpcomingCard extends StatelessWidget {
  const _UpcomingCard({
    required this.ride,
    required this.offers,
    required this.confirmed,
    required this.onOpen,
    required this.onCancel,
  });

  final RideRequest ride;
  final int offers;
  final bool confirmed;
  final VoidCallback onOpen;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final locale = Localizations.localeOf(context).toString();
    final when = ride.scheduledAt!;

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: Material(
        color: theme.colorScheme.onSurface,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onOpen,
          borderRadius: BorderRadius.circular(14),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
            child: Row(
              children: [
                Icon(
                  confirmed
                      ? Icons.event_available_rounded
                      : Icons.hourglass_top_rounded,
                  color: theme.colorScheme.primary,
                  size: 22,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        strings.upcomingTitle(
                          DateFormat(
                            strings.scheduleFormat,
                            locale,
                          ).format(when),
                        ),
                        style: theme.textTheme.labelLarge?.copyWith(
                          color: theme.colorScheme.primary,
                        ),
                      ),
                      Text(
                        confirmed
                            ? strings.upcomingConfirmed
                            : offers == 0
                            ? strings.upcomingWaiting
                            : strings.offersTitle(offers),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.surface.withValues(
                            alpha: 0.75,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: strings.actionCancel,
                  icon: Icon(
                    Icons.close_rounded,
                    color: theme.colorScheme.surface,
                  ),
                  onPressed: onCancel,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
