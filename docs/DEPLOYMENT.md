# Deployment

Local API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Container:

```bash
docker compose up --build
```

The image runs `scripts/migrate.py` before Uvicorn. Simulation uses SQLite; live deployments must set a PostgreSQL `DATABASE_URL`, run `scripts/validate_production.py`, and pass `/ready` before receiving traffic. CI runs lint, compilation, and the full pytest suite without production secrets.

Live secret minimums are `AUTH_SECRET` and `WEBHOOK_SECRET` with at least 32 random characters, a bootstrap `ADMIN_API_KEY`, verified finance settings, eBay/CJ credentials when those providers are enabled, and a secret-manager rotation policy. Never put these values in the image or compose file.

Deployment order:

1. Provision PostgreSQL and the secret manager.
2. Load environment secrets and set `APP_MODE=live`.
3. Run `python scripts/validate_production.py` and the migration startup.
4. Wait for `/ready` with a healthy database.
5. Issue a short-lived admin/operator token through `/auth/token` and perform a sandbox/canary check.

Rollback is a traffic rollback to the previous image plus database backup restore if a migration or integration contract fails. Keep the kill switch available during the canary.
