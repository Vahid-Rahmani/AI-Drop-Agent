# Operations

Health endpoints are `/health` and `/ready`; readiness includes the configured store health check and live configuration errors. The structured audit feed, approvals, orders, and metrics are protected by signed bearer tokens in live mode. SQLite is for development; PostgreSQL is selected by a `postgresql://` or `postgres://` `DATABASE_URL`. The kill switch is configured through `KILL_SWITCH=true`.

Recommended production controls: secret manager, database backups, alerting on policy blocks and supplier failures, bounded worker queues, request correlation IDs, provider rate limits, token rotation, and a manual shutdown runbook. The API-independent `Worker` can run one bounded job at a time under an external scheduler or process supervisor.
