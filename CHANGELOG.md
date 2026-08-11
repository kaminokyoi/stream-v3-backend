# Changelog

All notable changes to StreamPartner Backend are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/) and adheres to [SemVer 2.0](https://semver.org/).

## [3.0.0] — 2026-08-11

### Breaking Changes
- Removed `Card.cvv` field (PCI-DSS compliance) — migration required
- Encrypted `Account.email`, `Account.password`, `User.twofa_secret` with Fernet — `FERNET_KEY` mandatory in production
- JWT auth now sets HttpOnly cookies alongside JSON response (dual-auth for mobile)
- `celery-types` moved to dev dependencies

### Security
- JWT HttpOnly cookies (`sp_access`, `sp_refresh`) with `SameSite=Lax` (L3.1)
- CSRF double-submit middleware (`DoubleSubmitCSRFMiddleware`) (L2.5)
- `EncryptedCharField` for `Account.email`, `Account.password`, `User.twofa_secret` (L2.1-2)
- CVV field removed from `Card` model (L2.3, PCI-DSS)
- Production hardening: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `DEBUG` guard, `FERNET_KEY` required (L1.1-3)
- `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` via env vars (L1.4)
- Scoped throttling: login 5/min, OTP 3/min, register 5/min (L1.8)
- 2FA `expires_in` returned in challenge response

### Features
- `drf-spectacular` OpenAPI schema + Swagger UI at `/api/schema/` (L2.12)
- Health check endpoint `GET /api/v1/public/health/` (L1.5)
- `django-structlog` structured logging (JSON in prod, console in dev) (L1.23)
- Sentry error tracking (Django + Celery + Redis integrations) (L1.7)
- Idempotent subscription notification tracking (`notified_j3/j/j1` flags) — prevents duplicate notifications, resets on renewal/bonus
- Password reset via phone (custom `PasswordResetSerializer`, `NoopPasswordResetEmail`)
- `PaymentCompletionService._create_subscription` resets notification flags on renewal
- `ReviewService.submit_review` resets notification flags on +7 day bonus

### Architecture
- `EncryptedCharField` moved to `core/fields.py` (shared module)
- `Account.save()` derivation logic extracted to `pre_save` signal `normalize_account_fields` (L2.21)
- `CookieJWTAuthentication` — reads JWT from cookie or Authorization header
- `CookieTokenRefreshView` — refresh from cookie or body
- `LogoutView` — clears JWT cookies
- Django app `notifications` decoupled from `dashboard`

### Infrastructure
- `gunicorn` (3 workers, 120s timeout) replaces `runserver` in Docker (L1.16)
- `docker-compose.yaml` with healthchecks on PostgreSQL + Redis, `migrate` one-shot service, `flower` monitoring (L1.18-20, L1.39)
- `Procfile` for Railway (L1.17)
- `entrypoint.sh` runs `collectstatic` + `migrate` (L1.20)
- Python 3.13, all dependencies pinned with major version upper bounds (L1.21-22)
- `pre-commit` config (ruff, detect-private-key) (L1.33)
- GitHub Actions CI: pytest + coverage + migration rollback test (L1.35, L1.37, L2.24)
- pytest coverage measurement (`--cov-fail-under=10`) (L1.37)
- `.env.example` with all env vars documented (L2.22)
- `AGENTS.md` with project context (L1.32)
- `README.md` with setup instructions (L1.30)
- `docs/` copied into backend repo (L1.31)
- `docs/repo-strategy.md`, `docs/operations.md` (S3 lifecycle, secrets rotation, PG backups)

### Fixes
- `send_rejection_proof_email` UUID serialization (cast `order_id` to `str` for Celery)
- Celery logger shadow fix
- `WHATOMATE_API_KEY` warning on missing key
- Tests tracked in git (removed from `.gitignore`)
- `conftest.py` clears cache between tests (throttle counter reset)
- `.env.exemple` typo → `.env.example`
- Ordering: accounts by `('status', F('end_date').asc(nulls_last=True))`
- Ordering: expired subscriptions by `-expiration_date`
- Search: profiles by `account__number__istartswith` + `account__platform__icontains`

### Tests
- 139 tests (134 original + 5 new expiration tracking tests)
- `test_expiration_tracking.py`: flag set, no re-send, mark expired, reset on renewal, skip without email