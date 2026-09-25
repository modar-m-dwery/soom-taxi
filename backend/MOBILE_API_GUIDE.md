# Mobile API quick start

Swagger is available at `/api/docs/`; schema JSON is at `/api/schema/`.

## Authentication

Every protected endpoint uses `Authorization: Token <token>`. In Swagger, click **Authorize**, enter `Token ` followed by the token, then use **Try it out**. Authorization is retained while the browser tab remains open.

For a ready development environment run:

```powershell
python manage.py seed_mobile_demo
```

It creates/refreshes service areas, rating tags, an active driver vehicle and three accounts. The command prints current tokens as JSON; do not commit or share that output.

- customer: creates rides, views offers, selects/cancels rides, rates and complains.
- driver: goes online, submits offers, accepts invitations, and runs the trip lifecycle.
- admin: reviews drivers and uses operational endpoints.

## Suggested happy-path test

1. Authorize as the customer; `POST /auth/me/` is not needed—use `GET /auth/me/` to verify identity.
2. Create a request with `POST /rides/` using Jableh coordinates near longitude `35.90`, latitude `35.36`.
3. Authorize as the driver; call `POST /drivers/me/go-online/`, then list candidates and submit an offer.
4. Switch back to customer; list offers and select one.
5. As driver: `arrived`, `start`, then `complete` for the ride id.
6. As customer: fetch the trip, rate it, or submit a complaint.

## Safe cleaning

Preview global operational cleanup first:

```powershell
python manage.py reset_operational_data
```

Execute it only on development/test data:

```powershell
python manage.py reset_operational_data --yes
python manage.py seed_mobile_demo
```

`reset_operational_data` removes rides, offers, trips, notifications, ratings, complaints and presence keys, but keeps users, driver profiles, vehicles, service areas and rating tags. It refuses production unless explicitly confirmed.

For a single command reset in a disposable environment:

```powershell
python manage.py seed_mobile_demo --reset-operational --i-understand-reset
```

## WebSocket

Use `ws://<host>/ws/...` locally and `wss://<host>/ws/...` in production. Authenticate with the same token according to the route’s documented query/header convention in the mobile client integration. Start Daphne and Redis before testing real-time flows.

## Production notes

OTP, routing and FCM require their real provider configuration. The production configuration deliberately rejects the console OTP backend.