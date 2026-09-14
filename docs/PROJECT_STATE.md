# Project state

Updated: 2026-09-14

## Scope

AI Drop Agent is a German-market dropshipping research and operating core. The safe path is simulation first; live marketplace and supplier writes are intentionally not implied by configuration.

## Architecture

- Existing: LangGraph research pipeline, eBay search/OAuth foundation, CJ supplier lookup, product matching, FX conversion, eBay fee uncertainty handling, profit bridge, and SELL/WATCH/REJECT decisions.
- Added: typed domain contracts, central `Brain`, explicit specialist agents, deterministic unit economics, policy engine, SQLite/PostgreSQL stores, idempotent order state machine, marketing/listing/support/analytics workflow, FastAPI endpoints, signed auth/webhooks, eBay/CJ adapters, worker runner, Docker migration startup, and CI.
- Persistence: SQLite remains the development default; `DATABASE_URL` selects the transactional PostgreSQL adapter for production. Both stores include webhook duplicate claims and health checks.

## Verified behavior

The simulation runs market opportunity -> supplier -> match -> economics -> compliance -> product approval -> listing draft -> bounded experiment -> simulated order -> fulfillment -> support -> metrics -> business review. No external credentials are used on this path.

## Known limits

The code-controlled live boundary is implemented. Actual eBay/CJ writes, secret-manager provisioning, managed PostgreSQL operations, tax/legal sign-off, and real account-specific fee verification require external access and a separate production canary.

## Highest-priority next work

1. Provision the external secret manager, approved marketplace/supplier accounts, and managed PostgreSQL.
2. Run sandbox contract checks and a human-reviewed production canary with the kill switch available.
3. Add operational dashboards/alerting in the deployment environment.
