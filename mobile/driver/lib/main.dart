import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:soum_core/soum_core.dart';
import 'package:soum_push/soum_push.dart';
import 'package:soum_ui/soum_ui.dart';

import 'env.dart';
import 'features/earnings/balance_screen.dart';
import 'features/publish/publish_screen.dart';
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
      child: const DriverApp(),
    ),
  );
}

class DriverApp extends StatelessWidget {
  const DriverApp({super.key});

  @override
  Widget build(BuildContext context) {
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => BootGate(
            appName: SoumStrings.of(context).appNameDriver,
            onReady: (context, ready) => DriverShell(boot: ready),
          ),
          routes: [
            GoRoute(
              path: 'balance',
              builder: (context, state) => const BalanceScreen(),
            ),
            GoRoute(
              path: 'publish',
              builder: (context, state) => const PublishScreen(),
            ),
          ],
        ),
      ],
    );

    return SoumApp(
      onGenerateTitle: (context) => SoumStrings.of(context).appNameDriver,
      routerConfig: router,
    );
  }
}
