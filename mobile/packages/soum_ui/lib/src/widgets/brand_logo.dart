/// شعار «سووم تكسي» كما يظهر داخل التطبيق.
///
/// الصورة تُولَّد من `tools/make_logo.ps1` لا تُرسم يدويًّا، فأيّ تغيير في
/// الشعار يمرّ من هناك ويصل إلى أيقونة الإطلاق وشاشة الإقلاع وهنا معًا.
library;

import 'package:flutter/material.dart';

class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.size = 132, this.radius = 28});

  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Image.asset(
        'assets/brand/logo.png',
        package: 'soum_ui',
        width: size,
        height: size,
        filterQuality: FilterQuality.medium,
        // بلا الصورة (اختبارٌ بلا أصول مثلًا) يبقى الاسم نصًّا لا مربّعًا فارغًا.
        errorBuilder: (context, _, _) => SizedBox(
          width: size,
          height: size,
          child: const Icon(Icons.local_taxi_rounded, size: 48),
        ),
      ),
    );
  }
}
