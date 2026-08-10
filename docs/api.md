# StreamPartner — API Documentation

> Base URL: `/api/v1/`
> Format: JSON (UTF-8)
> Auth: JWT (SimpleJWT)

---

## 1. Overview

The StreamPartner backend exposes a REST API consumed by three frontends:
- **web-user** (`/api/v1/public/*` + `/api/v1/user/*`) — public catalog + authenticated user resources
- **web-admin** (`/api/v1/admin/*`) — admin CRUD + actions
- **mobile-admin** (`/api/v1/public/*` + `/api/v1/user/*` + `/api/v1/admin/*`) — Expo SDK 57 mobile app with push notifications

### URL structure

```
/api/v1/public/*    — no auth required (register, login, catalog, legal)
/api/v1/user/*      — JWT required (own resources only)
/api/v1/admin/*     — JWT + is_superuser required
```

---

## 2. Authentication

### JWT (SimpleJWT + Djoser)

- **Login field**: `phone_number` (not email). Email is optional.
- **Token type**: JWT with `Authorization: JWT <access_token>` header
- **Access token lifetime**: 60 minutes (configurable via `JWT_ACCESS_MINUTES`)
- **Refresh token lifetime**: 7 days (configurable via `JWT_REFRESH_DAYS`)
- **Rotation**: enabled (`ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`)

### Permissions

| Level | Permission class | Description |
|---|---|---|
| Public | `AllowAny` | No auth required |
| User | `IsAuthenticated` | JWT required, access restricted to own resources |
| Admin | `IsAdminUser` | JWT required + `is_superuser=True` |

### Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/public/auth/users/` | None | Register (phone_number, password, first_name, last_name, country_code) |
| POST | `/api/v1/public/auth/jwt/create/` | None | Login → `{access, refresh}` |
| POST | `/api/v1/public/auth/jwt/refresh/` | None | Refresh access token |
| POST | `/api/v1/public/auth/jwt/verify/` | None | Verify token validity |
| POST | `/api/v1/public/auth/password/reset/` | None | Reset password (sends email or fallback to admin) |

### Register example

```http
POST /api/v1/public/auth/users/
Content-Type: application/json

{
  "phone_number": "690123456",
  "country_code": "237",
  "password": "mypassword",
  "first_name": "Jean",
  "last_name": "Dupont"
}
```

Response: `201 Created` with user object.

### Login example

```http
POST /api/v1/public/auth/jwt/create/
Content-Type: application/json

{
  "phone_number": "690123456",
  "password": "mypassword"
}
```

Response:
```json
{
  "access": "eyJ...",
  "refresh": "eyJ..."
}
```

---

## 3. Conventions

### Pagination

All list endpoints use `PageNumberPagination` with `PAGE_SIZE=20`.

Response format:
```json
{
  "count": 42,
  "next": "https://api.example.com/api/v1/admin/users/?page=2",
  "previous": null,
  "results": [...]
}
```

Query parameter: `?page=N` for pagination.

### Errors

| Status | Format | Description |
|---|---|---|
| 400 | `{"field": ["message"]}` or `{"detail": "message"}` | Validation error |
| 401 | `{"detail": "Authentication credentials were not provided."}` | No token |
| 403 | `{"detail": "You do not have permission..."}` | Insufficient permissions |
| 404 | `{"detail": "Not found."}` | Resource not found |
| 500 | `{"detail": "..."}` | Server error |

### File uploads

Use `multipart/form-data` for:
- Payment proof images (`/api/v1/user/payments/manual/<order_id>/`)
- Notification image (`/api/v1/admin/messaging/notifications/` POST/PATCH)
- CSV import (`/api/v1/admin/users/import_csv/`)

### Filtering

Filtering is done via manual query parameters in each ViewSet's `get_queryset` (no DRF filter backends). Each endpoint documents its supported filter params below.

### Ordering

- Subscriptions: ordered by `-order__purchase_date` (newest purchase first)
- Accounts: ordered by `-remaining_day`
- Cards: ordered by `['expiration_date', 'status']`
- Users: ordered by `-date_joined`

### Access masking (security)

The backend enforces platform-specific access masking in serializers:
- **Spotify / Apple Music**: only the main profile (first created, `Min(id)`) sees email/password; others see empty fields
- **Surfshark**: all access fields hidden (email, password, profile_num, profile_pin)
- **Onoff**: managed by account type
- Expired + unlinked subscriptions: excluded from display
- Expired + still linked: shown with `status='expired'`

---

## 4. Public endpoints (`/api/v1/public/*`)

### Auth (Djoser)

| Method | URL | Description |
|---|---|---|
| POST | `auth/users/` | Register |
| POST | `auth/jwt/create/` | Login (phone_number + password) |
| POST | `auth/jwt/refresh/` | Refresh token |
| POST | `auth/jwt/verify/` | Verify token |
| POST | `auth/password/reset/` | Password reset |

### Catalog (read-only)

| Method | URL | Filters | Description |
|---|---|---|---|
| GET | `platforms/` | — | List all platforms |
| GET | `platforms/{id}/` | — | Platform detail |
| GET | `platforms/{id}/pricing/` | — | Price tiers for a platform |
| GET | `reviews/` | — | Published reviews |
| GET | `faqs/` | — | FAQ entries |

### Platform list response

```json
{
  "count": 11,
  "results": [
    {
      "id": 1,
      "name": "Netflix",
      "sub": "Netflix",
      "logo": "/media/netflix.svg",
      "has_personal": true,
      "shared_prices": [...],
      "personal_prices": [...]
    }
  ]
}
```

---

## 5. User endpoints (`/api/v1/user/*`)

All require `Authorization: JWT <access_token>`. Access restricted to the authenticated user's own resources.

### Profile

| Method | URL | Description |
|---|---|---|
| GET | `profile/` | Current user profile |
| PATCH | `profile/` | Update email (email setup) |

### Dashboard

| Method | URL | Description |
|---|---|---|
| GET | `dashboard/` | Aggregated dashboard (masked subscriptions, orders, pending orders, expiration notifications) |

### Orders

| Method | URL | Description |
|---|---|---|
| GET | `orders/` | List own orders |
| POST | `orders/` | Create order (purchase_init) — price recalculated server-side |
| GET | `orders/{id}/` | Order detail |
| DELETE | `orders/{id}/` | Cancel order (if not completed) |
| POST | `orders/{id}/renewal/` | Create renewal order |

**Order create body:**
```json
{
  "platform": "Netflix",
  "duration": "1 mois",
  "type": "mutual",
  "gift_code": "ABCD1234"
}
```

**Order create response:** `201 Created` with order object (status=`pending_payment`, price recalculated).

### Payments

| Method | URL | Body | Description |
|---|---|---|---|
| POST | `payments/manual/{order_id}/` | `multipart/form-data` with `image` (and optional `image2`) | Upload payment proof |

### Subscriptions

| Method | URL | Description |
|---|---|---|
| GET | `subscriptions/` | List own subscriptions (access masked) |
| GET | `subscriptions/{id}/` | Subscription detail (access masked) |

### Reviews

| Method | URL | Description |
|---|---|---|
| GET | `reviews/` | Get own review |
| POST | `reviews/` | Submit review (first review with active sub → +7 days bonus) |

### Gift codes

| Method | URL | Description |
|---|---|---|
| POST | `gift-code/verify/` | Verify gift code validity before purchase |

### Device & Push Notifications

| Method | URL | Body | Description |
|---|---|---|---|
| POST | `device/register/` | `{token, platform}` | Register/update Expo push token |
| POST | `device/unregister/` | `{token}` | Deactivate push token (on logout) |
| GET | `notifications/` | — | List push notifications (filters: `is_read`, `type`, `page`) |
| POST | `notifications/{id}/mark_read/` | — | Mark single notification as read |
| POST | `notifications/mark_all_read/` | — | Mark all notifications as read |
| GET | `notifications/unread_count/` | — | Get unread count |

**Push notification response:**
```json
{
  "id": 1,
  "title": "Nouvelle commande",
  "body": "Netflix — Medi Matuta — 2500 FCFA",
  "data": {"screen": "orders", "type": "order", "resource_id": 42},
  "notification_type": "order",
  "is_read": false,
  "created_at": "2026-07-18T10:00:00Z",
  "read_at": null
}
```

> Note: `/user/notifications/` (push history) is separate from `/admin/messaging/notifications/` (bulk email broadcasts).

---

## 6. Admin endpoints (`/api/v1/admin/*`)

All require `Authorization: JWT <access_token>` with `is_superuser=True`.

### Dashboard

| Method | URL | Params | Description |
|---|---|---|---|
| GET | `dashboard/` | — | Stats (total_revenue, total_users, active_subs, expired_subs, platform_labels, platform_data, last_orders) |
| GET | `dashboard/?action=chart_data` | `type` (revenue/users/subs_active/subs_expired), `period` (today/7_days/30_days/6_months/1_year/custom), `start_date`, `end_date` | Chart data (labels, data, total, order_count) |
| GET | `download-image/?url=...` | `url` | Download image from S3 or local media |

### Users

| Method | URL | Filters | Description |
|---|---|---|---|
| GET | `users/` | `q` (search name/phone/email), `status` (active/inactive), `email` (with_email/without_email), `country` (country_code), `page` | List users |
| POST | `users/` | — | Create user |
| GET | `users/{id}/` | — | User detail |
| PATCH | `users/{id}/` | — | Update user |
| DELETE | `users/{id}/` | — | Delete user |
| GET | `users/export_csv/` | — | Export users CSV |
| POST | `users/import_csv/` | `multipart/form-data` with `file` | Import users CSV |

### Orders

| Method | URL | Filters | Description |
|---|---|---|---|
| GET | `orders/` | `q`, `status`, `platform`, `type`, `duration`, `motif`, `linked`, `period`, `page` | List orders |
| POST | `orders/` | — | Create order |
| PATCH | `orders/{id}/` | — | Update order |
| DELETE | `orders/{id}/` | — | Delete order |

### Payment proofs

| Method | URL | Description |
|---|---|---|
| GET | `proofs/` | List proofs (filters: `validated`, `rejected`) |
| POST | `proofs/{id}/validate/` | Validate proof → activates subscription + assigns profile |
| POST | `proofs/{id}/validate_only/` | Validate without activation |
| POST | `proofs/{id}/reject/` | Reject proof (body: `{"reason": "..."}`) |

### Subscriptions

| Method | URL | Description |
|---|---|---|
| GET | `subscriptions/` | List (filters: `q`, `status`, `platform`, `duration`, `account`, `page`) |
| POST | `subscriptions/` | Create |
| PATCH/DELETE | `subscriptions/{id}/` | Update / Delete |
| POST | `subscriptions/{id}/change_profile/` | Link/change profile (body: `{"profile_id": N}`) |
| POST | `subscriptions/{id}/unlink_profile/` | Unlink profile (records history + notifies) |
| GET | `subscriptions/{id}/profile_history/` | Profile history timeline |
| POST | `subscriptions/{id}/renew/` | Admin renewal (body: `{"duration": "1 mois"}`) |
| POST | `subscriptions/{id}/mark/` | Add marker (body: `{"marker_name": "VIP", "marker_color": "#ff0000"}`) |
| POST/DELETE | `subscriptions/{id}/unmark/` | Remove marker (body: `{"marker_id": N}`) |
| POST | `subscriptions/{id}/mark_expired/` | Force expiration |
| POST | `subscriptions/{id}/toggle_expiry/` | Toggle active/expired |

### Accounts

| Method | URL | Description |
|---|---|---|
| GET | `accounts/` | List (filters: `platform`, `status`) |
| POST | `accounts/` | Create (body includes `card` as card ID or null) |
| PATCH/DELETE | `accounts/{id}/` | Update / Delete |
| POST | `accounts/{id}/renew/` | Add 1 month to end_date |
| POST | `accounts/{id}/mark/` | Add account marker (body: `{"marker_name": "...", "marker_color": "..."}`) |
| POST/DELETE | `accounts/{id}/unmark/` | Remove marker (body: `{"marker_id": N}`) |

### Profiles

| Method | URL | Description |
|---|---|---|
| GET | `profiles/` | List (filters: `platform`, `account`) |
| POST | `profiles/` | Create |
| PATCH/DELETE | `profiles/{id}/` | Update / Delete |

### Cards

| Method | URL | Filters | Description |
|---|---|---|---|
| GET | `cards/` | `q` (search nom/telephone), `page` | List cards |
| POST | `cards/` | — | Create card (numero encrypted at rest) |
| GET | `cards/{id}/` | — | Card detail (numero decrypted, masked_numero + formatted_numero) |
| PATCH | `cards/{id}/` | — | Update card |
| DELETE | `cards/{id}/` | — | Delete card |

**Card response:**
```json
{
  "id": 1,
  "numero": "1234567890123456",
  "masked_numero": "**** **** **** 3456",
  "formatted_numero": "1234 5678 9012 3456",
  "nom": "Visa Premier",
  "cvv": "123",
  "telephone": "+237690000000",
  "expiration_date": "2027-06-01",
  "status": "actif",
  "linked_accounts": ["ACC1", "ACC2"],
  "created_at": "2026-07-14T10:00:00Z"
}
```

### Account markers

| Method | URL | Description |
|---|---|---|
| GET | `account-markers/` | List all markers |
| POST | `account-markers/` | Create marker |

### Platforms & price tiers

| Method | URL | Description |
|---|---|---|
| GET/POST | `platforms/` | List / Create platform |
| PATCH/DELETE | `platforms/{id}/` | Update / Delete |
| GET/POST | `price-tiers/` | List / Create price tier |

### FAQ

| Method | URL | Description |
|---|---|---|
| GET/POST | `faqs/` | List / Create |
| DELETE | `faqs/{id}/` | Delete |

### Reviews

| Method | URL | Description |
|---|---|---|
| GET | `reviews/` | List (filters: `q`, `stars`, `page`) |

> Note: Delete action is intentionally not exposed in the admin UI (ethical reason).

### Gift codes

| Method | URL | Description |
|---|---|---|
| GET/POST | `giftcodes/` | List / Create |
| PATCH/DELETE | `giftcodes/{id}/` | Update / Delete |
| POST | `giftcodes/{id}/toggle/` | Toggle active/inactive |

### Payment numbers

| Method | URL | Description |
|---|---|---|
| GET/POST | `payment-numbers/` | List / Create |
| PATCH/DELETE | `payment-numbers/{id}/` | Update / Delete |
| POST | `payment-numbers/{id}/toggle/` | Toggle active/inactive |

### Messaging

| Method | URL | Description |
|---|---|---|
| GET/POST | `messaging/notifications/` | List / Create notification |
| PATCH/DELETE | `messaging/notifications/{id}/` | Update / Delete |
| POST | `messaging/notifications/{id}/send/` | Send (body: `{"send_to_all": false, "recipients": [1,2,3], "channel": "mail"}`) |
| GET/POST | `messaging/messages/` | List / Create message |
| PATCH/DELETE | `messaging/messages/{id}/` | Update / Delete |
| POST | `messaging/messages/{id}/send/` | Send (same body format) |

**Send body:**
```json
{
  "send_to_all": false,
  "recipients": [1, 2, 3],
  "channel": "mail"
}
```

If `send_to_all=true`, `recipients` is ignored and all users are targeted. If `recipients` is empty and `send_to_all=false`, returns 400.

---

## 7. Security

### CORS

`django-cors-headers` with `CorsMiddleware` in first position. Allowed origins:
- `http://localhost:3000` (web-user dev)
- `http://localhost:3001` (web-admin dev)
- Production origins (configurable via `CORS_ALLOWED_ORIGINS` env var, comma-separated)

### Encryption

`Card.numero` is encrypted at rest using Fernet (symmetric encryption from the `cryptography` package). The key is derived from `FERNET_KEY` env var, or from `SECRET_KEY` (SHA-256 → base64) if `FERNET_KEY` is not set. The `EncryptedCharField` encrypts on write and decrypts on read transparently.

### Pricing

Prices are **always recalculated server-side** via `calculate_price()`. The frontend never sends a price — it sends `platform`, `duration`, and `type`, and the backend computes the price from `PriceTier.base_price`.

### Access masking

Platform-specific access masking (Spotify, Apple Music, Surfshark, Onoff) is enforced in the **serializers**, not the frontend. See §3 "Access masking" above.

---

## 8. Celery tasks & beat schedule

| Schedule | Task | Module | Rôle |
|---|---|---|---|
| 00:00 daily | `update_remaining_days` | `payments.tasks` | Update account `remaining_day` |
| 00:15 daily | `delete_stale_pending_orders_task` | `payments.tasks` | Delete `pending_payment` orders > 24h |
| 00:30 daily | `check_expiring_cards_task` | `notifications.tasks` | Auto-expire cards (`status→inactif`) |
| 08:00 daily | `check_expiring_subscriptions_task` | `payments.tasks` | Expiration notifications J-3/J/J+1 |
| Monday 08:00 | `send_report_email_task` | `dashboard.tasks` | Weekly PDF report |
| End of month 23:30 | `send_report_email_end_of_month_task` | `dashboard.tasks` | Monthly PDF report |

Email + push notifications are sent asynchronously via Celery tasks in `notifications/tasks.py`:
- `send_email_task` (generic email sender)
- `send_push_notification_task` (push to single user via Expo Push API)
- `send_push_to_admins_task` (push to all admins)
- `send_access_update_notification` (account/profile access changes — email + push)
- `send_rejection_proof_email` (payment proof rejected — email + push to admins)
- `send_password_reset_link_task` (password reset — email + push)
- `notify_admin_login_task` (admin login alert — email + push to admins)
- `send_bulk_notification_task` / `send_bulk_message_task` (bulk messaging)
- `check_expiring_cards_task` (daily card auto-expiration)

All 15 `notify_*` functions in `notifications/services.py` send **email AND push in parallel**. Push payload includes `{screen, type, resource_id}` for deep linking.

---

## 9. Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `django-insecure-...` | Django secret key (required in prod) |
| `ENVIRONMENT` | — | `production` or `development` |
| `DATABASE_URL` | — | PostgreSQL URL (prod) |
| `FERNET_KEY` | derived from SECRET_KEY | Fernet encryption key for Card.numero |
| `REDIS_URL` | — | Redis URL for Celery broker + cache. If empty, falls back to LocMemCache |
| `CACHE_BACKEND` | — | Override to `locmem` to force local memory cache |
| `CELERY_BROKER_URL` | — | Celery broker URL (defaults to REDIS_URL) |
| `CELERY_RESULT_BACKEND` | — | Celery result backend |
| `AWS_ACCESS_KEY_ID` | — | AWS S3 access key |
| `AWS_SECRET_ACCESS_KEY` | — | AWS S3 secret key |
| `AWS_S3_BUCKET_NAME` | — | S3 bucket name |
| `AWS_S3_ENDPOINT_URL` | — | S3 endpoint (for non-AWS S3) |
| `AWS_S3_REGION_NAME` | — | S3 region |
| `AWS_ENDPOINT_URL` | — | S3 endpoint (general) |
| `RESEND_API_KEY` | — | Resend email API key |
| `REPORT_RECIPIENT_EMAIL` | `streampartnernotif@gmail.com` | Report recipient |
| `REPORT_PERIOD_DAYS` | `7` | Report period in days |
| `SUBSCRIPTION_NOTIFICATION_EMAIL` | `streampartnernotif@gmail.com` | Subscription notification sender |
| `MOBILE_MONEY_MTN_NUMBER` | — | Fallback MTN number |
| `MOBILE_MONEY_MTN_NAME` | `Stream Partner` | Fallback MTN name |
| `MOBILE_MONEY_ORANGE_NUMBER` | — | Fallback Orange number |
| `MOBILE_MONEY_ORANGE_NAME` | `Stream Partner` | Fallback Orange name |
| `JWT_ACCESS_MINUTES` | `60` | JWT access token lifetime (minutes) |
| `JWT_REFRESH_DAYS` | `7` | JWT refresh token lifetime (days) |
| `CORS_ALLOWED_ORIGINS` | — | Additional CORS origins (comma-separated) |

---

## 10. Tests

- **Framework**: pytest-django
- **Count**: 104 tests (backend)
- **Location**: `backend/tests/`
- **Fixtures**: `backend/tests/conftest.py` — `api_client`, `admin_client`, `user`, `make_order`, `make_subscription`, `make_account`, `make_profile`, `make_platform`, `make_price_tier`
- **Test isolation**: `CELERY_TASK_ALWAYS_EAGER=True` (tasks run synchronously), `LocMemCache` (no Redis required)
- **Run**: `cd backend && uv run pytest tests/`

### Test files

| File | Tests | Coverage |
|---|---|---|
| `test_api_public.py` | 13 | Auth, platforms, reviews, FAQs |
| `test_api_user.py` | 36 | Profile, dashboard, orders, payments, subscriptions, reviews, gift codes, push notifications (device register/unregister, list, mark_read, mark_all_read, unread_count, filter, service, admins) |
| `test_api_admin.py` | 39 | Dashboard stats, users CRUD, orders, proofs, subscriptions, accounts, profiles, cards (encryption), account markers, platforms, price tiers, FAQs, reviews, gift codes, payment numbers, notifications, messages |
| `test_pricing.py` | — | Pricing formula verification |
| `test_review_bonus.py` | — | +7 days bonus on first review |
| `test_subscription_access.py` | — | Access masking rules per platform |
