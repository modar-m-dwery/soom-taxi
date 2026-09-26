# سووم تكسي

منصّة تكسي بثلاث طرق طلب: **سوم** (عروض أسعار من السائقين أو سعرٌ يعرضه
الزبون)، و**الأقرب**، و**اختر سيارتك**.

| الجزء | المسار |
|---|---|
| الخادم (Django · Channels · Celery · PostGIS · Redis) | [`backend/`](backend/) |
| تطبيق الزبون (Flutter) | [`mobile/apps/customer/`](mobile/apps/customer/) |
| تطبيق السائق (Flutter) | [`mobile/apps/driver/`](mobile/apps/driver/) |
| الحزم المشتركة | [`mobile/packages/`](mobile/packages/) |

## البدء

**اقرأ [دليل المطوّرين](docs/DEVELOPERS.md)** لكلّ ما يلزم: التنزيل، تشغيل
الخادم، تشغيل التطبيقين، الاختبارات، وقواعد العمل.

وباختصار شديد:

```bash
cd backend
cp .env.docker.example .env.docker
mkdir -p secrets && export FCM_SECRETS_DIR=./secrets
docker compose -f compose.dev.yaml up -d --build
# ← http://localhost:8000/api/docs/

cd ../mobile && flutter pub get
cd apps/customer && flutter run --dart-define=SOUM_API=http://10.0.2.2:8000/api/v1
```

## الوثائق

| الملفّ | ماذا |
|---|---|
| [`docs/DEVELOPERS.md`](docs/DEVELOPERS.md) | دليل المطوّرين |
| [`docs/AUDIT.md`](docs/AUDIT.md) | التدقيق الصريح وما ينقص قبل الإطلاق |
| [`docs/flows/index.html`](docs/flows/index.html) | خطوات الزبون والسائق بالصور (افتحه في المتصفّح) |
| [`docs/PRODUCT-DECISIONS.md`](docs/PRODUCT-DECISIONS.md) | قرارات المنتج وأسبابها |
| [`docs/GAP-ANALYSIS.md`](docs/GAP-ANALYSIS.md) | المطلوب مقابل المنفَّذ |
| [`docs/INTEGRITY.md`](docs/INTEGRITY.md) | نظام كشف الغش |
| [`docs/SIMULATION-REPORT.md`](docs/SIMULATION-REPORT.md) | تقرير محاكاة المدينة |
