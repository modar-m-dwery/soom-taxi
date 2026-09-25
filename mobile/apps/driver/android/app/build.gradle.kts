plugins {
    id("com.android.application")
    id("com.google.gms.google-services")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "sy.soum.soum_driver"
    compileSdk = flutter.compileSdkVersion
    // ndkVersion مُعطَّل عمدًا.
    //
    // السطر الأصلي `ndkVersion = flutter.ndkVersion` من قالب فلاتر،
    // وهو يجعل AGP يتحقّق من وجود NDK بنسخة بعينها وقت الإعداد،
    // ويحاول تثبيتها إن غابت باستدعاء sdkmanager.
    //
    // وذلك يفشل على ويندوز: الاستدعاء يمرّر «ndk;28.2.13676358»
    // بلا علامات تنصيص، والفاصلة المنقوطة فاصلُ معاملات في cmd —
    // فيصل الاسم مقطّعًا اثنين:
    //     Package ndk not found.
    //     Package 28.2.13676358 not found.
    // ثمّ ينهار sdkmanager نفسه بـNTSTATUS 0xC0000409.
    //
    // والأهمّ: **هذا التطبيق لا يحتاج NDK إطلاقًا.** لا شيفرة C أو
    // C++ فيه، ولا في أيّ من إضافاته (geolocator، permission_handler،
    // image_picker، url_launcher، flutter_secure_storage). ومحرّك
    // فلاتر يأتي مبنيًّا جاهزًا. فالسطر كان يفرض تنزيل غيغابايت
    // لا يُستعمَل.
    //
    // أعِده إن أضفت يومًا إضافةً فيها externalNativeBuild — وحينها
    // ثبّت الـNDK يدويًّا بعلامات تنصيص:
    //     sdkmanager.bat "ndk;28.2.13676358"
    // ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "sy.soum.soum_driver"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // كان هنا `packaging.jniLibs.keepDebugSymbols += "**/*.so"` حين كان
    // مجلّد الـNDK هيكلًا فارغًا بلا llvm-strip. منذ 2026-09-20 الـNDK حقيقيّ
    // (r28c في D:/Dev/AndroidSdk/ndk/28.2.13676358) فتُجرَّد المكتبات
    // وينزل حجم الإصدار من ~170 إلى ~35 ميغابايت.

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
