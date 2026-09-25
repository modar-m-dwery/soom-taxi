# تشغيل سووم تكسي على دوكر

## بيئة التطوير — أمر واحد

```bash
docker compose -f compose.dev.yaml up -d --build
```

هذا يرفع خمس حاويات:

| الحاوية | الدور | المنفذ |
|---|---|---|
| `taxi-postgres` | PostgreSQL 16 + PostGIS 3.5 | `5433` على المضيف |
| `taxi-redis` | Redis 7 (cache + channels + celery + presence) | `6379` |
| `taxi-web` | Daphne / ASGI — REST + WebSocket | `8000` |
| `taxi-celery` | Celery worker | — |
| `taxi-beat` | Celery beat (13 مهمة مجدولة) | — |

عند أوّل إقلاع تُفعَّل إضافة PostGIS، تُشغَّل الترحيلات، وتُزرع حسابات
العرض تلقائيًا (`SEED_DEMO=1` افتراضيًا).

### تحقّق من أن كلّ شيء يعمل

```bash
python scripts/smoke_test.py
```

يفحص أربع طبقات ويتوقّف عند أوّل انهيار: الصحّة → Swagger (بما فيه
ملفّاته الساكنة) → دورة OTP كاملة → دورة رحلة من الطلب إلى التقييم →
ترقية WebSocket.

### الروابط

| | |
|---|---|
| Swagger UI | http://localhost:8000/api/docs/ |
| Redoc | http://localhost:8000/api/redoc/ |
| مخطّط OpenAPI | http://localhost:8000/api/schema/ |
| الصحّة | http://localhost:8000/api/v1/health/ |
| لوحة الإدارة | http://localhost:8000/admin/ |
| WebSocket | ws://localhost:8000/ws/rides/{ride_id}/ |

### الحصول على توكن للاختبار في Swagger

```bash
docker compose -f compose.dev.yaml exec web python manage.py seed_mobile_demo
```

يطبع توكنات ثلاثة حسابات (زبون، سائق، مدير) بصيغة JSON. في Swagger
اضغط **Authorize** وأدخل `Token <القيمة>`.

أو من دورة OTP الطبيعية — في وضع `DEBUG=True` يعود الرمز في الاستجابة:

```bash
curl -X POST http://localhost:8000/api/v1/auth/request-otp/ \
  -H "Content-Type: application/json" \
  -d '{"phone":"+963991234567","device_id":"dev-1"}'
# → {"development_code": "482915", ...}
```

### أوامر يومية

```bash
# السجلات
docker compose -f compose.dev.yaml logs -f web
docker compose -f compose.dev.yaml logs -f celery beat

# صدفة داخل التطبيق
docker compose -f compose.dev.yaml exec web python manage.py shell

# اختبارات المشروع
docker compose -f compose.dev.yaml exec web python manage.py test

# اختبارات E2E المكتوبة في المشروع
docker compose -f compose.dev.yaml exec web python manage.py run_all_e2e

# قاعدة البيانات
docker compose -f compose.dev.yaml exec postgres \
  psql -U postgres -d taxi_backend -c "SELECT PostGIS_Version();"

# تنظيف البيانات التشغيلية مع إبقاء الحسابات
docker compose -f compose.dev.yaml exec web \
  python manage.py reset_operational_data --yes

# إيقاف / حذف كلّ شيء بما فيه البيانات
docker compose -f compose.dev.yaml down
docker compose -f compose.dev.yaml down -v
```

---

## ما تغيّر عن الإعداد السابق ولماذا

### 1. Swagger كان سيظهر صفحة بيضاء تحت دوكر

`runserver` يلفّ التطبيق تلقائيًا بـ`ASGIStaticFilesHandler`، أمّا
**daphne — وهو أمر التشغيل في `Dockerfile` — فلا يخدم `/static/`
إطلاقًا**. النتيجة: `/api/docs/` تعيد HTML سليمًا بينما كلّ ملفّات
Swagger UI القادمة من `drf-spectacular-sidecar` تعيد 404.

الإصلاح في `config/asgi.py` + مفتاح `SERVE_STATIC_FILES` في الإعدادات
(افتراضه `DEBUG`). في الإنتاج يخدمها Nginx فيُضبَط على `False`.

### 2. مسارات ويندوز في `.env` كانت ستُسقط الحاوية

```
GDAL_LIBRARY_PATH=C:\Users\ML\...\gdal313.dll
GEOS_LIBRARY_PATH=C:\Users\ML\...\geos_c.dll
FCM_SERVICE_ACCOUNT_FILE=C:\secrets\...json
```

`settings.py` يقرأ `.env` أيضًا داخل الحاوية، فلو تُركت هذه المفاتيح
غائبة من ملفّ دوكر لتسرّبت قيم ويندوز إلى لينكس. `.env.docker` يضبطها
فارغة صراحةً، فيبحث GeoDjango عن المكتبات بنفسه.

### 3. لا `.dockerignore` — والأسرار كانت تدخل الصورة

`COPY . .` كان ينسخ `.env` (وفيه `SECRET_KEY`)، و`logs/`، و`media/`،
و`celerybeat-schedule.*` المبنيّ على ويندوز، و`__pycache__` داخل الصورة.

### 4. `depends_on` وحده لا يعني «جاهز»

يعني «بدأت الحاوية». التطبيق كان يقلع قبل أن يقبل PostgreSQL أوّل
اتصال. الآن: `healthcheck` على postgres وredis + `condition:
service_healthy` + انتظار فعلي في `entrypoint.sh`.

### 5. لا خطوة ترحيل ولا تفعيل PostGIS

قاعدة فارغة عند أوّل إقلاع. `entrypoint.sh` ينفّذ
`CREATE EXTENSION IF NOT EXISTS postgis` ثم `migrate` — من خدمة `web`
وحدها (`RUN_MIGRATIONS=1`)، لأنّ تشغيله من ثلاث حاويات معًا يفتح سباقًا
على جدول `django_migrations`.

### 6. `compose.production.yaml` لم يكن يعرض منفذًا

لا `ports` ولا Nginx: خدمة `web` غير قابلة للوصول من خارج شبكة دوكر.
وكان يقرأ `.env` أي ملفّ التطوير بـ`DEBUG=True`. أُضيف Nginx (مع تمرير
`Upgrade` للـWebSocket — بدونه يفشل كلّ `/ws/` بصمت)، وكلمة مرور
لريديس، وحدود ذاكرة، وتدوير سجلات، و`.env.production` منفصل.

---

## الإنتاج

```bash
cp .env.production.example .env.production
# املأ SECRET_KEY (٥٠ محرفًا فأكثر) وDB_PASSWORD وREDIS_PASSWORD
# وALLOWED_HOSTS وOTP_DELIVERY_BACKEND الحقيقي

docker compose -f compose.production.yaml --env-file .env.production up -d --build
```

`settings.py` يرفض الإقلاع في الإنتاج إن كان `DEBUG=True` أو
`SECRET_KEY` قصيرًا أو `OTP_DELIVERY_BACKEND` هو الطابعة — وهذا سلوك
مقصود وجيّد.

قبل الإطلاق تبقى ثلاثة أمور غير مبنية بعد: نسخ احتياطي مجدول
(`pg_dump` + اختبار استعادة)، تخزين كائنات لوثائق السائقين بدل القرص
المحلّي، وشهادة TLS في `docker/certs/`.

---

## استكشاف الأعطال

| العَرَض | السبب الأرجح |
|---|---|
| Swagger صفحة بيضاء | `SERVE_STATIC_FILES=False` مع daphne بلا Nginx |
| `django.db.utils.OperationalError` | postgres لم يجهز — راجع `logs postgres` |
| `Could not find the GDAL library` | `GDAL_LIBRARY_PATH` غير فارغ داخل الحاوية |
| `permission denied: /app/logs` | استُبدل الحجم المُسمّى بـbind mount |
| beat يعيد التشغيل باستمرار | `/app/run` غير قابل للكتابة |
| `/ws/` يفشل خلف Nginx | نقص `proxy_set_header Upgrade/Connection` |
| 429 على `request-otp` | حدّ 3 طلبات/10 دقائق لكلّ رقم — غيّر `device_id` |
