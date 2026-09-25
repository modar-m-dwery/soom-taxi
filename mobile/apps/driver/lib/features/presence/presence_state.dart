import 'package:soum_core/soum_core.dart';

/// حالة تشغيل السائق.
///
/// التمييز بين `online` و`matchable` هو بيت القصيد في هذا الملفّ، وهو
/// تمييزٌ لا تذكره الوثيقة ومقيسٌ على خادم يعمل:
///
///   `online`    = الخادم قَبِل `go-online` وسجّل السائق متّصلًا.
///   `matchable` = السائق يظهر فعلًا في نتائج المطابقة.
///
/// والثاني يشترط الأوّل **وأكثر منه**: `MatchingService` يفلتر بـ
/// `is_driver_location_fresh`، وهي تقرأ `last_location_at` الذي لا
/// يتحدّث إلّا بنبض `location.update` في غرفة السائق.
///
/// أثبتناه بالتجربة: سائق بوثائق أربع مقبولة ومركبة فعّالة و`online=True`
/// أعادت له `candidates` قائمةً فارغة، وردّ `offers` بـ
/// `driver.not_eligible` — حتّى أُرسلت أوّل نبضة، فنجح كلّ شيء فورًا.
///
/// عرض هذا الفرق في الواجهة ليس ترفًا: سائقٌ يرى «متّصل» ولا يصله طلب
/// طوال ساعة لا يعرف أنّ المشكلة في نبضٍ لا يصل — فيتّهم المنصّة.
enum PresenceStage {
  /// متوقّف بأمره.
  offline,

  /// النداء جارٍ.
  connecting,

  /// الخادم قَبِل، والنبض لم يصل بعد — لم يدخل المطابقة.
  onlineNoHeartbeat,

  /// متّصل وينبض: يظهر في المطابقة.
  matchable,

  /// النبض انقطع مدّة تجاوزت `presence_stale_seconds`.
  stale,
}

/// ما يمنع السائق من العمل — مصنَّفًا لا مكتوبًا.
///
/// الواجهة هي من تترجم. وحدة التحكّم لا تعرف لغة المستخدم، ونصٌّ مكتوب
/// فيها يخرج من ملفّ الترجمة فلا يُترجَم — وهو بندٌ يُفحص آليًّا في T2.4.
enum PresenceBlocker {
  none,

  /// إذن الموقع مرفوض أو الخدمة مغلقة.
  locationUnavailable,

  /// الخادم رفض: وثيقة ناقصة أو منتهية أو حساب موقوف. التفصيل في
  /// `failure.detail` بنصّه العربيّ الجاهز للعرض.
  serverRefused,

  /// الخادم رفض الموقع لأنّه من تطبيق تزييف (`location.rejected` بالسبب
  /// `mock_location`). السائق متّصل لكنّه خارج المطابقة حتّى يطفئه.
  mockLocation,
}

class PresenceState {
  const PresenceState({
    this.stage = PresenceStage.offline,
    this.lastAck,
    this.lastPosition,
    this.failure,
    this.blocker = PresenceBlocker.none,
    this.roomGeneration = 0,
  });

  final PresenceStage stage;

  /// آخر `presence.ack` من الخادم — دليل وصول النبض لا إرساله.
  final DateTime? lastAck;

  final GeoPoint? lastPosition;

  /// سبب تعذّر الاتّصال — `driver.not_eligible` مثلًا مع نصّه الصريح.
  final ApiException? failure;

  /// تصنيف المانع، تترجمه الواجهة.
  final PresenceBlocker blocker;

  /// يزيد كلّما أُنشئت غرفة سائق جديدة (كلّ `go-online`، ومنها العودة من
  /// الخلفية). من يشترك في الغرفة يراقبه لا `isOnline` وحده: الغرفة القديمة
  /// تُغلق ويبقى المشترك فيها يسمع صمتًا.
  final int roomGeneration;

  bool get isOnline =>
      stage == PresenceStage.onlineNoHeartbeat ||
      stage == PresenceStage.matchable ||
      stage == PresenceStage.stale;

  bool get isMatchable => stage == PresenceStage.matchable;

  PresenceState copyWith({
    PresenceStage? stage,
    DateTime? lastAck,
    GeoPoint? lastPosition,
    ApiException? failure,
    PresenceBlocker? blocker,
    int? roomGeneration,
    bool clearFailure = false,
  }) =>
      PresenceState(
        roomGeneration: roomGeneration ?? this.roomGeneration,
        stage: stage ?? this.stage,
        lastAck: lastAck ?? this.lastAck,
        lastPosition: lastPosition ?? this.lastPosition,
        failure: clearFailure ? null : (failure ?? this.failure),
        blocker: clearFailure
            ? PresenceBlocker.none
            : (blocker ?? this.blocker),
      );
}
