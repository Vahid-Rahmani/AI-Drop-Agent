# Implementation status

| Area | Status | Evidence |
| --- | --- | --- |
| Repository audit | DONE | Existing modules/tests inspected; baseline is documented in `PROJECT_STATE.md`. |
| Market and supplier research | DONE | Existing eBay/CJ adapters plus deterministic simulation agents. |
| Product matching | DONE | Existing matcher retained and wrapped with confidence/evidence. |
| Deterministic profit | DONE | Existing fee/profit engines plus `app/core/economics.py`. |
| Compliance/risk | DONE | Configured high-risk term gate; uncertain/live legal policy remains human review. |
| Listing and marketing drafts | DONE | Grounded listing draft and bounded experiment object; no publish/spend action. |
| Orders and fulfillment | DONE | Validated transitions and idempotency keys. |
| Support and analytics | DONE | Evidence-backed status reply and business review. |
| Brain/provider abstraction | DONE | Mock, OpenAI-compatible, and named local open-weight adapter; malformed/non-object JSON rejected. |
| Policy/approvals/kill switch | DONE | Permission levels, budget/exposure gates, kill-switch check, and durable approval queue. |
| Audit/events | DONE | Append-only structured event log persisted through SQLite adapter. |
| Simulation E2E | DONE | `POST /simulate`, `drop-agent-sim`, and integration test. |
| API/health | DONE | `/health`, `/ready`, `/agents`, `/tools`, `/profit/calculate`, `/simulate`, `/orders`, `/approvals`, `/audit`, `/metrics`. |
| Durable persistence | DONE | SQLite development store and transactional PostgreSQL adapter are selectable through `DATABASE_URL`; migrations and health checks exist. |
| Authentication and RBAC | DONE | HMAC bearer tokens, admin bootstrap issuance, viewer/operator/admin roles, live read protection, and approval guards are implemented. |
| Signed webhooks and redaction | DONE | Timestamped HMAC verification has replay protection backed by the configured store; recursive secret redaction is covered by tests. |
| SSRF-safe outbound clients | DONE | Allowlisted `SafeHttpClient` blocks credentials, private/reserved literal IPs, metadata hosts, and redirects. |
| Provider contract fixtures | DONE | Mock, OpenAI-compatible, and local-compatible providers share malformed-output, timeout, retry, rate-limit, and schema tests. |
| Marketplace/supplier adapters | DONE | eBay inventory/offer/order sync and CJ search/inventory/shipping/order/tracking/cancel boundaries are implemented with fixtures, retries, normalized errors, and idempotency. |
| Finance configuration | DONE | VAT, marketplace/payment/advertising fees, returns, shipping, operating cost, discounts, and explicit verification are validated from settings. |
| Deployment and worker readiness | DONE | Fail-fast production validator, migration startup, health/readiness checks, Docker healthcheck, and one-shot worker runner exist. |
| Live marketplace/supplier execution | BLOCKED_EXTERNAL | Final execution still requires approved eBay/CJ accounts, credentials, account-specific policies, and a managed PostgreSQL deployment. |
| Authenticated production control plane | DONE | Live-mode bootstrap admin key, signed multi-user bearer tokens, RBAC, protected reads, protected writes, and approval-gated tools are implemented. |
