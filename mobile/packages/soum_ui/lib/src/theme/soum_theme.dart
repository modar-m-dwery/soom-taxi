/// هويّة سووم تكسي البصرية.
///
/// ثلاثة قرارات تستحقّ التفسير:
///
/// **١. الخطّ مُضمَّن لا مُنزَّل.** حزمة `google_fonts` تجلب الخطّ عند أوّل
/// تشغيل وتخبّئه. في تطبيق نقل يُفتح على رصيف بشبكة ضعيفة، ذلك يعني شاشة
/// أولى بخطّ بديل — والعربية بخطّ بديل تتغيّر عرضًا وارتفاعًا فتقفز الشاشة
/// حين يصل الخطّ. IBM Plex Sans Arabic مُضمَّن بأربعة أوزان، 950 كيلوبايت
/// ثمنًا لشاشة لا ترتجف.
///
/// **٢. الأرقام جدوليّة في كلّ مكان.** الأجرة والعدّاد والمسافة أرقامٌ
/// تتغيّر في مكانها. بخطّ متناسب تتغيّر عرضًا مع كلّ ثانية، فيرتجف السطر —
/// وهو ما يجعل عدّاد الدعوة يبدو معطوبًا وهو سليم.
///
/// **٣. الأصفر للفعل وحده.** أصفر الشعار — لوحة التاكسي — يميّز الزرّ الذي
/// يُضغط: اطلب، ادعُ، اقبل. استعماله للزينة يُفقده معناه، فلا يعود المستخدم
/// يعرف أين يضغط في شاشة فيها ستّة عناصر برّاقة. والنصّ عليه حبرٌ داكن
/// دائمًا: الأبيض على الأصفر لا يُقرأ في الشمس.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

abstract final class SoumColors {
  // أصفر الشعار — لون التاكسي. للفعل الأساسيّ وحده، وعلى حبرٍ داكن لا
  // أبيض: الأصفر على الأبيض لا يُقرأ، وعلى الأسود هو لوحة التاكسي نفسها.
  static const brand = Color(0xFFFFC800);
  static const brandDark = Color(0xFFFFD23F);
  static const brandSoft = Color(0xFFFFF1B8);
  static const brandSoftDark = Color(0xFF3D3100);
  static const onBrand = Color(0xFF1A1500);
  static const goldInk = Color(0xFF8A6500);

  // الفيروزيّ — الساحل. للثانويّ والروابط وما «نجح».
  static const teal = Color(0xFF186063);
  static const tealDark = Color(0xFF6FB4B6);

  // دلاليّة — منفصلة عن لون الهويّة عمدًا: «نجح» يجب ألّا يشبه «اضغط».
  static const success = Color(0xFF2C6E49);
  static const successDark = Color(0xFF6FBF8E);
  static const warning = Color(0xFFA8501A);
  static const warningDark = Color(0xFFE09062);
  static const danger = Color(0xFFB3261E);
  static const dangerDark = Color(0xFFE79189);

  // محايدات دافئة بميلٍ إلى الأصفر — رماديّ خالص يبدو غير مقصود، وبارد
  // بجوار الأصفر.
  static const ink = Color(0xFF17150F);
  static const paper = Color(0xFFF7F5EE);
  static const surface = Color(0xFFFFFFFF);
  static const line = Color(0xFFE6E1D2);

  static const inkDark = Color(0xFFEFEBE0);
  static const paperDark = Color(0xFF121109);
  static const surfaceDark = Color(0xFF1B1912);
  static const lineDark = Color(0xFF34301F);

  /// الاسم القديم أبقيناه: شاشاتٌ كثيرة تقول `amber` وتقصد لون الفعل.
  static const amber = brand;
  static const amberDark = brandDark;
}

abstract final class SoumTheme {
  static const fontFamily = 'IBMPlexSansArabic';

  static ThemeData light() => _build(Brightness.light);
  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;

    final scheme = ColorScheme(
      brightness: brightness,
      primary: isDark ? SoumColors.brandDark : SoumColors.brand,
      onPrimary: SoumColors.onBrand,
      primaryContainer: isDark ? SoumColors.brandSoftDark : SoumColors.brandSoft,
      onPrimaryContainer: isDark ? SoumColors.brandDark : SoumColors.onBrand,
      secondary: isDark ? SoumColors.tealDark : SoumColors.teal,
      onSecondary: isDark ? const Color(0xFF00201F) : Colors.white,
      error: isDark ? SoumColors.dangerDark : SoumColors.danger,
      onError: isDark ? const Color(0xFF370002) : Colors.white,
      surface: isDark ? SoumColors.surfaceDark : SoumColors.surface,
      onSurface: isDark ? SoumColors.inkDark : SoumColors.ink,
      surfaceContainerLowest: isDark ? SoumColors.paperDark : SoumColors.paper,
      surfaceContainerHighest:
          isDark ? const Color(0xFF26231A) : const Color(0xFFEFECE2),
      outline: isDark ? const Color(0xFF4A4530) : const Color(0xFFC9C3B0),
      outlineVariant: isDark ? SoumColors.lineDark : SoumColors.line,
      onSurfaceVariant: isDark ? const Color(0xFF9C9686) : const Color(0xFF6B675A),
      // الثالثيّ = «حبر ذهبيّ»: الأصفر نفسه حين يُكتب به نصٌّ أو رابط على سطح
      // فاتح — الأصفر الخالص لا يُقرأ كنصّ، والذهبيّ الداكن يُقرأ ويبقى من العائلة.
      tertiary: isDark ? SoumColors.brandDark : SoumColors.goldInk,
      onTertiary: isDark ? SoumColors.onBrand : Colors.white,
    );

    final text = _textTheme(scheme.onSurface, scheme.onSurfaceVariant);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      fontFamily: fontFamily,
      scaffoldBackgroundColor: scheme.surfaceContainerLowest,
      textTheme: text,

      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0.5,
        centerTitle: false,
        titleTextStyle: text.titleLarge,
        systemOverlayStyle:
            isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      ),

      cardTheme: CardThemeData(
        color: scheme.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          // ارتفاع 52: الزرّ يُضغط بإبهام واحد وسيارةٌ تتحرّك، لا بمؤشّر
          // فأرة. الحدّ الأدنى الموصى به 48، وزدناه لأنّ أخطاء اللمس هنا
          // تكلّف رحلة.
          minimumSize: const Size.fromHeight(52),
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),

      // أزرار النصّ بالحبر الذهبيّ لا بالأصفر: نصٌّ أصفر على سطح فاتح يختفي.
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: scheme.tertiary,
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(52),
          foregroundColor: scheme.onSurface,
          side: BorderSide(color: scheme.outline),
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),

      // الرقائق: المختارة حبرٌ داكن بنصٍّ أصفر — لوحة التاكسي مقلوبة —
      // فتُقرأ من بعيد ولا تلتبس بالزرّ الأساسيّ.
      chipTheme: ChipThemeData(
        backgroundColor: scheme.surfaceContainerHighest,
        selectedColor: scheme.onSurface,
        side: BorderSide.none,
        labelStyle: TextStyle(
          fontFamily: fontFamily,
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
        secondaryLabelStyle: TextStyle(
          fontFamily: fontFamily,
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: scheme.primary,
        ),
        checkmarkColor: scheme.primary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),

      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? SoumColors.onBrand
              : scheme.surface,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.outlineVariant,
        ),
        trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.onSurface, width: 1.6),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.error),
        ),
      ),

      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant,
        thickness: 1,
        space: 1,
      ),

      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: scheme.onSurface,
        contentTextStyle: TextStyle(
          fontFamily: fontFamily,
          color: scheme.surface,
          fontSize: 14.5,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),

      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
      ),
    );
  }

  static TextTheme _textTheme(Color ink, Color muted) {
    TextStyle style(double size, FontWeight weight,
            {double height = 1.45, Color? color, double spacing = 0}) =>
        TextStyle(
          fontFamily: fontFamily,
          fontSize: size,
          fontWeight: weight,
          height: height,
          letterSpacing: spacing,
          color: color ?? ink,
        );

    return TextTheme(
      displaySmall: style(32, FontWeight.w700, height: 1.25),
      headlineMedium: style(24, FontWeight.w700, height: 1.32),
      headlineSmall: style(20, FontWeight.w700, height: 1.35),
      titleLarge: style(18, FontWeight.w700),
      titleMedium: style(16, FontWeight.w500),
      bodyLarge: style(16, FontWeight.w400, height: 1.6),
      bodyMedium: style(14.5, FontWeight.w400, height: 1.6),
      bodySmall: style(13, FontWeight.w400, height: 1.5, color: muted),
      labelLarge: style(15, FontWeight.w600),
      labelMedium: style(13, FontWeight.w500, color: muted),
      labelSmall: style(11.5, FontWeight.w500, color: muted, spacing: 0.3),
    );
  }

  /// نمط الأرقام التي تتغيّر في مكانها — أجرة، عدّاد، مسافة.
  static TextStyle tabular(TextStyle base) => base.copyWith(
        fontFeatures: const [FontFeature.tabularFigures()],
      );
}
