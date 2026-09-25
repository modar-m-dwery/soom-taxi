import 'package:flutter/material.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_maps/soum_maps.dart';
import 'package:soum_ui/soum_ui.dart';

/// علامة السيارة على الخريطة: سيارةٌ من فوق تدور مع اتجاه سيرها، وبطاقةٌ
/// صغيرة فوقها بما يحتاجه الزبون ليختار — التقييم، واسم السائق الأوّل،
/// ودقائق الوصول، ومقاعدها نقاطًا إن كانت في رحلة مشتركة.
///
/// سيارةٌ فيها ركّاب تُميَّز بصريًّا عن الفارغة: `is_sharing` يعني مقعدًا
/// شاغرًا في رحلة قائمة، وهو خيارٌ مختلف تمامًا عن استئجار السيارة كاملةً.
/// إخفاء الفرق يجعل الزبون يدعو سيارة يظنّها فارغة.
///
/// مركز العلامة هو مركز السيارة لا مركز البطاقة: الصندوق متناظر عموديًّا
/// والبطاقة في نصفه العلويّ، فتقع السيارة على موضعها الحقيقيّ بالضبط.
MapMarker vehicleMarker(
  NearbyVehicle vehicle, {
  required bool isSelected,
  required VoidCallback onTap,
  bool showLabel = true,
}) =>
    MapMarker(
      id: 'driver-${vehicle.driverId}',
      position: vehicle.position,
      size: const Size(_boxWidth, _boxHeight),
      rotationDegrees: vehicle.routeBearing,
      animate: true,
      builder: (context) => _VehiclePin(
        vehicle: vehicle,
        isSelected: isSelected,
        showLabel: showLabel,
        onTap: onTap,
      ),
    );

/// سيارة السائق في رحلة جارية — بلا بطاقة، وتنزلق مع كلّ موقع.
MapMarker driverCarMarker(GeoPoint position) => MapMarker(
      id: 'my-driver',
      position: position,
      size: const Size(_carBox, _carBox),
      animate: true,
      builder: (context) {
        final scheme = Theme.of(context).colorScheme;
        return _Car(
          heading: MarkerHeading.of(context) ?? 0,
          body: scheme.primary,
          outline: scheme.onSurface,
        );
      },
    );

const _carBox = 44.0;
const _labelHeight = 26.0;
const _boxWidth = 176.0;
const _boxHeight = _carBox + 2 * (_labelHeight + 4);

class _VehiclePin extends StatelessWidget {
  const _VehiclePin({
    required this.vehicle,
    required this.isSelected,
    required this.showLabel,
    required this.onTap,
  });

  final NearbyVehicle vehicle;
  final bool isSelected;
  final bool showLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final heading = MarkerHeading.of(context) ?? vehicle.routeBearing ?? 0;
    final body = vehicle.isSharing ? scheme.secondary : scheme.primary;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.deferToChild,
      child: Column(
        children: [
          SizedBox(
            height: _labelHeight + 4,
            child: showLabel || isSelected
                ? Center(
                    child: _Label(vehicle: vehicle, isSelected: isSelected),
                  )
                : null,
          ),
          SizedBox(
            width: _carBox,
            height: _carBox,
            child: _Car(
              heading: heading,
              body: body,
              outline: scheme.onSurface,
              isSelected: isSelected,
            ),
          ),
        ],
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label({required this.vehicle, required this.isSelected});

  final NearbyVehicle vehicle;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    final strings = SoumStrings.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    // المختارة لوحة التاكسي مقلوبة كبقيّة التطبيق: حبرٌ داكن بنصٍّ أصفر.
    final background = isSelected ? scheme.onSurface : scheme.surface;
    final ink = isSelected ? scheme.primary : scheme.onSurface;
    final style = SoumTheme.tabular(theme.textTheme.labelSmall!)
        .copyWith(color: ink, fontWeight: FontWeight.w600, height: 1.1);

    final name = driverFirstName(vehicle.driverName);
    final soft = isSelected ? ink : scheme.secondary;

    final parts = <Widget>[
      // صفرٌ يعني «لم يُقيَّم بعد» لا «أسوأ سائق»: نقول «جديد».
      if (vehicle.rating case final rating? when rating > 0) ...[
        Icon(Icons.star_rounded, size: 12, color: isSelected ? ink : scheme.tertiary),
        Text(rating.toStringAsFixed(1), style: style),
      ] else
        Text(strings.carNew, style: style.copyWith(color: soft)),
      const SizedBox(width: 5),
      // الاسم الأوّل وحده: يكفي ليعرف الزبون من سيأتيه، والاسم الكامل لا
      // يظهر إلّا بعد القبول.
      Flexible(
        child: Text(
          name.isEmpty ? vehicle.vehicleLabel : name,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: style,
        ),
      ),
      const SizedBox(width: 5),
      // «0 د» يقرأها الزبون «لن يأتي»؛ السيارة التي بجانبه دقيقة.
      Text(
        strings.unitMinutes(vehicle.etaMinutes < 1 ? 1 : vehicle.etaMinutes),
        style: style.copyWith(color: soft),
      ),
      if (vehicle.isSharing) ...[
        const SizedBox(width: 5),
        SeatDots(
          occupied: vehicle.onboardPassengers ?? vehicle.currentOccupancy,
          total: vehicle.seats > 0
              ? vehicle.seats
              : (vehicle.onboardPassengers ?? vehicle.currentOccupancy) +
                  vehicle.availableSeats,
          color: isSelected ? ink : scheme.onSurface,
          semanticLabel: strings.carPassengers(
            vehicle.onboardPassengers ?? vehicle.currentOccupancy,
          ),
        ),
      ],
    ];

    return Container(
      constraints: const BoxConstraints(maxWidth: _boxWidth),
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.outlineVariant, width: 0.8),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.14),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: parts),
    );
  }
}

/// الاسم الأوّل من اسم السائق — `driver_name` يصل كاملًا من الخادم.
String driverFirstName(String fullName) {
  final trimmed = fullName.trim();
  if (trimmed.isEmpty) return '';
  return trimmed.split(RegExp(r'\s+')).first;
}

/// «محمد ع.» — الاسم الأوّل وأوّل حرف من الثاني.
///
/// قبل القبول لا يُعرض اسم السائق كاملًا (قرار الخصوصية في وثيقة المنتج):
/// الاسم الكامل مع نوع السيارة ولونها يكفي لتعقّب السائق خارج العمل.
String driverShortName(String fullName) {
  final words = fullName.trim().split(RegExp(r'\s+'))
    ..removeWhere((w) => w.isEmpty);
  if (words.isEmpty) return '';
  if (words.length == 1) return words.first;
  return '${words.first} ${words[1].characters.first}.';
}

/// مقاعد السيارة المشتركة نقاطًا: الممتلئة مصمتة والشاغرة مفرّغة.
///
/// نقاطٌ لا نصّ: «●●○○» تُقرأ من نظرة على خريطة مزدحمة، و«2 ركّاب من 4»
/// لا تتّسع في البطاقة. النصّ نفسه يبقى لقارئ الشاشة.
class SeatDots extends StatelessWidget {
  const SeatDots({
    super.key,
    required this.occupied,
    required this.total,
    required this.color,
    this.semanticLabel,
  });

  /// أكثر من ثمانية مقاعد (سرفيس) تُختصر: النقاط للمح لا للعدّ.
  static const maxDots = 8;

  final int occupied;
  final int total;
  final Color color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final count = total.clamp(0, maxDots);
    final filled = occupied.clamp(0, count);

    return Semantics(
      label: semanticLabel,
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < count; i++)
            Container(
              width: 6,
              height: 6,
              margin: const EdgeInsetsDirectional.only(end: 1.5),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: i < filled ? color : null,
                border: Border.all(color: color, width: 1),
              ),
            ),
        ],
      ),
    );
  }
}

/// سيارة من فوق، مقدّمتها إلى الشمال عند اتجاه صفر.
class _Car extends StatelessWidget {
  const _Car({
    required this.heading,
    required this.body,
    required this.outline,
    this.isSelected = false,
  });

  final double heading;
  final Color body;
  final Color outline;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: heading * 3.1415926535 / 180,
      child: CustomPaint(
        painter: _CarPainter(
          body: body,
          outline: outline,
          isSelected: isSelected,
        ),
      ),
    );
  }
}

class _CarPainter extends CustomPainter {
  _CarPainter({
    required this.body,
    required this.outline,
    required this.isSelected,
  });

  final Color body;
  final Color outline;
  final bool isSelected;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width * 0.46;
    final h = size.height * 0.86;
    final car = Rect.fromCenter(
      center: size.center(Offset.zero),
      width: w,
      height: h,
    );
    final shape = RRect.fromRectAndRadius(car, Radius.circular(w * 0.34));

    // الظلّ يفصل السيارة عن بلاطات الخريطة الفاتحة والداكنة معًا.
    canvas.drawRRect(
      shape.shift(const Offset(0, 1.5)),
      Paint()
        ..color = Colors.black.withValues(alpha: 0.22)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2.5),
    );

    if (isSelected) {
      canvas.drawRRect(
        shape.inflate(3.5),
        Paint()..color = outline,
      );
    }

    canvas.drawRRect(shape, Paint()..color = body);
    canvas.drawRRect(
      shape,
      Paint()
        ..color = outline.withValues(alpha: 0.85)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.3,
    );

    final glass = Paint()..color = outline.withValues(alpha: 0.78);

    // الزجاج الأماميّ أعرض من الخلفيّ: به تُقرأ جهة السير من نظرة.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(car.left + w * 0.12, car.top + h * 0.2, w * 0.76, h * 0.17),
        Radius.circular(w * 0.1),
      ),
      glass,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(car.left + w * 0.16, car.top + h * 0.72, w * 0.68, h * 0.11),
        Radius.circular(w * 0.08),
      ),
      glass,
    );

    // لافتة التاكسي على السقف.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: Offset(car.center.dx, car.top + h * 0.52),
          width: w * 0.42,
          height: h * 0.1,
        ),
        Radius.circular(w * 0.06),
      ),
      Paint()..color = outline,
    );
  }

  @override
  bool shouldRepaint(_CarPainter old) =>
      old.body != body || old.outline != outline || old.isSelected != isSelected;
}

/// علامة ثابتة — الانطلاق أو الوجهة.
MapMarker pointMarker({
  required String id,
  required GeoPoint position,
  required IconData icon,
  required Color color,
}) =>
    MapMarker(
      id: id,
      position: position,
      size: const Size(34, 34),
      builder: (context) => Container(
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: Theme.of(context).colorScheme.surface,
            width: 2.5,
          ),
        ),
        // الأيقونة بلون النصّ المقابل للّون لا بالأبيض: على الأصفر يلزم حبرٌ داكن.
        child: Icon(icon, size: 17, color: _onColor(color)),
      ),
    );

/// حبرٌ داكن على الفاتح، أبيض على الداكن — بحساب الإضاءة لا بالتخمين.
Color _onColor(Color color) =>
    color.computeLuminance() > 0.45 ? const Color(0xFF1A1500) : Colors.white;

/// دائرة نطاق البحث.
///
/// نصف قطرها نطاق الزبون إن اختار واحدًا، وإلّا `matching_radius_km` —
/// نفس الرقم الذي يفلتر به الخادم. رسمُها برقم آخر يجعل الشاشة تَعِد بما
/// لا يفي به الخادم.
MapCircle searchRadius(BuildContext context, GeoPoint center, double km) {
  final scheme = Theme.of(context).colorScheme;
  return MapCircle(
    center: center,
    radiusMeters: km * 1000,
    color: scheme.primary.withValues(alpha: 0.07),
    borderColor: scheme.primary.withValues(alpha: 0.35),
  );
}
