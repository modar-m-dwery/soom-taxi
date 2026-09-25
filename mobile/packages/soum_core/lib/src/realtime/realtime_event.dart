/// الحدث الحيّ — وتوحيد الأشكال الثلاثة التي يرسلها الخادم فعلًا.
///
/// دليل التكامل يصف شكلًا واحدًا. القراءة في `realtime/events.py` و
/// `realtime/consumers.py`، ثمّ التحقّق على خادم يعمل، أظهرت ثلاثة أشكال
/// على المقبس نفسه:
///
/// ١ — اللقطة، ويبنيها الـConsumer مباشرةً. النسخة في المستوى الأعلى:
///
///     {"event_type":"ride.snapshot","entity_type":"ride","entity_id":2,
///      "version":0,"payload":{"ride":{...},"offers":[...]}}
///
/// ٢ — حدث أعمال، ويمرّ بـ`EventBus.publish`. النسخة **داخل** payload،
///     والبيانات الفعلية تحت `payload.data`:
///
///     {"event_type":"offer.created",
///      "payload":{"event_id":"…","entity_type":"ride","entity_id":2,
///                 "version":1,"timestamp":…,"data":{…العرض…}}}
///
/// ٣ — حدث زائل، ويمرّ بـ`publish_ephemeral`. بلا نسخة إطلاقًا، لأنّه
///     «آخر قيمة تفوز» — `driver.location` يصل كلّ ثلاث ثوانٍ:
///
///     {"event_type":"driver.location","payload":{…خام…}}
///
/// وشكلٌ رابع للحاق بعد انقطاع: `ride.resync` يحمل `events` مصفوفةً،
/// ومفتاح البيانات في سجلّ الأحداث هو `payload` لا `data`.
///
/// توحيدها هنا — في موضع واحد — هو ما يمنع كلّ شاشة من أن تحمل فرعها
/// الخاصّ لقراءة النسخة. والفرق ليس جماليًّا: شاشةٌ تقرأ `version` من
/// المستوى الأعلى تراها `null` في كلّ حدث أعمال، فيصير حارس الترتيب
/// معطَّلًا بصمت — وهو أخطر أنواع التعطّل لأنّه لا يُبلَّغ عنه.
library;

import '../models/json.dart';

class RealtimeEvent {
  const RealtimeEvent({
    required this.type,
    required this.data,
    this.entityType,
    this.entityId,
    this.version,
    this.eventId,
    this.timestamp,
    this.raw = const {},
  });

  /// `offer.created`، `ride.snapshot`، `driver.location`…
  final String type;

  /// البيانات الفعلية، مهما كان الشكل الذي وصلت به.
  final Json data;

  final String? entityType;
  final int? entityId;

  /// `null` للأحداث الزائلة ورسائل التحكّم — وهذا مقصود: حارس الترتيب
  /// يتجاهل ما لا نسخة له بدل أن يفترض صفرًا ويُسقط أحداثًا صحيحة.
  final int? version;

  final String? eventId;
  final DateTime? timestamp;

  /// الإطار كما وصل — للتشخيص وحده.
  final Json raw;

  bool get isSnapshot => type.endsWith('.snapshot');
  bool get isConnectionEstablished => type == 'connection.established';
  bool get isPong => type == 'pong';
  bool get isError => type == 'error';
  bool get isVersioned => version != null;

  /// يفكّ إطارًا واحدًا إلى حدث أو أكثر. `ride.resync` وحده يُنتج أكثر من واحد.
  static List<RealtimeEvent> parse(Json frame) {
    final type = readString(frame, 'event_type');
    if (type.isEmpty) return const [];

    // الشكل الرابع: ردّ اللحاق يحمل مصفوفة أحداث كاملة.
    if (frame['events'] is List) {
      final list = frame['events'] as List;
      return list
          .whereType<Map>()
          .map((e) => _fromLogEntry(e.cast<String, dynamic>()))
          .toList(growable: false);
    }

    final payloadRaw = frame['payload'];
    final payload = asJson(payloadRaw);

    // الشكل الأوّل: النسخة في المستوى الأعلى — اللقطة.
    if (frame.containsKey('version')) {
      return [
        RealtimeEvent(
          type: type,
          data: payload,
          entityType: readStringOrNull(frame, 'entity_type'),
          entityId: readIntOrNull(frame, 'entity_id'),
          version: readIntOrNull(frame, 'version'),
          raw: frame,
        ),
      ];
    }

    // الشكل الثاني: النسخة داخل payload، والبيانات تحت data.
    if (payload.containsKey('version') && payload.containsKey('data')) {
      return [
        RealtimeEvent(
          type: type,
          data: asJson(payload['data']),
          entityType: readStringOrNull(payload, 'entity_type'),
          entityId: readIntOrNull(payload, 'entity_id'),
          version: readIntOrNull(payload, 'version'),
          eventId: readStringOrNull(payload, 'event_id'),
          timestamp: _readUnix(payload['timestamp']),
          raw: frame,
        ),
      ];
    }

    // الشكل الثالث: زائل أو رسالة تحكّم.
    //
    // رسائل التحكّم (connection.established، error) تحمل حقولها في
    // المستوى الأعلى لا في payload، فنمرّر الإطار نفسه بيانةً حتّى لا
    // تضيع `group` و`detail`.
    return [
      RealtimeEvent(
        type: type,
        data: payloadRaw is Map ? payload : frame,
        raw: frame,
      ),
    ];
  }

  /// مدخلة من سجلّ الأحداث — مفتاح بياناتها `payload` لا `data`.
  static RealtimeEvent _fromLogEntry(Json entry) => RealtimeEvent(
        type: readString(entry, 'event_type'),
        data: asJson(entry['payload']),
        entityType: readStringOrNull(entry, 'entity_type'),
        entityId: readIntOrNull(entry, 'entity_id'),
        version: readIntOrNull(entry, 'version'),
        eventId: readStringOrNull(entry, 'event_id'),
        timestamp: _readUnix(entry['timestamp']),
        raw: entry,
      );

  static DateTime? _readUnix(Object? raw) {
    if (raw is! num) return null;
    return DateTime.fromMillisecondsSinceEpoch(
      (raw * 1000).round(),
      isUtc: true,
    ).toLocal();
  }

  @override
  String toString() =>
      'RealtimeEvent($type'
      '${version == null ? '' : ' v$version'}'
      '${entityId == null ? '' : ' #$entityId'})';
}

/// أسماء الأحداث — §7.2 في دليل التكامل.
abstract final class RealtimeEventType {
  // تحكّم
  static const connectionEstablished = 'connection.established';
  static const pong = 'pong';
  static const error = 'error';

  // غرفة الرحلة
  static const rideSnapshot = 'ride.snapshot';
  static const rideResync = 'ride.resync';
  static const offerCreated = 'offer.created';
  static const offerExpired = 'offer.expired';
  static const offerAccepted = 'offer.accepted';
  static const rideDriverSelected = 'ride.driver_selected';
  static const driverLocation = 'driver.location';
  static const driverArrived = 'driver.arrived';
  static const tripStarted = 'trip.started';
  static const tripCompleted = 'trip.completed';
  static const tripCancelled = 'trip.cancelled';
  static const rideCancelled = 'ride.cancelled';
  static const rideCancelledByDriver = 'ride.cancelled_by_driver';

  /// الزبون عرض سعره أو رفعه (سوم بنمط inDrive).
  static const rideFareProposed = 'ride.fare_proposed';
  static const rideExpired = 'ride.expired';
  static const complaintUpdated = 'complaint.updated';

  // الدعوة
  static const invitationCreated = 'invitation.created';
  static const invitationSent = 'invitation.sent';
  static const invitationAccepted = 'invitation.accepted';
  static const invitationRejected = 'invitation.rejected';
  static const invitationExpired = 'invitation.expired';
  static const invitationCancelled = 'invitation.cancelled';

  /// «الأقرب» جرّب كلّ من يمكن تجربته ولم يقبل أحد — الطلب صار مزادًا.
  static const autoDispatchExhausted = 'auto_dispatch.exhausted';

  // غرفة السائق
  static const presenceAck = 'presence.ack';
  static const presenceOffline = 'presence.offline';

  /// الخادم رفض نبضة موقع: `payload.reason` =
  /// `mock_location` (تطبيق تزييف) أو `implausible_speed` (قفزة مستحيلة)
  /// أو خطأ صيغة. الموقع لم يُكتب ولم يُبثّ.
  static const locationRejected = 'location.rejected';

  // السوق
  static const marketplaceSnapshot = 'marketplace.snapshot';
  static const vehicleEnteredArea = 'vehicle.entered_area';
  static const vehicleLeftArea = 'vehicle.left_area';
  static const vehicleUpdated = 'vehicle.updated';
}
