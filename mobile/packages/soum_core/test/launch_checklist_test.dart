// قائمة التحقّق قبل الإطلاق — §12 في دليل التكامل، بندًا بندًا.
//
// «مررتُ على هذه القائمة بنفسي على خادم يعمل. كلّ سطر منها انكسر مرّة في
// مكان ما».
//
// هذا الملفّ يحوّل تلك القائمة من نصٍّ يُقرأ إلى فحصٍ يسقط. الفرق أنّ
// النصّ يُراجَع مرّة قبل التسليم، والفحص يُراجَع عند كلّ تعديل — وبنودٌ
// مثل «لا رقم مثبَّت في الشيفرة» تُخرَق بعد ستّة أشهر في تعديل عابر، لا
// في المراجعة الأولى.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// جذر مساحة العمل، أيًّا كان مجلّد تشغيل الاختبار.
Directory get _workspace {
  var dir = Directory.current;
  for (var i = 0; i < 6; i++) {
    if (File('${dir.path}/pubspec.yaml').existsSync() &&
        Directory('${dir.path}/apps').existsSync()) {
      return dir;
    }
    dir = dir.parent;
  }
  fail('تعذّر إيجاد جذر مساحة العمل من ${Directory.current.path}');
}

Iterable<File> _sources({bool includeTests = false}) sync* {
  final root = _workspace;
  final roots = [
    Directory('${root.path}/packages/soum_core/lib'),
    Directory('${root.path}/packages/soum_ui/lib'),
    Directory('${root.path}/packages/soum_maps/lib'),
    Directory('${root.path}/apps/customer/lib'),
    Directory('${root.path}/apps/driver/lib'),
    if (includeTests) ...[
      Directory('${root.path}/packages/soum_core/test'),
      Directory('${root.path}/apps/customer/test'),
      Directory('${root.path}/apps/driver/test'),
    ],
  ];

  for (final dir in roots) {
    if (!dir.existsSync()) continue;
    for (final entity in dir.listSync(recursive: true)) {
      if (entity is File &&
          entity.path.endsWith('.dart') &&
          !entity.path.endsWith('.g.dart') &&
          !entity.path.contains('/generated/')) {
        yield entity;
      }
    }
  }
}

/// أسطر الشيفرة وحدها — بلا تعليقات.
Iterable<(File, int, String)> _codeLines() sync* {
  for (final file in _sources()) {
    final lines = file.readAsLinesSync();
    var inBlockComment = false;

    for (var i = 0; i < lines.length; i++) {
      final line = lines[i];
      final trimmed = line.trimLeft();

      if (inBlockComment) {
        if (trimmed.contains('*/')) inBlockComment = false;
        continue;
      }
      if (trimmed.startsWith('/*')) {
        inBlockComment = !trimmed.contains('*/');
        continue;
      }
      if (trimmed.startsWith('//')) continue;

      yield (file, i + 1, line);
    }
  }
}

/// المسار النسبيّ بفواصل مائلة أماميّة على كلّ نظام. على ويندوز يعطي
/// `listSync` فواصل خلفيّة، فكانت قوائم السماح لا تطابق شيئًا ويسقط
/// الفحص على آلة المطوّر وحدها.
String _rel(File file) => file.path
    .replaceAll('\\', '/')
    .replaceFirst('${_workspace.path.replaceAll('\\', '/')}/', '');

void main() {
  // =================================================================
  // §12.1 — الأساس
  // =================================================================

  group('§12.1 الأساس', () {
    test('GET /config/ يُقرأ عند كلّ إقلاع', () {
      final boot = File(
        '${_workspace.path}/packages/soum_ui/lib/src/boot/boot_controller.dart',
      ).readAsStringSync();

      expect(boot, contains('config.load'),
          reason: 'تسلسل الإقلاع لا يقرأ الإعداد');

      // وقبل المصادقة: شاشة الهاتف نفسها تحتاجه.
      final configAt = boot.indexOf('config.load');
      final authAt = boot.indexOf('auth.me');
      expect(configAt, lessThan(authAt),
          reason: 'الإعداد يُقرأ قبل المصادقة لا بعدها');
    });

    test('لا رقم من أرقام الإعداد مثبَّت في الشيفرة', () {
      // الأرقام الشهيرة التي تُكتب بالخطأ: أنصاف الأقطار بالأمتار،
      // ومهل الحضور بالثواني، ومهل الدعوة.
      final hardcoded = RegExp(
        r'(radius|Radius|ttl|Ttl|TTL|timeout|Timeout|stale|Stale)\w*\s*[=:]\s*'
        r'(200|300|60|30|20|40|90|5000|10000)\b',
      );

      final offenders = <String>[];
      for (final (file, line, text) in _codeLines()) {
        // المُهل المحلّية الخالصة مستثناة: مهلة انتظار إقرار مقبس ليست
        // إعدادًا من الخادم.
        if (text.contains('Duration(')) continue;
        if (hardcoded.hasMatch(text)) {
          offenders.add('${_rel(file)}:$line: ${text.trim()}');
        }
      }

      expect(offenders, isEmpty,
          reason: 'قيمة إعداد مثبَّتة في الشيفرة:\n${offenders.join('\n')}');
    });

    test('device_id ثابت — يُولَّد مرّة ويُحفظ ولا يُمحى عند الخروج', () {
      final session = File(
        '${_workspace.path}/packages/soum_core/lib/src/storage/session.dart',
      ).readAsStringSync();

      // `clearToken` يمحو المفتاح ولا يلمس المعرّف.
      final clearBlock = session.substring(
        session.indexOf('Future<void> clearToken()'),
        session.indexOf('Future<String> deviceId()'),
      );
      expect(clearBlock, isNot(contains('_deviceKey')),
          reason: 'محوُ المعرّف يجعل كلّ خروج تثبيتًا جديدًا فيُبطل حدّ الجهاز');
    });

    test('/me/active-ride/ هو أوّل نداء بعد المصادقة', () {
      final boot = File(
        '${_workspace.path}/packages/soum_ui/lib/src/boot/boot_controller.dart',
      ).readAsStringSync();

      final authAt = boot.indexOf('auth.me');
      final activeAt = boot.indexOf('rides.activeRide');

      expect(activeAt, greaterThan(authAt));

      // ولا نداء آخر بينهما.
      final between = boot.substring(authAt, activeAt);
      expect(between, isNot(contains('_soum.rides.mine')));
      expect(between, isNot(contains('_soum.driver.')));
    });

    test('التفرّع على code لا على نصّ الرسالة', () {
      // مقارنةُ `detail` بنصّ تعني شاشةً تنكسر عند أوّل تعديل صياغة في
      // الخادم — وهو تعديلٌ لا أحد يعدّه كسرًا للعقد.
      final comparing = RegExp(r'\.detail\s*==\s*[\x27"]');

      final offenders = <String>[];
      for (final (file, line, text) in _codeLines()) {
        if (comparing.hasMatch(text)) {
          offenders.add('${_rel(file)}:$line: ${text.trim()}');
        }
      }

      expect(offenders, isEmpty, reason: 'مقارنة نصّ خطأ: $offenders');
    });

    test('الأرقام المالية decimal لا عائمة', () {
      final money = RegExp(
        r'(double|num)\s+\w*(fare|Fare|amount|Amount|price|Price|'
        r'balance|Balance|total|Total)\w*\s*[=;)]',
      );

      final offenders = <String>[];
      for (final (file, line, text) in _codeLines()) {
        // `distanceKm` و`compatibilityScore` ليست مالًا.
        if (text.contains('Km') || text.contains('Score')) continue;
        if (money.hasMatch(text)) {
          offenders.add('${_rel(file)}:$line: ${text.trim()}');
        }
      }

      expect(offenders, isEmpty, reason: 'مال بعدد عائم: $offenders');
    });

    test('429 يُحترم بـretry_after لا بإعادة محاولة فورية', () {
      final guard = File(
        '${_workspace.path}/packages/soum_core/lib/src/network/throttle_guard.dart',
      ).readAsStringSync();

      expect(guard, contains('retryAfter'));
      expect(guard, contains('handler.reject'),
          reason: 'النداء داخل النافذة يجب أن يُرفض محلّيًّا لا أن يغادر');
    });
  });

  // =================================================================
  // §12.2 — الحيّ
  // =================================================================

  group('§12.2 الحيّ', () {
    test('إعادة الاتصال تعيد الاشتراك وترسم من اللقطة', () {
      final room = File(
        '${_workspace.path}/packages/soum_core/lib/src/realtime/realtime_room.dart',
      ).readAsStringSync();

      expect(room, contains('onReconnected'));
      expect(room, contains('_scheduleRetry'),
          reason: 'تراجع أسّي لا محاولة كلّ ملّي ثانية');
    });

    test('version الأصغر يُهمَل، والقفزة تُعالَج بـGET', () {
      final guard = File(
        '${_workspace.path}/packages/soum_core/lib/src/realtime/version_guard.dart',
      ).readAsStringSync();

      expect(guard, contains('VersionVerdict.stale'));
      expect(guard, contains('VersionVerdict.gap'));

      final room = File(
        '${_workspace.path}/packages/soum_core/lib/src/realtime/realtime_room.dart',
      ).readAsStringSync();
      expect(room, contains('requestResync'));
    });

    test('نبض الموقع كل 3–5 ثوانٍ، من الإعداد', () {
      final config = File(
        '${_workspace.path}/packages/soum_core/lib/src/config/app_config.dart',
      ).readAsStringSync();

      expect(config, contains('heartbeatInterval'));
      expect(config, contains('clamp(3, 5)'),
          reason: '§6.2 يحدّدها صراحةً «كل 3–5 ثوانٍ»');
    });

    test('العودة من الخلفية تعيد go-online', () {
      final presence = File(
        '${_workspace.path}/apps/driver/lib/features/presence/'
        'presence_controller.dart',
      ).readAsStringSync();

      expect(presence, contains('AppLifecycleState.resumed'));

      final resumed = presence.substring(
        presence.indexOf('AppLifecycleState.resumed'),
        presence.indexOf('AppLifecycleState.paused'),
      );
      expect(resumed, contains('goOnline'),
          reason: 'إعادة فتح المقبس وحدها لا تكفي');
    });

    test('الاشتراك في خليّة السوق يتبع حركة الخريطة', () {
      final marketplace = File(
        '${_workspace.path}/apps/customer/lib/features/map/'
        'marketplace_controller.dart',
      ).readAsStringSync();

      expect(marketplace, contains('followCamera'));
      expect(marketplace, contains('_settle'),
          reason: 'التبديل يتبع استقرار الكاميرا لا كلّ إطار');
    });
  });

  // =================================================================
  // §12.3 — الحالات التي ينساها الجميع
  // =================================================================

  group('§12.3 الحالات المنسيّة', () {
    test('route_source: estimated يُعرض كـ«سعر تقريبي» وبلا خطّ مسار', () {
      final fareCard = File(
        '${_workspace.path}/packages/soum_ui/lib/src/widgets/fare_card.dart',
      ).readAsStringSync();
      expect(fareCard, contains('fareApproximate'));
      expect(fareCard, contains('isApproximate'));

      // والخطّ لا يُرسم إلّا من هندسة حقيقية.
      final trip = File(
        '${_workspace.path}/apps/customer/lib/features/trip/trip_screen.dart',
      ).readAsStringSync();
      expect(trip, contains('routeGeometry != null'),
          reason: 'خطٌّ مستقيم بدل مسار تعذّر حسابه كذبٌ بصريّ');
    });

    test('409 عند اختيار سائق: رسالة لطيفة وقائمة محدَّثة', () {
      final auction = File(
        '${_workspace.path}/apps/customer/lib/features/auction/'
        'auction_screen.dart',
      ).readAsStringSync();

      expect(auction, contains('isDriverTaken'));
      expect(auction, contains('offerTaken'));
      expect(auction, isNot(contains('ApiErrorView')),
          reason: 'شاشة خطأ كاملة تُخرج الزبون من التدفّق');
    });

    test('زرّ تأكيد الدفع النقدي في تطبيق السائق فقط', () {
      final customerCharge = <String>[];
      for (final (file, line, text) in _codeLines()) {
        if (!file.path.contains('/apps/customer/')) continue;
        if (text.contains('payments.charge')) {
          customerCharge.add('${_rel(file)}:$line');
        }
      }
      expect(customerCharge, isEmpty,
          reason: 'الزبون لا يؤكّد قبض مالٍ لم يُقبَض');

      final driverCollect = File(
        '${_workspace.path}/apps/driver/lib/features/work/work_controller.dart',
      ).readAsStringSync();
      expect(driverCollect, contains('payments.charge'),
          reason: 'وزرّ التأكيد موجودٌ عند السائق');
    });

    test('pending_payment غير فارغ يفتح شاشة الدفع لا الرئيسية', () {
      final shell = File(
        '${_workspace.path}/apps/customer/lib/shell.dart',
      ).readAsStringSync();
      expect(shell, contains('ResumeStage.awaitingPayment'));
      expect(shell, contains('FinishScreen'));
    });

    test('سبب منع السائق يُعرض من detail لا برسالة عامّة', () {
      final bar = File(
        '${_workspace.path}/apps/driver/lib/features/presence/presence_bar.dart',
      ).readAsStringSync();
      expect(bar, contains('failure?.detail'));
    });

    test('مهلة الانقطاع من timings لا من الرقم 60', () {
      final presence = File(
        '${_workspace.path}/apps/driver/lib/features/presence/'
        'presence_controller.dart',
      ).readAsStringSync();
      expect(presence, contains('presenceStaleSeconds'));
      expect(presence, isNot(RegExp(r'=\s*60\s*;')));
    });

    test('فئات المركبات من vehicle_categories لا من قائمة مكتوبة', () {
      final form = File(
        '${_workspace.path}/apps/driver/lib/features/onboarding/'
        'onboarding_screen.dart',
      ).readAsStringSync();
      expect(form, contains('config.vehicleCategories'));

      final sheet = File(
        '${_workspace.path}/apps/customer/lib/features/home/request_sheet.dart',
      ).readAsStringSync();
      expect(sheet, contains('vehicleCategories'));
      expect(sheet, contains('config.rideModes'),
          reason: 'والأنماط كذلك — §12.3');
    });

    test('دائرة البحث بـmatching_radius_km لا برقم ثابت', () {
      final marker = File(
        '${_workspace.path}/apps/customer/lib/features/map/vehicle_marker.dart',
      ).readAsStringSync();
      expect(marker, contains('searchRadius'));

      final home = File(
        '${_workspace.path}/apps/customer/lib/features/home/home_screen.dart',
      ).readAsStringSync();
      expect(home, contains('geometry.matchingRadiusKm'));
    });

    test('تليغرام يظهر فقط إن كانت قناته configured', () {
      final channels = File(
        '${_workspace.path}/apps/customer/lib/features/notifications/'
        'channels_screen.dart',
      ).readAsStringSync();
      expect(channels, contains('isVisible'));
      expect(channels, contains('503'),
          reason: '503 على الربط تُخفي الخيار لا تعرض خطأ');
    });
  });

  // =================================================================
  // حدود معمارية تحرس القائمة نفسها
  // =================================================================

  group('حدود معمارية', () {
    test('الطبقة المشتركة لا ترسم شيئًا', () {
      final offenders = <String>[];
      for (final file in _sources()) {
        if (!file.path.contains('/packages/soum_core/')) continue;
        final source = file.readAsStringSync();
        if (source.contains('package:flutter/material.dart') ||
            source.contains('package:flutter/widgets.dart')) {
          offenders.add(_rel(file));
        }
      }
      expect(offenders, isEmpty);
    });

    test('لا شاشة تستورد مزوّد الخرائط مباشرةً', () {
      final offenders = <String>[];
      for (final file in _sources()) {
        if (file.path.contains('/packages/soum_maps/')) continue;
        final source = file.readAsStringSync();
        if (source.contains('package:flutter_map/') ||
            source.contains('package:latlong2/')) {
          offenders.add(_rel(file));
        }
      }
      expect(offenders, isEmpty,
          reason: 'استبدال المزوّد يجب أن يبقى تنفيذًا ثانيًا خلف الواجهة');
    });

    test('بناء مسارات غرف البثّ محصورٌ في موضعين موثَّقين', () {
      // القاعدة: المسارات تأتي من `/me/active-ride/`. والاستثناءان
      // موثَّقان في موضعهما ولهما سبب مقيس:
      //
      //   • غرفة الرحلة بعد `POST /rides/` — الاستجابة لا تحملها،
      //     وانتظارُ نداءٍ لقراءتها يُضيّع أوّل عرض.
      //   • غرفة السائق — الخادم لا يعطي مسارها إلّا مع رحلة قائمة.
      //
      // ما يقيسه الفحص هو **البناء** لا القراءة: تعبيرٌ منتظم يفكّ
      // مسارًا جاء من الخادم ليس بناءً.
      const allowed = {
        'apps/customer/lib/features/ride/ride_controller.dart',
        'apps/driver/lib/features/presence/presence_controller.dart',
        'packages/soum_core/lib/src/soum.dart',
      };

      // بناءٌ = تركيب نصّ فيه استيفاء أو ضمّ، لا نمطٌ للمطابقة.
      final building = RegExp(r"""'/ws/\w+/\$""");

      final offenders = <String>[];
      for (final (file, line, text) in _codeLines()) {
        if (allowed.contains(_rel(file))) continue;
        if (building.hasMatch(text)) {
          offenders.add('${_rel(file)}:$line: ${text.trim()}');
        }
      }

      expect(offenders, isEmpty,
          reason: 'بناء مسار غرفة خارج المواضع الموثَّقة: $offenders');

      // والاستثناء الأوّل موثَّق فعلًا لا مسكوتٌ عنه.
      final rideController = File(
        '${_workspace.path}/apps/customer/lib/features/ride/'
        'ride_controller.dart',
      ).readAsStringSync();
      expect(rideController, contains('الموضع **الوحيد**'),
          reason: 'الاستثناء بلا تفسير يصير قاعدةً بعد ستّة أشهر');
    });
  });

  // ---------------------------------------------------------------
  // بيان أندرويد
  //
  // هذه المجموعة أُضيفت بعد عطلٍ حقيقيّ لا احتياطًا: بناء release
  // اجتاز مئةً واثنين وثمانين اختبارًا ثمّ خرج بلا إذن INTERNET،
  // لأنّ فلاتر تضع ذلك الإذن في بيان الـdebug وحده وgeolocator_android
  // لا يُصرّح بصلاحيات الموقع في بيانه إطلاقًا.
  //
  // والسبب في أنّ الاختبارات لم تلتقطه أنّها تعمل في آلة Dart على
  // لينكس لا على أندرويد، فلا بيان يُقرأ ولا إذن يُفحص. أي أنّ هذا
  // بالضبط الصنف الذي لا يكشفه إلّا فحصُ ملفّ البناء نفسه.
  // ---------------------------------------------------------------
  group('بيان أندرويد', () {
    String manifestOf(String app) => File(
          '${_workspace.path}/apps/$app/android/app/src/main/'
          'AndroidManifest.xml',
        ).readAsStringSync();

    /// أذونات لا يضيفها أحدٌ نيابةً عن التطبيق.
    const shared = [
      'android.permission.INTERNET',
      'android.permission.ACCESS_FINE_LOCATION',
      'android.permission.ACCESS_COARSE_LOCATION',
      'android.permission.POST_NOTIFICATIONS',
    ];

    for (final app in ['customer', 'driver']) {
      test('$app: الأذونات مُصرَّحة في بيان release لا في بيان debug', () {
        final manifest = manifestOf(app);
        for (final permission in shared) {
          expect(
            manifest,
            contains('android:name="$permission"'),
            reason: 'أندرويد لا يخبر المستخدم بنقص الإذن — يرفض العملية '
                'بصمت. الناقص: $permission',
          );
        }
      });

      test('$app: سياسة النصّ الصريح مُعلَنة لا متروكة للافتراض', () {
        // الافتراض منذ أندرويد ٩ هو المنع. وتطبيقٌ يعتمد عليه ضمنًا
        // ينكسر حين يتغيّر targetSdk ولا أحد يعرف لماذا. فليكن
        // الاختيار مكتوبًا — `true` اليوم للتطوير على خادم محلّي،
        // و`false` يوم تُركَّب شهادة TLS.
        expect(
          manifestOf(app),
          contains('android:usesCleartextTraffic='),
          reason: 'قيمةٌ ضمنية تجعل انقطاعَ الشبكة يبدو عطلَ خادم',
        );
      });
    }

    test('السائق يُصرّح بالكاميرا، والزبون لا يفعل', () {
      // شاشة التوثيق تستعمل `ImageSource.camera`. وإذنٌ في تطبيق لا
      // يحتاجه سؤالٌ إضافيّ في المتجر وسببُ رفض.
      expect(manifestOf('driver'), contains('android.permission.CAMERA'));
      expect(manifestOf('customer'),
          isNot(contains('android.permission.CAMERA')));
    });

    test('لا موقع في الخلفية — القرار مكتوب لا منسيّ', () {
      // غيابُ الإذن هنا قرارٌ معلَّل في README: نبضٌ من تطبيق مغلق
      // يعرض على خريطة الزبون سيارةً لا أحد فيها.
      final driver = manifestOf('driver');
      expect(driver, isNot(contains('ACCESS_BACKGROUND_LOCATION="')));
      expect(driver, contains('ACCESS_BACKGROUND_LOCATION'),
          reason: 'القرار بالغياب يجب أن يُذكر، وإلّا قُرئ نسيانًا');
    });
  });
}
