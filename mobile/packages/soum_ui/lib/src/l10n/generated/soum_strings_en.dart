// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'soum_strings.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class SoumStringsEn extends SoumStrings {
  SoumStringsEn([String locale = 'en']) : super(locale);

  @override
  String get appNameCustomer => 'Soom Taksi';

  @override
  String get appNameDriver => 'Soom Taksi — Driver';

  @override
  String get actionRetry => 'Try again';

  @override
  String get actionCancel => 'Cancel';

  @override
  String get actionConfirm => 'Confirm';

  @override
  String get actionContinue => 'Continue';

  @override
  String get actionClose => 'Close';

  @override
  String get actionBack => 'Back';

  @override
  String get actionEdit => 'Edit';

  @override
  String get bootLoadingConfig => 'Reading your city settings…';

  @override
  String get bootLoadingSession => 'Restoring your session…';

  @override
  String get bootRestoringRide => 'Taking you back to your ride…';

  @override
  String get bootNoConnection => 'No internet connection';

  @override
  String get bootNoConnectionBody =>
      'We need a connection once to read your city settings. Check your network and try again.';

  @override
  String get bootOutsideServiceArea => 'Outside our service areas';

  @override
  String get bootOutsideServiceAreaBody =>
      'We don\'t serve your location yet. You can browse, but you won\'t find nearby cars.';

  @override
  String get authPhoneTitle => 'Enter your phone number';

  @override
  String get authPhoneSubtitle => 'We\'ll send you a short verification code.';

  @override
  String get authPhoneLabel => 'Phone number';

  @override
  String get authPhoneHint => '9XXXXXXXX';

  @override
  String get authPhoneInvalid => 'Enter a valid Syrian number';

  @override
  String get authSendCode => 'Send code';

  @override
  String get authCodeTitle => 'Enter the code';

  @override
  String authCodeSubtitle(String phone) {
    return 'We sent a code to $phone';
  }

  @override
  String get authCodeLabel => 'Verification code';

  @override
  String get authCodeInvalid => 'The code is incomplete';

  @override
  String get authVerify => 'Verify';

  @override
  String authResendIn(int seconds) {
    return 'Resend in ${seconds}s';
  }

  @override
  String get authResend => 'Resend code';

  @override
  String get authChangePhone => 'Change number';

  @override
  String authDevelopmentCode(String code) {
    return 'Development code: $code';
  }

  @override
  String authCodeExpiresIn(int seconds) {
    return 'Code expires in ${seconds}s';
  }

  @override
  String authThrottled(int seconds) {
    return 'Too many attempts. Try again in ${seconds}s.';
  }

  @override
  String get errorNetwork => 'No internet connection';

  @override
  String get errorNetworkBody => 'Check your network and try again.';

  @override
  String get errorGeneric => 'Couldn\'t complete that';

  @override
  String errorSupportReference(String requestId) {
    return 'Reference: $requestId';
  }

  @override
  String get sessionExpiredTitle => 'Your session ended';

  @override
  String get sessionExpiredBody => 'Sign in again to continue.';

  @override
  String get logout => 'Sign out';

  @override
  String get logoutConfirm => 'Sign out of your account?';

  @override
  String get currencySyp => 'SYP';

  @override
  String get fareApproximate => 'Estimated price';

  @override
  String get fareRouted => 'Routed price';

  @override
  String get fareBreakdownTitle => 'Fare breakdown';

  @override
  String get fareBase => 'Base fare';

  @override
  String get fareDistance => 'Distance';

  @override
  String get fareTime => 'Time';

  @override
  String get fareGross => 'Total';

  @override
  String get farePlatformFee => 'Platform fee';

  @override
  String get fareCustomerTotal => 'You pay';

  @override
  String get fareDriverNet => 'Driver receives';

  @override
  String get fareApproximateNote =>
      'We couldn\'t compute the real route, so this is an estimate and may differ slightly.';

  @override
  String get homeWhereTo => 'Where to?';

  @override
  String get homePickup => 'Pickup';

  @override
  String get homeDestination => 'Destination';

  @override
  String get homeSetOnMap => 'Set on map';

  @override
  String get homeMyLocation => 'My location';

  @override
  String homeCarsNearby(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count cars nearby',
      one: '1 car nearby',
      zero: 'No cars nearby',
    );
    return '$_temp0';
  }

  @override
  String homeNoCarsInRange(String km) {
    return 'No cars within $km km';
  }

  @override
  String get homeOutsideArea => 'You\'re outside our service areas';

  @override
  String get homeLocating => 'Finding you…';

  @override
  String get modeFast => 'Fast';

  @override
  String get modeFastHint => 'Nearest driver, with live map and direct invite';

  @override
  String get modeExpress => 'Express';

  @override
  String get modeExpressHint => 'Fastest, with direct invite';

  @override
  String get modeStandard => 'Standard';

  @override
  String get modeStandardHint => 'The usual balance of price and time';

  @override
  String get modeSaving => 'Saving';

  @override
  String get modeSavingHint => 'Cheapest — wider range, longer wait';

  @override
  String get modeShared => 'Shared';

  @override
  String get modeSharedHint => 'Join an existing ride and split the fare';

  @override
  String get categoryCity => 'Within the city';

  @override
  String get categoryIntercity => 'Between cities';

  @override
  String get categoryServiceLine => 'Service line';

  @override
  String get categoryRecreational => 'Leisure trip';

  @override
  String get cityOrigin => 'Origin city';

  @override
  String get cityDestination => 'Destination city';

  @override
  String get cityRequired => 'Required for this type';

  @override
  String passengers(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count passengers',
      one: '1 passenger',
    );
    return '$_temp0';
  }

  @override
  String get vehicleAny => 'Any car';

  @override
  String get requestRide => 'Request ride';

  @override
  String get scheduleFor => 'Schedule for later';

  @override
  String get searchingTitle => 'Finding you a driver';

  @override
  String searchingSubtitle(String km) {
    return 'Within $km km of your pickup';
  }

  @override
  String searchingTimeLeft(int seconds) {
    return '${seconds}s';
  }

  @override
  String offersTitle(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count offers',
      one: '1 offer',
    );
    return '$_temp0';
  }

  @override
  String get offersEmpty => 'No offers yet';

  @override
  String offerEta(int minutes) {
    return '$minutes min';
  }

  @override
  String get offerChoose => 'Choose';

  @override
  String get offerTaken => 'That car is no longer available. Pick another.';

  @override
  String get rideExpired => 'No driver found';

  @override
  String get rideExpiredBody =>
      'The search window closed with no offers. Try a wider mode or search again.';

  @override
  String get rideCancelled => 'Request cancelled';

  @override
  String get cancelRide => 'Cancel request';

  @override
  String get inviteTitle => 'Invite a specific car';

  @override
  String get inviteSend => 'Invite';

  @override
  String get inviteWaiting => 'Waiting for the driver';

  @override
  String get inviteTtl => 'Response window';

  @override
  String get inviteRejected => 'The driver declined. Pick another car.';

  @override
  String get inviteExpired => 'The window closed with no reply';

  @override
  String get inviteCancel => 'Cancel invite';

  @override
  String inviteSeatsAvailable(int count) {
    return '$count seats free';
  }

  @override
  String inviteDistance(int meters) {
    return 'about $meters m away';
  }

  @override
  String get tripDriverAssigned => 'Your ride is confirmed';

  @override
  String get tripDriverArriving => 'Your driver is on the way';

  @override
  String get tripDriverArrived => 'Your driver is waiting';

  @override
  String get tripInProgress => 'On the way to your destination';

  @override
  String get tripCompleted => 'You\'ve arrived';

  @override
  String get tripCancelledBy => 'Ride cancelled';

  @override
  String get tripCallDriver => 'Call driver';

  @override
  String get tripCancelTrip => 'Cancel ride';

  @override
  String get tripPlate => 'Plate';

  @override
  String get paymentTitle => 'Payment';

  @override
  String get paymentCashWaiting =>
      'Waiting for the driver to confirm they were paid';

  @override
  String get paymentCashNote =>
      'Pay the driver in cash. They confirm it in their app.';

  @override
  String get paymentPaid => 'Paid';

  @override
  String get paymentAmount => 'Amount';

  @override
  String get rateTitle => 'How was your ride?';

  @override
  String get rateSubmit => 'Submit rating';

  @override
  String get rateReasonRequired => 'Pick a reason or write a comment';

  @override
  String get rateComment => 'Comment (optional)';

  @override
  String get rateThanks => 'Thanks for rating';

  @override
  String get rateAlready => 'You already rated this ride';

  @override
  String get complaintOpen => 'File a complaint';

  @override
  String get complaintDescription => 'Tell us what happened';

  @override
  String get complaintSubmit => 'Submit complaint';

  @override
  String get historyTitle => 'My rides';

  @override
  String get historyEmpty => 'No rides yet';

  @override
  String get historyViewPath => 'View route';

  @override
  String get skip => 'Skip';

  @override
  String get done => 'Done';

  @override
  String unitKm(String value) {
    return '$value km';
  }

  @override
  String unitMinutes(int value) {
    return '$value min';
  }

  @override
  String routeSummary(String km, String minutes) {
    return '$km · $minutes';
  }

  @override
  String get complaintCategory => 'Complaint type';

  @override
  String get complaintCatFare => 'Fare';

  @override
  String get complaintCatDriver => 'Driver conduct';

  @override
  String get complaintCatSafety => 'Safety';

  @override
  String get complaintCatLostItem => 'Lost item';

  @override
  String get complaintCatOther => 'Other';

  @override
  String get complaintSent => 'We got your complaint and we\'ll follow up.';

  @override
  String get complaintWindow =>
      'You can file a complaint within 30 days of the ride.';

  @override
  String get driverGoOnline => 'Go online';

  @override
  String get driverGoOffline => 'Go offline';

  @override
  String get driverConnecting => 'Connecting…';

  @override
  String get driverOffline => 'Offline';

  @override
  String get driverOnlineNoHeartbeat =>
      'Online — waiting for first location ping';

  @override
  String get driverOnlineNoHeartbeatHint =>
      'You won\'t get requests until the server has your location.';

  @override
  String get driverMatchable => 'You\'re working';

  @override
  String get driverMatchableHint =>
      'Riders can see you and requests will come in.';

  @override
  String get driverStale => 'Location ping lost';

  @override
  String get driverStaleHint =>
      'You dropped out of the visible fleet. Reconnecting…';

  @override
  String get driverLocationNeeded => 'We need location access for you to work';

  @override
  String get driverNotEligible => 'You can\'t work yet';

  @override
  String get onboardTitle => 'Before you start';

  @override
  String get onboardBecomeDriver => 'Switch your account to driver';

  @override
  String get onboardAddVehicle => 'Register your vehicle';

  @override
  String get onboardDocuments => 'Upload the four documents';

  @override
  String get onboardPendingReview => 'Waiting for admin review';

  @override
  String get onboardStepDone => 'Done';

  @override
  String get vehicleTitle => 'My vehicle';

  @override
  String get vehicleAdd => 'Register a vehicle';

  @override
  String get vehicleType => 'Category';

  @override
  String get vehicleMake => 'Make';

  @override
  String get vehicleModel => 'Model';

  @override
  String get vehicleYear => 'Year';

  @override
  String get vehicleColor => 'Color';

  @override
  String get vehiclePlate => 'Plate number';

  @override
  String get vehicleSeats => 'Seats';

  @override
  String get vehicleActive => 'Active';

  @override
  String get vehicleActivate => 'Activate';

  @override
  String get vehicleDeactivate => 'Deactivate';

  @override
  String get vehicleSaved => 'Vehicle saved';

  @override
  String get docsTitle => 'My documents';

  @override
  String get docNationalId => 'National ID';

  @override
  String get docDriverLicense => 'Driver\'s licence';

  @override
  String get docVehicleRegistration => 'Vehicle registration';

  @override
  String get docInsurance => 'Insurance';

  @override
  String get docUpload => 'Upload';

  @override
  String get docReplace => 'Replace';

  @override
  String get docPending => 'Under review';

  @override
  String get docApproved => 'Approved';

  @override
  String get docRejected => 'Rejected';

  @override
  String get docExpired => 'Expired';

  @override
  String docExpiresOn(String date) {
    return 'Expires $date';
  }

  @override
  String get docUploading => 'Uploading…';

  @override
  String get workCandidates => 'Available requests';

  @override
  String get workNoCandidates => 'No requests right now';

  @override
  String get workNoCandidatesHint =>
      'Nearby requests will appear here as they come in.';

  @override
  String get workOfferTitle => 'Make an offer';

  @override
  String get workOfferPrice => 'Price';

  @override
  String get workOfferEta => 'Arrival time in minutes';

  @override
  String get workOfferSend => 'Send offer';

  @override
  String get workOfferSent => 'Offer sent';

  @override
  String workFareRange(String min, String max) {
    return 'Between $min and $max';
  }

  @override
  String get workFareOutOfRange => 'Price is outside the allowed range';

  @override
  String workDistanceToPickup(String km) {
    return '$km to pickup';
  }

  @override
  String get invitationIncoming => 'Incoming invite';

  @override
  String get invitationAccept => 'Accept';

  @override
  String get invitationReject => 'Decline';

  @override
  String get invitationRejectReason => 'Reason (optional)';

  @override
  String get invitationGone => 'That invite is no longer valid';

  @override
  String get runArrived => 'I\'ve arrived';

  @override
  String get runStart => 'Start ride';

  @override
  String get runComplete => 'End ride';

  @override
  String runTooFarPickup(int meters) {
    return 'Get closer: you must be within $meters m of the pickup point';
  }

  @override
  String runTooFarDropoff(int meters) {
    return 'You must be within $meters m of the destination';
  }

  @override
  String runRemaining(int meters) {
    return '$meters m to go';
  }

  @override
  String get runToPickup => 'To pickup';

  @override
  String get runToDestination => 'To destination';

  @override
  String get runPassenger => 'Passenger';

  @override
  String get collectTitle => 'Collect fare';

  @override
  String get collectConfirm => 'I received the money';

  @override
  String get collectDone => 'Collection recorded';

  @override
  String get collectNote =>
      'Only you can confirm cash was received. The rider can\'t.';

  @override
  String get balanceTitle => 'My balance';

  @override
  String get balanceTotal => 'Total';

  @override
  String get publishTitle => 'Publish a trip';

  @override
  String get publishCapacity => 'Seats';

  @override
  String get publishPricePerSeat => 'Price per seat';

  @override
  String get publishWhen => 'When';

  @override
  String get publishSubmit => 'Publish';

  @override
  String get publishDone => 'Trip published';

  @override
  String get publishTitleField => 'Trip title';

  @override
  String get sharedTitle => 'Shared rides nearby';

  @override
  String get sharedNone => 'No shared rides available right now';

  @override
  String get sharedJoin => 'Join';

  @override
  String sharedCompatibility(String score) {
    return '$score% match';
  }

  @override
  String sharedSeatsLeft(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count seats left',
      one: '1 seat left',
    );
    return '$_temp0';
  }

  @override
  String sharedOnboard(int male, int female) {
    return 'On board: $male men · $female women';
  }

  @override
  String get sharedJoined => 'You\'ve joined the ride';

  @override
  String get sharedFull => 'Seats filled up. Pick another ride.';

  @override
  String get catalogTitle => 'Published trips';

  @override
  String get catalogEmpty => 'No published trips right now';

  @override
  String get catalogBook => 'Book a seat';

  @override
  String get catalogBooked => 'Seat booked';

  @override
  String get catalogPricePerSeat => 'per seat';

  @override
  String catalogDeparts(String when) {
    return 'Departs $when';
  }

  @override
  String get catalogFilterAll => 'All';

  @override
  String get notificationsTitle => 'Notifications';

  @override
  String get notificationsEmpty => 'No notifications';

  @override
  String get channelsTitle => 'Alert channels';

  @override
  String get channelsHint =>
      'The first channel that delivers stops the chain, so you won\'t hear it three times.';

  @override
  String get channelPush => 'Push';

  @override
  String get channelTelegram => 'Telegram';

  @override
  String get channelSms => 'SMS';

  @override
  String get channelLink => 'Link';

  @override
  String get channelUnlink => 'Unlink';

  @override
  String get channelLinked => 'Linked';

  @override
  String get channelNotLinked => 'Not linked';

  @override
  String get channelTelegramOpening => 'Opening Telegram… tap Start there.';

  @override
  String get channelTelegramLinked => 'Telegram linked';

  @override
  String get channelPriority => 'Priority';

  @override
  String get paymentDiscountFirstRide => 'First-ride discount';

  @override
  String get paymentDiscountCredit => 'Referral credit';

  @override
  String get paymentDiscount => 'Discount';

  @override
  String get paymentSubtotal => 'Fare';

  @override
  String get perksTitle => 'Morning pass & invites';

  @override
  String get perksSubscriptionsSection => 'Morning pass';

  @override
  String get perksSubscriptionsEmpty =>
      'No pass yet. Add your daily ride and we send a car before the time every day.';

  @override
  String get perksSubscriptionAdd => 'New pass';

  @override
  String get perksSubscriptionLabel => 'Name (optional)';

  @override
  String get perksSubscriptionLabelHint => 'To university';

  @override
  String get perksSubscriptionTime => 'Departure time';

  @override
  String get perksSubscriptionDays => 'Days';

  @override
  String get perksSubscriptionPickup => 'Pickup: your current location';

  @override
  String get perksSubscriptionDestination => 'Destination';

  @override
  String get perksSubscriptionPickDestination => 'Pick destination on the map';

  @override
  String get perksSubscriptionDestinationSet => 'Destination set';

  @override
  String perksSubscriptionNext(String when) {
    return 'Next request: $when';
  }

  @override
  String get perksSubscriptionPaused => 'Paused';

  @override
  String get perksSubscriptionCancel => 'Cancel pass';

  @override
  String get perksSubscriptionCancelConfirm =>
      'Cancel this pass? No more rides will be requested for it.';

  @override
  String get perksSubscriptionCreated =>
      'Pass created. We\'ll request a car 30 minutes before the time.';

  @override
  String get perksSubscriptionNeedDestination => 'Set a destination first.';

  @override
  String get perksReferralSection => 'Refer a friend';

  @override
  String get perksReferralMyCode => 'My invite code';

  @override
  String get perksReferralExplain =>
      'Share your code. After your friend\'s first ride you both get credit off the next ride.';

  @override
  String get perksReferralShare => 'Share code';

  @override
  String perksReferralShareText(String code) {
    return 'Try Soom Taksi — enter my invite code $code before your first ride and we both get credit.';
  }

  @override
  String get perksReferralCopied => 'Code copied';

  @override
  String get perksReferralEnter => 'Enter a friend\'s code';

  @override
  String get perksReferralEnterHint => 'e.g. ABC123';

  @override
  String get perksReferralApply => 'Apply';

  @override
  String perksReferralApplied(String code) {
    return 'Code $code applied. Credit arrives after your first ride.';
  }

  @override
  String perksReferralLinked(String code) {
    return 'Invited by: $code';
  }

  @override
  String get perksCreditBalance => 'Your credit';

  @override
  String get perksFirstRideAvailable =>
      'Your first ride is half price — applied automatically at payment.';

  @override
  String get perksFirstRideUsed => 'First-ride discount used.';

  @override
  String get dayMon => 'Mon';

  @override
  String get dayTue => 'Tue';

  @override
  String get dayWed => 'Wed';

  @override
  String get dayThu => 'Thu';

  @override
  String get dayFri => 'Fri';

  @override
  String get daySat => 'Sat';

  @override
  String get daySun => 'Sun';

  @override
  String get listSeparator => ', ';

  @override
  String get perksNextFormat => 'EEEE d MMM, HH:mm';

  @override
  String get balanceOwedToYou =>
      'Soum owes you this — customer discounts and wasted-trip compensation';

  @override
  String get balanceYouOwe => 'You owe the platform';

  @override
  String get balanceLifetimeEarned => 'Lifetime earned';

  @override
  String get balanceLifetimeCommission => 'Lifetime commission';

  @override
  String get balanceZero => 'Nothing pending between you and the platform';

  @override
  String collectDiscountNote(String customer, String rest, String net) {
    return 'The customer pays $customer after Soum\'s discount; the remaining $rest is added to your platform balance. Your full fare is $net.';
  }

  @override
  String get scheduleNow => 'Now';

  @override
  String get scheduleLater => 'Later';

  @override
  String get scheduleFormat => 'EEEE d MMM, HH:mm';

  @override
  String get scheduleTooSoon =>
      'Pick a time at least 10 minutes ahead — or request now.';

  @override
  String get requestScheduledRide => 'Book the time';

  @override
  String upcomingTitle(String when) {
    return 'Your booking: $when';
  }

  @override
  String get upcomingWaiting =>
      'Waiting for driver offers — we\'ll tell you when one arrives.';

  @override
  String get upcomingConfirmed =>
      'Your driver is confirmed. We\'ll remind you before the time.';

  @override
  String get historyStatusCancelled => 'Cancelled';

  @override
  String get historyStatusDisputed => 'Under review';

  @override
  String get historyStatusUpcoming => 'Upcoming';

  @override
  String driverBookingTitle(String when) {
    return 'Booking: $when';
  }

  @override
  String get driverBookingOpen => 'Go';

  @override
  String get dispatchOffers => 'Soum';

  @override
  String get dispatchOffersHint => 'Drivers bid, you pick';

  @override
  String get dispatchNearest => 'Nearest';

  @override
  String get dispatchNearestHint => 'The closest driver is sent automatically';

  @override
  String get dispatchPick => 'Pick a car';

  @override
  String get dispatchPickHint => 'Tap the car you want on the map';

  @override
  String get pickTapCar => 'Tap a car on the map to pick it';

  @override
  String pickSelected(String name, String vehicle) {
    return '$name · $vehicle';
  }

  @override
  String get searchRadiusLabel => 'Search range';

  @override
  String radiusKm(String km) {
    return '$km km';
  }

  @override
  String radiusMeters(String meters) {
    return '$meters m';
  }

  @override
  String get nearestTitle => 'Finding the nearest driver';

  @override
  String get nearestLooking => 'Asking the closest drivers in turn…';

  @override
  String get nearestAsking => 'Waiting for the nearest driver — a few seconds';

  @override
  String get nearestExhausted => 'Nobody accepted yet — offers are open now';

  @override
  String get requestNearest => 'Send nearest driver';

  @override
  String get requestPicked => 'Request this car';

  @override
  String get moreOptions => 'More options';

  @override
  String get serviceClass => 'Class';

  @override
  String carPassengers(int count) {
    return '$count riders';
  }

  @override
  String get carNew => 'New';

  @override
  String get runCancel => 'Cancel trip';

  @override
  String get runCancelTitle => 'Why are you cancelling?';

  @override
  String get runCancelWarning =>
      'The request goes back to searching for the rider. Repeated cancellations pause your offers for a while.';

  @override
  String get cancelReasonCar => 'Car problem';

  @override
  String get cancelReasonNoAnswer => 'Rider not answering';

  @override
  String get cancelReasonFar => 'Too far or road closed';

  @override
  String get cancelReasonOther => 'Other reason';

  @override
  String passengerChip(String name, int count) {
    return '$name · $count riders';
  }

  @override
  String lateCancelBadge(int count) {
    return 'Cancelled $count times recently';
  }

  @override
  String get cancelFreeNow => 'Cancelling now is free.';

  @override
  String get cancelDriverLateFree => 'The driver is late — cancelling is free.';

  @override
  String cancelCountsStrike(int limit) {
    return 'This cancellation counts as a strike. At $limit strikes in a week, Nearest and Pick a car pause for a day.';
  }

  @override
  String get driverCancelledRequeued =>
      'The driver cancelled — finding you another driver now.';

  @override
  String get shareRide => 'Share the ride';

  @override
  String get shareRideHint => 'Cheaper: share the car with riders on your way';

  @override
  String get callDriver => 'Call driver';

  @override
  String get callCustomer => 'Call rider';

  @override
  String get serviceSoon => 'Soon';

  @override
  String serviceComingSoon(String name) {
    return '$name is coming soon to Soum.';
  }

  @override
  String get incentivesTitle => 'Incentives';

  @override
  String incentiveRemaining(int count, String reward) {
    return '$count more trips to earn $reward';
  }

  @override
  String incentiveEarned(String reward) {
    return 'You earned $reward — collect it from the Soum office';
  }

  @override
  String get incentiveDelivered => 'Reward delivered — thank you';

  @override
  String get tripCancelWhy => 'Why are you cancelling the trip?';

  @override
  String get riderCancelChangedMind => 'I changed my mind';

  @override
  String get riderCancelDriverLate => 'The driver is late';

  @override
  String get riderCancelDriverNotMoving =>
      'The driver isn\'t moving towards me';

  @override
  String get riderCancelDriverAsked => 'The driver asked me to cancel';

  @override
  String get riderCancelFoundOther => 'I found another ride';

  @override
  String get riderCancelWrongPickup => 'Wrong pickup spot';

  @override
  String get riderCancelOther => 'Other reason';

  @override
  String get driverMockLocation =>
      'Your phone is sending a fake (mock) location, so we can\'t send you riders. Turn off the fake-location app in Developer options, then go online again.';

  @override
  String get runNoShow => 'Rider didn\'t show';

  @override
  String runNoShowWait(String time) {
    return '\"Rider didn\'t show\" unlocks in $time';
  }

  @override
  String get runNoShowConfirmTitle => 'Mark the rider as a no-show?';

  @override
  String get runNoShowConfirmBody =>
      'This cancellation won\'t count against you, and the request closes. If you\'re eligible, a compensation is added to your balance right away.';

  @override
  String get runNoShowDone =>
      'Rider marked as a no-show — it doesn\'t count against you.';

  @override
  String runNoShowCompensated(String amount) {
    return 'Rider marked as a no-show; $amount was added to your balance.';
  }

  @override
  String get rideEndedNoShow =>
      'Your driver arrived and waited, but you didn\'t show, so the request was closed.';

  @override
  String get proposalTitle => 'Your price';

  @override
  String proposalYours(String amount) {
    return 'Your price shown to drivers: $amount';
  }

  @override
  String proposalHint(String amount) {
    return 'Platform fare $amount — drivers accept your price or offer more.';
  }

  @override
  String get proposalSend => 'Offer my price';

  @override
  String get proposalRaise => 'Raise my price';

  @override
  String get proposalSent => 'Your price was sent to nearby drivers.';

  @override
  String get proposalLower => 'Lower';

  @override
  String get proposalHigher => 'Higher';

  @override
  String workCustomerPrice(String amount) {
    return 'Rider\'s price: $amount';
  }

  @override
  String get workAcceptCustomerPrice => 'Accept rider\'s price';

  @override
  String workCounterUpTo(String amount) {
    return 'Or offer more — up to $amount';
  }

  @override
  String get workCustomerPriceLabel => 'Rider\'s price';

  @override
  String unitMeters(String value) {
    return '$value m';
  }

  @override
  String workPickupAway(String distance) {
    return 'Pickup $distance away';
  }

  @override
  String get runCustomerCancelled => 'The rider cancelled the trip.';

  @override
  String runCustomerCancelledCompensated(String amount) {
    return 'The rider cancelled after you waited — $amount was added to your balance.';
  }
}
