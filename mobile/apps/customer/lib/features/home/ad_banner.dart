/// إعلانٌ في مكانٍ واحد — يظهر فقط حين يفعّل المشغّل ميزة `ads` ويوجد
/// إعلانٌ حيّ لهذه المدينة. غيابه لا يترك فراغًا: لا ارتفاع ولا مكان محجوز.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:soum_core/soum_core.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers.dart';

final adsProvider = FutureProvider.autoDispose.family<List<AdItem>, String>((ref, placement) async {
  final config = ref.watch(configProvider);
  if (!config.feature('ads')) return const [];
  try {
    return await ref.read(soumProvider).ads.list(placement, area: config.areaCode);
  } on ApiException {
    return const [];
  }
});

class AdBanner extends ConsumerStatefulWidget {
  const AdBanner({super.key, required this.placement, this.onOpenService, this.height = 84});

  final String placement;
  final double height;
  final ValueChanged<String>? onOpenService;

  @override
  ConsumerState<AdBanner> createState() => _AdBannerState();
}

class _AdBannerState extends ConsumerState<AdBanner> {
  final _counted = <int>{};

  @override
  Widget build(BuildContext context) {
    final ads = ref.watch(adsProvider(widget.placement)).value ?? const <AdItem>[];
    if (ads.isEmpty) return const SizedBox.shrink();
    final ad = ads.first;

    // ظهورٌ واحد لكلّ إعلان في عمر الشاشة، لا مع كلّ إعادة بناء.
    if (_counted.add(ad.id)) {
      unawaited(ref.read(soumProvider).ads.event(ad.id, 'impression'));
    }

    return Semantics(
      label: ad.title,
      button: ad.opensLink || ad.serviceCode.isNotEmpty,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: Material(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          child: InkWell(
            onTap: () => _open(ad),
            child: SizedBox(
              height: widget.height,
              width: double.infinity,
              child: Image.network(
                ad.imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => const SizedBox.shrink(),
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _open(AdItem ad) {
    unawaited(ref.read(soumProvider).ads.event(ad.id, 'click'));
    if (ad.serviceCode.isNotEmpty) {
      widget.onOpenService?.call(ad.serviceCode);
    } else if (ad.opensLink) {
      unawaited(launchUrl(Uri.parse(ad.linkUrl), mode: LaunchMode.externalApplication));
    }
  }
}
