/// العقد مع خادم سوم تاكسي.
///
/// هذه الحزمة لا تستورد `flutter/material.dart` ولا ترسم شيئًا. القاعدة
/// مفروضة باختبار: كلّ ما هنا يعمل بلا شاشة ولا محاكي، وهو ما يجعل المسار
/// الذي لا يراه المستخدم — الأخطاء، الحدود، إعادة الاتصال، حارس الترتيب —
/// قابلًا للاختبار فعلًا بدل أن يُجرَّب يدويًّا مرّة واحدة قبل التسليم.
library;

export 'src/api/ads_api.dart';
export 'src/api/auth_api.dart';
export 'src/api/driver_api.dart';
export 'src/api/feedback_api.dart';
export 'src/api/invitations_api.dart';
export 'src/api/maps_api.dart';
export 'src/api/notifications_api.dart';
export 'src/api/payments_api.dart';
export 'src/api/rides_api.dart';
export 'src/api/sharing_api.dart';

export 'src/config/app_config.dart';
export 'src/config/config_repository.dart';
export 'src/config/server_clock.dart';

export 'src/models/active_ride.dart';
export 'src/models/enums.dart';
export 'src/models/fare_proposal.dart';
export 'src/models/geo.dart';
export 'src/models/geohash.dart';
export 'src/models/incentive.dart';
export 'src/models/invitation.dart';
export 'src/models/json.dart';
export 'src/models/money.dart';
export 'src/models/names.dart';
export 'src/models/nearby_vehicle.dart';
export 'src/models/offer.dart';
export 'src/models/payment.dart';
export 'src/models/referral.dart';
export 'src/models/format.dart';
export 'src/models/ride.dart';
export 'src/models/subscription.dart';
export 'src/models/trip.dart';
export 'src/models/user.dart';
export 'src/models/vehicle.dart';

export 'src/network/api_client.dart';
export 'src/network/api_exception.dart';
export 'src/network/throttle_guard.dart';

export 'src/realtime/realtime_event.dart';
export 'src/realtime/realtime_room.dart';
export 'src/realtime/version_guard.dart';

export 'src/soum.dart';

export 'src/storage/session.dart';
export 'src/storage/stores.dart';
