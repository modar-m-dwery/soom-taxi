# كيف تطبّق هذه الحزمة

كلّ ملفّ هنا مُختبَر فعليًا: البيئة أُقلعت، وSwagger فُتح، ومرّت
‏**26/26** فحصًا دخانيًا، و**106/106** اختبارًا في مجموعة Django،
و**243/243** فحصًا في تسع مجموعات E2E.

## النسخ

```
Dockerfile                → جذر المشروع (يستبدل القديم)
.dockerignore             → جذر المشروع (جديد)
.env.docker               → جذر المشروع (جديد)
compose.dev.yaml          → جذر المشروع (جديد)
compose.production.yaml   → جذر المشروع (يستبدل القديم)
requirements.txt          → جذر المشروع (يستبدل القديم)
DOCKER_QUICKSTART.md      → جذر المشروع (جديد)

docker/entrypoint.sh      → docker/entrypoint.sh          (جديد)
docker/nginx.conf         → docker/nginx.conf             (جديد)
docker/extra-ca/README.md → docker/extra-ca/README.md     (جديد)

config/asgi.py            → config/asgi.py                (يستبدل)
config/settings.py        → config/settings.py            (يستبدل)

scripts/smoke_test.py     → scripts/smoke_test.py         (جديد)

ops_cmd/seed_mobile_demo.py → ops/management/commands/seed_mobile_demo.py
ops_cmd/run_all_e2e.py      → ops/management/commands/run_all_e2e.py

tests_fix/test_api_flow.py               → matching/tests/test_api_flow.py
tests_fix/test_invitation_e2e.py         → matching/management/commands/
tests_fix/test_trip_lifecycle_e2e.py     → trips/management/commands/
tests_fix/test_ride_room_e2e.py          → realtime/management/commands/
tests_fix/test_driver_room_e2e.py        → realtime/management/commands/
tests_fix/test_marketplace_e2e.py        → realtime/management/commands/
tests_fix/test_presence_consistency_e2e.py → realtime/management/commands/
```

## احذف ملفًّا واحدًا

```bash
rm trips/tests.py
```

ثلاثة أسطر فارغة من قالب جانغو، لكن وجودها بجانب مجلّد `trips/tests/`
يجعل اكتشاف الاختبارات ينهار قبل أن يبدأ — فلا تعمل مجموعة الاختبارات
كلّها، لا في trips وحدها.

## أضف ملفًّا واحدًا

```bash
touch notifications/management/__init__.py
touch notifications/management/commands/__init__.py
```

التطبيق الوحيد الذي تنقصه، وبقيّة التطبيقات التسعة تحويها.

## ثمّ

```bash
docker compose -f compose.dev.yaml up -d --build
python scripts/smoke_test.py
```

## ما لم أُصلحه — قرارٌ لك لا خطأ برمجي

`MAPS_ROUTING_ENABLED` و`MAPS_ROUTING_REQUIRED` معرَّفان في
`settings.py` ولا يقرأهما أحد. عمليًا: `POST /rides/` يستدعي
`RoutingService.route()` بلا شرط، وإن كان مزوّد التوجيه غير متاح يرمي
`RideRequestValidationError` — أي أنّ **انقطاع OSRM يوقف حجز الرحلات
كلّه**. والمسافة الهوائية (Haversine) محسوبة أصلًا في نفس الطلب
وصالحة كبديل. القرار — هل يسقط الحجز أم يتراجع إلى تقدير أضعف — قرار
منتَج لا برمجة، ولذلك تركته لك.
