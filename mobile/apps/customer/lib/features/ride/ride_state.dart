/// حالة قوس الرحلة — كما يراها الزبون.
library;

import 'package:soum_core/soum_core.dart';

class RideArc {
  const RideArc({
    this.ride,
    this.trip,
    this.offers = const [],
    this.invitation,
    this.driverLocation,
    this.pendingPayment,
    this.cooldownDrivers = const {},
    this.isBusy = false,
    this.lastError,
    this.endedReason,
    this.autoDispatchExhausted = false,
    this.driverRequeued = false,
  });

  /// السائق ألغى بعد القبول والطلب عاد إلى البحث — تُعرض رسالة مرّة.
  final bool driverRequeued;

  final RideRequest? ride;
  final Trip? trip;

  /// العروض القائمة، الأرخص أوّلًا ثمّ الأسرع.
  final List<RideOffer> offers;

  /// دعوة معلّقة — واحدة على الأكثر بحسب `invitation_max_parallel`.
  final RideInvitation? invitation;

  /// آخر موقع للسائق من `driver.location`. زائل: «آخر قيمة تفوز».
  final GeoPoint? driverLocation;

  final Payment? pendingPayment;

  /// سائقون رفضوا مؤخّرًا — تُخفى سياراتهم حتّى تنقضي التهدئة (§5.1).
  final Set<int> cooldownDrivers;

  final bool isBusy;
  final ApiException? lastError;

  /// سبب انتهاء الرحلة كما وصل من الخادم — لعرضه بدل رسالة عامّة.
  final String? endedReason;

  /// «الأقرب» لم يجد من يقبل، والطلب صار مزادًا عاديًّا.
  final bool autoDispatchExhausted;

  /// الخادم يدعو السائقين بنفسه الآن.
  bool get isAutoDispatching =>
      (ride?.autoDispatch ?? false) && !autoDispatchExhausted;

  bool get isIdle => ride == null && pendingPayment == null;
  bool get hasOffers => offers.isNotEmpty;

  /// المرحلة المعروضة.
  ///
  /// مشتقّة من الحالات التي **وصلت** لا من الفعل الذي أُرسل — وهو الفرق
  /// الذي تحذّر منه الوثيقة: «الحالة تتغيّر لأسباب لا يراها تطبيقك: مهلة
  /// انقضت في Celery، إدارةٌ ألغت، سائقٌ انقطع اتّصاله».
  ///
  /// والخريطة هنا تطابق `_resolve_stage` في `trips/services/resume.py`
  /// حرفًا بحرف. أيّ تباعد بينهما يعني شاشةً تختلف بين الإقلاع (يقرأ من
  /// الخادم) والبثّ الحيّ (يشتقّ محلّيًّا) — وهو أسوأ أنواع التناقض لأنّه
  /// يظهر عند إعادة فتح التطبيق وحدها.
  ResumeStage get stage {
    final currentTrip = trip;
    if (currentTrip != null) {
      final fromTrip = switch (currentTrip.status) {
        TripStatus.created => ResumeStage.driverAssigned,
        TripStatus.driverArriving => ResumeStage.driverArriving,
        TripStatus.driverArrived => ResumeStage.driverArrived,
        TripStatus.inProgress => ResumeStage.inProgress,
        _ => null,
      };
      if (fromTrip != null) return fromTrip;
    }

    final currentRide = ride;
    if (currentRide == null) {
      return pendingPayment != null
          ? ResumeStage.awaitingPayment
          : ResumeStage.idle;
    }

    return switch (currentRide.status) {
      RideStatus.searching => ResumeStage.searching,
      RideStatus.offersReceived => ResumeStage.choosingOffer,
      RideStatus.driverSelected => ResumeStage.driverAssigned,
      RideStatus.driverArriving => ResumeStage.driverArriving,
      RideStatus.driverArrived => ResumeStage.driverArrived,
      RideStatus.inProgress => ResumeStage.inProgress,
      _ => pendingPayment != null
          ? ResumeStage.awaitingPayment
          : ResumeStage.idle,
    };
  }

  RideArc copyWith({
    RideRequest? ride,
    Trip? trip,
    List<RideOffer>? offers,
    RideInvitation? invitation,
    GeoPoint? driverLocation,
    Payment? pendingPayment,
    Set<int>? cooldownDrivers,
    bool? isBusy,
    ApiException? lastError,
    String? endedReason,
    bool? autoDispatchExhausted,
    bool? driverRequeued,
    bool clearRide = false,
    bool clearTrip = false,
    bool clearInvitation = false,
    bool clearError = true,
    bool clearPayment = false,
  }) =>
      RideArc(
        ride: clearRide ? null : (ride ?? this.ride),
        trip: clearTrip ? null : (trip ?? this.trip),
        offers: offers ?? this.offers,
        invitation: clearInvitation ? null : (invitation ?? this.invitation),
        driverLocation: driverLocation ?? this.driverLocation,
        pendingPayment:
            clearPayment ? null : (pendingPayment ?? this.pendingPayment),
        cooldownDrivers: cooldownDrivers ?? this.cooldownDrivers,
        isBusy: isBusy ?? this.isBusy,
        // الخطأ يُمحى افتراضًا عند كلّ تحديث: خطأٌ يبقى معلّقًا بعد نجاح
        // العملية التالية يجعل الشاشة تكذب.
        lastError: clearError ? lastError : (lastError ?? this.lastError),
        endedReason: endedReason ?? this.endedReason,
        autoDispatchExhausted:
            autoDispatchExhausted ?? this.autoDispatchExhausted,
        driverRequeued: driverRequeued ?? this.driverRequeued,
      );
}
