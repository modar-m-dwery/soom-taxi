import '../models/invitation.dart';
import '../models/json.dart';
import '../models/nearby_vehicle.dart';
import '../network/api_client.dart';

/// الخريطة الحيّة والدعوة المباشرة — الميزة التي تميّز المنصّة.
class InvitationsApi {
  InvitationsApi(this._client);

  final ApiClient _client;

  /// السيارات القريبة من طلب قائم. إحداثياتها مقرَّبة إلى ~110 أمتار.
  Future<List<NearbyVehicle>> nearbyVehicles(int rideId) async {
    final body =
        await _client.get<dynamic>('/customer/rides/$rideId/nearby-vehicles/');
    return readResults(body).map(NearbyVehicle.fromJson).toList(growable: false);
  }

  /// §5.1 — `ttlSeconds` **يجب** أن يكون من `timings.invitationTtlOptions`.
  /// أيّ قيمة أخرى تُرفض بـ400، ولا معنى لتخمينها.
  Future<RideInvitation> invite({
    required int rideId,
    required int driverId,
    required int ttlSeconds,
  }) async =>
      RideInvitation.fromJson(asJson(await _client.post<dynamic>(
        '/customer/rides/$rideId/invitations/',
        body: {'driver_id': driverId, 'ttl_seconds': ttlSeconds},
      )));

  Future<List<RideInvitation>> driverInvitations() async {
    final body = await _client.get<dynamic>('/driver/invitations/');
    return readResults(body).map(RideInvitation.fromJson).toList(growable: false);
  }

  Future<RideInvitation> accept(int invitationId) async =>
      RideInvitation.fromJson(asJson(await _client.post<dynamic>(
        '/driver/invitations/$invitationId/accept/',
      )));

  Future<RideInvitation> reject(int invitationId, {String? reason}) async =>
      RideInvitation.fromJson(asJson(await _client.post<dynamic>(
        '/driver/invitations/$invitationId/reject/',
        body: {if (reason != null && reason.isNotEmpty) 'reason': reason},
      )));
}
