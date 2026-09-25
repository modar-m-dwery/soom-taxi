# دليل اختبار تطبيق الموبايل عبر Swagger

هذا الدليل مخصص لبيئة التطوير فقط. افتح Swagger من:

`http://127.0.0.1:8000/api/docs/`

قاعدة العنوان لكل الطلبات هي: `http://127.0.0.1:8000/api/v1`

## 1. التحضير قبل الاختبار

شغّل الخدمات التالية في نوافذ طرفية منفصلة:

```powershell
python manage.py runserver
celery -A config worker -l info -P solo
celery -A config beat -l info
daphne -b 0.0.0.0 -p 8001 config.asgi:application
```

ثم أنشئ حسابات وبيانات الاختبار:

```powershell
python manage.py seed_mobile_demo
```

ينشئ الأمر ثلاثة حسابات ويطبع Tokens في الطرفية:

| الدور | الاستخدام |
| --- | --- |
| customer | طلب الرحلة، مشاهدة العروض، الاختيار، الإلغاء، التقييم، الشكاوى |
| driver | الظهور أونلاين، عروض السعر، الدعوات، ودورة الرحلة |
| admin | مراجعة السائقين ولوحة التشغيل |

لا تضع Token في Git أو في لقطات الشاشة. في Swagger اضغط **Authorize** وأدخل القيمة بصيغة:

```text
Token الصق_التوكن_هنا
```

## 2. اختبار OTP

### 2.1 إعداد مدة قصيرة للاختبار

القيمة الافتراضية هي `OTP_TTL_SECONDS=300`، أي خمس دقائق. لا توجد مدة ثابتة 20 ثانية في الكود. لاختبار الانتهاء بسرعة في التطوير، ضع في `.env`:

```dotenv
DEBUG=True
OTP_TTL_SECONDS=20
OTP_MAX_ATTEMPTS=5
```

ثم أعد تشغيل Django. لا تستخدم مدة 20 ثانية للإنتاج.

### 2.2 طلب الرمز

`POST /auth/request-otp/`

```json
{
  "phone": "+963991234567",
  "device_id": "android-swagger-demo-01"
}
```

النتيجة المتوقعة: `201`. في `DEBUG=True` ستحتوي الاستجابة على `development_code`. انسخه فورًا.

### 2.3 التحقق قبل الانتهاء

`POST /auth/verify-otp/`

```json
{
  "phone": "+963991234567",
  "device_id": "android-swagger-demo-01",
  "code": "123456"
}
```

استبدل `123456` بالرمز الظاهر. النتيجة `200` وتحتوي `token` و`user`.

### 2.4 حالات يجب تجربتها

- انتظر أكثر من 20 ثانية ثم أرسل نفس الرمز: `400 Invalid or expired OTP`.
- أرسل رمزًا خاطئًا خمس مرات: المحاولات تنتهي ويصبح الرد `429`.
- اطلب الرمز أكثر من الحد: حدود التطوير الافتراضية هي 3 لكل هاتف، و5 لكل جهاز، و10 لكل IP خلال 10 دقائق.
- أرسل رقمًا بلا `+` أو رمزًا غير رقمي: `400` مع تفاصيل الحقل.

في الإنتاج لا يجب أن يعود `development_code` أبدًا، ويجب أن يرسل مزود SMS الرمز.

## 3. المصادقة والجلسة

بعد وضع Token في Authorize اختبر:

`GET /auth/me/` ? يعيد بيانات المستخدم الحالي.

`POST /auth/logout/` ? يلغي Token الحالي. بعده يجب أن تفشل الطلبات المحمية بـ `401` حتى تسجل دخولًا من جديد.

## 4. سيناريو الرحلة الفردية الكامل

استخدم customer أولًا، ثم driver، ثم customer مجددًا. احفظ `ride_id` من كل استجابة.

### 4.1 العميل ينشئ طلبًا

`POST /rides/`

```json
{
  "pickup_lat": 35.36,
  "pickup_lng": 35.90,
  "destination_lat": 35.37,
  "destination_lng": 35.91,
  "mode": "fast",
  "passenger_count": 1,
  "requested_vehicle_type": "sedan",
  "trip_category": "city"
}
```

المتوقع: `201` وحالة `searching` مع مسافة/مدة/سعر تقديري وسياسة التسعير. احتفظ بالمعرف مثلًا `ride_id=42`.

جرّب أيضًا: `passenger_count=0` أو `mode` غير موجود ? `400`.

### 4.2 السائق يصبح متاحًا

ضع Token السائق ثم:

`POST /drivers/me/go-online/`

بعدها يمكن اختبار الواجهة الحية عبر WebSocket أو متابعة REST. إذا لم يظهر السائق في المرشحين، تأكد من وجود مركبة فعّالة ومن أن موقعه داخل منطقة جبلة.

### 4.3 السائق يرى المرشحين ويرسل عرضًا

`GET /driver/rides/candidates/`

ابحث عن `ride_id`، ثم:

`POST /driver/rides/42/offers/`

```json
{
  "gross_fare": "25000.00",
  "eta_minutes": 3
}
```

المتوقع: عرض `pending` بمهلة محدودة؛ المهلة الافتراضية للعروض هي 30 ثانية (`RIDE_OFFER_TTL_SECONDS=30`). انتظر أكثر من ذلك ثم حاول الاختيار لاختبار `expired`.

### 4.4 العميل يشاهد العرض ويختاره

ضع Token العميل:

`GET /customer/rides/42/offers/`

ثم:

`POST /customer/rides/42/offers/<offer_id>/select/`

المتوقع: تتحول الرحلة إلى `driver_selected` وينشأ Trip تلقائيًا. محاولة اختيار عرض آخر بعد ذلك يجب أن ترفض.

### 4.5 السائق يصل ويبدأ وينهي

ضع Token السائق. يجب أن يكون موقع السائق قريبًا من نقطة الالتقاط؛ نصف قطر الوصول الافتراضي 200 متر.

```text
POST /driver/rides/42/arrived/
POST /driver/rides/42/start/
POST /driver/rides/42/complete/
```

- محاولة `start` قبل `arrived` ترفض.
- محاولة `complete` قبل `start` ترفض.
- عند `complete` ضمن 300 متر من الوجهة، يكون `dropoff_verified=true` غالبًا.
- إذا انتهت بعيدًا، لا تُحجب الرحلة، لكن `needs_review=true` و`review_reason` يفسران السبب.
- بعد الإنهاء يعود السائق متاحًا على الخريطة.

### 4.6 العميل يقرأ النتيجة

```text
GET /trips/42/
GET /trips/42/path/
```

تحقق من `status=completed` و`final_fare` و`distance_m` و`completion_record`.

### 4.7 إلغاء صحيح

قبل `start` يمكن للعميل استعمال:

`POST /customer/rides/42/cancel-trip/`

```json
{ "reason": "تغيرت الخطة" }
```

أو إذا كانت ما زالت في البحث:

`POST /rides/42/cancel/`

بعد بدء الرحلة لا يعد الإلغاء العادي مسموحًا؛ يجب فتح شكوى عند وجود مشكلة.

## 5. الخريطة الحية والدعوة المباشرة

أنشئ طلبًا جديدًا واجعل السائق Online.

1. العميل: `GET /customer/rides/<ride_id>/nearby-vehicles/`.
2. اختر `driver_id` الظاهر.
3. العميل: `POST /customer/rides/<ride_id>/invitations/`.

```json
{ "driver_id": 9, "ttl_seconds": 20 }
```

استبدل `9` بالمعرف الذي أعاده seed أو nearby endpoint. المهل المسموح بها للمنطقة هي عادة `[20, 40, 60]`؛ قيمة غير موجودة ترفض. لا يسمح افتراضيًا بأكثر من دعوة معلقة واحدة لنفس الطلب.

4. السائق: `GET /driver/invitations/`.
5. السائق: `POST /driver/invitations/<invitation_id>/accept/` أو `reject/`.

```json
{ "reason": "بعيد عن موقعي" }
```

اختبر الانتهاء: لا تقبل الدعوة بعد انتهاء `ttl_seconds`. اختبر التهدئة: بعد رفض السائق لا يستطيع العميل دعوته مباشرة لفترة الرفض الافتراضية 60 ثانية.

## 6. الرحلة المشتركة والمجدولة

### رحلة مشتركة فورية

أنشئ طلبًا بـ:

```json
{
  "pickup_lat": 35.36,
  "pickup_lng": 35.90,
  "destination_lat": 35.40,
  "destination_lng": 35.95,
  "mode": "shared",
  "passenger_count": 1,
  "trip_category": "city"
}
```

ثم استخدم:

```text
GET  /customer/rides/<ride_id>/shared-offers/
POST /customer/shared-offers/<join_request_id>/accept/
```

تحقق أن السيارة المشتركة لا تظهر لطلب فردي، وأنها تظهر فقط لطلب مشترك متوافق وله مقاعد شاغرة. لا يجب أن تظهر إحداثيات وجهة الركاب الآخرين بدقة.

### رحلة منشورة/بين المدن

السائق ينشر:

`POST /driver/trips/publish/`

```json
{
  "vehicle_id": 1,
  "trip_category": "intercity",
  "scheduled_at": "2026-09-01T08:00:00Z",
  "capacity": 4,
  "pickup_lat": 35.36,
  "pickup_lng": 35.90,
  "destination_lat": 35.53,
  "destination_lng": 35.78,
  "origin_city": "Jableh",
  "destination_city": "Lattakia",
  "price_per_seat": "15000.00",
  "features": ["ac", "no_smoking"]
}
```

ثم العميل:

```text
GET  /trips/
POST /trips/<trip_id>/book/
```

```json
{ "passenger_count": 1 }
```

اختبر السعة: لا يجوز الحجز فوق `remaining_capacity`.

## 7. التقييمات والشكاوى

بعد إتمام رحلة:

```text
GET  /feedback/trips/<ride_id>/rating-state/
POST /feedback/trips/<ride_id>/rate/
GET  /feedback/me/rating-summary/
POST /feedback/complaints/
GET  /feedback/complaints/
```

مثال تقييم عالٍ:

```json
{ "score": 5, "tags": ["clean_car"], "comment": "رحلة ممتازة" }
```

مثال تقييم منخفض؛ يجب أن يحتوي سببًا (وسم أو تعليق):

```json
{ "score": 1, "tags": ["unsafe_driving"], "comment": "قيادة غير آمنة" }
```

مثال شكوى:

```json
{
  "ride_id": 42,
  "category": "safety",
  "description": "وصف واضح للمشكلة لا يقل عن عشرة أحرف"
}
```

حالات الاختبار المهمة:

- لا يمكن تقييم رحلة غير مكتملة.
- لا يمكن التقييم مرتين للرحلة نفسها.
- الطرف الآخر لا يرى تقييمك قبل أن يقيّم أو تنتهي مهلة التقييم (14 يومًا افتراضيًا).
- شكوى safety تصبح حرجة تلقائيًا.
- لا تفتح شكوى مكررة من الفئة نفسها ما دامت السابقة مفتوحة.

## 8. الإشعارات

سجل جهازًا بعد وضع Token المستخدم:

`POST /push/devices/register/`

```json
{ "token": "demo-fcm-token-unique-001", "platform": "android" }
```

ثم:

```text
GET  /me/notifications/
POST /push/devices/unregister/
```

في التطوير الافتراضي قد تكون الإشعارات Console؛ لذلك تحقق من صفوف الإشعارات وlogs. لا تستخدم token حقيقي لأحد المستخدمين الآخرين في الاختبار.

## 9. اختبار الخرائط

`GET /maps/route/?pickup_lat=35.36&pickup_lng=35.90&destination_lat=35.37&destination_lng=35.91`

المتوقع: `distance_km` و`duration_minutes` و`geometry`. إذا كان مزود التوجيه غير متاح يكون الرد `502`؛ هذا متوقع في حال انقطاع الإنترنت أو تعطيل المزود.

## 10. لوحة التشغيل (Admin فقط)

باستخدام Token admin:

```text
GET  /ops/overview/
GET  /ops/attention/
GET  /ops/drivers/live/
GET  /ops/actions/
POST /ops/drivers/<driver_id>/release/
POST /ops/drivers/<driver_id>/status/
POST /ops/rides/<ride_id>/force-complete/
POST /ops/rides/<ride_id>/force-cancel/
```

كل تدخل إداري يحتاج `reason` مكتوبًا من 10 أحرف على الأقل. اختبر أن الطلب بلا سبب يرفض، وأن السجل يظهر بعدها في `/ops/actions/`.

## 11. WebSocket

Swagger لا يختبر WebSocket مباشرة. استخدم Daphne على المنفذ 8001 وعميل WebSocket منفصل. المسارات الفعلية ظاهرة في `realtime/routing.py`. اختبر على الأقل:

- `connection.established` عند الاتصال.
- `ride.snapshot` عند دخول غرفة رحلة.
- `offer.created` و`offer.accepted` و`ride.cancelled`.
- `driver.location` أثناء الرحلة.
- `trip.completed` عند الإنهاء.
- `vehicle.entered_area` و`vehicle.left_area` في الخريطة الحية.

في الإنتاج استخدم `wss://` وليس `ws://`.

## 12. التنظيف وإعادة التجربة

اعرض ما سيحذف أولًا:

```powershell
python manage.py reset_operational_data
```

ثم نفّذ فقط في قاعدة تطوير/اختبار:

```powershell
python manage.py reset_operational_data --yes
python manage.py seed_mobile_demo
```

الأمر ينظف الرحلات والعروض والدعوات والتقييمات والشكاوى والإشعارات وRedis، لكنه يبقي الحسابات والمركبات والمناطق ووسوم التقييم. لا تستخدم `wipe_database.py` في اختبار الموبايل الاعتيادي.