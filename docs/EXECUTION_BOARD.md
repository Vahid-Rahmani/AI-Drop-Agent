# Execution board

This board records the specialist workstreams that were executed in the current continuation loop. Each row names the runtime ownership, implementation evidence, review gate, and acceptance condition.

| Workstream | Implemented modules | Reviewer/gate | Acceptance evidence |
| --- | --- | --- | --- |
| Security | `app/security/auth.py`, `webhooks.py`, `redaction.py`, `app/core/http.py` | adversarial tests | RBAC, signed replay protection, redaction, allowlist/SSRF tests pass |
| Persistence | `app/core/storage.py`, `postgres.py`, `migrations/001_initial.sql` | repository fixture review | restart-safe approvals, transactional store contract, webhook claim and health check |
| AI provider | `app/core/providers.py` | provider contract tests | valid output, schema mismatch, malformed JSON, timeout, retry, rate-limit and fallback behavior |
| Marketplace | `app/integrations/marketplace.py`, `ebay.py` | integration fixture review | OAuth refresh, listing create/update/end, inventory/order sync, errors, retries and idempotency |
| Supplier | `app/integrations/supplier.py`, `cj.py` | integration fixture review | search, detail, inventory, shipping, order, tracking and cancellation boundary |
| Finance | `app/core/finance_config.py`, `app/agents/specialists.py` | policy/finance review | validated fee/tax assumptions and cash-limited reinvestment approval |
| Tools/Brain | `app/brain.py`, `app/core/tools.py` | architecture review | handlers are explicit; caller permission and policy approval are enforced |
| Operations | `scripts/validate_production.py`, `scripts/migrate.py`, `app/workers.py`, Docker | release review | fail-fast validation, startup migration, health/readiness, bounded one-shot jobs |
| UI/UX | `app/ui/templates/`, `app/ui/static/` | accessibility/UX review | responsive navigation, readable tables/forms, loading/error/empty/warning states, confirmation prompts |
| Frontend | `app/ui/static/app.js`, `styles.css` | backend/API review | thin same-origin client; no duplicated economics, policy, approvals, or order logic |
| Admin API | `app/admin_ui.py`, `app/security/session.py` | security/API review | session login, CSRF, protected BFF endpoints, safe config summaries, no secret response |
| Integration UX | admin integration routes and cards | integration review | eBay/CJ/PostgreSQL/AI statuses distinguish configured, missing, and external blockers |
| Finance UX | admin business-settings route/form | finance review | VAT, fees, return reserve, spend/loss/exposure/margin validated by backend |
| UI QA/accessibility | `tests/test_admin_ui.py` | QA/UX review | auth, CSRF, security headers, secret handling, simulation, products, approvals, metrics, persistence |
| QA | `tests/test_integrations_and_operations.py`, `test_provider_contracts.py`, `test_admin_ui.py` and full suite | orchestrator review | 68 tests, lint, and compile pass |

The remaining row is intentionally external: approved eBay/CJ accounts and credentials, a managed PostgreSQL instance, secret-manager provisioning, account-specific financial verification, and a human-reviewed canary. Those steps cannot be completed from repository code alone.
