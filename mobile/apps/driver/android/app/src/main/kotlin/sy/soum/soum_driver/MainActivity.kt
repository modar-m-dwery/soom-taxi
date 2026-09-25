package sy.soum.soum_driver

import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createChannels()
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
