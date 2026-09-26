# دليل المطوّرين — سووم تكسي

من الصفر إلى رحلة كاملة على جهازك: تنزيل المستودع، تشغيل الخادم، تشغيل
تطبيقي الزبون والسائق، الاختبارات، وقواعد العمل في الشيفرة.

> **الوقت المتوقَّع:** قرابة ساعة في المرّة الأولى، أغلبها تنزيل Docker
> وFlutter وAndroid SDK.

---

## ١. ما هذا المشروع

منصّة تكسي بثلاث طرق طلب:

- **سوم:** الزبون يطلب، والسائقون القريبون يعرضون أسعارهم، أو يعرض الزبون
  سعره فيقبله السائق أو يعرض أعلى منه.
- **الأقرب:** الخادم يدعو أقرب سائق بسعر المنصّة.
- **اختر سيارتك:** الزبون يلمس سيارةً على الخريطة فيدعو سائقها.

والمستودع من ثلاثة أجزاء:

| الجزء | المسار | التقنية |
|---|---|---|
| الخادم | `backend/` | Django 5.2 · DRF · Channels (WebSocket) · Celery · PostgreSQL/PostGIS · Redis |
| تطبيق الزبون | `mobile/apps/customer/` | Flutter · Riverpod · flutter_map |
| تطبيق السائق | `mobile/apps/driver/` | Flutter · Riverpod · flutter_map |
| الحزم المشتركة | `mobile/packages/` | `soum_core` · `soum_ui` · `soum_maps` · `soum_push` |
| الوثائق | `docs/` | هذا الملفّ وقرارات المنتج والتدقيق |

---

## ٢. ما تحتاجه على جهازك

| الأداة | النسخة | لماذا |
|---|---|---|
| Git | أيّ نسخة حديثة | التنزيل |
| Docker Desktop (أو Docker Engine مع Compose v2) | حديثة | قاعدة البيانات وRedis والخادم |
| Flutter | **3.47.x** (stable) — ومعه Dart 3.13 | التطبيقان (`sdk: ^3.13.0`) |
| Android Studio + Android SDK + JDK 17 | حديثة | البناء والمحاكي |
| Python | 3.12 (يعمل على 3.11) | فقط إن شغّلت الخادم بلا دوكر |

تحقّق:

```bash
git --version
docker compose version
flutter --version
flutter doctor
```

---

## ٣. تنزيل المستودع

المستودع يجب أن يكون **خاصًّا**، والدخول إليه بدعوة من صاحبه (GitHub ← Settings ← Collaborators).

```bash
git clone https://github.com/modar-m-dwery/soom-taxi.git
cd soom-taxi
git checkout claude/taxi-app-features-design-w1fat8
```

> الفرع أعلاه يحمل آخر عمل إلى أن يُدمج في الفرع الرئيسيّ. بعد الدمج
> استعمل الفرع الرئيسيّ.

**نهايات الأسطر:** ملفّات كثيرة محفوظة بـCRLF عمدًا. لا تدع Git أو المحرّر
يحوّلها، وإلا ظهر كلّ سطر في الملفّ على أنّه تغيّر:

```bash
git config core.autocrlf false
```

وفي VS Code اترك `files.eol` على `auto`.

---

## ٤. تشغيل الخادم — الطريق الموصى به (دوكر)

أمرٌ واحد يرفع خمس حاويات: PostgreSQL+PostGIS، Redis، الخادم (Daphne)،
عامل Celery، ومجدول Celery beat.

```bash
cd backend
cp .env.docker.example .env.docker
mkdir -p secrets
```

ثمّ حدّد مجلّد مفاتيح Firebase: فارغٌ الآن، ولا يلزم إلا لتجربة
الإشعارات الحقيقيّة.

**لينكس/ماك:**

```bash
export FCM_SECRETS_DIR=./secrets
docker compose -f compose.dev.yaml up -d --build
```

**ويندوز (PowerShell):**

```powershell
$env:FCM_SECRETS_DIR = "./secrets"
docker compose -f compose.dev.yaml up -d --build
```

> بلا `FCM_SECRETS_DIR` يأخذ الملفّ `C:/secrets` افتراضيًّا، وهذا المسار
> يُسقط الأمر على لينكس وماك.

عند أوّل إقلاع يحدث ما يلي وحده:

1. يُفعَّل امتداد PostGIS.
2. تُشغَّل الترحيلات.
3. تُزرع حسابات العرض ومناطق الخدمة.

**تحقّق أنّه يعمل:**

| الرابط | ماذا |
|---|---|
| http://localhost:8000/api/v1/health/ | الصحّة |
| http://localhost:8000/api/docs/ | Swagger — كلّ نقاط الـAPI وتجربتها |
| http://localhost:8000/admin/ | لوحة الإدارة |
| ws://localhost:8000/ws/... | المقابس الحيّة (يستعملها التطبيقان) |

وفحصٌ شامل آليّ يشمل: الصحّة، وSwagger، ودورة رمز الدخول، ورحلة كاملة،
والمقبس:

```bash
docker compose -f compose.dev.yaml exec web python scripts/smoke_test.py
```

### حسابات العرض

| الدور | الهاتف |
|---|---|
| زبون | `+963990000101` |
| سائق (موثَّق وله سيارة) | `+963990000102` |
| مدير | `+963990000103` |

**رمز الدخول (OTP):** في التطوير لا تُرسل رسائل. الرمز يظهر في مكانين:

- على شاشة التطبيق نفسه تحت عنوان «رمز التطوير».
- في سجلّ العامل:

```bash
docker compose -f compose.dev.yaml logs -f celery
```

**توكنات جاهزة لـSwagger:** شغّل الأمر التالي، ثمّ في Swagger اضغط
**Authorize** وأدخل `Token <القيمة>`:

```bash
docker compose -f compose.dev.yaml exec web python manage.py seed_mobile_demo
```

**مستخدم للوحة الإدارة:**

```bash
docker compose -f compose.dev.yaml exec web python manage.py createsuperuser
```

الحقل الأوّل هو رقم الهاتف، لأنّ الدخول بالهاتف لا باسم المستخدم.

### سيارات تتحرّك على الخريطة

سائقٌ واحد واقف لا يُظهر «الأقرب» ولا «اختر سيارتك». هذا الأمر يشغّل أسطولًا
آليًّا يدور في المدينة، وخيار `--accept` يجعل السائقين يقبلون الدعوات وحدهم:

```bash
docker compose -f compose.dev.yaml exec web python scripts/sim_fleet.py --drivers 8 --accept
```

### أوامر يوميّة

```bash
docker compose -f compose.dev.yaml logs -f web            # سجلّ الخادم
docker compose -f compose.dev.yaml exec web python manage.py shell
docker compose -f compose.dev.yaml restart celery beat    # بعد تعديل مهمّة مجدولة
docker compose -f compose.dev.yaml down                   # إيقاف (البيانات تبقى)
docker compose -f compose.dev.yaml down -v                # إيقاف ومسح القاعدة كلّها
```

الشيفرة مربوطة بالحاوية مباشرةً، فتعديل ملفّ Python ينعكس بلا إعادة بناء.
أعد تشغيل `web` بعد تغيير الإعدادات، وأعد البناء (`--build`) بعد تغيير
`requirements.txt`.

---

## ٥. تشغيل الخادم بلا دوكر (اختياريّ)

القاعدة وRedis تبقيان في دوكر، والخادم يعمل مباشرةً على جهازك. هذا أسرع
للتصحيح بنقاط التوقّف (debugger).

```bash
cd backend
docker compose up -d                 # postgres (المنفذ 5433) + redis فقط
python -m venv .venv
source .venv/bin/activate            # ويندوز: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

**مكتبات GeoDjango (GDAL/GEOS):**

| النظام | التثبيت |
|---|---|
| أوبونتو/ديبيان | `sudo apt install gdal-bin` |
| ماك | `brew install gdal` |
| ويندوز | ثبّت OSGeo4W، ثمّ اضبط `GDAL_LIBRARY_PATH` و`GEOS_LIBRARY_PATH` في `.env` (السطران موجودان معلَّقَين فيه) |

ثمّ:

```bash
python manage.py migrate
python manage.py seed_mobile_demo
```

**ثلاث نوافذ طرفيّة:**

```bash
# ١ — الخادم (REST + WebSocket)
daphne -b 0.0.0.0 -p 8000 config.asgi:application

# ٢ — العامل (رموز الدخول، الإشعارات، المهامّ)
celery -A config worker -l info          # ويندوز: أضف --pool=solo

# ٣ — المجدول (انتهاء العروض، كشف الغش، التقارير)
celery -A config beat -l info
```

> استعمل `daphne` لا `runserver`: الثاني لا يخدم المقابس الحيّة، فتبدو
> العروض والتتبّع معطّلة بلا سبب ظاهر.

---

## ٦. تشغيل التطبيقين

### أ) مرّة واحدة

```bash
cd mobile
flutter pub get                      # مساحة عمل واحدة: التطبيقان والحزم الأربع معًا
```

**ملفّ Firebase:** البناء لأندرويد يحتاج `google-services.json` في:

- `mobile/apps/customer/android/app/google-services.json`
- `mobile/apps/driver/android/app/google-services.json`

الملفّان سرّيّان وخارج المستودع. لهما مصدران:

- خذهما من صاحب المشروع عبر قناة خاصّة، لا في محادثة عامّة.
- أو أنشئ مشروع Firebase للتطوير باسمي الحزمتين `sy.soum.soum_customer`
  و`sy.soum.soum_driver`.

بلا إشعارات يعمل التطبيق كاملًا عبر المقبس، لكنّ **البناء** يحتاج
الملفّ.

### ب) التشغيل

عنوان الخادم يُمرَّر عند التشغيل ولا يُكتب في الشيفرة:

```bash
cd mobile/apps/customer
flutter run --dart-define=SOUM_API=http://10.0.2.2:8000/api/v1
```

```bash
cd mobile/apps/driver
flutter run --dart-define=SOUM_API=http://10.0.2.2:8000/api/v1
```

| أين يعمل التطبيق | قيمة `SOUM_API` |
|---|---|
| محاكي أندرويد | `http://10.0.2.2:8000/api/v1` (الافتراض — `localhost` داخل المحاكي هو المحاكي نفسه) |
| هاتف حقيقيّ على نفس الشبكة | `http://<عنوان-حاسوبك-في-الشبكة>:8000/api/v1` مثل `http://192.168.1.20:8000/api/v1` |
| نسخة الإصدار (release) | **يجب** أن يبدأ بـ`https://` — التطبيق يرفض غيره عند الإقلاع |

لتجربة رحلة كاملة شغّل التطبيقين معًا، على محاكيين أو محاكٍ وهاتف:

1. سجّل الدخول بحساب الزبون وحساب السائق.
2. في تطبيق السائق فعّل «تعمل الآن».
3. من الزبون اختر وجهةً واطلب.

الخطوات بالصور في «دليل رحلات سووم»: افتح `docs/flows/index.html` في المتصفّح.

**موقع المحاكي:** السائق والزبون يجب أن يكونا داخل منطقة خدمة. حسابات
العرض في جبلة، فاضبط موقع المحاكي قربها (`35.3617, 35.9275`، واللاذقية منطقةٌ ثانية) من
Extended Controls ← Location.

---

## ٧. الاختبارات

### الخادم

```bash
# داخل دوكر
docker compose -f compose.dev.yaml exec web python manage.py test --noinput --parallel 1

# أو محلّيًّا
cd backend && python manage.py test --noinput --parallel 1

# تطبيقٌ واحد فقط (أسرع)
python manage.py test trips matching --noinput --parallel 1
```

463 اختبارًا في قرابة 5 دقائق، وكلّها تنجح الآن. قاعدة الاختبار تُنشأ
وتُحذف وحدها، فيحتاج مستخدم القاعدة صلاحية `CREATEDB` (مستخدم `postgres`
في التطوير يملكها).

**اختبارات طرفيّة على خادم حيّ:**

```bash
python manage.py run_all_e2e
```

**محاكاة مدينة في الذروة مع غشّاشين**، تقيس كشف الغش وتكتب تقريرًا:

```bash
python manage.py simulate_city --days 2 --report sim.md
```

> المحاكاة تكتب في القاعدة ولا تُمسح بياناتها، لأنّ دفتر المدفوعات لا يقبل
> الحذف. شغّلها على قاعدة تطوير فقط. وهي ترفض العمل في الإنتاج.

### التطبيقان

كلّ حزمة تُختبر من مجلّدها:

```bash
cd mobile/packages/soum_core && flutter test
cd mobile/packages/soum_ui   && flutter test
cd mobile/packages/soum_maps && flutter test
cd mobile/apps/customer      && flutter test
cd mobile/apps/driver        && flutter test
```

والتحليل الساكن للمساحة كلّها من `mobile/`:

```bash
flutter analyze
```

### عقد الـAPI بين الخادم والتطبيقين

`mobile/packages/soum_core/test/contract/openapi.json` نسخةٌ من مخطّط
الخادم. اختبار العقد يقارنها بما تقرؤه نماذج `soum_core`، فحقلٌ يُحذف أو
تتغيّر تسميته يُكسر هنا قبل أن يُكسر عند الزبون.

بعد **أيّ** تغيير في serializers أو views أو urls:

```bash
cd backend
python scripts/regen_contract.py
cd ../mobile/packages/soum_core && flutter test test/contract_test.dart
```

السكربت يحفظ الملفّ بنهايات CRLF كما كان، فلا يظهر فرقٌ زائف.

---

## ٨. خريطة الشيفرة

### الخادم (`backend/`)

| التطبيق | مسؤوليّته |
|---|---|
| `config/` | الإعدادات، المسارات، ASGI، Celery وجدول مهامّه |
| `users/` | المستخدمون والأدوار، الدخول برمز الهاتف، التوكنات |
| `drivers/` · `vehicles/` | ملفّ السائق ووثائقه وتوثيقه، السيارات وأنواعها |
| `locations/` | مناطق الخدمة، وكلّ أرقام المنطقة (تسعير، مهل، تعويضات)، ونقطة `/config/` التي يقرؤها التطبيقان |
| `pricing/` · `maps/` | حساب السعر، والتوجيه عبر OSRM مع قاطع دارة وتقدير احتياطيّ |
| `rides/` | طلب الرحلة وطرقه الثلاث، وسعر الزبون المقترَح |
| `matching/` | العروض، الدعوات، المزاد، حدود الأسعار |
| `trips/` | دورة الرحلة: التوجّه، الوصول، البدء، الإنهاء، الإلغاء وأسبابه، الزبون الذي لم يحضر وتعويض السائق |
| `payments/` | الدفع، ودفتر قيود مزدوجة لا يقبل الحذف (`LedgerEntry`)، وأرصدة السائقين |
| `presence/` | السائقون المتّصلون ومواقعهم الحيّة (Redis)، الخريطة الحيّة |
| `realtime/` | المقابس (Channels): غرف الرحلة والسائق والسوق |
| `notifications/` | الإشعارات: FCM، رسائل نصّيّة احتياطيّة، تليغرام |
| `integrity/` | كشف الغش: مواقع مزيّفة، إلغاءات، رحلات خارج التطبيق، نقاط ومراجعة |
| `feedback/` | التقييمات والأوسمة والشكاوى |
| `growth/` | العمولات، العروض، الحوافز، التقارير |
| `catalog/` · `ads/` | الخدمات والميزات، الإعلانات |
| `ops/` | لوحة التشغيل وأدواتها وأوامر زرع بيانات العرض |
| `health/` | فحص الصحّة |
| `scripts/` | فحص الدخان، الأسطول الآليّ، توليد العقد |
| `docker/` | نقطة الدخول، nginx، النسخ الاحتياطيّ والاستعادة |

### التطبيقان (`mobile/`)

| الحزمة | مسؤوليّتها |
|---|---|
| `packages/soum_core` | النماذج، عميل الـAPI، المقبس، التخزين، المال (`Money` لا `double`). بلا واجهة |
| `packages/soum_ui` | السمة والخطّ، النصوص (ARB)، الإقلاع، العناصر المشتركة |
| `packages/soum_maps` | الخريطة، علامات السيارات وحركتها، مزوّد البلاطات من الخادم |
| `packages/soum_push` | إشعارات FCM، وتفشل بصمت على هاتف بلا خدمات Google |
| `apps/customer/lib/features/` | الرئيسية والخريطة، المزاد (سوم)، الدعوة، الرحلة، الإنهاء، السجلّ |
| `apps/driver/lib/features/` | الحضور (تعمل الآن)، الطلبات والعروض، تنفيذ الرحلة، الأرباح، التسجيل |

**مسار الإقلاع:**

1. التطبيق يطلب `/config/` لمنطقته.
2. يأخذ منه كلّ الأرقام: المهل، حدود الأسعار، رابط بلاطات الخريطة.
3. يستعيد الرحلة الجارية إن وُجدت.
4. يفتح المقبس.

---

## ٩. قواعد العمل

1. **لا أرقام تشغيليّة ثابتة في التطبيقين.** المهل والنسب والحدود تأتي من
   الخادم لكلّ منطقة، وتعديلها من لوحة الإدارة بلا تحديث للتطبيق.
2. **كلّ نصّ في الواجهة في ملفّات ARB:**
   - المصدر العربيّ `packages/soum_ui/lib/src/l10n/app_ar.arb`، ومعه
     `app_en.arb`.
   - بعد التعديل: `cd mobile/packages/soum_ui && flutter gen-l10n`،
     والملفّات المولَّدة تُرفع مع التغيير.
   - اختبارٌ يمنع أيّ نصّ عربيّ مكتوب مباشرةً في شيفرة الواجهة.
3. **المال:** `Decimal` في الخادم و`Money` في التطبيقين، ولا `float` ولا
   `double`.
4. **دفتر المدفوعات لا يُعدَّل ولا يُحذف منه.** التصحيح يكون بقيدٍ معاكس.
5. **التعليقات بالعربيّة وتشرح «لماذا».** أسماء المتغيّرات والدوالّ
   بالإنجليزيّة.
6. **كلّ إصلاح معه اختبار** يفشل قبل الإصلاح وينجح بعده.
7. **قبل الرفع:** اختبارات الخادم، و`flutter analyze`، واختبارات الحزم
   التي لمستها. وإن غيّرت الـAPI فأعد توليد العقد.
8. **الفروع:** فرعٌ لكلّ عمل، وطلب دمج (Pull Request) للمراجعة، ولا رفع
   مباشر على الفرع الرئيسيّ.

---

## ١٠. متغيّرات البيئة المهمّة

القائمة الكاملة للتطوير في `backend/.env.example` و`backend/.env.docker.example`،
وللإنتاج في `backend/.env.production.example`.

| المتغيّر | ماذا |
|---|---|
| `DEPLOYMENT_ENV` | `development` أو `production` (الإنتاج يفرض مفتاحًا قويًّا وHTTPS ومزوّد رسائل حقيقيًّا) |
| `SECRET_KEY` · `DEBUG` · `ALLOWED_HOSTS` | أساسيّات Django |
| `DB_*` · `REDIS_URL` · `PRESENCE_REDIS_URL` | القاعدة وRedis |
| `OTP_DELIVERY_BACKEND` | `console` في التطوير. في الإنتاج مزوّد رسائل مع `SMS_ENDPOINT` و`SMS_API_KEY` و`SMS_SENDER_ID` |
| `NOTIFICATION_BACKEND` | الطابعة في التطوير، و`notifications.backends.fcm.FCMBackend` في الإنتاج |
| `FCM_SERVICE_ACCOUNT_FILE` أو `FCM_SERVICE_ACCOUNT_JSON` | مفتاح خادم Firebase، مسار ملفّ أو محتواه (JSON أو Base64) |
| `MAPS_ROUTING_BASE_URL` | خادم OSRM. العامّ للتجربة فقط، وللإنتاج خادم خاصّ |
| `MAP_TILES_URL` · `MAP_TILES_DARK_URL` · `MAP_TILES_ATTRIBUTION` · `MAP_TILES_MAX_ZOOM` | مزوّد صور الخريطة للتطبيقين، ويتبدّل بلا تحديث للتطبيق |
| `TELEGRAM_BOT_TOKEN` · `TELEGRAM_WEBHOOK_SECRET` | قناة تليغرام (اختياريّة) |
| `ADMIN_URL` · `ADMIN_ALLOWED_IPS` | إخفاء لوحة الإدارة وتقييدها بعناوين |

---

## ١١. الأمان — لا تساهل فيه

- **لا يُرفع أبدًا:**
  - `.env` و`.env.docker` ومجلّد `secrets/`.
  - مفاتيح Firebase و`google-services.json`.
  - ملفّات التوقيع (`*.jks` و`key.properties`).
  - أيّ توكن.
  
  كلّها في `.gitignore`. وإن رُفع شيءٌ منها خطأً فالحلّ **تغيير المفتاح**،
  لأنّ حذفه من المستودع لا يمحوه من تاريخه.
- لا تلصق مفتاحًا في محادثة أو تذكرة أو لقطة شاشة.
- حسابات العرض (`seed_mobile_demo`) للتطوير فقط، والأمر يرفض العمل في
  الإنتاج.
- نسخة الإصدار موقَّعة حاليًّا بمفتاح التطوير. قبل النشر على المتجر
  يلزم مفتاح توقيع حقيقيّ يحفظه صاحب المشروع وحده.

---

## ١٢. النشر (باختصار)

| الملفّ | ماذا |
|---|---|
| `backend/compose.production.yaml` | الخادم والعامل والمجدول وnginx والنسخ الاحتياطيّ |
| `backend/.env.production.example` | القالب، ويُنسخ إلى `.env` على الخادم |
| `backend/docker/nginx.conf` | الوكيل العكسيّ وHTTPS |
| `backend/docker/backup.sh` · `restore.sh` | نسخ القاعدة واستعادتها |

قبل الإطلاق يجب تركيب:

- مزوّد رسائل الدخول.
- مفتاح FCM.
- خادم توجيه OSRM خاصّ.
- مزوّد صور خريطة مدفوع.
- اسم نطاق بشهادة HTTPS.

---

## ١٣. مشاكل شائعة

| العَرَض | السبب والحلّ |
|---|---|
| التطبيق لا يصل للخادم من المحاكي | استعمل `10.0.2.2` لا `localhost` |
| التطبيق لا يصل من هاتف حقيقيّ | استعمل عنوان حاسوبك في الشبكة، وتأكّد أنّ الجدار الناريّ يسمح بالمنفذ 8000 |
| `400 Bad Request` / `DisallowedHost` | `ALLOWED_HOSTS` لا يضمّ العنوان المطلوب. في التطوير `*` |
| `compose` يفشل بمسار `C:/secrets` على لينكس/ماك | اضبط `FCM_SECRETS_DIR=./secrets` (القسم ٤) |
| `File google-services.json is missing` | ضع ملفّ Firebase في `android/app/` (القسم ٦) |
| لا يصل رمز الدخول | لا رسائل في التطوير. الرمز على الشاشة وفي `logs -f celery` |
| العروض لا تظهر لحظيًّا | الخادم يعمل بـ`runserver` لا `daphne`، أو Redis متوقّف |
| الخريطة رماديّة بلا شوارع | لا إنترنت، أو مزوّد البلاطات حجب الطلبات. اضبط `MAP_TILES_URL` |
| «لا سيارات» على الخريطة | لا سائق متّصل في المنطقة. شغّل `sim_fleet.py` أو فعّل «تعمل الآن» |
| GDAL/GEOS not found (محلّيًّا) | ثبّت GDAL، وعلى ويندوز اضبط `GDAL_LIBRARY_PATH` |
| `too many clients` من PostgreSQL | اخفض `DB_POOL_MAX` أو ارفع `max_connections` |
| اختبار العقد يفشل بعد تغيير الـAPI | `python scripts/regen_contract.py` (القسم ٧) |
| كلّ أسطر الملفّ تظهر متغيّرة | نهايات الأسطر تحوّلت. `git config core.autocrlf false` وأعد الملفّ |

---

## ١٤. وثائق أخرى في `docs/`

| الملفّ | ماذا |
|---|---|
| `PRODUCT-DECISIONS.md` | لماذا صُمّم كلّ شيء كما هو |
| `GAP-ANALYSIS.md` | ما طُلب وما نُفّذ |
| `INTEGRITY.md` | نظام كشف الغش بالتفصيل |
| `SIMULATION-REPORT.md` | نتائج محاكاة المدينة |
| `AUDIT.md` | التدقيق الصريح: ما يعمل، وما لم يُختبر، وما ينقص قبل الإطلاق |
| `flows/index.html` | دليل رحلات سووم: خطوات الزبون والسائق وسيناريوهاتها بصور من التطبيق |
