import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_push/soum_push.dart';
import 'package:soum_ui/soum_ui.dart';

import 'env.dart';
import 'shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SoumPush.install();

  final soum = await Soum.create(
    baseUrl: Env.apiBaseUrl,
    secure: PlatformSecureStore(),
    prefs: await PlatformPrefsStore.open(),
  );

  runApp(
    ProviderScope(
      overrides: [soumProvider.overrideWithValue(soum)],
      child: const CustomerApp(),
    ),
  );
}

class CustomerApp extends StatelessWidget {
  const CustomerApp({super.key});

  @override
  Widget build(BuildContext context) {
    // مسار واحد: البوّابة هي من يقرّر الشاشة من حالة الإقلاع، لا جدول
    // مسارات يُقفز إليه. التنقّل داخل قوس الرحلة يأتي في M3.
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => BootGate(
            appName: SoumStrings.of(context).appNameCustomer,
            onReady: (context, ready) => CustomerShell(boot: ready),
          ),
        ),
      ],
    );

    return SoumApp(
      onGenerateTitle: (context) => SoumStrings.of(context).appNameCustomer,
      routerConfig: router,
    );
  }
}
