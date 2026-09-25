// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'soum_strings.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class SoumStringsAr extends SoumStrings {
  SoumStringsAr([String locale = 'ar']) : super(locale);

  @override
  String get appNameCustomer => 'سووم تكسي';

  @override
  String get appNameDriver => 'سووم تكسي — سائق';

  @override
  String get actionRetry => 'أعد المحاولة';

  @override
  String get actionCancel => 'إلغاء';

  @override
  String get actionConfirm => 'تأكيد';

  @override
  String get actionContinue => 'متابعة';

  @override
  String get actionClose => 'إغلاق';

  @override
  String get actionBack => 'رجوع';

  @override
  String get actionEdit => 'تعديل';

  @override
  String get bootLoadingConfig => 'نقرأ إعدادات مدينتك…';

  @override
  String get bootLoadingSession => 'نستعيد جلستك…';

  @override
  String get bootRestoringRide => 'نعيدك إلى رحلتك…';

  @override
  String get bootNoConnection => 'لا اتصال بالإنترنت';

  @override
  String get bootNoConnectionBody =>
      'نحتاج اتصالًا مرّة واحدة لقراءة إعدادات مدينتك. تحقّق من شبكتك ثمّ أعد المحاولة.';

  @override
  String get bootOutsideServiceArea => 'خارج مناطق الخدمة';

  @override
  String get bootOutsideServiceAreaBody =>
      'لا نخدم موقعك الحالي بعد. تستطيع تصفّح التطبيق، لكن لن تجد سيارات قريبة.';

  @override
  String get authPhoneTitle => 'أدخل رقم هاتفك';

  @override
  String get authPhoneSubtitle =>
      'سنرسل لك رمزًا من أربعة إلى ستّة أرقام للتحقّق.';

  @override
  String get authPhoneLabel => 'رقم الهاتف';

  @override
  String get authPhoneHint => '9XXXXXXXX';

  @override
  String get authPhoneInvalid => 'أدخل رقمًا سوريًّا صحيحًا';

  @override
  String get authSendCode => 'أرسل الرمز';

  @override
  String get authCodeTitle => 'أدخل الرمز';

  @override
  String authCodeSubtitle(String phone) {
    return 'أرسلنا رمزًا إلى $phone';
  }

  @override
  String get authCodeLabel => 'رمز التحقّق';

  @override
  String get authCodeInvalid => 'الرمز غير مكتمل';

  @override
  String get authVerify => 'تحقّق';

  @override
  String authResendIn(int seconds) {
    return 'إعادة الإرسال بعد $seconds ثانية';
  }

  @override
  String get authResend => 'أعد إرسال الرمز';

  @override
  String get authChangePhone => 'غيّر الرقم';

  @override
  String authDevelopmentCode(String code) {
    return 'رمز التطوير: $code';
  }

  @override
  String authCodeExpiresIn(int seconds) {
    return 'ينتهي الرمز بعد $seconds ثانية';
  }

  @override
  String authThrottled(int seconds) {
    return 'تجاوزتَ عدد المحاولات. أعد المحاولة بعد $seconds ثانية.';
  }

  @override
  String get errorNetwork => 'لا اتصال بالإنترنت';

  @override
  String get errorNetworkBody => 'تحقّق من شبكتك ثمّ أعد المحاولة.';

  @override
  String get errorGeneric => 'تعذّر إتمام العملية';

  @override
  String errorSupportReference(String requestId) {
    return 'رقم المرجع: $requestId';
  }

  @override
  String get sessionExpiredTitle => 'انتهت جلستك';

  @override
  String get sessionExpiredBody => 'سجّل الدخول مرّة أخرى للمتابعة.';

  @override
  String get logout => 'تسجيل الخروج';

  @override
  String get logoutConfirm => 'هل تريد تسجيل الخروج؟';

  @override
  String get currencySyp => 'ل.س';

  @override
  String get fareApproximate => 'سعر تقريبي';

  @override
  String get fareRouted => 'سعر المسار';

  @override
  String get fareBreakdownTitle => 'تفصيل الأجرة';

  @override
  String get fareBase => 'الأجرة الأساسية';

  @override
  String get fareDistance => 'المسافة';

  @override
  String get fareTime => 'الزمن';

  @override
  String get fareGross => 'الإجمالي';

  @override
  String get farePlatformFee => 'عمولة المنصّة';

  @override
  String get fareCustomerTotal => 'ما تدفعه';

  @override
  String get fareDriverNet => 'ما يقبضه السائق';

  @override
  String get fareApproximateNote =>
      'تعذّر حساب المسار الفعليّ، فهذا تقدير قد يختلف قليلًا.';

  @override
  String get homeWhereTo => 'إلى أين؟';

  @override
  String get homePickup => 'نقطة الانطلاق';

  @override
  String get homeDestination => 'الوجهة';

  @override
  String get homeSetOnMap => 'حدّد على الخريطة';

  @override
  String get homeMyLocation => 'موقعي';

  @override
  String homeCarsNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count سيارة قريبة',
      few: '$count سيارات قريبة',
      two: 'سيارتان قريبتان',
      one: 'سيارة واحدة قريبة',
      zero: 'لا سيارات قريبة',
    );
    return '$_temp0';
  }

  @override
  String homeNoCarsInRange(String km) {
    return 'لا سيارات ضمن $km كم';
  }

  @override
  String get homeOutsideArea => 'أنت خارج مناطق الخدمة';

  @override
  String get homeLocating => 'نحدّد موقعك…';

  @override
  String get modeFast => 'سريع';

  @override
  String get modeFastHint => 'أقرب سائق، وخريطة حيّة ودعوة مباشرة';

  @override
  String get modeExpress => 'فوري';

  @override
  String get modeExpressHint => 'الأسرع، بدعوة مباشرة';

  @override
  String get modeStandard => 'عادي';

  @override
  String get modeStandardHint => 'التوازن المعتاد بين السعر والزمن';

  @override
  String get modeSaving => 'اقتصادي';

  @override
  String get modeSavingHint => 'الأرخص، بنطاق أوسع وانتظار أطول';

  @override
  String get modeShared => 'مشترك';

  @override
  String get modeSharedHint => 'تنضمّ إلى رحلة قائمة وتتقاسم الأجرة';

  @override
  String get categoryCity => 'داخل المدينة';

  @override
  String get categoryIntercity => 'بين المدينتين';

  @override
  String get categoryServiceLine => 'خطّ سرفيس';

  @override
  String get categoryRecreational => 'رحلة ترفيهية';

  @override
  String get cityOrigin => 'مدينة الانطلاق';

  @override
  String get cityDestination => 'مدينة الوصول';

  @override
  String get cityRequired => 'مطلوبة لهذا النوع';

  @override
  String passengers(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count راكبًا',
      few: '$count ركّاب',
      two: 'راكبان',
      one: 'راكب واحد',
    );
    return '$_temp0';
  }

  @override
  String get vehicleAny => 'أي سيارة';

  @override
  String get requestRide => 'اطلب الرحلة';

  @override
  String get scheduleFor => 'احجز لوقت لاحق';

  @override
  String get searchingTitle => 'نبحث عن سائق';

  @override
  String searchingSubtitle(String km) {
    return 'ضمن $km كم من نقطة انطلاقك';
  }

  @override
  String searchingTimeLeft(int seconds) {
    return '$seconds ثانية';
  }

  @override
  String offersTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count عرضًا',
      few: '$count عروض',
      two: 'عرضان',
      one: 'عرض واحد',
    );
    return '$_temp0';
  }

  @override
  String get offersEmpty => 'لم يصل عرض بعد';

  @override
  String offerEta(int minutes) {
    return '$minutes دقيقة';
  }

  @override
  String get offerChoose => 'اختر';

  @override
  String get offerTaken => 'هذه السيارة لم تعد متاحة. اختر غيرها.';

  @override
  String get rideExpired => 'لم نجد سائقًا';

  @override
  String get rideExpiredBody =>
      'انتهت مهلة البحث بلا عرض. جرّب نمطًا أوسع أو أعد المحاولة.';

  @override
  String get rideCancelled => 'أُلغي الطلب';

  @override
  String get cancelRide => 'ألغِ الطلب';

  @override
  String get inviteTitle => 'ادعُ سيارة بعينها';

  @override
  String get inviteSend => 'ادعُ';

  @override
  String get inviteWaiting => 'بانتظار ردّ السائق';

  @override
  String get inviteTtl => 'مهلة الردّ';

  @override
  String get inviteRejected => 'اعتذر السائق. اختر سيارة أخرى.';

  @override
  String get inviteExpired => 'انقضت المهلة بلا ردّ';

  @override
  String get inviteCancel => 'ألغِ الدعوة';

  @override
  String inviteSeatsAvailable(int count) {
    return '$count مقعد متاح';
  }

  @override
  String inviteDistance(int meters) {
    return '$meters متر تقريبًا';
  }

  @override
  String get tripDriverAssigned => 'تأكّدت رحلتك';

  @override
  String get tripDriverArriving => 'السائق في الطريق إليك';

  @override
  String get tripDriverArrived => 'سائقك بانتظارك';

  @override
  String get tripInProgress => 'في الطريق إلى وجهتك';

  @override
  String get tripCompleted => 'وصلت';

  @override
  String get tripCancelledBy => 'أُلغيت الرحلة';

  @override
  String get tripCallDriver => 'اتّصل بالسائق';

  @override
  String get tripCancelTrip => 'ألغِ الرحلة';

  @override
  String get tripPlate => 'اللوحة';

  @override
  String get paymentTitle => 'الدفع';

  @override
  String get paymentCashWaiting => 'بانتظار تأكيد السائق قبض المبلغ';

  @override
  String get paymentCashNote =>
      'ادفع للسائق نقدًا. هو من يؤكّد القبض في تطبيقه.';

  @override
  String get paymentPaid => 'تمّ الدفع';

  @override
  String get paymentAmount => 'المبلغ';

  @override
  String get rateTitle => 'كيف كانت رحلتك؟';

  @override
  String get rateSubmit => 'أرسل التقييم';

  @override
  String get rateReasonRequired => 'اختر سببًا أو اكتب تعليقًا';

  @override
  String get rateComment => 'تعليق (اختياري)';

  @override
  String get rateThanks => 'شكرًا لتقييمك';

  @override
  String get rateAlready => 'قيّمتَ هذه الرحلة من قبل';

  @override
  String get complaintOpen => 'قدّم شكوى';

  @override
  String get complaintDescription => 'اشرح ما حدث';

  @override
  String get complaintSubmit => 'أرسل الشكوى';

  @override
  String get historyTitle => 'رحلاتي';

  @override
  String get historyEmpty => 'لا رحلات بعد';

  @override
  String get historyViewPath => 'اعرض المسار';

  @override
  String get skip => 'تخطَّ';

  @override
  String get done => 'تمّ';

  @override
  String unitKm(String value) {
    return '$value كم';
  }

  @override
  String unitMinutes(int value) {
    return '$value د';
  }

  @override
  String routeSummary(String km, String minutes) {
    return '$km · $minutes';
  }

  @override
  String get complaintCategory => 'نوع الشكوى';

  @override
  String get complaintCatFare => 'الأجرة';

  @override
  String get complaintCatDriver => 'سلوك السائق';

  @override
  String get complaintCatSafety => 'السلامة';

  @override
  String get complaintCatLostItem => 'غرض منسيّ';

  @override
  String get complaintCatOther => 'أخرى';

  @override
  String get complaintSent => 'وصلت شكواك. سنتابعها.';

  @override
  String get complaintWindow => 'تستطيع تقديم شكوى خلال ٣٠ يومًا من الرحلة.';

  @override
  String get driverGoOnline => 'ابدأ العمل';

  @override
  String get driverGoOffline => 'أنهِ العمل';

  @override
  String get driverConnecting => 'نوصلك…';

  @override
  String get driverOffline => 'متوقّف';

  @override
  String get driverOnlineNoHeartbeat => 'متّصل — بانتظار أوّل نبضة موقع';

  @override
  String get driverOnlineNoHeartbeatHint =>
      'لن تصلك طلبات حتّى يستقبل الخادم موقعك.';

  @override
  String get driverMatchable => 'تعمل الآن';

  @override
  String get driverMatchableHint => 'تظهر للزبائن وتصلك الطلبات.';

  @override
  String get driverStale => 'انقطع النبض';

  @override
  String get driverStaleHint => 'خرجت من الأسطول المرئي. نعيد الاتّصال…';

  @override
  String get driverLocationNeeded => 'نحتاج إذن الموقع لتعمل';

  @override
  String get driverNotEligible => 'لا تستطيع العمل بعد';

  @override
  String get onboardTitle => 'لتبدأ العمل';

  @override
  String get onboardBecomeDriver => 'حوّل حسابك إلى سائق';

  @override
  String get onboardAddVehicle => 'سجّل مركبتك';

  @override
  String get onboardDocuments => 'ارفع الوثائق الأربع';

  @override
  String get onboardPendingReview => 'بانتظار مراجعة الإدارة';

  @override
  String get onboardStepDone => 'اكتمل';

  @override
  String get vehicleTitle => 'مركبتي';

  @override
  String get vehicleAdd => 'سجّل مركبة';

  @override
  String get vehicleType => 'الفئة';

  @override
  String get vehicleMake => 'الصانع';

  @override
  String get vehicleModel => 'الطراز';

  @override
  String get vehicleYear => 'سنة الصنع';

  @override
  String get vehicleColor => 'اللون';

  @override
  String get vehiclePlate => 'رقم اللوحة';

  @override
  String get vehicleSeats => 'عدد المقاعد';

  @override
  String get vehicleActive => 'فعّالة';

  @override
  String get vehicleActivate => 'فعّل';

  @override
  String get vehicleDeactivate => 'عطّل';

  @override
  String get vehicleSaved => 'حُفظت المركبة';

  @override
  String get docsTitle => 'وثائقي';

  @override
  String get docNationalId => 'الهويّة';

  @override
  String get docDriverLicense => 'رخصة القيادة';

  @override
  String get docVehicleRegistration => 'دفتر المركبة';

  @override
  String get docInsurance => 'التأمين';

  @override
  String get docUpload => 'ارفع';

  @override
  String get docReplace => 'استبدل';

  @override
  String get docPending => 'قيد المراجعة';

  @override
  String get docApproved => 'مقبولة';

  @override
  String get docRejected => 'مرفوضة';

  @override
  String get docExpired => 'منتهية';

  @override
  String docExpiresOn(String date) {
    return 'تنتهي في $date';
  }

  @override
  String get docUploading => 'يُرفع…';

  @override
  String get workCandidates => 'الطلبات المتاحة';

  @override
  String get workNoCandidates => 'لا طلبات الآن';

  @override
  String get workNoCandidatesHint =>
      'ستظهر الطلبات القريبة منك هنا فور وصولها.';

  @override
  String get workOfferTitle => 'قدّم عرضك';

  @override
  String get workOfferPrice => 'السعر';

  @override
  String get workOfferEta => 'زمن الوصول بالدقائق';

  @override
  String get workOfferSend => 'أرسل العرض';

  @override
  String get workOfferSent => 'أُرسل عرضك';

  @override
  String workFareRange(String min, String max) {
    return 'بين $min و $max';
  }

  @override
  String get workFareOutOfRange => 'السعر خارج الممرّ المسموح';

  @override
  String workDistanceToPickup(String km) {
    return '$km إلى نقطة الالتقاء';
  }

  @override
  String get invitationIncoming => 'دعوة واردة';

  @override
  String get invitationAccept => 'اقبل';

  @override
  String get invitationReject => 'ارفض';

  @override
  String get invitationRejectReason => 'سبب الرفض (اختياري)';

  @override
  String get invitationGone => 'لم تعد الدعوة صالحة';

  @override
  String get runArrived => 'وصلتُ';

  @override
  String get runStart => 'ابدأ الرحلة';

  @override
  String get runComplete => 'أنهِ الرحلة';

  @override
  String runTooFarPickup(int meters) {
    return 'اقترب أكثر: عليك أن تكون ضمن $meters متر من نقطة الالتقاء';
  }

  @override
  String runTooFarDropoff(int meters) {
    return 'عليك أن تكون ضمن $meters متر من الوجهة';
  }

  @override
  String runRemaining(int meters) {
    return 'تبقّى $meters متر';
  }

  @override
  String get runToPickup => 'إلى نقطة الالتقاء';

  @override
  String get runToDestination => 'إلى الوجهة';

  @override
  String get runPassenger => 'الراكب';

  @override
  String get collectTitle => 'تحصيل الأجرة';

  @override
  String get collectConfirm => 'استلمتُ المبلغ';

  @override
  String get collectDone => 'سُجّل التحصيل';

  @override
  String get collectNote =>
      'أنت وحدك من يؤكّد قبض النقد. لا يستطيع الزبون ذلك.';

  @override
  String get balanceTitle => 'رصيدي';

  @override
  String get balanceTotal => 'الإجمالي';

  @override
  String get publishTitle => 'انشر رحلة';

  @override
  String get publishCapacity => 'المقاعد';

  @override
  String get publishPricePerSeat => 'سعر المقعد';

  @override
  String get publishWhen => 'الموعد';

  @override
  String get publishSubmit => 'انشر';

  @override
  String get publishDone => 'نُشرت الرحلة';

  @override
  String get publishTitleField => 'عنوان الرحلة';

  @override
  String get sharedTitle => 'رحلات مشتركة قريبة';

  @override
  String get sharedNone => 'لا رحلات مشتركة متاحة الآن';

  @override
  String get sharedJoin => 'انضمّ';

  @override
  String sharedCompatibility(String score) {
    return 'توافق $score٪';
  }

  @override
  String sharedSeatsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count مقعدًا متبقّيًا',
      few: '$count مقاعد متبقّية',
      two: 'مقعدان متبقّيان',
      one: 'مقعد واحد متبقٍّ',
    );
    return '$_temp0';
  }

  @override
  String sharedOnboard(int male, int female) {
    return 'على المتن: $male رجل · $female امرأة';
  }

  @override
  String get sharedJoined => 'انضممتَ إلى الرحلة';

  @override
  String get sharedFull => 'امتلأت المقاعد. اختر رحلة أخرى.';

  @override
  String get catalogTitle => 'سفريات ورحلات منشورة';

  @override
  String get catalogEmpty => 'لا رحلات منشورة الآن';

  @override
  String get catalogBook => 'احجز مقعدًا';

  @override
  String get catalogBooked => 'حُجز مقعدك';

  @override
  String get catalogPricePerSeat => 'للمقعد';

  @override
  String catalogDeparts(String when) {
    return 'ينطلق $when';
  }

  @override
  String get catalogFilterAll => 'الكلّ';

  @override
  String get notificationsTitle => 'الإشعارات';

  @override
  String get notificationsEmpty => 'لا إشعارات';

  @override
  String get channelsTitle => 'قنوات التنبيه';

  @override
  String get channelsHint =>
      'أوّل قناة تُسلّم توقف السلسلة، فلا يصلك الخبر ثلاث مرّات.';

  @override
  String get channelPush => 'إشعار الدفع';

  @override
  String get channelTelegram => 'تليغرام';

  @override
  String get channelSms => 'رسالة نصّية';

  @override
  String get channelLink => 'اربط';

  @override
  String get channelUnlink => 'افصل';

  @override
  String get channelLinked => 'مربوط';

  @override
  String get channelNotLinked => 'غير مربوط';

  @override
  String get channelTelegramOpening => 'نفتح تليغرام… اضغط «ابدأ» هناك.';

  @override
  String get channelTelegramLinked => 'رُبط تليغرام';

  @override
  String get channelPriority => 'الأولوية';

  @override
  String get paymentDiscountFirstRide => 'خصم أوّل مشوار';

  @override
  String get paymentDiscountCredit => 'رصيد الدعوات';

  @override
  String get paymentDiscount => 'الخصم';

  @override
  String get paymentSubtotal => 'الأجرة';

  @override
  String get perksTitle => 'اشتراك الصباح والدعوات';

  @override
  String get perksSubscriptionsSection => 'اشتراك الصباح';

  @override
  String get perksSubscriptionsEmpty =>
      'لا اشتراك بعد. أضف مشوارك اليوميّ ونرسل السيارة كلّ يوم قبل الموعد.';

  @override
  String get perksSubscriptionAdd => 'اشتراك جديد';

  @override
  String get perksSubscriptionLabel => 'اسم الاشتراك (اختياريّ)';

  @override
  String get perksSubscriptionLabelHint => 'إلى الجامعة';

  @override
  String get perksSubscriptionTime => 'موعد الانطلاق';

  @override
  String get perksSubscriptionDays => 'الأيام';

  @override
  String get perksSubscriptionPickup => 'نقطة الانطلاق: موقعك الآن';

  @override
  String get perksSubscriptionDestination => 'الوجهة';

  @override
  String get perksSubscriptionPickDestination => 'اختر الوجهة من الخريطة';

  @override
  String get perksSubscriptionDestinationSet => 'الوجهة محدّدة';

  @override
  String perksSubscriptionNext(String when) {
    return 'الطلب القادم: $when';
  }

  @override
  String get perksSubscriptionPaused => 'متوقّف';

  @override
  String get perksSubscriptionCancel => 'إلغاء الاشتراك';

  @override
  String get perksSubscriptionCancelConfirm =>
      'نلغي هذا الاشتراك؟ لن نُنشئ طلبًا له بعد الآن.';

  @override
  String get perksSubscriptionCreated =>
      'أُنشئ الاشتراك. سنطلب لك سيارة قبل الموعد بنصف ساعة.';

  @override
  String get perksSubscriptionNeedDestination => 'حدّد الوجهة أوّلًا.';

  @override
  String get perksReferralSection => 'زبون يجلب زبونًا';

  @override
  String get perksReferralMyCode => 'رمز دعوتي';

  @override
  String get perksReferralExplain =>
      'شارك رمزك مع صديق. بعد أوّل مشوار له يحصل كلاكما على رصيد يُخصم من الرحلة التالية.';

  @override
  String get perksReferralShare => 'مشاركة الرمز';

  @override
  String perksReferralShareText(String code) {
    return 'جرّب سووم تكسي — أدخل رمز دعوتي $code قبل أوّل مشوار لك ونحصل معًا على رصيد.';
  }

  @override
  String get perksReferralCopied => 'نُسخ الرمز';

  @override
  String get perksReferralEnter => 'أدخل رمز صديق';

  @override
  String get perksReferralEnterHint => 'مثل ABC123';

  @override
  String get perksReferralApply => 'تفعيل';

  @override
  String perksReferralApplied(String code) {
    return 'فُعّل رمز $code. الرصيد يصلكما بعد أوّل مشوار.';
  }

  @override
  String perksReferralLinked(String code) {
    return 'دعاك: $code';
  }

  @override
  String get perksCreditBalance => 'رصيدك';

  @override
  String get perksFirstRideAvailable =>
      'أوّل مشوار لك بنصف السعر — الخصم يُطبَّق تلقائيًّا عند الدفع.';

  @override
  String get perksFirstRideUsed => 'استُخدم خصم أوّل مشوار.';

  @override
  String get dayMon => 'الاثنين';

  @override
  String get dayTue => 'الثلاثاء';

  @override
  String get dayWed => 'الأربعاء';

  @override
  String get dayThu => 'الخميس';

  @override
  String get dayFri => 'الجمعة';

  @override
  String get daySat => 'السبت';

  @override
  String get daySun => 'الأحد';

  @override
  String get listSeparator => '، ';

  @override
  String get perksNextFormat => 'EEEE d MMM، HH:mm';

  @override
  String get balanceOwedToYou =>
      'تدين لك سووم بهذا المبلغ — خصوماتٌ تحمّلتها عن زبائنك';

  @override
  String get balanceYouOwe => 'عليك للمنصّة';

  @override
  String get balanceLifetimeEarned => 'مجموع ما كسبته';

  @override
  String get balanceLifetimeCommission => 'مجموع العمولة';

  @override
  String get balanceZero => 'لا شيء معلّق بينك وبين المنصّة';

  @override
  String collectDiscountNote(String customer, String rest, String net) {
    return 'الزبون يدفع $customer بعد خصم سووم، والباقي $rest يُضاف إلى رصيدك عند المنصّة. أجرتك كاملة $net.';
  }

  @override
  String get scheduleNow => 'الآن';

  @override
  String get scheduleLater => 'في موعد';

  @override
  String get scheduleFormat => 'EEEE d MMM، HH:mm';

  @override
  String get scheduleTooSoon =>
      'اختر موعدًا بعد عشر دقائق على الأقلّ — وإلّا اطلب الآن.';

  @override
  String get requestScheduledRide => 'احجز الموعد';

  @override
  String upcomingTitle(String when) {
    return 'موعدك: $when';
  }

  @override
  String get upcomingWaiting => 'بانتظار عروض السائقين — نخبرك حين يصل عرض.';

  @override
  String get upcomingConfirmed => 'سائقك مؤكَّد. سنذكّرك قبل الموعد.';

  @override
  String get historyStatusCancelled => 'أُلغيت';

  @override
  String get historyStatusDisputed => 'قيد المراجعة';

  @override
  String get historyStatusUpcoming => 'قادمة';

  @override
  String driverBookingTitle(String when) {
    return 'حجز: $when';
  }

  @override
  String get driverBookingOpen => 'توجّه';

  @override
  String get dispatchOffers => 'سوم';

  @override
  String get dispatchOffersHint => 'السائقون يعرضون أسعارهم وأنت تختار الأنسب';

  @override
  String get dispatchNearest => 'الأقرب';

  @override
  String get dispatchNearestHint => 'أقرب سائق يُرسَل إليك تلقائيًّا';

  @override
  String get dispatchPick => 'اختر سيارتك';

  @override
  String get dispatchPickHint => 'المس السيارة التي تريدها على الخريطة';

  @override
  String get pickTapCar => 'المس سيارة على الخريطة لتختارها';

  @override
  String pickSelected(String name, String vehicle) {
    return '$name · $vehicle';
  }

  @override
  String get searchRadiusLabel => 'نطاق البحث';

  @override
  String radiusKm(String km) {
    return '$km كم';
  }

  @override
  String radiusMeters(String meters) {
    return '$meters م';
  }

  @override
  String get nearestTitle => 'نبحث عن أقرب سائق';

  @override
  String get nearestLooking => 'نسأل أقرب السائقين بالترتيب…';

  @override
  String get nearestAsking => 'ننتظر ردّ أقرب سائق — ثوانٍ قليلة';

  @override
  String get nearestExhausted => 'لم يقبل أحدٌ بعد — العروض مفتوحة الآن';

  @override
  String get requestNearest => 'أرسل أقرب سائق';

  @override
  String get requestPicked => 'اطلب هذه السيارة';

  @override
  String get moreOptions => 'خيارات أكثر';

  @override
  String get serviceClass => 'الدرجة';

  @override
  String carPassengers(int count) {
    return '$count ركّاب';
  }

  @override
  String get carNew => 'جديد';

  @override
  String get runCancel => 'ألغِ الرحلة';

  @override
  String get runCancelTitle => 'لماذا تلغي؟';

  @override
  String get runCancelWarning =>
      'الطلب يعود للبحث عند الزبون. الإلغاء المتكرّر يوقف العروض عنك مؤقّتًا.';

  @override
  String get cancelReasonCar => 'عطل بالسيارة';

  @override
  String get cancelReasonNoAnswer => 'الزبون لا يردّ';

  @override
  String get cancelReasonFar => 'المكان بعيد أو الطريق مغلق';

  @override
  String get cancelReasonOther => 'سبب آخر';

  @override
  String passengerChip(String name, int count) {
    return '$name · $count ركّاب';
  }

  @override
  String lateCancelBadge(int count) {
    return 'ألغى $count مرّات مؤخرًا';
  }

  @override
  String get cancelFreeNow => 'الإلغاء الآن مجّاني.';

  @override
  String get cancelDriverLateFree => 'السائق تأخّر عن موعده — الإلغاء مجّاني.';

  @override
  String cancelCountsStrike(int limit) {
    return 'سيُحسب هذا الإلغاء مخالفة. عند $limit مخالفات خلال أسبوع يتوقّف «الأقرب» و«اختر سيارتك» عنك يومًا.';
  }

  @override
  String get driverCancelledRequeued =>
      'السائق اعتذر — نبحث لك عن سائق آخر الآن.';

  @override
  String get shareRide => 'شارك الرحلة';

  @override
  String get shareRideHint => 'أرخص: تتقاسم السيارة مع ركّاب بطريقك';

  @override
  String get callDriver => 'اتّصل بالسائق';

  @override
  String get callCustomer => 'اتّصل بالزبون';

  @override
  String get serviceSoon => 'قريبًا';

  @override
  String serviceComingSoon(String name) {
    return '«$name» قريبًا في سووم — ترقّبها.';
  }

  @override
  String get incentivesTitle => 'الحوافز';

  @override
  String incentiveRemaining(int count, String reward) {
    return 'بقي $count مشوارًا لتحصل على $reward';
  }

  @override
  String incentiveEarned(String reward) {
    return 'استحققت $reward — تُسلَّم من مكتب سووم';
  }

  @override
  String get incentiveDelivered => 'سُلّمت المكافأة — شكرًا لك';

  @override
  String get tripCancelWhy => 'لماذا تلغي الرحلة؟';

  @override
  String get riderCancelChangedMind => 'غيّرت رأيي';

  @override
  String get riderCancelDriverLate => 'السائق تأخّر';

  @override
  String get riderCancelDriverNotMoving => 'السائق لا يتحرّك نحوي';

  @override
  String get riderCancelDriverAsked => 'السائق طلب منّي أن ألغي';

  @override
  String get riderCancelFoundOther => 'وجدت وسيلة أخرى';

  @override
  String get riderCancelWrongPickup => 'مكان الالتقاط خاطئ';

  @override
  String get riderCancelOther => 'سبب آخر';

  @override
  String get driverMockLocation =>
      'هاتفك يرسل موقعًا مزيّفًا (Mock location)، فلا نستطيع إرسالك إلى الزبائن. أطفئ تطبيق تزييف الموقع من «خيارات المطوّر» ثمّ شغّل العمل من جديد.';
}
