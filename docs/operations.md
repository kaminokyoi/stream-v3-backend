# Operations — Runbooks

## L1.40 — S3 Lifecycle (backup cross-region)

Configure on the S3 bucket a lifecycle rule:

```
Prefix: backups/
Status: Enabled
Transitions:
  - Storage class: GLACIER (after 30 days)
  - Storage class: DEEP_ARCHIVE (after 90 days)
Expiration: 365 days
Noncurrent version expiration: 30 days
```

T3 Storage / AWS console → Lifecycle configuration. Applies to versioned backups only.

## L1.41 — Secrets Rotation

### StreamPartner secrets inventory

| Secret | Where | Rotation cadence |
|--------|-------|------------------|
| `SECRET_KEY` (Django) | `.env` VPS + Railway env | Quarterly |
| `FERNET_KEY` (Card encryption) | `.env` VPS — NEVER rotate without re-encrypting all `Card.numero` | Document-only |
| `RESEND_API_KEY` | Railway env | On compromise |
| `WHATOMATE_API_KEY` | `.env` VPS | On compromise |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `.env` VPS | Quarterly |
| `FLOWER_USER` / `FLOWER_PASSWORD` | docker-compose env | Quarterly |
| `SENTRY_DSN` | Railway env + VPS env | On compromise |

### Procedure (per secret)

1. Generate new value
2. Update `.env` on VPS: `docker compose down && nano .env && docker compose up -d`
3. Update Railway env vars via CLI: `railway variables set KEY=newvalue`
4. Verify `/api/v1/public/health/` returns 200
5. Revoke old value at the source (AWS IAM, Resend dashboard, etc.)

### FERNET_KEY special case

`FERNET_KEY` encrypts `Card.numero`. To rotate:

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Run management command (TBD): `manage.py rotate_fernet_key OLD_KEY NEW_KEY`
3. Update `.env` with new key only after the rotation command completes
4. Take a DB backup before rotation

## L1.42 — PostgreSQL Backups

### Daily automated backup

Add to the VPS crontab:

```bash
0 3 * * *  docker exec stream-postgres pg_dump -U postgres -Fc postgres > /backups/streampartner_$(date +\%Y\%m\%d).dump && aws s3 cp /backups/streampartner_$(date +\%Y\%m\%d).dump s3://storage-ryfqlql2ghbmi8szj/backups/
```

### Restore procedure

```bash
docker exec -i stream-postgres pg_restore -U postgres -d postgres -c < /backups/streampartner_YYYYMMDD.dump
```

### Retention

- Daily backups kept 7 days locally
- Daily backups moved to S3 with 365-day lifecycle (L1.40)
- Weekly full backup kept 1 year in S3 Glacier
