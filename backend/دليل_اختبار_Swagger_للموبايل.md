# Ïáíá ÇÎÊÈÇÑ ÊØÈíŞ ÇáãæÈÇíá ÚÈÑ Swagger

åĞÇ ÇáÏáíá ãÎÕÕ áÈíÆÉ ÇáÊØæíÑ İŞØ. ÇİÊÍ Swagger ãä:

`http://127.0.0.1:8000/api/docs/`

ŞÇÚÏÉ ÇáÚäæÇä áßá ÇáØáÈÇÊ åí: `http://127.0.0.1:8000/api/v1`

## 1. ÇáÊÍÖíÑ ŞÈá ÇáÇÎÊÈÇÑ

ÔÛøá ÇáÎÏãÇÊ ÇáÊÇáíÉ İí äæÇİĞ ØÑİíÉ ãäİÕáÉ:

```powershell
python manage.py runserver
celery -A config worker -l info -P solo
celery -A config beat -l info
daphne -b 0.0.0.0 -p 8001 config.asgi:application
```

Ëã ÃäÔÆ ÍÓÇÈÇÊ æÈíÇäÇÊ ÇáÇÎÊÈÇÑ:

```powershell
python manage.py seed_mobile_demo
```

íäÔÆ ÇáÃãÑ ËáÇËÉ ÍÓÇÈÇÊ æíØÈÚ Tokens İí ÇáØÑİíÉ:

| ÇáÏæÑ | ÇáÇÓÊÎÏÇã |
| --- | --- |
| customer | ØáÈ ÇáÑÍáÉ¡ ãÔÇåÏÉ ÇáÚÑæÖ¡ ÇáÇÎÊíÇÑ¡ ÇáÅáÛÇÁ¡ ÇáÊŞííã¡ ÇáÔßÇæì |
| driver | ÇáÙåæÑ ÃæäáÇíä¡ ÚÑæÖ ÇáÓÚÑ¡ ÇáÏÚæÇÊ¡ æÏæÑÉ ÇáÑÍáÉ |
| admin | ãÑÇÌÚÉ ÇáÓÇÆŞíä æáæÍÉ ÇáÊÔÛíá |

áÇ ÊÖÚ Token İí Git Ãæ İí áŞØÇÊ ÇáÔÇÔÉ. İí Swagger ÇÖÛØ **Authorize** æÃÏÎá ÇáŞíãÉ ÈÕíÛÉ:

```text
Token ÇáÕŞ_ÇáÊæßä_åäÇ
```

## 2. ÇÎÊÈÇÑ OTP

### 2.1 ÅÚÏÇÏ ãÏÉ ŞÕíÑÉ ááÇÎÊÈÇÑ

ÇáŞíãÉ ÇáÇİÊÑÇÖíÉ åí `OTP_TTL_SECONDS=300`¡ Ãí ÎãÓ ÏŞÇÆŞ. áÇ ÊæÌÏ ãÏÉ ËÇÈÊÉ 20 ËÇäíÉ İí ÇáßæÏ. áÇÎÊÈÇÑ ÇáÇäÊåÇÁ ÈÓÑÚÉ İí ÇáÊØæíÑ¡ ÖÚ İí `.env`:

```dotenv
DEBUG=True
OTP_TTL_SECONDS=20
OTP_MAX_ATTEMPTS=5
```

Ëã ÃÚÏ ÊÔÛíá Django. áÇ ÊÓÊÎÏã ãÏÉ 20 ËÇäíÉ ááÅäÊÇÌ.

### 2.2 ØáÈ ÇáÑãÒ

`POST /auth/request-otp/`

```json
{
  "phone": "+963991234567",
  "device_id": "android-swagger-demo-01"
}
```

ÇáäÊíÌÉ ÇáãÊæŞÚÉ: `201`. İí `DEBUG=True` ÓÊÍÊæí ÇáÇÓÊÌÇÈÉ Úáì `development_code`. ÇäÓÎå İæÑğÇ.

### 2.3 ÇáÊÍŞŞ ŞÈá ÇáÇäÊåÇÁ

`POST /auth/verify-otp/`

```json
{
  "phone": "+963991234567",
  "device_id": "android-swagger-demo-01",
  "code": "123456"
}
```

ÇÓÊÈÏá `123456` ÈÇáÑãÒ ÇáÙÇåÑ. ÇáäÊíÌÉ `200` æÊÍÊæí `token` æ`user`.

### 2.4 ÍÇáÇÊ íÌÈ ÊÌÑÈÊåÇ

- ÇäÊÙÑ ÃßËÑ ãä 20 ËÇäíÉ Ëã ÃÑÓá äİÓ ÇáÑãÒ: `400 Invalid or expired OTP`.
- ÃÑÓá ÑãÒğÇ ÎÇØÆğÇ ÎãÓ ãÑÇÊ: ÇáãÍÇæáÇÊ ÊäÊåí æíÕÈÍ ÇáÑÏ `429`.
- ÇØáÈ ÇáÑãÒ ÃßËÑ ãä ÇáÍÏ: ÍÏæÏ ÇáÊØæíÑ ÇáÇİÊÑÇÖíÉ åí 3 áßá åÇÊİ¡ æ5 áßá ÌåÇÒ¡ æ10 áßá IP ÎáÇá 10 ÏŞÇÆŞ.
- ÃÑÓá ÑŞãğÇ ÈáÇ `+` Ãæ ÑãÒğÇ ÛíÑ ÑŞãí: `400` ãÚ ÊİÇÕíá ÇáÍŞá.

İí ÇáÅäÊÇÌ áÇ íÌÈ Ãä íÚæÏ `development_code` ÃÈÏğÇ¡ æíÌÈ Ãä íÑÓá ãÒæÏ SMS ÇáÑãÒ.

## 3. ÇáãÕÇÏŞÉ æÇáÌáÓÉ

ÈÚÏ æÖÚ Token İí Authorize ÇÎÊÈÑ:

`GET /auth/me/` ? íÚíÏ ÈíÇäÇÊ ÇáãÓÊÎÏã ÇáÍÇáí.

`POST /auth/logout/` ? íáÛí Token ÇáÍÇáí. ÈÚÏå íÌÈ Ãä ÊİÔá ÇáØáÈÇÊ ÇáãÍãíÉ ÈÜ `401` ÍÊì ÊÓÌá ÏÎæáğÇ ãä ÌÏíÏ.

## 4. ÓíäÇÑíæ ÇáÑÍáÉ ÇáİÑÏíÉ ÇáßÇãá

ÇÓÊÎÏã customer ÃæáğÇ¡ Ëã driver¡ Ëã customer ãÌÏÏğÇ. ÇÍİÙ `ride_id` ãä ßá ÇÓÊÌÇÈÉ.

### 4.1 ÇáÚãíá íäÔÆ ØáÈğÇ

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

ÇáãÊæŞÚ: `201` æÍÇáÉ `searching` ãÚ ãÓÇİÉ/ãÏÉ/ÓÚÑ ÊŞÏíÑí æÓíÇÓÉ ÇáÊÓÚíÑ. ÇÍÊİÙ ÈÇáãÚÑİ ãËáğÇ `ride_id=42`.

ÌÑøÈ ÃíÖğÇ: `passenger_count=0` Ãæ `mode` ÛíÑ ãæÌæÏ ? `400`.

### 4.2 ÇáÓÇÆŞ íÕÈÍ ãÊÇÍğÇ

ÖÚ Token ÇáÓÇÆŞ Ëã:

`POST /drivers/me/go-online/`

ÈÚÏåÇ íãßä ÇÎÊÈÇÑ ÇáæÇÌåÉ ÇáÍíÉ ÚÈÑ WebSocket Ãæ ãÊÇÈÚÉ REST. ÅĞÇ áã íÙåÑ ÇáÓÇÆŞ İí ÇáãÑÔÍíä¡ ÊÃßÏ ãä æÌæÏ ãÑßÈÉ İÚøÇáÉ æãä Ãä ãæŞÚå ÏÇÎá ãäØŞÉ ÌÈáÉ.

### 4.3 ÇáÓÇÆŞ íÑì ÇáãÑÔÍíä æíÑÓá ÚÑÖğÇ

`GET /driver/rides/candidates/`

ÇÈÍË Úä `ride_id`¡ Ëã:

`POST /driver/rides/42/offers/`

```json
{
  "gross_fare": "25000.00",
  "eta_minutes": 3
}
```

ÇáãÊæŞÚ: ÚÑÖ `pending` ÈãåáÉ ãÍÏæÏÉº ÇáãåáÉ ÇáÇİÊÑÇÖíÉ ááÚÑæÖ åí 30 ËÇäíÉ (`RIDE_OFFER_TTL_SECONDS=30`). ÇäÊÙÑ ÃßËÑ ãä Ğáß Ëã ÍÇæá ÇáÇÎÊíÇÑ áÇÎÊÈÇÑ `expired`.

### 4.4 ÇáÚãíá íÔÇåÏ ÇáÚÑÖ æíÎÊÇÑå

ÖÚ Token ÇáÚãíá:

`GET /customer/rides/42/offers/`

Ëã:

`POST /customer/rides/42/offers/<offer_id>/select/`

ÇáãÊæŞÚ: ÊÊÍæá ÇáÑÍáÉ Åáì `driver_selected` æíäÔÃ Trip ÊáŞÇÆíğÇ. ãÍÇæáÉ ÇÎÊíÇÑ ÚÑÖ ÂÎÑ ÈÚÏ Ğáß íÌÈ Ãä ÊÑİÖ.

### 4.5 ÇáÓÇÆŞ íÕá æíÈÏÃ æíäåí

ÖÚ Token ÇáÓÇÆŞ. íÌÈ Ãä íßæä ãæŞÚ ÇáÓÇÆŞ ŞÑíÈğÇ ãä äŞØÉ ÇáÇáÊŞÇØº äÕİ ŞØÑ ÇáæÕæá ÇáÇİÊÑÇÖí 200 ãÊÑ.

```text
POST /driver/rides/42/arrived/
POST /driver/rides/42/start/
POST /driver/rides/42/complete/
```

- ãÍÇæáÉ `start` ŞÈá `arrived` ÊÑİÖ.
- ãÍÇæáÉ `complete` ŞÈá `start` ÊÑİÖ.
- ÚäÏ `complete` Öãä 300 ãÊÑ ãä ÇáæÌåÉ¡ íßæä `dropoff_verified=true` ÛÇáÈğÇ.
- ÅĞÇ ÇäÊåÊ ÈÚíÏğÇ¡ áÇ ÊõÍÌÈ ÇáÑÍáÉ¡ áßä `needs_review=true` æ`review_reason` íİÓÑÇä ÇáÓÈÈ.
- ÈÚÏ ÇáÅäåÇÁ íÚæÏ ÇáÓÇÆŞ ãÊÇÍğÇ Úáì ÇáÎÑíØÉ.

### 4.6 ÇáÚãíá íŞÑÃ ÇáäÊíÌÉ

```text
GET /trips/42/
GET /trips/42/path/
```

ÊÍŞŞ ãä `status=completed` æ`final_fare` æ`distance_m` æ`completion_record`.

### 4.7 ÅáÛÇÁ ÕÍíÍ

ŞÈá `start` íãßä ááÚãíá ÇÓÊÚãÇá:

`POST /customer/rides/42/cancel-trip/`

```json
{ "reason": "ÊÛíÑÊ ÇáÎØÉ" }
```

Ãæ ÅĞÇ ßÇäÊ ãÇ ÒÇáÊ İí ÇáÈÍË:

`POST /rides/42/cancel/`

ÈÚÏ ÈÏÁ ÇáÑÍáÉ áÇ íÚÏ ÇáÅáÛÇÁ ÇáÚÇÏí ãÓãæÍğÇº íÌÈ İÊÍ Ôßæì ÚäÏ æÌæÏ ãÔßáÉ.

## 5. ÇáÎÑíØÉ ÇáÍíÉ æÇáÏÚæÉ ÇáãÈÇÔÑÉ

ÃäÔÆ ØáÈğÇ ÌÏíÏğÇ æÇÌÚá ÇáÓÇÆŞ Online.

1. ÇáÚãíá: `GET /customer/rides/<ride_id>/nearby-vehicles/`.
2. ÇÎÊÑ `driver_id` ÇáÙÇåÑ.
3. ÇáÚãíá: `POST /customer/rides/<ride_id>/invitations/`.

```json
{ "driver_id": 9, "ttl_seconds": 20 }
```

ÇÓÊÈÏá `9` ÈÇáãÚÑİ ÇáĞí ÃÚÇÏå seed Ãæ nearby endpoint. Çáãåá ÇáãÓãæÍ ÈåÇ ááãäØŞÉ åí ÚÇÏÉ `[20, 40, 60]`º ŞíãÉ ÛíÑ ãæÌæÏÉ ÊÑİÖ. áÇ íÓãÍ ÇİÊÑÇÖíğÇ ÈÃßËÑ ãä ÏÚæÉ ãÚáŞÉ æÇÍÏÉ áäİÓ ÇáØáÈ.

4. ÇáÓÇÆŞ: `GET /driver/invitations/`.
5. ÇáÓÇÆŞ: `POST /driver/invitations/<invitation_id>/accept/` Ãæ `reject/`.

```json
{ "reason": "ÈÚíÏ Úä ãæŞÚí" }
```

ÇÎÊÈÑ ÇáÇäÊåÇÁ: áÇ ÊŞÈá ÇáÏÚæÉ ÈÚÏ ÇäÊåÇÁ `ttl_seconds`. ÇÎÊÈÑ ÇáÊåÏÆÉ: ÈÚÏ ÑİÖ ÇáÓÇÆŞ áÇ íÓÊØíÚ ÇáÚãíá ÏÚæÊå ãÈÇÔÑÉ áİÊÑÉ ÇáÑİÖ ÇáÇİÊÑÇÖíÉ 60 ËÇäíÉ.

## 6. ÇáÑÍáÉ ÇáãÔÊÑßÉ æÇáãÌÏæáÉ

### ÑÍáÉ ãÔÊÑßÉ İæÑíÉ

ÃäÔÆ ØáÈğÇ ÈÜ:

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

Ëã ÇÓÊÎÏã:

```text
GET  /customer/rides/<ride_id>/shared-offers/
POST /customer/shared-offers/<join_request_id>/accept/
```

ÊÍŞŞ Ãä ÇáÓíÇÑÉ ÇáãÔÊÑßÉ áÇ ÊÙåÑ áØáÈ İÑÏí¡ æÃäåÇ ÊÙåÑ İŞØ áØáÈ ãÔÊÑß ãÊæÇİŞ æáå ãŞÇÚÏ ÔÇÛÑÉ. áÇ íÌÈ Ãä ÊÙåÑ ÅÍÏÇËíÇÊ æÌåÉ ÇáÑßÇÈ ÇáÂÎÑíä ÈÏŞÉ.

### ÑÍáÉ ãäÔæÑÉ/Èíä ÇáãÏä

ÇáÓÇÆŞ íäÔÑ:

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

Ëã ÇáÚãíá:

```text
GET  /trips/
POST /trips/<trip_id>/book/
```

```json
{ "passenger_count": 1 }
```

ÇÎÊÈÑ ÇáÓÚÉ: áÇ íÌæÒ ÇáÍÌÒ İæŞ `remaining_capacity`.

## 7. ÇáÊŞííãÇÊ æÇáÔßÇæì

ÈÚÏ ÅÊãÇã ÑÍáÉ:

```text
GET  /feedback/trips/<ride_id>/rating-state/
POST /feedback/trips/<ride_id>/rate/
GET  /feedback/me/rating-summary/
POST /feedback/complaints/
GET  /feedback/complaints/
```

ãËÇá ÊŞííã ÚÇáò:

```json
{ "score": 5, "tags": ["clean_car"], "comment": "ÑÍáÉ ããÊÇÒÉ" }
```

ãËÇá ÊŞííã ãäÎİÖº íÌÈ Ãä íÍÊæí ÓÈÈğÇ (æÓã Ãæ ÊÚáíŞ):

```json
{ "score": 1, "tags": ["unsafe_driving"], "comment": "ŞíÇÏÉ ÛíÑ ÂãäÉ" }
```

ãËÇá Ôßæì:

```json
{
  "ride_id": 42,
  "category": "safety",
  "description": "æÕİ æÇÖÍ ááãÔßáÉ áÇ íŞá Úä ÚÔÑÉ ÃÍÑİ"
}
```

ÍÇáÇÊ ÇáÇÎÊÈÇÑ ÇáãåãÉ:

- áÇ íãßä ÊŞííã ÑÍáÉ ÛíÑ ãßÊãáÉ.
- áÇ íãßä ÇáÊŞííã ãÑÊíä ááÑÍáÉ äİÓåÇ.
- ÇáØÑİ ÇáÂÎÑ áÇ íÑì ÊŞííãß ŞÈá Ãä íŞíøã Ãæ ÊäÊåí ãåáÉ ÇáÊŞííã (14 íæãğÇ ÇİÊÑÇÖíğÇ).
- Ôßæì safety ÊÕÈÍ ÍÑÌÉ ÊáŞÇÆíğÇ.
- áÇ ÊİÊÍ Ôßæì ãßÑÑÉ ãä ÇáİÆÉ äİÓåÇ ãÇ ÏÇãÊ ÇáÓÇÈŞÉ ãİÊæÍÉ.

## 8. ÇáÅÔÚÇÑÇÊ

ÓÌá ÌåÇÒğÇ ÈÚÏ æÖÚ Token ÇáãÓÊÎÏã:

`POST /push/devices/register/`

```json
{ "token": "demo-fcm-token-unique-001", "platform": "android" }
```

Ëã:

```text
GET  /me/notifications/
POST /push/devices/unregister/
```

İí ÇáÊØæíÑ ÇáÇİÊÑÇÖí ŞÏ Êßæä ÇáÅÔÚÇÑÇÊ Consoleº áĞáß ÊÍŞŞ ãä Õİæİ ÇáÅÔÚÇÑÇÊ ælogs. áÇ ÊÓÊÎÏã token ÍŞíŞí áÃÍÏ ÇáãÓÊÎÏãíä ÇáÂÎÑíä İí ÇáÇÎÊÈÇÑ.

## 9. ÇÎÊÈÇÑ ÇáÎÑÇÆØ

`GET /maps/route/?pickup_lat=35.36&pickup_lng=35.90&destination_lat=35.37&destination_lng=35.91`

ÇáãÊæŞÚ: `distance_km` æ`duration_minutes` æ`geometry`. ÅĞÇ ßÇä ãÒæÏ ÇáÊæÌíå ÛíÑ ãÊÇÍ íßæä ÇáÑÏ `502`º åĞÇ ãÊæŞÚ İí ÍÇá ÇäŞØÇÚ ÇáÅäÊÑäÊ Ãæ ÊÚØíá ÇáãÒæÏ.

## 10. áæÍÉ ÇáÊÔÛíá (Admin İŞØ)

ÈÇÓÊÎÏÇã Token admin:

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

ßá ÊÏÎá ÅÏÇÑí íÍÊÇÌ `reason` ãßÊæÈğÇ ãä 10 ÃÍÑİ Úáì ÇáÃŞá. ÇÎÊÈÑ Ãä ÇáØáÈ ÈáÇ ÓÈÈ íÑİÖ¡ æÃä ÇáÓÌá íÙåÑ ÈÚÏåÇ İí `/ops/actions/`.

## 11. WebSocket

Swagger áÇ íÎÊÈÑ WebSocket ãÈÇÔÑÉ. ÇÓÊÎÏã Daphne Úáì ÇáãäİĞ 8001 æÚãíá WebSocket ãäİÕá. ÇáãÓÇÑÇÊ ÇáİÚáíÉ ÙÇåÑÉ İí `realtime/routing.py`. ÇÎÊÈÑ Úáì ÇáÃŞá:

- `connection.established` ÚäÏ ÇáÇÊÕÇá.
- `ride.snapshot` ÚäÏ ÏÎæá ÛÑİÉ ÑÍáÉ.
- `offer.created` æ`offer.accepted` æ`ride.cancelled`.
- `driver.location` ÃËäÇÁ ÇáÑÍáÉ.
- `trip.completed` ÚäÏ ÇáÅäåÇÁ.
- `vehicle.entered_area` æ`vehicle.left_area` İí ÇáÎÑíØÉ ÇáÍíÉ.

İí ÇáÅäÊÇÌ ÇÓÊÎÏã `wss://` æáíÓ `ws://`.

## 12. ÇáÊäÙíİ æÅÚÇÏÉ ÇáÊÌÑÈÉ

ÇÚÑÖ ãÇ ÓíÍĞİ ÃæáğÇ:

```powershell
python manage.py reset_operational_data
```

Ëã äİøĞ İŞØ İí ŞÇÚÏÉ ÊØæíÑ/ÇÎÊÈÇÑ:

```powershell
python manage.py reset_operational_data --yes
python manage.py seed_mobile_demo
```

ÇáÃãÑ íäÙİ ÇáÑÍáÇÊ æÇáÚÑæÖ æÇáÏÚæÇÊ æÇáÊŞííãÇÊ æÇáÔßÇæì æÇáÅÔÚÇÑÇÊ æRedis¡ áßäå íÈŞí ÇáÍÓÇÈÇÊ æÇáãÑßÈÇÊ æÇáãäÇØŞ ææÓæã ÇáÊŞííã. áÇ ÊÓÊÎÏã `wipe_database.py` İí ÇÎÊÈÇÑ ÇáãæÈÇíá ÇáÇÚÊíÇÏí.