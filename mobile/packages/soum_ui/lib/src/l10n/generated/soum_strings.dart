import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'soum_strings_ar.dart';
import 'soum_strings_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of SoumStrings
/// returned by `SoumStrings.of(context)`.
///
/// Applications need to include `SoumStrings.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/soum_strings.dart';
///
/// return MaterialApp(
///   localizationsDelegates: SoumStrings.localizationsDelegates,
///   supportedLocales: SoumStrings.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the SoumStrings.supportedLocales
/// property.
abstract class SoumStrings {
  SoumStrings(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static SoumStrings of(BuildContext context) {
    return Localizations.of<SoumStrings>(context, SoumStrings)!;
  }

  static const LocalizationsDelegate<SoumStrings> delegate =
      _SoumStringsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('ar'),
    Locale('en'),
  ];

  /// No description provided for @appNameCustomer.
  ///
  /// In ar, this message translates to:
  /// **'سووم تكسي'**
  String get appNameCustomer;

  /// No description provided for @appNameDriver.
  ///
  /// In ar, this message translates to:
  /// **'سووم تكسي — سائق'**
  String get appNameDriver;

  /// No description provided for @actionRetry.
  ///
  /// In ar, this message translates to:
  /// **'أعد المحاولة'**
  String get actionRetry;

  /// No description provided for @actionCancel.
  ///
  /// In ar, this message translates to:
  /// **'إلغاء'**
  String get actionCancel;

  /// No description provided for @actionConfirm.
  ///
  /// In ar, this message translates to:
  /// **'تأكيد'**
  String get actionConfirm;

  /// No description provided for @actionContinue.
  ///
  /// In ar, this message translates to:
  /// **'متابعة'**
  String get actionContinue;

  /// No description provided for @actionClose.
  ///
  /// In ar, this message translates to:
  /// **'إغلاق'**
  String get actionClose;

  /// No description provided for @actionBack.
  ///
  /// In ar, this message translates to:
  /// **'رجوع'**
  String get actionBack;

  /// No description provided for @actionEdit.
  ///
  /// In ar, this message translates to:
  /// **'تعديل'**
  String get actionEdit;

  /// No description provided for @bootLoadingConfig.
  ///
  /// In ar, this message translates to:
  /// **'نقرأ إعدادات مدينتك…'**
  String get bootLoadingConfig;

  /// No description provided for @bootLoadingSession.
  ///
  /// In ar, this message translates to:
  /// **'نستعيد جلستك…'**
  String get bootLoadingSession;

  /// No description provided for @bootRestoringRide.
  ///
  /// In ar, this message translates to:
  /// **'نعيدك إلى رحلتك…'**
  String get bootRestoringRide;

  /// No description provided for @bootNoConnection.
  ///
  /// In ar, this message translates to:
  /// **'لا اتصال بالإنترنت'**
  String get bootNoConnection;

  /// No description provided for @bootNoConnectionBody.
  ///
  /// In ar, this message translates to:
  /// **'نحتاج اتصالًا مرّة واحدة لقراءة إعدادات مدينتك. تحقّق من شبكتك ثمّ أعد المحاولة.'**
  String get bootNoConnectionBody;

  /// No description provided for @bootOutsideServiceArea.
  ///
  /// In ar, this message translates to:
  /// **'خارج مناطق الخدمة'**
  String get bootOutsideServiceArea;

  /// No description provided for @bootOutsideServiceAreaBody.
  ///
  /// In ar, this message translates to:
  /// **'لا نخدم موقعك الحالي بعد. تستطيع تصفّح التطبيق، لكن لن تجد سيارات قريبة.'**
  String get bootOutsideServiceAreaBody;

  /// No description provided for @authPhoneTitle.
  ///
  /// In ar, this message translates to:
  /// **'أدخل رقم هاتفك'**
  String get authPhoneTitle;

  /// No description provided for @authPhoneSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'سنرسل لك رمزًا من أربعة إلى ستّة أرقام للتحقّق.'**
  String get authPhoneSubtitle;

  /// No description provided for @authPhoneLabel.
  ///
  /// In ar, this message translates to:
  /// **'رقم الهاتف'**
  String get authPhoneLabel;

  /// No description provided for @authPhoneHint.
  ///
  /// In ar, this message translates to:
  /// **'9XXXXXXXX'**
  String get authPhoneHint;

  /// No description provided for @authPhoneInvalid.
  ///
  /// In ar, this message translates to:
  /// **'أدخل رقمًا سوريًّا صحيحًا'**
  String get authPhoneInvalid;

  /// No description provided for @authSendCode.
  ///
  /// In ar, this message translates to:
  /// **'أرسل الرمز'**
  String get authSendCode;

  /// No description provided for @authCodeTitle.
  ///
  /// In ar, this message translates to:
  /// **'أدخل الرمز'**
  String get authCodeTitle;

  /// No description provided for @authCodeSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'أرسلنا رمزًا إلى {phone}'**
  String authCodeSubtitle(String phone);

  /// No description provided for @authCodeLabel.
  ///
  /// In ar, this message translates to:
  /// **'رمز التحقّق'**
  String get authCodeLabel;

  /// No description provided for @authCodeInvalid.
  ///
  /// In ar, this message translates to:
  /// **'الرمز غير مكتمل'**
  String get authCodeInvalid;

  /// No description provided for @authVerify.
  ///
  /// In ar, this message translates to:
  /// **'تحقّق'**
  String get authVerify;

  /// No description provided for @authResendIn.
  ///
  /// In ar, this message translates to:
  /// **'إعادة الإرسال بعد {seconds} ثانية'**
  String authResendIn(int seconds);

  /// No description provided for @authResend.
  ///
  /// In ar, this message translates to:
  /// **'أعد إرسال الرمز'**
  String get authResend;

  /// No description provided for @authChangePhone.
  ///
  /// In ar, this message translates to:
  /// **'غيّر الرقم'**
  String get authChangePhone;

  /// No description provided for @authDevelopmentCode.
  ///
  /// In ar, this message translates to:
  /// **'رمز التطوير: {code}'**
  String authDevelopmentCode(String code);

  /// No description provided for @authCodeExpiresIn.
  ///
  /// In ar, this message translates to:
  /// **'ينتهي الرمز بعد {seconds} ثانية'**
  String authCodeExpiresIn(int seconds);

  /// No description provided for @authThrottled.
  ///
  /// In ar, this message translates to:
  /// **'تجاوزتَ عدد المحاولات. أعد المحاولة بعد {seconds} ثانية.'**
  String authThrottled(int seconds);

  /// No description provided for @errorNetwork.
  ///
  /// In ar, this message translates to:
  /// **'لا اتصال بالإنترنت'**
  String get errorNetwork;

  /// No description provided for @errorNetworkBody.
  ///
  /// In ar, this message translates to:
  /// **'تحقّق من شبكتك ثمّ أعد المحاولة.'**
  String get errorNetworkBody;

  /// No description provided for @errorGeneric.
  ///
  /// In ar, this message translates to:
  /// **'تعذّر إتمام العملية'**
  String get errorGeneric;

  /// No description provided for @errorSupportReference.
  ///
  /// In ar, this message translates to:
  /// **'رقم المرجع: {requestId}'**
  String errorSupportReference(String requestId);

  /// No description provided for @sessionExpiredTitle.
  ///
  /// In ar, this message translates to:
  /// **'انتهت جلستك'**
  String get sessionExpiredTitle;

  /// No description provided for @sessionExpiredBody.
  ///
  /// In ar, this message translates to:
  /// **'سجّل الدخول مرّة أخرى للمتابعة.'**
  String get sessionExpiredBody;

  /// No description provided for @logout.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الخروج'**
  String get logout;

  /// No description provided for @logoutConfirm.
  ///
  /// In ar, this message translates to:
  /// **'هل تريد تسجيل الخروج؟'**
  String get logoutConfirm;

  /// No description provided for @currencySyp.
  ///
  /// In ar, this message translates to:
  /// **'ل.س'**
  String get currencySyp;

  /// No description provided for @fareApproximate.
  ///
  /// In ar, this message translates to:
  /// **'سعر تقريبي'**
  String get fareApproximate;

  /// No description provided for @fareRouted.
  ///
  /// In ar, this message translates to:
  /// **'سعر المسار'**
  String get fareRouted;

  /// No description provided for @fareBreakdownTitle.
  ///
  /// In ar, this message translates to:
  /// **'تفصيل الأجرة'**
  String get fareBreakdownTitle;

  /// No description provided for @fareBase.
  ///
  /// In ar, this message translates to:
  /// **'الأجرة الأساسية'**
  String get fareBase;

  /// No description provided for @fareDistance.
  ///
  /// In ar, this message translates to:
  /// **'المسافة'**
  String get fareDistance;

  /// No description provided for @fareTime.
  ///
  /// In ar, this message translates to:
  /// **'الزمن'**
  String get fareTime;

  /// No description provided for @fareGross.
  ///
  /// In ar, this message translates to:
  /// **'الإجمالي'**
  String get fareGross;

  /// No description provided for @farePlatformFee.
  ///
  /// In ar, this message translates to:
  /// **'عمولة المنصّة'**
  String get farePlatformFee;

  /// No description provided for @fareCustomerTotal.
  ///
  /// In ar, this message translates to:
  /// **'ما تدفعه'**
  String get fareCustomerTotal;

  /// No description provided for @fareDriverNet.
  ///
  /// In ar, this message translates to:
  /// **'ما يقبضه السائق'**
  String get fareDriverNet;

  /// No description provided for @fareApproximateNote.
  ///
  /// In ar, this message translates to:
  /// **'تعذّر حساب المسار الفعليّ، فهذا تقدير قد يختلف قليلًا.'**
  String get fareApproximateNote;

  /// No description provided for @homeWhereTo.
  ///
  /// In ar, this message translates to:
  /// **'إلى أين؟'**
  String get homeWhereTo;

  /// No description provided for @homePickup.
  ///
  /// In ar, this message translates to:
  /// **'نقطة الانطلاق'**
  String get homePickup;

  /// No description provided for @homeDestination.
  ///
  /// In ar, this message translates to:
  /// **'الوجهة'**
  String get homeDestination;

  /// No description provided for @homeSetOnMap.
  ///
  /// In ar, this message translates to:
  /// **'حدّد على الخريطة'**
  String get homeSetOnMap;

  /// No description provided for @homeMyLocation.
  ///
  /// In ar, this message translates to:
  /// **'موقعي'**
  String get homeMyLocation;

  /// No description provided for @homeCarsNearby.
  ///
  /// In ar, this message translates to:
  /// **'{count,plural, =0{لا سيارات قريبة} =1{سيارة واحدة قريبة} =2{سيارتان قريبتان} few{{count} سيارات قريبة} other{{count} سيارة قريبة}}'**
  String homeCarsNearby(int count);

  /// No description provided for @homeNoCarsInRange.
  ///
  /// In ar, this message translates to:
  /// **'لا سيارات ضمن {km} كم'**
  String homeNoCarsInRange(String km);

  /// No description provided for @homeOutsideArea.
  ///
  /// In ar, this message translates to:
  /// **'أنت خارج مناطق الخدمة'**
  String get homeOutsideArea;

  /// No description provided for @homeLocating.
  ///
  /// In ar, this message translates to:
  /// **'نحدّد موقعك…'**
  String get homeLocating;

  /// No description provided for @modeFast.
  ///
  /// In ar, this message translates to:
  /// **'سريع'**
  String get modeFast;

  /// No description provided for @modeFastHint.
  ///
  /// In ar, this message translates to:
  /// **'أقرب سائق، وخريطة حيّة ودعوة مباشرة'**
  String get modeFastHint;

  /// No description provided for @modeExpress.
  ///
  /// In ar, this message translates to:
  /// **'فوري'**
  String get modeExpress;

  /// No description provided for @modeExpressHint.
  ///
  /// In ar, this message translates to:
  /// **'الأسرع، بدعوة مباشرة'**
  String get modeExpressHint;

  /// No description provided for @modeStandard.
  ///
  /// In ar, this message translates to:
  /// **'عادي'**
  String get modeStandard;

  /// No description provided for @modeStandardHint.
  ///
  /// In ar, this message translates to:
  /// **'التوازن المعتاد بين السعر والزمن'**
  String get modeStandardHint;

  /// No description provided for @modeSaving.
  ///
  /// In ar, this message translates to:
  /// **'اقتصادي'**
  String get modeSaving;

  /// No description provided for @modeSavingHint.
  ///
  /// In ar, this message translates to:
  /// **'الأرخص، بنطاق أوسع وانتظار أطول'**
  String get modeSavingHint;

  /// No description provided for @modeShared.
  ///
  /// In ar, this message translates to:
  /// **'مشترك'**
  String get modeShared;

  /// No description provided for @modeSharedHint.
  ///
  /// In ar, this message translates to:
  /// **'تنضمّ إلى رحلة قائمة وتتقاسم الأجرة'**
  String get modeSharedHint;

  /// No description provided for @categoryCity.
  ///
  /// In ar, this message translates to:
  /// **'داخل المدينة'**
  String get categoryCity;

  /// No description provided for @categoryIntercity.
  ///
  /// In ar, this message translates to:
  /// **'بين المدينتين'**
  String get categoryIntercity;

  /// No description provided for @categoryServiceLine.
  ///
  /// In ar, this message translates to:
  /// **'خطّ سرفيس'**
  String get categoryServiceLine;

  /// No description provided for @categoryRecreational.
  ///
  /// In ar, this message translates to:
  /// **'رحلة ترفيهية'**
  String get categoryRecreational;

  /// No description provided for @cityOrigin.
  ///
  /// In ar, this message translates to:
  /// **'مدينة الانطلاق'**
  String get cityOrigin;

  /// No description provided for @cityDestination.
  ///
  /// In ar, this message translates to:
  /// **'مدينة الوصول'**
  String get cityDestination;

  /// No description provided for @cityRequired.
  ///
  /// In ar, this message translates to:
  /// **'مطلوبة لهذا النوع'**
  String get cityRequired;

  /// No description provided for @passengers.
  ///
  /// In ar, this message translates to:
  /// **'{count,plural, =1{راكب واحد} =2{راكبان} few{{count} ركّاب} other{{count} راكبًا}}'**
  String passengers(int count);

  /// No description provided for @vehicleAny.
  ///
  /// In ar, this message translates to:
  /// **'أي سيارة'**
  String get vehicleAny;

  /// No description provided for @requestRide.
  ///
  /// In ar, this message translates to:
  /// **'اطلب الرحلة'**
  String get requestRide;

  /// No description provided for @scheduleFor.
  ///
  /// In ar, this message translates to:
  /// **'احجز لوقت لاحق'**
  String get scheduleFor;

  /// No description provided for @searchingTitle.
  ///
  /// In ar, this message translates to:
  /// **'نبحث عن سائق'**
  String get searchingTitle;

  /// No description provided for @searchingSubtitle.
  ///
  /// In ar, this message translates to:
  /// **'ضمن {km} كم من نقطة انطلاقك'**
  String searchingSubtitle(String km);

  /// No description provided for @searchingTimeLeft.
  ///
  /// In ar, this message translates to:
  /// **'{seconds} ثانية'**
  String searchingTimeLeft(int seconds);

  /// No description provided for @offersTitle.
  ///
  /// In ar, this message translates to:
  /// **'{count,plural, =1{عرض واحد} =2{عرضان} few{{count} عروض} other{{count} عرضًا}}'**
  String offersTitle(int count);

  /// No description provided for @offersEmpty.
  ///
  /// In ar, this message translates to:
  /// **'لم يصل عرض بعد'**
  String get offersEmpty;

  /// No description provided for @offerEta.
  ///
  /// In ar, this message translates to:
  /// **'{minutes, plural, =0{أقلّ من دقيقة} =1{دقيقة واحدة} =2{دقيقتان} few{{minutes} دقائق} other{{minutes} دقيقة}}'**
  String offerEta(int minutes);

  /// No description provided for @offerChoose.
  ///
  /// In ar, this message translates to:
  /// **'اختر'**
  String get offerChoose;

  /// No description provided for @offerTaken.
  ///
  /// In ar, this message translates to:
  /// **'هذه السيارة لم تعد متاحة. اختر غيرها.'**
  String get offerTaken;

  /// No description provided for @rideExpired.
  ///
  /// In ar, this message translates to:
  /// **'لم نجد سائقًا'**
  String get rideExpired;

  /// No description provided for @rideExpiredBody.
  ///
  /// In ar, this message translates to:
  /// **'انتهت مهلة البحث بلا عرض. جرّب نمطًا أوسع أو أعد المحاولة.'**
  String get rideExpiredBody;

  /// No description provided for @rideCancelled.
  ///
  /// In ar, this message translates to:
  /// **'أُلغي الطلب'**
  String get rideCancelled;

  /// No description provided for @cancelRide.
  ///
  /// In ar, this message translates to:
  /// **'ألغِ الطلب'**
  String get cancelRide;

  /// No description provided for @inviteTitle.
  ///
  /// In ar, this message translates to:
  /// **'ادعُ سيارة بعينها'**
  String get inviteTitle;

  /// No description provided for @inviteSend.
  ///
  /// In ar, this message translates to:
  /// **'ادعُ'**
  String get inviteSend;

  /// No description provided for @inviteWaiting.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار ردّ السائق'**
  String get inviteWaiting;

  /// No description provided for @inviteTtl.
  ///
  /// In ar, this message translates to:
  /// **'مهلة الردّ'**
  String get inviteTtl;

  /// No description provided for @inviteRejected.
  ///
  /// In ar, this message translates to:
  /// **'اعتذر السائق. اختر سيارة أخرى.'**
  String get inviteRejected;

  /// No description provided for @inviteExpired.
  ///
  /// In ar, this message translates to:
  /// **'انقضت المهلة بلا ردّ'**
  String get inviteExpired;

  /// No description provided for @inviteCancel.
  ///
  /// In ar, this message translates to:
  /// **'ألغِ الدعوة'**
  String get inviteCancel;

  /// No description provided for @inviteSeatsAvailable.
  ///
  /// In ar, this message translates to:
  /// **'{count} مقعد متاح'**
  String inviteSeatsAvailable(int count);

  /// No description provided for @inviteDistance.
  ///
  /// In ar, this message translates to:
  /// **'{meters} متر تقريبًا'**
  String inviteDistance(int meters);

  /// No description provided for @tripDriverAssigned.
  ///
  /// In ar, this message translates to:
  /// **'تأكّدت رحلتك'**
  String get tripDriverAssigned;

  /// No description provided for @tripDriverArriving.
  ///
  /// In ar, this message translates to:
  /// **'السائق في الطريق إليك'**
  String get tripDriverArriving;

  /// No description provided for @tripDriverArrived.
  ///
  /// In ar, this message translates to:
  /// **'سائقك بانتظارك'**
  String get tripDriverArrived;

  /// No description provided for @tripInProgress.
  ///
  /// In ar, this message translates to:
  /// **'في الطريق إلى وجهتك'**
  String get tripInProgress;

  /// No description provided for @tripCompleted.
  ///
  /// In ar, this message translates to:
  /// **'وصلت'**
  String get tripCompleted;

  /// No description provided for @tripCancelledBy.
  ///
  /// In ar, this message translates to:
  /// **'أُلغيت الرحلة'**
  String get tripCancelledBy;

  /// No description provided for @tripCallDriver.
  ///
  /// In ar, this message translates to:
  /// **'اتّصل بالسائق'**
  String get tripCallDriver;

  /// No description provided for @tripCancelTrip.
  ///
  /// In ar, this message translates to:
  /// **'ألغِ الرحلة'**
  String get tripCancelTrip;

  /// No description provided for @tripPlate.
  ///
  /// In ar, this message translates to:
  /// **'اللوحة'**
  String get tripPlate;

  /// No description provided for @paymentTitle.
  ///
  /// In ar, this message translates to:
  /// **'الدفع'**
  String get paymentTitle;

  /// No description provided for @paymentCashWaiting.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار تأكيد السائق قبض المبلغ'**
  String get paymentCashWaiting;

  /// No description provided for @paymentCashNote.
  ///
  /// In ar, this message translates to:
  /// **'ادفع للسائق نقدًا. هو من يؤكّد القبض في تطبيقه.'**
  String get paymentCashNote;

  /// No description provided for @paymentPaid.
  ///
  /// In ar, this message translates to:
  /// **'تمّ الدفع'**
  String get paymentPaid;

  /// No description provided for @paymentAmount.
  ///
  /// In ar, this message translates to:
  /// **'المبلغ'**
  String get paymentAmount;

  /// No description provided for @rateTitle.
  ///
  /// In ar, this message translates to:
  /// **'كيف كانت رحلتك؟'**
  String get rateTitle;

  /// No description provided for @rateSubmit.
  ///
  /// In ar, this message translates to:
  /// **'أرسل التقييم'**
  String get rateSubmit;

  /// No description provided for @rateReasonRequired.
  ///
  /// In ar, this message translates to:
  /// **'اختر سببًا أو اكتب تعليقًا'**
  String get rateReasonRequired;

  /// No description provided for @rateComment.
  ///
  /// In ar, this message translates to:
  /// **'تعليق (اختياري)'**
  String get rateComment;

  /// No description provided for @rateThanks.
  ///
  /// In ar, this message translates to:
  /// **'شكرًا لتقييمك'**
  String get rateThanks;

  /// No description provided for @rateAlready.
  ///
  /// In ar, this message translates to:
  /// **'قيّمتَ هذه الرحلة من قبل'**
  String get rateAlready;

  /// No description provided for @complaintOpen.
  ///
  /// In ar, this message translates to:
  /// **'قدّم شكوى'**
  String get complaintOpen;

  /// No description provided for @complaintDescription.
  ///
  /// In ar, this message translates to:
  /// **'اشرح ما حدث'**
  String get complaintDescription;

  /// No description provided for @complaintSubmit.
  ///
  /// In ar, this message translates to:
  /// **'أرسل الشكوى'**
  String get complaintSubmit;

  /// No description provided for @historyTitle.
  ///
  /// In ar, this message translates to:
  /// **'رحلاتي'**
  String get historyTitle;

  /// No description provided for @historyEmpty.
  ///
  /// In ar, this message translates to:
  /// **'لا رحلات بعد'**
  String get historyEmpty;

  /// No description provided for @historyViewPath.
  ///
  /// In ar, this message translates to:
  /// **'اعرض المسار'**
  String get historyViewPath;

  /// No description provided for @skip.
  ///
  /// In ar, this message translates to:
  /// **'تخطَّ'**
  String get skip;

  /// No description provided for @done.
  ///
  /// In ar, this message translates to:
  /// **'تمّ'**
  String get done;

  /// No description provided for @unitKm.
  ///
  /// In ar, this message translates to:
  /// **'{value} كم'**
  String unitKm(String value);

  /// No description provided for @unitMinutes.
  ///
  /// In ar, this message translates to:
  /// **'{value} د'**
  String unitMinutes(int value);

  /// No description provided for @routeSummary.
  ///
  /// In ar, this message translates to:
  /// **'{km} · {minutes}'**
  String routeSummary(String km, String minutes);

  /// No description provided for @complaintCategory.
  ///
  /// In ar, this message translates to:
  /// **'نوع الشكوى'**
  String get complaintCategory;

  /// No description provided for @complaintCatFare.
  ///
  /// In ar, this message translates to:
  /// **'الأجرة'**
  String get complaintCatFare;

  /// No description provided for @complaintCatDriver.
  ///
  /// In ar, this message translates to:
  /// **'سلوك السائق'**
  String get complaintCatDriver;

  /// No description provided for @complaintCatSafety.
  ///
  /// In ar, this message translates to:
  /// **'السلامة'**
  String get complaintCatSafety;

  /// No description provided for @complaintCatLostItem.
  ///
  /// In ar, this message translates to:
  /// **'غرض منسيّ'**
  String get complaintCatLostItem;

  /// No description provided for @complaintCatOther.
  ///
  /// In ar, this message translates to:
  /// **'أخرى'**
  String get complaintCatOther;

  /// No description provided for @complaintSent.
  ///
  /// In ar, this message translates to:
  /// **'وصلت شكواك. سنتابعها.'**
  String get complaintSent;

  /// No description provided for @complaintWindow.
  ///
  /// In ar, this message translates to:
  /// **'تستطيع تقديم شكوى خلال ٣٠ يومًا من الرحلة.'**
  String get complaintWindow;

  /// No description provided for @driverGoOnline.
  ///
  /// In ar, this message translates to:
  /// **'ابدأ العمل'**
  String get driverGoOnline;

  /// No description provided for @driverGoOffline.
  ///
  /// In ar, this message translates to:
  /// **'أنهِ العمل'**
  String get driverGoOffline;

  /// No description provided for @driverConnecting.
  ///
  /// In ar, this message translates to:
  /// **'نوصلك…'**
  String get driverConnecting;

  /// No description provided for @driverOffline.
  ///
  /// In ar, this message translates to:
  /// **'متوقّف'**
  String get driverOffline;

  /// No description provided for @driverOnlineNoHeartbeat.
  ///
  /// In ar, this message translates to:
  /// **'متّصل — بانتظار أوّل نبضة موقع'**
  String get driverOnlineNoHeartbeat;

  /// No description provided for @driverOnlineNoHeartbeatHint.
  ///
  /// In ar, this message translates to:
  /// **'لن تصلك طلبات حتّى يستقبل الخادم موقعك.'**
  String get driverOnlineNoHeartbeatHint;

  /// No description provided for @driverMatchable.
  ///
  /// In ar, this message translates to:
  /// **'تعمل الآن'**
  String get driverMatchable;

  /// No description provided for @driverMatchableHint.
  ///
  /// In ar, this message translates to:
  /// **'تظهر للزبائن وتصلك الطلبات.'**
  String get driverMatchableHint;

  /// No description provided for @driverStale.
  ///
  /// In ar, this message translates to:
  /// **'انقطع النبض'**
  String get driverStale;

  /// No description provided for @driverStaleHint.
  ///
  /// In ar, this message translates to:
  /// **'خرجت من الأسطول المرئي. نعيد الاتّصال…'**
  String get driverStaleHint;

  /// No description provided for @driverLocationNeeded.
  ///
  /// In ar, this message translates to:
  /// **'نحتاج إذن الموقع لتعمل'**
  String get driverLocationNeeded;

  /// No description provided for @driverNotEligible.
  ///
  /// In ar, this message translates to:
  /// **'لا تستطيع العمل بعد'**
  String get driverNotEligible;

  /// No description provided for @onboardTitle.
  ///
  /// In ar, this message translates to:
  /// **'لتبدأ العمل'**
  String get onboardTitle;

  /// No description provided for @onboardBecomeDriver.
  ///
  /// In ar, this message translates to:
  /// **'حوّل حسابك إلى سائق'**
  String get onboardBecomeDriver;

  /// No description provided for @onboardAddVehicle.
  ///
  /// In ar, this message translates to:
  /// **'سجّل مركبتك'**
  String get onboardAddVehicle;

  /// No description provided for @onboardDocuments.
  ///
  /// In ar, this message translates to:
  /// **'ارفع الوثائق الأربع'**
  String get onboardDocuments;

  /// No description provided for @onboardPendingReview.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار مراجعة الإدارة'**
  String get onboardPendingReview;

  /// No description provided for @onboardStepDone.
  ///
  /// In ar, this message translates to:
  /// **'اكتمل'**
  String get onboardStepDone;

  /// No description provided for @vehicleTitle.
  ///
  /// In ar, this message translates to:
  /// **'مركبتي'**
  String get vehicleTitle;

  /// No description provided for @vehicleAdd.
  ///
  /// In ar, this message translates to:
  /// **'سجّل مركبة'**
  String get vehicleAdd;

  /// No description provided for @vehicleType.
  ///
  /// In ar, this message translates to:
  /// **'الفئة'**
  String get vehicleType;

  /// No description provided for @vehicleMake.
  ///
  /// In ar, this message translates to:
  /// **'الصانع'**
  String get vehicleMake;

  /// No description provided for @vehicleModel.
  ///
  /// In ar, this message translates to:
  /// **'الطراز'**
  String get vehicleModel;

  /// No description provided for @vehicleYear.
  ///
  /// In ar, this message translates to:
  /// **'سنة الصنع'**
  String get vehicleYear;

  /// No description provided for @vehicleColor.
  ///
  /// In ar, this message translates to:
  /// **'اللون'**
  String get vehicleColor;

  /// No description provided for @vehiclePlate.
  ///
  /// In ar, this message translates to:
  /// **'رقم اللوحة'**
  String get vehiclePlate;

  /// No description provided for @vehicleSeats.
  ///
  /// In ar, this message translates to:
  /// **'عدد المقاعد'**
  String get vehicleSeats;

  /// No description provided for @vehicleActive.
  ///
  /// In ar, this message translates to:
  /// **'فعّالة'**
  String get vehicleActive;

  /// No description provided for @vehicleActivate.
  ///
  /// In ar, this message translates to:
  /// **'فعّل'**
  String get vehicleActivate;

  /// No description provided for @vehicleDeactivate.
  ///
  /// In ar, this message translates to:
  /// **'عطّل'**
  String get vehicleDeactivate;

  /// No description provided for @vehicleSaved.
  ///
  /// In ar, this message translates to:
  /// **'حُفظت المركبة'**
  String get vehicleSaved;

  /// No description provided for @docsTitle.
  ///
  /// In ar, this message translates to:
  /// **'وثائقي'**
  String get docsTitle;

  /// No description provided for @docNationalId.
  ///
  /// In ar, this message translates to:
  /// **'الهويّة'**
  String get docNationalId;

  /// No description provided for @docDriverLicense.
  ///
  /// In ar, this message translates to:
  /// **'رخصة القيادة'**
  String get docDriverLicense;

  /// No description provided for @docVehicleRegistration.
  ///
  /// In ar, this message translates to:
  /// **'دفتر المركبة'**
  String get docVehicleRegistration;

  /// No description provided for @docInsurance.
  ///
  /// In ar, this message translates to:
  /// **'التأمين'**
  String get docInsurance;

  /// No description provided for @docUpload.
  ///
  /// In ar, this message translates to:
  /// **'ارفع'**
  String get docUpload;

  /// No description provided for @docReplace.
  ///
  /// In ar, this message translates to:
  /// **'استبدل'**
  String get docReplace;

  /// No description provided for @docPending.
  ///
  /// In ar, this message translates to:
  /// **'قيد المراجعة'**
  String get docPending;

  /// No description provided for @docApproved.
  ///
  /// In ar, this message translates to:
  /// **'مقبولة'**
  String get docApproved;

  /// No description provided for @docRejected.
  ///
  /// In ar, this message translates to:
  /// **'مرفوضة'**
  String get docRejected;

  /// No description provided for @docExpired.
  ///
  /// In ar, this message translates to:
  /// **'منتهية'**
  String get docExpired;

  /// No description provided for @docExpiresOn.
  ///
  /// In ar, this message translates to:
  /// **'تنتهي في {date}'**
  String docExpiresOn(String date);

  /// No description provided for @docUploading.
  ///
  /// In ar, this message translates to:
  /// **'يُرفع…'**
  String get docUploading;

  /// No description provided for @workCandidates.
  ///
  /// In ar, this message translates to:
  /// **'الطلبات المتاحة'**
  String get workCandidates;

  /// No description provided for @workNoCandidates.
  ///
  /// In ar, this message translates to:
  /// **'لا طلبات الآن'**
  String get workNoCandidates;

  /// No description provided for @workNoCandidatesHint.
  ///
  /// In ar, this message translates to:
  /// **'ستظهر الطلبات القريبة منك هنا فور وصولها.'**
  String get workNoCandidatesHint;

  /// No description provided for @workOfferTitle.
  ///
  /// In ar, this message translates to:
  /// **'قدّم عرضك'**
  String get workOfferTitle;

  /// No description provided for @workOfferPrice.
  ///
  /// In ar, this message translates to:
  /// **'السعر'**
  String get workOfferPrice;

  /// No description provided for @workOfferEta.
  ///
  /// In ar, this message translates to:
  /// **'زمن الوصول بالدقائق'**
  String get workOfferEta;

  /// No description provided for @workOfferSend.
  ///
  /// In ar, this message translates to:
  /// **'أرسل العرض'**
  String get workOfferSend;

  /// No description provided for @workOfferSent.
  ///
  /// In ar, this message translates to:
  /// **'أُرسل عرضك'**
  String get workOfferSent;

  /// No description provided for @workFareRange.
  ///
  /// In ar, this message translates to:
  /// **'بين {min} و {max}'**
  String workFareRange(String min, String max);

  /// No description provided for @workFareOutOfRange.
  ///
  /// In ar, this message translates to:
  /// **'السعر خارج الممرّ المسموح'**
  String get workFareOutOfRange;

  /// No description provided for @workDistanceToPickup.
  ///
  /// In ar, this message translates to:
  /// **'{km} إلى نقطة الالتقاء'**
  String workDistanceToPickup(String km);

  /// No description provided for @invitationIncoming.
  ///
  /// In ar, this message translates to:
  /// **'دعوة واردة'**
  String get invitationIncoming;

  /// No description provided for @invitationAccept.
  ///
  /// In ar, this message translates to:
  /// **'اقبل'**
  String get invitationAccept;

  /// No description provided for @invitationReject.
  ///
  /// In ar, this message translates to:
  /// **'ارفض'**
  String get invitationReject;

  /// No description provided for @invitationRejectReason.
  ///
  /// In ar, this message translates to:
  /// **'سبب الرفض (اختياري)'**
  String get invitationRejectReason;

  /// No description provided for @invitationGone.
  ///
  /// In ar, this message translates to:
  /// **'لم تعد الدعوة صالحة'**
  String get invitationGone;

  /// No description provided for @runArrived.
  ///
  /// In ar, this message translates to:
  /// **'وصلتُ'**
  String get runArrived;

  /// No description provided for @runStart.
  ///
  /// In ar, this message translates to:
  /// **'ابدأ الرحلة'**
  String get runStart;

  /// No description provided for @runComplete.
  ///
  /// In ar, this message translates to:
  /// **'أنهِ الرحلة'**
  String get runComplete;

  /// No description provided for @runTooFarPickup.
  ///
  /// In ar, this message translates to:
  /// **'اقترب أكثر: عليك أن تكون ضمن {meters} متر من نقطة الالتقاء'**
  String runTooFarPickup(int meters);

  /// No description provided for @runTooFarDropoff.
  ///
  /// In ar, this message translates to:
  /// **'عليك أن تكون ضمن {meters} متر من الوجهة'**
  String runTooFarDropoff(int meters);

  /// No description provided for @runRemaining.
  ///
  /// In ar, this message translates to:
  /// **'تبقّى {meters} متر'**
  String runRemaining(int meters);

  /// No description provided for @runToPickup.
  ///
  /// In ar, this message translates to:
  /// **'إلى نقطة الالتقاء'**
  String get runToPickup;

  /// No description provided for @runToDestination.
  ///
  /// In ar, this message translates to:
  /// **'إلى الوجهة'**
  String get runToDestination;

  /// No description provided for @runPassenger.
  ///
  /// In ar, this message translates to:
  /// **'الراكب'**
  String get runPassenger;

  /// No description provided for @collectTitle.
  ///
  /// In ar, this message translates to:
  /// **'تحصيل الأجرة'**
  String get collectTitle;

  /// No description provided for @collectConfirm.
  ///
  /// In ar, this message translates to:
  /// **'استلمتُ المبلغ'**
  String get collectConfirm;

  /// No description provided for @collectDone.
  ///
  /// In ar, this message translates to:
  /// **'سُجّل التحصيل'**
  String get collectDone;

  /// No description provided for @collectNote.
  ///
  /// In ar, this message translates to:
  /// **'أنت وحدك من يؤكّد قبض النقد. لا يستطيع الزبون ذلك.'**
  String get collectNote;

  /// No description provided for @balanceTitle.
  ///
  /// In ar, this message translates to:
  /// **'رصيدي'**
  String get balanceTitle;

  /// No description provided for @balanceTotal.
  ///
  /// In ar, this message translates to:
  /// **'الإجمالي'**
  String get balanceTotal;

  /// No description provided for @publishTitle.
  ///
  /// In ar, this message translates to:
  /// **'انشر رحلة'**
  String get publishTitle;

  /// No description provided for @publishCapacity.
  ///
  /// In ar, this message translates to:
  /// **'المقاعد'**
  String get publishCapacity;

  /// No description provided for @publishPricePerSeat.
  ///
  /// In ar, this message translates to:
  /// **'سعر المقعد'**
  String get publishPricePerSeat;

  /// No description provided for @publishWhen.
  ///
  /// In ar, this message translates to:
  /// **'الموعد'**
  String get publishWhen;

  /// No description provided for @publishSubmit.
  ///
  /// In ar, this message translates to:
  /// **'انشر'**
  String get publishSubmit;

  /// No description provided for @publishDone.
  ///
  /// In ar, this message translates to:
  /// **'نُشرت الرحلة'**
  String get publishDone;

  /// No description provided for @publishTitleField.
  ///
  /// In ar, this message translates to:
  /// **'عنوان الرحلة'**
  String get publishTitleField;

  /// No description provided for @sharedTitle.
  ///
  /// In ar, this message translates to:
  /// **'رحلات مشتركة قريبة'**
  String get sharedTitle;

  /// No description provided for @sharedNone.
  ///
  /// In ar, this message translates to:
  /// **'لا رحلات مشتركة متاحة الآن'**
  String get sharedNone;

  /// No description provided for @sharedJoin.
  ///
  /// In ar, this message translates to:
  /// **'انضمّ'**
  String get sharedJoin;

  /// No description provided for @sharedCompatibility.
  ///
  /// In ar, this message translates to:
  /// **'توافق {score}٪'**
  String sharedCompatibility(String score);

  /// No description provided for @sharedSeatsLeft.
  ///
  /// In ar, this message translates to:
  /// **'{count,plural, =1{مقعد واحد متبقٍّ} =2{مقعدان متبقّيان} few{{count} مقاعد متبقّية} other{{count} مقعدًا متبقّيًا}}'**
  String sharedSeatsLeft(int count);

  /// No description provided for @sharedOnboard.
  ///
  /// In ar, this message translates to:
  /// **'على المتن: {male} رجل · {female} امرأة'**
  String sharedOnboard(int male, int female);

  /// No description provided for @sharedJoined.
  ///
  /// In ar, this message translates to:
  /// **'انضممتَ إلى الرحلة'**
  String get sharedJoined;

  /// No description provided for @sharedFull.
  ///
  /// In ar, this message translates to:
  /// **'امتلأت المقاعد. اختر رحلة أخرى.'**
  String get sharedFull;

  /// No description provided for @catalogTitle.
  ///
  /// In ar, this message translates to:
  /// **'سفريات ورحلات منشورة'**
  String get catalogTitle;

  /// No description provided for @catalogEmpty.
  ///
  /// In ar, this message translates to:
  /// **'لا رحلات منشورة الآن'**
  String get catalogEmpty;

  /// No description provided for @catalogBook.
  ///
  /// In ar, this message translates to:
  /// **'احجز مقعدًا'**
  String get catalogBook;

  /// No description provided for @catalogBooked.
  ///
  /// In ar, this message translates to:
  /// **'حُجز مقعدك'**
  String get catalogBooked;

  /// No description provided for @catalogPricePerSeat.
  ///
  /// In ar, this message translates to:
  /// **'للمقعد'**
  String get catalogPricePerSeat;

  /// No description provided for @catalogDeparts.
  ///
  /// In ar, this message translates to:
  /// **'ينطلق {when}'**
  String catalogDeparts(String when);

  /// No description provided for @catalogFilterAll.
  ///
  /// In ar, this message translates to:
  /// **'الكلّ'**
  String get catalogFilterAll;

  /// No description provided for @notificationsTitle.
  ///
  /// In ar, this message translates to:
  /// **'الإشعارات'**
  String get notificationsTitle;

  /// No description provided for @notificationsEmpty.
  ///
  /// In ar, this message translates to:
  /// **'لا إشعارات'**
  String get notificationsEmpty;

  /// No description provided for @channelsTitle.
  ///
  /// In ar, this message translates to:
  /// **'قنوات التنبيه'**
  String get channelsTitle;

  /// No description provided for @channelsHint.
  ///
  /// In ar, this message translates to:
  /// **'أوّل قناة تُسلّم توقف السلسلة، فلا يصلك الخبر ثلاث مرّات.'**
  String get channelsHint;

  /// No description provided for @channelPush.
  ///
  /// In ar, this message translates to:
  /// **'إشعار الدفع'**
  String get channelPush;

  /// No description provided for @channelTelegram.
  ///
  /// In ar, this message translates to:
  /// **'تليغرام'**
  String get channelTelegram;

  /// No description provided for @channelSms.
  ///
  /// In ar, this message translates to:
  /// **'رسالة نصّية'**
  String get channelSms;

  /// No description provided for @channelLink.
  ///
  /// In ar, this message translates to:
  /// **'اربط'**
  String get channelLink;

  /// No description provided for @channelUnlink.
  ///
  /// In ar, this message translates to:
  /// **'افصل'**
  String get channelUnlink;

  /// No description provided for @channelLinked.
  ///
  /// In ar, this message translates to:
  /// **'مربوط'**
  String get channelLinked;

  /// No description provided for @channelNotLinked.
  ///
  /// In ar, this message translates to:
  /// **'غير مربوط'**
  String get channelNotLinked;

  /// No description provided for @channelTelegramOpening.
  ///
  /// In ar, this message translates to:
  /// **'نفتح تليغرام… اضغط «ابدأ» هناك.'**
  String get channelTelegramOpening;

  /// No description provided for @channelTelegramLinked.
  ///
  /// In ar, this message translates to:
  /// **'رُبط تليغرام'**
  String get channelTelegramLinked;

  /// No description provided for @channelPriority.
  ///
  /// In ar, this message translates to:
  /// **'الأولوية'**
  String get channelPriority;

  /// No description provided for @paymentDiscountFirstRide.
  ///
  /// In ar, this message translates to:
  /// **'خصم أوّل مشوار'**
  String get paymentDiscountFirstRide;

  /// No description provided for @paymentDiscountCredit.
  ///
  /// In ar, this message translates to:
  /// **'رصيد الدعوات'**
  String get paymentDiscountCredit;

  /// No description provided for @paymentDiscount.
  ///
  /// In ar, this message translates to:
  /// **'الخصم'**
  String get paymentDiscount;

  /// No description provided for @paymentSubtotal.
  ///
  /// In ar, this message translates to:
  /// **'الأجرة'**
  String get paymentSubtotal;

  /// No description provided for @perksTitle.
  ///
  /// In ar, this message translates to:
  /// **'اشتراك الصباح والدعوات'**
  String get perksTitle;

  /// No description provided for @perksSubscriptionsSection.
  ///
  /// In ar, this message translates to:
  /// **'اشتراك الصباح'**
  String get perksSubscriptionsSection;

  /// No description provided for @perksSubscriptionsEmpty.
  ///
  /// In ar, this message translates to:
  /// **'لا اشتراك بعد. أضف مشوارك اليوميّ ونرسل السيارة كلّ يوم قبل الموعد.'**
  String get perksSubscriptionsEmpty;

  /// No description provided for @perksSubscriptionAdd.
  ///
  /// In ar, this message translates to:
  /// **'اشتراك جديد'**
  String get perksSubscriptionAdd;

  /// No description provided for @perksSubscriptionLabel.
  ///
  /// In ar, this message translates to:
  /// **'اسم الاشتراك (اختياريّ)'**
  String get perksSubscriptionLabel;

  /// No description provided for @perksSubscriptionLabelHint.
  ///
  /// In ar, this message translates to:
  /// **'إلى الجامعة'**
  String get perksSubscriptionLabelHint;

  /// No description provided for @perksSubscriptionTime.
  ///
  /// In ar, this message translates to:
  /// **'موعد الانطلاق'**
  String get perksSubscriptionTime;

  /// No description provided for @perksSubscriptionDays.
  ///
  /// In ar, this message translates to:
  /// **'الأيام'**
  String get perksSubscriptionDays;

  /// No description provided for @perksSubscriptionPickup.
  ///
  /// In ar, this message translates to:
  /// **'نقطة الانطلاق: موقعك الآن'**
  String get perksSubscriptionPickup;

  /// No description provided for @perksSubscriptionDestination.
  ///
  /// In ar, this message translates to:
  /// **'الوجهة'**
  String get perksSubscriptionDestination;

  /// No description provided for @perksSubscriptionPickDestination.
  ///
  /// In ar, this message translates to:
  /// **'اختر الوجهة من الخريطة'**
  String get perksSubscriptionPickDestination;

  /// No description provided for @perksSubscriptionDestinationSet.
  ///
  /// In ar, this message translates to:
  /// **'الوجهة محدّدة'**
  String get perksSubscriptionDestinationSet;

  /// No description provided for @perksSubscriptionNext.
  ///
  /// In ar, this message translates to:
  /// **'الطلب القادم: {when}'**
  String perksSubscriptionNext(String when);

  /// No description provided for @perksSubscriptionPaused.
  ///
  /// In ar, this message translates to:
  /// **'متوقّف'**
  String get perksSubscriptionPaused;

  /// No description provided for @perksSubscriptionCancel.
  ///
  /// In ar, this message translates to:
  /// **'إلغاء الاشتراك'**
  String get perksSubscriptionCancel;

  /// No description provided for @perksSubscriptionCancelConfirm.
  ///
  /// In ar, this message translates to:
  /// **'نلغي هذا الاشتراك؟ لن نُنشئ طلبًا له بعد الآن.'**
  String get perksSubscriptionCancelConfirm;

  /// No description provided for @perksSubscriptionCreated.
  ///
  /// In ar, this message translates to:
  /// **'أُنشئ الاشتراك. سنطلب لك سيارة قبل الموعد بنصف ساعة.'**
  String get perksSubscriptionCreated;

  /// No description provided for @perksSubscriptionNeedDestination.
  ///
  /// In ar, this message translates to:
  /// **'حدّد الوجهة أوّلًا.'**
  String get perksSubscriptionNeedDestination;

  /// No description provided for @perksReferralSection.
  ///
  /// In ar, this message translates to:
  /// **'زبون يجلب زبونًا'**
  String get perksReferralSection;

  /// No description provided for @perksReferralMyCode.
  ///
  /// In ar, this message translates to:
  /// **'رمز دعوتي'**
  String get perksReferralMyCode;

  /// No description provided for @perksReferralExplain.
  ///
  /// In ar, this message translates to:
  /// **'شارك رمزك مع صديق. بعد أوّل مشوار له يحصل كلاكما على رصيد يُخصم من الرحلة التالية.'**
  String get perksReferralExplain;

  /// No description provided for @perksReferralShare.
  ///
  /// In ar, this message translates to:
  /// **'مشاركة الرمز'**
  String get perksReferralShare;

  /// No description provided for @perksReferralShareText.
  ///
  /// In ar, this message translates to:
  /// **'جرّب سووم تكسي — أدخل رمز دعوتي {code} قبل أوّل مشوار لك ونحصل معًا على رصيد.'**
  String perksReferralShareText(String code);

  /// No description provided for @perksReferralCopied.
  ///
  /// In ar, this message translates to:
  /// **'نُسخ الرمز'**
  String get perksReferralCopied;

  /// No description provided for @perksReferralEnter.
  ///
  /// In ar, this message translates to:
  /// **'أدخل رمز صديق'**
  String get perksReferralEnter;

  /// No description provided for @perksReferralEnterHint.
  ///
  /// In ar, this message translates to:
  /// **'مثل ABC123'**
  String get perksReferralEnterHint;

  /// No description provided for @perksReferralApply.
  ///
  /// In ar, this message translates to:
  /// **'تفعيل'**
  String get perksReferralApply;

  /// No description provided for @perksReferralApplied.
  ///
  /// In ar, this message translates to:
  /// **'فُعّل رمز {code}. الرصيد يصلكما بعد أوّل مشوار.'**
  String perksReferralApplied(String code);

  /// No description provided for @perksReferralLinked.
  ///
  /// In ar, this message translates to:
  /// **'دعاك: {code}'**
  String perksReferralLinked(String code);

  /// No description provided for @perksCreditBalance.
  ///
  /// In ar, this message translates to:
  /// **'رصيدك'**
  String get perksCreditBalance;

  /// No description provided for @perksFirstRideAvailable.
  ///
  /// In ar, this message translates to:
  /// **'أوّل مشوار لك بنصف السعر — الخصم يُطبَّق تلقائيًّا عند الدفع.'**
  String get perksFirstRideAvailable;

  /// No description provided for @perksFirstRideUsed.
  ///
  /// In ar, this message translates to:
  /// **'استُخدم خصم أوّل مشوار.'**
  String get perksFirstRideUsed;

  /// No description provided for @dayMon.
  ///
  /// In ar, this message translates to:
  /// **'الاثنين'**
  String get dayMon;

  /// No description provided for @dayTue.
  ///
  /// In ar, this message translates to:
  /// **'الثلاثاء'**
  String get dayTue;

  /// No description provided for @dayWed.
  ///
  /// In ar, this message translates to:
  /// **'الأربعاء'**
  String get dayWed;

  /// No description provided for @dayThu.
  ///
  /// In ar, this message translates to:
  /// **'الخميس'**
  String get dayThu;

  /// No description provided for @dayFri.
  ///
  /// In ar, this message translates to:
  /// **'الجمعة'**
  String get dayFri;

  /// No description provided for @daySat.
  ///
  /// In ar, this message translates to:
  /// **'السبت'**
  String get daySat;

  /// No description provided for @daySun.
  ///
  /// In ar, this message translates to:
  /// **'الأحد'**
  String get daySun;

  /// No description provided for @listSeparator.
  ///
  /// In ar, this message translates to:
  /// **'، '**
  String get listSeparator;

  /// No description provided for @perksNextFormat.
  ///
  /// In ar, this message translates to:
  /// **'EEEE d MMM، HH:mm'**
  String get perksNextFormat;

  /// No description provided for @balanceOwedToYou.
  ///
  /// In ar, this message translates to:
  /// **'تدين لك سووم بهذا المبلغ — خصومات زبائنك وتعويضات المشاوير الفاضية'**
  String get balanceOwedToYou;

  /// No description provided for @balanceYouOwe.
  ///
  /// In ar, this message translates to:
  /// **'عليك للمنصّة'**
  String get balanceYouOwe;

  /// No description provided for @balanceLifetimeEarned.
  ///
  /// In ar, this message translates to:
  /// **'مجموع ما كسبته'**
  String get balanceLifetimeEarned;

  /// No description provided for @balanceLifetimeCommission.
  ///
  /// In ar, this message translates to:
  /// **'مجموع العمولة'**
  String get balanceLifetimeCommission;

  /// No description provided for @balanceZero.
  ///
  /// In ar, this message translates to:
  /// **'لا شيء معلّق بينك وبين المنصّة'**
  String get balanceZero;

  /// No description provided for @collectDiscountNote.
  ///
  /// In ar, this message translates to:
  /// **'الزبون يدفع {customer} بعد خصم سووم، والباقي {rest} يُضاف إلى رصيدك عند المنصّة. أجرتك كاملة {net}.'**
  String collectDiscountNote(String customer, String rest, String net);

  /// No description provided for @scheduleNow.
  ///
  /// In ar, this message translates to:
  /// **'الآن'**
  String get scheduleNow;

  /// No description provided for @scheduleLater.
  ///
  /// In ar, this message translates to:
  /// **'في موعد'**
  String get scheduleLater;

  /// No description provided for @scheduleFormat.
  ///
  /// In ar, this message translates to:
  /// **'EEEE d MMM، HH:mm'**
  String get scheduleFormat;

  /// No description provided for @scheduleTooSoon.
  ///
  /// In ar, this message translates to:
  /// **'اختر موعدًا بعد عشر دقائق على الأقلّ — وإلّا اطلب الآن.'**
  String get scheduleTooSoon;

  /// No description provided for @requestScheduledRide.
  ///
  /// In ar, this message translates to:
  /// **'احجز الموعد'**
  String get requestScheduledRide;

  /// No description provided for @upcomingTitle.
  ///
  /// In ar, this message translates to:
  /// **'موعدك: {when}'**
  String upcomingTitle(String when);

  /// No description provided for @upcomingWaiting.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار عروض السائقين — نخبرك حين يصل عرض.'**
  String get upcomingWaiting;

  /// No description provided for @upcomingConfirmed.
  ///
  /// In ar, this message translates to:
  /// **'سائقك مؤكَّد. سنذكّرك قبل الموعد.'**
  String get upcomingConfirmed;

  /// No description provided for @historyStatusCancelled.
  ///
  /// In ar, this message translates to:
  /// **'أُلغيت'**
  String get historyStatusCancelled;

  /// No description provided for @historyStatusDisputed.
  ///
  /// In ar, this message translates to:
  /// **'قيد المراجعة'**
  String get historyStatusDisputed;

  /// No description provided for @historyStatusUpcoming.
  ///
  /// In ar, this message translates to:
  /// **'قادمة'**
  String get historyStatusUpcoming;

  /// No description provided for @driverBookingTitle.
  ///
  /// In ar, this message translates to:
  /// **'حجز: {when}'**
  String driverBookingTitle(String when);

  /// No description provided for @driverBookingOpen.
  ///
  /// In ar, this message translates to:
  /// **'توجّه'**
  String get driverBookingOpen;

  /// No description provided for @dispatchOffers.
  ///
  /// In ar, this message translates to:
  /// **'سوم'**
  String get dispatchOffers;

  /// No description provided for @dispatchOffersHint.
  ///
  /// In ar, this message translates to:
  /// **'عروض من السائقين وأنت تختار'**
  String get dispatchOffersHint;

  /// No description provided for @dispatchNearest.
  ///
  /// In ar, this message translates to:
  /// **'الأقرب'**
  String get dispatchNearest;

  /// No description provided for @dispatchNearestHint.
  ///
  /// In ar, this message translates to:
  /// **'أقرب سائق يُرسَل إليك تلقائيًّا'**
  String get dispatchNearestHint;

  /// No description provided for @dispatchPick.
  ///
  /// In ar, this message translates to:
  /// **'اختر سيارتك'**
  String get dispatchPick;

  /// No description provided for @dispatchPickHint.
  ///
  /// In ar, this message translates to:
  /// **'المس السيارة التي تريدها على الخريطة'**
  String get dispatchPickHint;

  /// No description provided for @pickTapCar.
  ///
  /// In ar, this message translates to:
  /// **'المس سيارة على الخريطة لتختارها'**
  String get pickTapCar;

  /// No description provided for @pickSelected.
  ///
  /// In ar, this message translates to:
  /// **'{name} · {vehicle}'**
  String pickSelected(String name, String vehicle);

  /// No description provided for @searchRadiusLabel.
  ///
  /// In ar, this message translates to:
  /// **'نطاق البحث'**
  String get searchRadiusLabel;

  /// No description provided for @radiusKm.
  ///
  /// In ar, this message translates to:
  /// **'{km} كم'**
  String radiusKm(String km);

  /// No description provided for @radiusMeters.
  ///
  /// In ar, this message translates to:
  /// **'{meters} م'**
  String radiusMeters(String meters);

  /// No description provided for @nearestTitle.
  ///
  /// In ar, this message translates to:
  /// **'نبحث عن أقرب سائق'**
  String get nearestTitle;

  /// No description provided for @nearestLooking.
  ///
  /// In ar, this message translates to:
  /// **'نسأل أقرب السائقين بالترتيب…'**
  String get nearestLooking;

  /// No description provided for @nearestAsking.
  ///
  /// In ar, this message translates to:
  /// **'ننتظر ردّ أقرب سائق — ثوانٍ قليلة'**
  String get nearestAsking;

  /// No description provided for @nearestExhausted.
  ///
  /// In ar, this message translates to:
  /// **'لم يقبل أحدٌ بعد — العروض مفتوحة الآن'**
  String get nearestExhausted;

  /// No description provided for @requestNearest.
  ///
  /// In ar, this message translates to:
  /// **'أرسل أقرب سائق'**
  String get requestNearest;

  /// No description provided for @requestPicked.
  ///
  /// In ar, this message translates to:
  /// **'اطلب هذه السيارة'**
  String get requestPicked;

  /// No description provided for @moreOptions.
  ///
  /// In ar, this message translates to:
  /// **'خيارات أكثر'**
  String get moreOptions;

  /// No description provided for @serviceClass.
  ///
  /// In ar, this message translates to:
  /// **'الدرجة'**
  String get serviceClass;

  /// No description provided for @carPassengers.
  ///
  /// In ar, this message translates to:
  /// **'{count} ركّاب'**
  String carPassengers(int count);

  /// No description provided for @carNew.
  ///
  /// In ar, this message translates to:
  /// **'جديد'**
  String get carNew;

  /// No description provided for @runCancel.
  ///
  /// In ar, this message translates to:
  /// **'ألغِ الرحلة'**
  String get runCancel;

  /// No description provided for @runCancelTitle.
  ///
  /// In ar, this message translates to:
  /// **'لماذا تلغي؟'**
  String get runCancelTitle;

  /// No description provided for @runCancelWarning.
  ///
  /// In ar, this message translates to:
  /// **'الطلب يعود للبحث عند الزبون. الإلغاء المتكرّر يوقف العروض عنك مؤقّتًا.'**
  String get runCancelWarning;

  /// No description provided for @cancelReasonCar.
  ///
  /// In ar, this message translates to:
  /// **'عطل بالسيارة'**
  String get cancelReasonCar;

  /// No description provided for @cancelReasonNoAnswer.
  ///
  /// In ar, this message translates to:
  /// **'الزبون لا يردّ'**
  String get cancelReasonNoAnswer;

  /// No description provided for @cancelReasonFar.
  ///
  /// In ar, this message translates to:
  /// **'المكان بعيد أو الطريق مغلق'**
  String get cancelReasonFar;

  /// No description provided for @cancelReasonOther.
  ///
  /// In ar, this message translates to:
  /// **'سبب آخر'**
  String get cancelReasonOther;

  /// No description provided for @passengerChip.
  ///
  /// In ar, this message translates to:
  /// **'{name} · {count} ركّاب'**
  String passengerChip(String name, int count);

  /// No description provided for @lateCancelBadge.
  ///
  /// In ar, this message translates to:
  /// **'{count, plural, =1{ألغى مرّة مؤخرًا} =2{ألغى مرّتين مؤخرًا} few{ألغى {count} مرّات مؤخرًا} other{ألغى {count} مرّة مؤخرًا}}'**
  String lateCancelBadge(int count);

  /// No description provided for @cancelFreeNow.
  ///
  /// In ar, this message translates to:
  /// **'الإلغاء الآن مجّاني.'**
  String get cancelFreeNow;

  /// No description provided for @cancelDriverLateFree.
  ///
  /// In ar, this message translates to:
  /// **'السائق تأخّر عن موعده — الإلغاء مجّاني.'**
  String get cancelDriverLateFree;

  /// No description provided for @cancelCountsStrike.
  ///
  /// In ar, this message translates to:
  /// **'سيُحسب هذا الإلغاء مخالفة. عند {limit} مخالفات خلال أسبوع يتوقّف «الأقرب» و«اختر سيارتك» عنك يومًا.'**
  String cancelCountsStrike(int limit);

  /// No description provided for @driverCancelledRequeued.
  ///
  /// In ar, this message translates to:
  /// **'السائق اعتذر — نبحث لك عن سائق آخر الآن.'**
  String get driverCancelledRequeued;

  /// No description provided for @shareRide.
  ///
  /// In ar, this message translates to:
  /// **'شارك الرحلة'**
  String get shareRide;

  /// No description provided for @shareRideHint.
  ///
  /// In ar, this message translates to:
  /// **'أرخص: تتقاسم السيارة مع ركّاب بطريقك'**
  String get shareRideHint;

  /// No description provided for @callDriver.
  ///
  /// In ar, this message translates to:
  /// **'اتّصل بالسائق'**
  String get callDriver;

  /// No description provided for @callCustomer.
  ///
  /// In ar, this message translates to:
  /// **'اتّصل بالزبون'**
  String get callCustomer;

  /// No description provided for @serviceSoon.
  ///
  /// In ar, this message translates to:
  /// **'قريبًا'**
  String get serviceSoon;

  /// No description provided for @serviceComingSoon.
  ///
  /// In ar, this message translates to:
  /// **'«{name}» قريبًا في سووم — ترقّبها.'**
  String serviceComingSoon(String name);

  /// No description provided for @incentivesTitle.
  ///
  /// In ar, this message translates to:
  /// **'الحوافز'**
  String get incentivesTitle;

  /// No description provided for @incentiveRemaining.
  ///
  /// In ar, this message translates to:
  /// **'بقي {count} مشوارًا لتحصل على {reward}'**
  String incentiveRemaining(int count, String reward);

  /// No description provided for @incentiveEarned.
  ///
  /// In ar, this message translates to:
  /// **'استحققت {reward} — تُسلَّم من مكتب سووم'**
  String incentiveEarned(String reward);

  /// No description provided for @incentiveDelivered.
  ///
  /// In ar, this message translates to:
  /// **'سُلّمت المكافأة — شكرًا لك'**
  String get incentiveDelivered;

  /// No description provided for @tripCancelWhy.
  ///
  /// In ar, this message translates to:
  /// **'لماذا تلغي الرحلة؟'**
  String get tripCancelWhy;

  /// No description provided for @riderCancelChangedMind.
  ///
  /// In ar, this message translates to:
  /// **'غيّرت رأيي'**
  String get riderCancelChangedMind;

  /// No description provided for @riderCancelDriverLate.
  ///
  /// In ar, this message translates to:
  /// **'السائق تأخّر'**
  String get riderCancelDriverLate;

  /// No description provided for @riderCancelDriverNotMoving.
  ///
  /// In ar, this message translates to:
  /// **'السائق لا يتحرّك نحوي'**
  String get riderCancelDriverNotMoving;

  /// No description provided for @riderCancelDriverAsked.
  ///
  /// In ar, this message translates to:
  /// **'السائق طلب منّي أن ألغي'**
  String get riderCancelDriverAsked;

  /// No description provided for @riderCancelFoundOther.
  ///
  /// In ar, this message translates to:
  /// **'وجدت وسيلة أخرى'**
  String get riderCancelFoundOther;

  /// No description provided for @riderCancelWrongPickup.
  ///
  /// In ar, this message translates to:
  /// **'مكان الالتقاط خاطئ'**
  String get riderCancelWrongPickup;

  /// No description provided for @riderCancelOther.
  ///
  /// In ar, this message translates to:
  /// **'سبب آخر'**
  String get riderCancelOther;

  /// No description provided for @driverMockLocation.
  ///
  /// In ar, this message translates to:
  /// **'هاتفك يرسل موقعًا مزيّفًا (Mock location)، فلا نستطيع إرسالك إلى الزبائن. أطفئ تطبيق تزييف الموقع من «خيارات المطوّر» ثمّ شغّل العمل من جديد.'**
  String get driverMockLocation;

  /// No description provided for @runNoShow.
  ///
  /// In ar, this message translates to:
  /// **'الزبون لم يحضر'**
  String get runNoShow;

  /// No description provided for @runNoShowWait.
  ///
  /// In ar, this message translates to:
  /// **'«الزبون لم يحضر» يُتاح بعد {time}'**
  String runNoShowWait(String time);

  /// No description provided for @runNoShowConfirmTitle.
  ///
  /// In ar, this message translates to:
  /// **'نسجّل أنّ الزبون لم يحضر؟'**
  String get runNoShowConfirmTitle;

  /// No description provided for @runNoShowConfirmBody.
  ///
  /// In ar, this message translates to:
  /// **'لا يُحسب هذا الإلغاء عليك، ويُغلق الطلب. وإن استحققت تعويضًا عن المشوار يُضاف إلى رصيدك فورًا.'**
  String get runNoShowConfirmBody;

  /// No description provided for @runNoShowDone.
  ///
  /// In ar, this message translates to:
  /// **'سُجّل عدم حضور الزبون — لا يُحسب عليك.'**
  String get runNoShowDone;

  /// No description provided for @runNoShowCompensated.
  ///
  /// In ar, this message translates to:
  /// **'سُجّل عدم حضور الزبون، وأُضيف {amount} تعويضًا إلى رصيدك.'**
  String runNoShowCompensated(String amount);

  /// No description provided for @rideEndedNoShow.
  ///
  /// In ar, this message translates to:
  /// **'السائق وصل وانتظرك ولم تحضر، فأُغلق الطلب.'**
  String get rideEndedNoShow;

  /// No description provided for @proposalTitle.
  ///
  /// In ar, this message translates to:
  /// **'سعرك'**
  String get proposalTitle;

  /// No description provided for @proposalYours.
  ///
  /// In ar, this message translates to:
  /// **'سعرك المعروض على السائقين: {amount}'**
  String proposalYours(String amount);

  /// No description provided for @proposalHint.
  ///
  /// In ar, this message translates to:
  /// **'تسعيرة المنصّة {amount} — السائقون يقبلون سعرك أو يعرضون أعلى منه.'**
  String proposalHint(String amount);

  /// No description provided for @proposalSend.
  ///
  /// In ar, this message translates to:
  /// **'اعرض سعري'**
  String get proposalSend;

  /// No description provided for @proposalRaise.
  ///
  /// In ar, this message translates to:
  /// **'ارفع سعري'**
  String get proposalRaise;

  /// No description provided for @proposalSent.
  ///
  /// In ar, this message translates to:
  /// **'عُرض سعرك على السائقين القريبين.'**
  String get proposalSent;

  /// No description provided for @proposalLower.
  ///
  /// In ar, this message translates to:
  /// **'أنقص'**
  String get proposalLower;

  /// No description provided for @proposalHigher.
  ///
  /// In ar, this message translates to:
  /// **'زِد'**
  String get proposalHigher;

  /// No description provided for @workCustomerPrice.
  ///
  /// In ar, this message translates to:
  /// **'سعر الزبون: {amount}'**
  String workCustomerPrice(String amount);

  /// No description provided for @workAcceptCustomerPrice.
  ///
  /// In ar, this message translates to:
  /// **'اقبل بسعر الزبون'**
  String get workAcceptCustomerPrice;

  /// No description provided for @workCounterUpTo.
  ///
  /// In ar, this message translates to:
  /// **'أو اعرض أعلى — حتّى {amount}'**
  String workCounterUpTo(String amount);

  /// No description provided for @workCustomerPriceLabel.
  ///
  /// In ar, this message translates to:
  /// **'سعر الزبون'**
  String get workCustomerPriceLabel;

  /// No description provided for @unitMeters.
  ///
  /// In ar, this message translates to:
  /// **'{value} م'**
  String unitMeters(String value);

  /// No description provided for @workPickupAway.
  ///
  /// In ar, this message translates to:
  /// **'الالتقاط على بعد {distance} منك'**
  String workPickupAway(String distance);

  /// No description provided for @runCustomerCancelled.
  ///
  /// In ar, this message translates to:
  /// **'ألغى الزبون الرحلة.'**
  String get runCustomerCancelled;

  /// No description provided for @runCustomerCancelledCompensated.
  ///
  /// In ar, this message translates to:
  /// **'ألغى الزبون الرحلة بعد انتظارك — أُضيف {amount} تعويضًا إلى رصيدك.'**
  String runCustomerCancelledCompensated(String amount);
}

class _SoumStringsDelegate extends LocalizationsDelegate<SoumStrings> {
  const _SoumStringsDelegate();

  @override
  Future<SoumStrings> load(Locale locale) {
    return SynchronousFuture<SoumStrings>(lookupSoumStrings(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_SoumStringsDelegate old) => false;
}

SoumStrings lookupSoumStrings(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return SoumStringsAr();
    case 'en':
      return SoumStringsEn();
  }

  throw FlutterError(
    'SoumStrings.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
