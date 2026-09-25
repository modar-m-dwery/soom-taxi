/// شريط الخدمات — من كتالوج المشغّل لا من قائمة مكتوبة هنا.
///
/// خدمةٌ يطفئها المشغّل تختفي من الشريط فورًا بلا إصدار، وخدمةٌ قادمة
/// («تأجير سيارات»، «نقل عفش»، «عراضة») تظهر بشارة «قريبًا» — يعرف الزبون
/// أنّ التطبيق يكبر قبل أن تصل.
library;

import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_ui/soum_ui.dart';

class ServicesStrip extends StatelessWidget {
  const ServicesStrip({
    super.key,
    required this.services,
    required this.selected,
    required this.onSelect,
  });

  final List<ServiceInfo> services;
  final String selected;
  final ValueChanged<ServiceInfo> onSelect;

  @override
  Widget build(BuildContext context) {
    if (services.length < 2) return const SizedBox.shrink();

    return SizedBox(
      height: 78,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: services.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final service = services[index];
          return _ServiceTile(
            service: service,
            isSelected: service.code == selected,
            onTap: () => onSelect(service),
          );
        },
      ),
    );
  }
}

class _ServiceTile extends StatelessWidget {
  const _ServiceTile({
    required this.service,
    required this.isSelected,
    required this.onTap,
  });

  final ServiceInfo service;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final soon = service.isComingSoon;

    final ink = isSelected
        ? scheme.primary
        : soon
        ? scheme.onSurfaceVariant
        : scheme.onSurface;

    return Material(
      color: isSelected ? scheme.onSurface : scheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: SizedBox(
          width: 84,
          child: Stack(
            children: [
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(serviceIcon(service.icon), size: 24, color: ink),
                    const SizedBox(height: 4),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 4),
                      child: Text(
                        service.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: ink,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (soon)
                PositionedDirectional(
                  top: 4,
                  end: 4,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 5,
                      vertical: 1,
                    ),
                    decoration: BoxDecoration(
                      color: scheme.tertiary,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      strings.serviceSoon,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: scheme.onTertiary,
                        fontSize: 9.5,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// أسماء أيقونات Material التي يرسلها الكتالوج. غير المعروف يُرسم أيقونةً
/// عامّة بدل أن يختفي — المشغّل قد يضيف خدمة قبل أن يعرف التطبيق أيقونتها.
IconData serviceIcon(String name) => switch (name) {
  'local_taxi' => Icons.local_taxi_rounded,
  'groups' => Icons.groups_rounded,
  'route' => Icons.route_rounded,
  'directions_bus' => Icons.directions_bus_rounded,
  'event_seat' => Icons.event_seat_rounded,
  'wb_twilight' => Icons.wb_twilight_rounded,
  'car_rental' => Icons.car_rental_rounded,
  'local_shipping' => Icons.local_shipping_rounded,
  'chair' => Icons.chair_rounded,
  'celebration' => Icons.celebration_rounded,
  'delivery_dining' => Icons.delivery_dining_rounded,
  _ => Icons.apps_rounded,
};
