/// إشعارات الدفع — FCM.
///
/// ثلاثة قرارات:
///
/// **١. الإقلاع لا ينتظر Firebase.** التهيئة تُطلق ولا يُنتظر ردّها قبل
/// الشاشة الأولى؛ مزوّدٌ متأخّر أو محجوب لا يجعل التطبيق أبيض.
///
/// **٢. الإشعار والتطبيق مفتوح لا يُعرض.** المقبس يحدّث الشاشة لحظيًّا
/// أصلًا؛ إشعارٌ فوقها يكرّر ما يراه المستخدم. الإشعار للتطبيق في الخلفية
/// أو المغلق — وهناك يعرضه النظام نفسه من حقل `notification`.
///
/// **٣. الفشل صامت.** §10.2: «لا تبنِ منطق حالة على وصول إشعار». جهازٌ بلا
/// خدمات Google (بعض الهواتف في السوق السوريّ) يعمل بالمقبس وحده.
library;

import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:soum_ui/soum_ui.dart';

abstract final class SoumPush {
  static Future<bool>? _ready;

  /// يُنادى من `main` قبل `runApp`. لا يحجب الإقلاع.
  static void install() {
    _ready = _init();
    BootController.pushTokenProvider = _token;
    BootController.pushTokenRefresh = _refreshes();
  }

  static Future<bool> _init() async {
    try {
      await Firebase.initializeApp();
      return true;
    } on Object catch (error) {
      debugPrint('[soum_push] Firebase غير متاح: $error');
      return false;
    }
  }

  static Future<String?> _token() async {
    if (!await (_ready ?? Future.value(false))) return null;
    final messaging = FirebaseMessaging.instance;
    // أندرويد 13+ يسأل المستخدم؛ الرفض يعني المقبس وحده، لا خطأ.
    final settings = await messaging.requestPermission();
    if (settings.authorizationStatus == AuthorizationStatus.denied) return null;
    return messaging.getToken().timeout(const Duration(seconds: 15));
  }

  /// المفتاح يتغيّر بلا إنذار (إعادة تثبيت، مسح بيانات Google Play).
  static Stream<String> _refreshes() async* {
    if (!await (_ready ?? Future.value(false))) return;
    yield* FirebaseMessaging.instance.onTokenRefresh;
  }
}
