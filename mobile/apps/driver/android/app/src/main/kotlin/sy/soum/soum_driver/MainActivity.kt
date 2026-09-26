package sy.soum.soum_driver

import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createChannels()
    }

    // الشاشة تبقى مضاءة ما دام السائق «يعمل الآن». النبض يتوقّف عمدًا حين
    // يذهب التطبيق للخلفية (راجع البيان)، وقفلُ الشاشة التلقائيّ بعد نصف
    // دقيقة كان يُخرج السائق من الأسطول بعد دقيقة دون أن يدري.
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "sy.soum/screen")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "keepOn" -> {
                        if (call.arguments == true) {
                            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        } else {
                            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        }
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    // القناتان اللتان يسمّيهما الخادم في رسالة FCM (android.notification.channel_id).
    // العاجلة تنبثق فوق الشاشة بصوت — دعوة سائق، «السائق وصل» — والعامّة هادئة.
    // إنشاء قناة موجودة لا يفعل شيئًا، فالنداء عند كلّ إقلاع آمن.
    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel("soum_urgent", getString(R.string.channel_urgent), NotificationManager.IMPORTANCE_HIGH)
        )
        manager.createNotificationChannel(
            NotificationChannel("soum_general", getString(R.string.channel_general), NotificationManager.IMPORTANCE_DEFAULT)
        )
    }
}
