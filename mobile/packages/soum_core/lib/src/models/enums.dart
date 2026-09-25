/// تعدادات المنصّة.
///
/// كلّ تعداد هنا يحمل `unknown` وقرّاءً متساهلًا. السبب أنّ الرموز تُضاف من
/// الخادم: `RideMode` مثلًا يقرأه التطبيق من `/config/` لا من هذه القائمة،
/// وحالةٌ جديدة في الخادم يجب أن تُعرض بلا انهيار حتّى يصدر تحديث.
///
/// تحذير معماريّ: هذا التعداد **لا يُستعمل لبناء قائمة الأنماط في الواجهة**.
/// القائمة تُبنى من `AppConfig.rideModes` حصرًا — راجع §12.3 في الدليل.
library;

enum RideMode {
  fast('fast'),
  express('express'),
  standard('standard'),
  saving('saving'),
  shared('shared'),
  unknown('unknown');

  const RideMode(this.code);
  final String code;

  static RideMode from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => RideMode.unknown,
      );
}

enum TripCategory {
  city('city'),
  intercity('intercity'),
  serviceLine('service_line'),
  recreational('recreational'),
  unknown('unknown');

  const TripCategory(this.code);
  final String code;

  /// §3 في الدليل: بين‑المدن وخطّ الخدمة يفرضان مدينتَي الانطلاق والوصول.
  bool get requiresCities =>
      this == TripCategory.intercity || this == TripCategory.serviceLine;

  static TripCategory from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => TripCategory.unknown,
      );
}

/// حالات الطلب — §2.1. لكلّ حالة شاشة، ولا شيء غير ذلك.
enum RideStatus {
  draft('draft'),
  searching('searching'),
  offersReceived('offers_received'),
  driverSelected('driver_selected'),
  driverArriving('driver_arriving'),
  driverArrived('driver_arrived'),
  inProgress('in_progress'),
  completed('completed'),
  cancelled('cancelled'),
  expired('expired'),
  unknown('unknown');

  const RideStatus(this.code);
  final String code;

  static RideStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => RideStatus.unknown,
      );

  /// الطلب ما زال يقبل عروضًا.
  bool get isAuctioning =>
      this == RideStatus.searching || this == RideStatus.offersReceived;

  /// سائق ثُبّت والرحلة قائمة.
  bool get hasTrip => const {
        RideStatus.driverSelected,
        RideStatus.driverArriving,
        RideStatus.driverArrived,
        RideStatus.inProgress,
      }.contains(this);

  bool get isTerminal => const {
        RideStatus.completed,
        RideStatus.cancelled,
        RideStatus.expired,
      }.contains(this);
}

enum OfferStatus {
  pending('pending'),
  accepted('accepted'),
  rejected('rejected'),
  expired('expired'),
  cancelled('cancelled'),
  // السائق سحب عرضه قبل أن يختاره الزبون.
  withdrawn('withdrawn'),
  unknown('unknown');

  const OfferStatus(this.code);
  final String code;

  static OfferStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => OfferStatus.unknown,
      );

  bool get isLive => this == OfferStatus.pending;
}

enum InvitationStatus {
  pending('pending'),
  accepted('accepted'),
  rejected('rejected'),
  expired('expired'),
  cancelled('cancelled'),
  unknown('unknown');

  const InvitationStatus(this.code);
  final String code;

  static InvitationStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => InvitationStatus.unknown,
      );
}

enum TripStatus {
  created('created'),
  driverArriving('driver_arriving'),
  driverArrived('driver_arrived'),
  inProgress('in_progress'),
  completed('completed'),
  cancelled('cancelled'),
  disputed('disputed'),
  unknown('unknown');

  const TripStatus(this.code);
  final String code;

  static TripStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => TripStatus.unknown,
      );
}

enum PaymentStatus {
  pending('pending'),
  paid('paid'),
  partiallyRefunded('partially_refunded'),
  refunded('refunded'),
  failed('failed'),
  unknown('unknown');

  const PaymentStatus(this.code);
  final String code;

  static PaymentStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => PaymentStatus.unknown,
      );

  bool get isSettled =>
      this == PaymentStatus.paid ||
      this == PaymentStatus.refunded ||
      this == PaymentStatus.partiallyRefunded;
}

enum UserRole {
  customer('customer'),
  driver('driver'),
  admin('admin'),
  support('support'),
  unknown('unknown');

  const UserRole(this.code);
  final String code;

  static UserRole from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => UserRole.unknown,
      );
}

/// الوثائق الأربع — §1.3. حتّى تُقبل كلّها يردّ go-online بـ400.
enum DriverDocumentType {
  nationalId('national_id'),
  driverLicense('driver_license'),
  vehicleRegistration('vehicle_registration'),
  // الرمز في الخادم `vehicle_insurance` لا `insurance` — انظر
  // DocumentTypeEnum في contract/openapi.json. الخطأ السابق جعل التطبيق
  // يرى ثلاث وثائق من أربع، ويرسل نوعًا يرفضه الخادم بـ400 عند الرفع.
  insurance('vehicle_insurance');

  const DriverDocumentType(this.code);
  final String code;

  static DriverDocumentType? from(String? raw) {
    for (final value in values) {
      if (value.code == raw) return value;
    }
    return null;
  }
}

enum DocumentStatus {
  pending('pending'),
  approved('approved'),
  rejected('rejected'),
  expired('expired'),
  unknown('unknown');

  const DocumentStatus(this.code);
  final String code;

  static DocumentStatus from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => DocumentStatus.unknown,
      );
}

/// مصدر المسار — §3.2. الحقل الذي **يجب** أن يُعرض للمستخدم.
enum RouteSource {
  /// مسار حقيقي من مزوّد الخرائط، و`route_geometry` يحمل نقاطه.
  provider('provider'),

  /// مسافة هوائية × معامل التفاف. الرقم معقول لكنّه ليس مسارًا،
  /// و`route_geometry` فارغ فلا خطّ يُرسم.
  estimated('estimated'),

  unknown('unknown');

  const RouteSource(this.code);
  final String code;

  static RouteSource from(String? raw) => values.firstWhere(
        (e) => e.code == raw,
        orElse: () => RouteSource.unknown,
      );

  bool get isApproximate => this != RouteSource.provider;
}

/// لماذا ألغى الزبون رحلةً ثُبّت سائقها — `CancelReasonEnum` في الخادم.
///
/// الرمز يُرسل مع الإلغاء فيُعدّ ويُكشف منه: «السائق طلب منّي الإلغاء»
/// أشهر طريقة للتهرّب من العمولة، ولا تُعدّ من نصٍّ حرّ. بلا `unknown`
/// عمدًا: هذا تعدادٌ يُرسَل لا يُقرأ، والخادم يرفض رمزًا لا يعرفه.
enum CancelReason {
  changedMind('changed_mind'),
  driverLate('driver_late'),
  driverNotMoving('driver_not_moving'),
  driverAsked('driver_asked'),
  foundOther('found_other'),
  wrongPickup('wrong_pickup'),
  other('other');

  const CancelReason(this.code);
  final String code;
}
