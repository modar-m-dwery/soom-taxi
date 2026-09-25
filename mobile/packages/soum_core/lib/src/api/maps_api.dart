import '../models/enums.dart';
import '../models/geo.dart';
import '../models/json.dart';
import '../network/api_client.dart';

class RouteResult {
  const RouteResult({
    required this.distanceKm,
    required this.durationMinutes,
    required this.source,
    this.geometry,
  });

  final double distanceKm;
  final int durationMinutes;

  /// §9.2 — `estimated` يعني أنّ الخادم لم يصل إلى مزوّد الخرائط فحسب
  /// المسافة بخطّ مستقيم مضروبًا في معامل التفاف. الرقم معقول لكنّه ليس
  /// مسارًا، و`geometry` يكون فارغًا فلا خطّ يُرسم.
  final RouteSource source;

  final RouteGeometry? geometry;

  factory RouteResult.fromJson(Json json) => RouteResult(
        distanceKm: readDouble(json, 'distance_km'),
        durationMinutes: readInt(json, 'duration_minutes'),
        source: RouteSource.from(readStringOrNull(json, 'source')),
        geometry: RouteGeometry.fromJson(json['geometry']),
      );
}

class MapsApi {
  MapsApi(this._client);

  final ApiClient _client;

  /// لا تنكسر عند تعذّر المزوّد: تعود بتقدير و`source: estimated`.
  /// وإذا تكرّر الفشل يفتح قاطعٌ داخليّ فيتوقّف الخادم عن المحاولة ستّين
  /// ثانية — فيعود التقدير فورًا بلا انتظار. انتظار مزوّد ميّت أسوأ من
  /// تقدير سريع.
  Future<RouteResult> route({
    required GeoPoint origin,
    required GeoPoint destination,
  }) async =>
      RouteResult.fromJson(asJson(await _client.get<dynamic>(
        '/maps/route/',
        // الأسماء كما في المخطّط: `pickup_*` و`destination_*`. بـ`origin_*`
        // و`dest_*` كان كلّ طلب مسار يُردّ 400، فلا خطّ ولا تقدير قبل الطلب.
        query: {
          'pickup_lat': origin.lat,
          'pickup_lng': origin.lng,
          'destination_lat': destination.lat,
          'destination_lng': destination.lng,
        },
      )));
}
