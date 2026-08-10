# StreamPartner — Backend

## Context

Django 6.0 REST API for StreamPartner — a subscription management platform (Netflix, Spotify, etc.) for the Cameroonian market. Phone-based auth with 2FA (WhatsApp OTP), Mobile Money payments, admin panel.

## Commands

- `uv run manage.py runserver` — dev server
- `uv run pytest --nomigrations` — tests (134 pass, server slow without migrations)
- `uv run manage.py migrate` — apply migrations
- `uv run manage.py collectstatic --noinput` — collect static files
- `docker compose up --build` — full stack (gunicorn + celery + postgres + redis + flower)

## Conventions

- **Settings**: `ENVIRONMENT` var drives `IS_PRODUCTION` → SECURE_*, DEBUG, LOGGING format
- **Encryption**: `FERNET_KEY` encrypts `Card.numero` (must match dev + prod)
- **Throttling**: login 5/min, OTP 3/min, register 5/min (on view classes, not DEFAULT_THROTTLE_CLASSES)
- **Country code**: `237` format (no `+`), validated in `UserCreateSerializer`
- **Phone**: `User.phone_number` is unique, used as username for JWT
- **S3 storage**: T3 Storage, presigned URLs expire 1h
- **Tests**: `conftest.py` autouse fixture clears cache between tests (throttle counters)

## Key Files

- `config/settings.py` — env-driven settings, LOGGING, structlog, Sentry
- `api/views/auth.py` — UserViewSet, 2FA views, throttles
- `api/views/admin/inventory.py` — ordering, search
- `payments/models.py` — Order.order_id is UUID (cast to str for Celery)
- `notifications/tasks.py` — Celery tasks (email, push)