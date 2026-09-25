/// غلاف التطبيق — الاتجاه والثيم والترجمة في موضع واحد.
///
/// العربية أوّلًا لا كترجمة لاحقة: السوق الأوّل جبلة، والمستخدم الافتراضي
/// يقرأ من اليمين. `MaterialApp` يستنتج الاتجاه من اللغة، لكنّنا نثبّت
/// `ar` أوّل اللغات المدعومة حتّى يكون هو الافتراض حين تكون لغة الجهاز
/// غير مدعومة أصلًا.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'l10n/generated/soum_strings.dart';
import 'theme/soum_theme.dart';

class SoumApp extends StatelessWidget {
  const SoumApp({
    super.key,
    required this.onGenerateTitle,
    required this.routerConfig,
    this.themeMode = ThemeMode.system,
  });

  /// العنوان الذي يراه المستخدم في مبدّل التطبيقات.
  ///
  /// دالّة لا نصّ: `title` يُبنى قبل أن توجد الترجمة في الشجرة، فكتابته
  /// نصًّا هو الطريق الوحيد الذي يُخرج اسم التطبيق من ملفّ الترجمة —
  /// وهو ما يكسر الفحص الآليّ في T2.4 بحقّ.
  final String Function(BuildContext) onGenerateTitle;
  final RouterConfig<Object> routerConfig;
  final ThemeMode themeMode;

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      onGenerateTitle: onGenerateTitle,
      debugShowCheckedModeBanner: false,
      theme: SoumTheme.light(),
      darkTheme: SoumTheme.dark(),
      themeMode: themeMode,
      locale: const Locale('ar'),
      supportedLocales: SoumStrings.supportedLocales,
      localizationsDelegates: const [
        SoumStrings.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      routerConfig: routerConfig,
      builder: (context, child) {
        // حجم الخطّ يتبع تفضيل النظام، بسقف. مستخدمٌ ضبط جهازه على 200%
        // يكسر كلّ بطاقة فيها عدّاد وسعر معًا — والسقف يُبقي الشاشة
        // مقروءة بدل أن تصير غير مستعملة.
        final scale = MediaQuery.textScalerOf(context).clamp(
          minScaleFactor: 0.9,
          maxScaleFactor: 1.35,
        );
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: scale),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
