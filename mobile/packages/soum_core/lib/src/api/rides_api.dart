import '../models/active_ride.dart';
import '../models/enums.dart';
import '../models/geo.dart';
import '../models/json.dart';
import '../models/offer.dart';
import '../models/ride.dart';
import '../models/subscription.dart';
import '../models/trip.dart';
import '../network/api_client.dart';

class RidesApi {
  RidesApi(this._client);

  final ApiClient _client;

  /// §3.1 — إنشاء طلب.
  ///
  /// `mode` و`tripCategory` محوران مستقلّان (§3): الأوّل درجة الخدمة،
  /// والثاني نطاق الرحلة. «بين مدينتين بدرجة اقتصادية» تركيبٌ صحيح
  /// ومطلوب، فلا يُدمجان في قائمة واحدة في الواجهة.
  Future<RideRequest> create({
    required GeoPoint pickup,
    required GeoPoint destination,
    required String mode,
    required int passengerCount,
    String? requestedVehicleType,
    DateTime? scheduledAt,
    TripCategory tripCategory = TripCategory.city,
    String? originCity,
    String? destinationCity,
    double? searchRadiusKm,
    bool autoDispatch = false,
  }) async {
    final body = await _client.post<dynamic>('/rides/', body: {
      'pickup_lat': pickup.lat,
      'pickup_lng': pickup.lng,
      'destination_lat': destination.lat,
      'destination_lng': destination.lng,
      'mode': mode,
      'passenger_count': passengerCount,
      'requested_vehicle_type': ?requestedVehicleType,
      'scheduled_at': ?scheduledAt?.toUtc().toIso8601String(),
      'trip_category': tripCategory.code,
      'origin_city': ?originCity,
      'destination_city': ?destinationCity,
      'search_radius_km': ?searchRadiusKm,
      if (autoDispatch) 'auto_dispatch': true,
    });
    return RideRequest.fromJson(asJson(body));
  }

  Future<void> cancel(int rideId, {String? reason}) => _client.post<dynamic>(
        '/rides/$rideId/cancel/',
        body: {if (reason != null && reason.isNotEmpty) 'reason': reason},
      );

  Future<List<RideRequest>> mine({String? status}) async {
    final body = await _client.get<dynamic>(
      '/rides/mine/',
      query: {'status': ?status},
    );
    return readResults(body).map(RideRequest.fromJson).toList(growable: false);
  }

  /// §2.2 — أوّل نداء بعد المصادقة في كلّ إقلاع.
  Future<ActiveRideSnapshot> activeRide() async => ActiveRideSnapshot.fromJson(
        asJson(await _client.get<dynamic>('/me/active-ride/')),
      );

  Future<List<Trip>> myTrips({String? status}) async {
    final body = await _client.get<dynamic>(
      '/me/trips/',
      query: {'status': ?status},
    );
    return readResults(body).map(Trip.fromJson).toList(growable: false);
  }

  Future<Trip> trip(int rideId) async =>
      Trip.fromJson(asJson(await _client.get<dynamic>('/trips/$rideId/')));

  /// المسار المسجَّل لرحلة منتهية.
  Future<List<GeoPoint>> tripPath(int rideId) async {
    final body = await _client.get<dynamic>('/trips/$rideId/path/');
    final rows = readResults(body);
    return rows
        .map((row) => GeoPoint(
              readDouble(row, 'lat'),
              readDouble(row, 'lng'),
            ))
        .toList(growable: false);
  }

  Future<void> cancelTrip(int rideId, {String? reason}) => _client.post<dynamic>(
        '/customer/rides/$rideId/cancel-trip/',
        body: {if (reason != null && reason.isNotEmpty) 'reason': reason},
      );

  // -----------------------------------------------------------------
  // المزاد
  // -----------------------------------------------------------------

  Future<List<RideOffer>> offers(int rideId) async {
    final body = await _client.get<dynamic>('/customer/rides/$rideId/offers/');
    return readResults(body).map(RideOffer.fromJson).toList(growable: false);
  }

  /// §4.4 — قد يردّ 409 بـ`driver.unavailable`: زبون آخر سبقك إلى السائق
  /// نفسه. سلوكٌ متوقَّع لا عطل: اعرض «هذه السيارة لم تعد متاحة» وأعد
  /// الزبون إلى قائمة محدَّثة.
  Future<RideOffer> selectOffer(int rideId, int offerId) async =>
      RideOffer.fromJson(asJson(await _client.post<dynamic>(
        '/customer/rides/$rideId/offers/$offerId/select/',
      )));

  // ------------------------------------------------------------ اشتراك الصباح

  Future<List<RideSubscription>> subscriptions() async {
    final body = await _client.get<dynamic>('/rides/subscriptions/');
    return readResults(body)
        .map(RideSubscription.fromJson)
        .toList(growable: false);
  }

  /// `departureTime` بصيغة «HH:mm» بتوقيت الزبون المحلّيّ؛ الخادم يفسّرها
  /// بتوقيت دمشق. `weekdays` فارغة = الأحد–الخميس.
  Future<RideSubscription> createSubscription({
    required GeoPoint pickup,
    required GeoPoint destination,
    required String departureTime,
    String label = '',
    List<int> weekdays = const [],
    String mode = 'standard',
    int passengerCount = 1,
    String? requestedVehicleType,
    int leadMinutes = 30,
  }) async {
    final body = await _client.post<dynamic>('/rides/subscriptions/', body: {
      'label': label,
      'pickup_lat': pickup.lat,
      'pickup_lng': pickup.lng,
      'destination_lat': destination.lat,
      'destination_lng': destination.lng,
      'departure_time': departureTime,
      'weekdays': weekdays,
      'mode': mode,
      'passenger_count': passengerCount,
      'requested_vehicle_type': ?requestedVehicleType,
      'lead_minutes': leadMinutes,
    });
    return RideSubscription.fromJson(asJson(body));
  }

  Future<RideSubscription> cancelSubscription(int id) async =>
      RideSubscription.fromJson(asJson(
        await _client.delete<dynamic>('/rides/subscriptions/$id/'),
      ));
}
