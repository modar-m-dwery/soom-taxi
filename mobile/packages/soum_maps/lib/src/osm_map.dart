/// تنفيذ OpenStreetMap — المزوّد المجّاني.
///
/// اختير لأنّه لا يحتاج مفتاحًا ولا حساب فوترة، فيمكن بناء التطبيقين
/// واختبارهما كاملين قبل شراء أيّ اشتراك. ويتناغم مع الخادم: محرّك
/// التوجيه فيه OSRM، وهندسة المسار التي يرسلها مبنيّة على بيانات OSM
/// نفسها — فالخطّ المرسوم يطابق الطريق الذي حُسب عليه السعر.
///
/// شرط استعمال بلاطات OSM العامّة: معرّف تطبيق صريح وحدّ معقول للطلبات.
/// النشر الحقيقي بحجم مدينة يحتاج خادم بلاطات خاصًّا أو اشتراكًا — وهو
/// قرارٌ لاحق لا يمسّ سطرًا واحدًا خارج هذا الملفّ.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:soum_core/soum_core.dart';

import 'map_provider.dart';
import 'marker_motion.dart';

LatLng _toLatLng(GeoPoint point) => LatLng(point.lat, point.lng);
GeoPoint _toGeo(LatLng point) => GeoPoint(point.latitude, point.longitude);

class OsmMapController implements SoumMapController {
  final MapController raw = MapController();

  /// هل رُسمت الخريطة مرّةً؟ قبلها `raw.move` يرمي استثناءً:
  /// «You need to have the FlutterMap widget rendered at least once».
  ///
  /// والسباق حقيقيّ لا نظريّ: الشاشة الرئيسية تطلب الموقع ثمّ تحرّك
  /// الكاميرا، وحين يعود الموقع قبل أوّل إطار — وهو ما يحدث بموقعٍ
  /// مخزَّن — ينفجر `moveTo` غير معالَج، ولا يُنفَّذ ما بعده: لا اشتراك
  /// في خليّة السوق، فتبقى الخريطة فارغة و«لا سيارات» بلا سبب ظاهر.
  /// الأمر الأخير يُحفظ ويُطبَّق عند `onMapReady`.
  bool _ready = false;
  void Function()? _pending;

  void _onReady() {
    _ready = true;
    final pending = _pending;
    _pending = null;
    pending?.call();
  }

  @override
  void moveTo(GeoPoint center, {double? zoom}) {
    if (!_ready) {
      _pending = () => moveTo(center, zoom: zoom);
      return;
    }
    raw.move(_toLatLng(center), zoom ?? raw.camera.zoom);
  }

  @override
  void fitPoints(List<GeoPoint> points, {EdgeInsets padding = const EdgeInsets.all(48)}) {
    if (points.isEmpty) return;
    if (points.length == 1) {
      moveTo(points.first, zoom: 16);
      return;
    }
    if (!_ready) {
      _pending = () => fitPoints(points, padding: padding);
      return;
    }
    raw.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(points.map(_toLatLng).toList()),
        padding: padding,
      ),
    );
  }

  @override
  MapViewport? get viewport {
    try {
      final camera = raw.camera;
      final bounds = camera.visibleBounds;
      return MapViewport(
        center: _toGeo(camera.center),
        zoom: camera.zoom,
        northEast: _toGeo(bounds.northEast),
        southWest: _toGeo(bounds.southWest),
      );
    } on Object {
      // قبل أوّل رسم لا كاميرا بعد. null أصدق من إحداثيات مخترَعة.
      return null;
    }
  }
}

class SoumMap extends StatelessWidget {
  const SoumMap({
    super.key,
    required this.controller,
    required this.initialCamera,
    this.markers = const [],
    this.polylines = const [],
    this.circles = const [],
    this.onTap,
    this.onCameraIdle,
    this.minZoom = 10,
    this.maxZoom = 18,
  });

  final OsmMapController controller;
  final MapStart initialCamera;
  final List<MapMarker> markers;
  final List<MapPolyline> polylines;
  final List<MapCircle> circles;

  /// اختيار نقطة — الانطلاق أو الوجهة.
  final void Function(GeoPoint)? onTap;

  /// استقرار الكاميرا. عليه يُبنى تبديل خليّة السوق: الاشتراك يتبع حركة
  /// الخريطة، ولا يُبدَّل مع كلّ إطار أثناء السحب.
  final void Function(MapViewport)? onCameraIdle;

  final double minZoom;
  final double maxZoom;

  @override
  Widget build(BuildContext context) {
    return FlutterMap(
      mapController: controller.raw,
      options: MapOptions(
        initialCenter: _toLatLng(initialCamera.center),
        initialZoom: initialCamera.zoom,
        minZoom: minZoom,
        maxZoom: maxZoom,
        onMapReady: controller._onReady,
        onTap: onTap == null ? null : (_, point) => onTap!(_toGeo(point)),
        onPositionChanged: (camera, hasGesture) {
          if (!hasGesture) return;
          final viewport = controller.viewport;
          if (viewport != null) onCameraIdle?.call(viewport);
        },
        interactionOptions: const InteractionOptions(
          // التدوير معطَّل عمدًا: خريطةٌ مائلة تجعل «الشمال» غير بديهيّ،
          // وهو ما يربك قارئًا يوازن بين الخريطة والشارع أمامه.
          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
        ),
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'sy.soum.taxi',
          maxNativeZoom: 19,
          // خريطةٌ فارغة بلا سبب هي أسوأ عطل يُشخَّص. في التطوير نطبع
          // سبب كلّ بلاطة فشلت — شبكة، شهادة، حظر — بدل الصمت.
          errorTileCallback: kDebugMode
              ? (tile, error, _) =>
                  debugPrint('[soum_maps] tile ${tile.coordinates}: $error')
              : null,
        ),
        if (circles.isNotEmpty)
          CircleLayer(
            circles: circles
                .map((circle) => CircleMarker(
                      point: _toLatLng(circle.center),
                      radius: circle.radiusMeters,
                      useRadiusInMeter: true,
                      color: circle.color,
                      borderColor: circle.borderColor,
                      borderStrokeWidth: circle.borderWidth,
                    ))
                .toList(growable: false),
          ),
        if (polylines.isNotEmpty)
          PolylineLayer(
            polylines: polylines
                .map((line) => Polyline(
                      points: line.points.map(_toLatLng).toList(growable: false),
                      color: line.color,
                      strokeWidth: line.width,
                      pattern: line.isDashed
                          ? const StrokePattern.dotted()
                          : const StrokePattern.solid(),
                    ))
                .toList(growable: false),
          ),
        if (markers.any((m) => m.animate))
          _MovingMarkers(
            markers: markers.where((m) => m.animate).toList(growable: false),
          ),
        if (markers.any((m) => !m.animate))
          MarkerLayer(
            markers: markers
                .where((m) => !m.animate)
                .map((marker) => Marker(
                      key: ValueKey(marker.id),
                      point: _toLatLng(marker.position),
                      width: marker.size.width,
                      height: marker.size.height,
                      alignment: Alignment.center,
                      child: marker.rotationDegrees == null
                          ? Builder(builder: marker.builder)
                          : Transform.rotate(
                              angle: marker.rotationDegrees! * 3.1415926535 / 180,
                              child: Builder(builder: marker.builder),
                            ),
                    ))
                .toList(growable: false),
          ),
        // إسناد البلاطات شرطُ استعمالها، لا تزيين.
        const _OsmAttribution(),
      ],
    );
  }
}

/// العلامات المتحرّكة — السيارات.
///
/// طبقةٌ منفصلة عن الثابتة لسببين: تُعاد رسمًا مع كلّ إطار أثناء الانزلاق
/// فقط لا الخريطة كلّها، والمؤقّت يتوقّف حين تهدأ كلّ السيارات — لا بطارية
/// تُصرف على خريطة واقفة.
class _MovingMarkers extends StatefulWidget {
  const _MovingMarkers({required this.markers});

  final List<MapMarker> markers;

  @override
  State<_MovingMarkers> createState() => _MovingMarkersState();
}

class _MovingMarkersState extends State<_MovingMarkers>
    with SingleTickerProviderStateMixin {
  /// قرابة فترة النبضة: السيارة تصل قبل الموضع التالي بقليل.
  static const _glide = Duration(milliseconds: 2600);

  final Map<String, MarkerMotion> _motions = {};
  late final Ticker _ticker = createTicker((_) => _onTick());
  final Stopwatch _clock = Stopwatch()..start();

  Duration get _now => _clock.elapsed;

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(_MovingMarkers old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    final now = _now;
    final live = <String>{};
    for (final marker in widget.markers) {
      live.add(marker.id);
      final motion = _motions[marker.id];
      if (motion == null) {
        _motions[marker.id] =
            MarkerMotion(marker.position, heading: marker.rotationDegrees ?? 0);
      } else {
        motion.retarget(
          marker.position,
          now,
          duration: _glide,
          heading: marker.rotationDegrees,
        );
      }
    }
    _motions.removeWhere((id, _) => !live.contains(id));
    if (_motions.values.any((m) => m.isMoving(now)) && !_ticker.isActive) {
      _ticker.start();
    }
  }

  void _onTick() {
    if (!mounted) return;
    final now = _now;
    if (!_motions.values.any((m) => m.isMoving(now))) _ticker.stop();
    setState(() {});
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final now = _now;
    return MarkerLayer(
      markers: [
        for (final marker in widget.markers)
          if (_motions[marker.id] case final motion?)
            Marker(
              key: ValueKey(marker.id),
              point: _toLatLng(motion.positionAt(now)),
              width: marker.size.width,
              height: marker.size.height,
              alignment: Alignment.center,
              child: MarkerHeading(
                degrees: motion.headingAt(now),
                child: Builder(builder: marker.builder),
              ),
            ),
      ],
    );
  }
}

class _OsmAttribution extends StatelessWidget {
  const _OsmAttribution();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.bottomEnd,
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.75),
            borderRadius: BorderRadius.circular(3),
          ),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            child: Text(
              '© OpenStreetMap',
              style: TextStyle(fontSize: 9.5),
              textDirection: TextDirection.ltr,
            ),
          ),
        ),
      ),
    );
  }
}
