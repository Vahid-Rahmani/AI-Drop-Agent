# Security boundary

- Secrets are read from environment configuration and excluded by `.gitignore`.
- External market, supplier, customer, and model output is untrusted input.
- Provider output must be an object-shaped JSON response; it cannot authorize an action.
- Financial and external action levels are policy-gated; legal/account actions require explicit human approval.
- Simulation is default and has no real spending or marketplace write path.
- Live APIs use a bootstrap `X-Admin-API-Key` to issue signed bearer tokens, then enforce viewer/operator/admin RBAC on protected reads and writes. Keep the bootstrap key and signing secrets in a secret manager.
- `SafeHttpClient` only permits configured provider hosts and rejects URL credentials, metadata hosts, local names, private/reserved literal IPs, and redirects.
- Webhooks use `timestamp.body` HMAC-SHA256 signatures, a replay window, and a durable event-claim ledger. Provider dispatch remains intentionally narrow (`ebay` and `cj`).
- Tool invocation checks the caller permission level before a handler runs. External and financial handlers additionally require policy approval; kill switch and budget checks remain deterministic.
- `redact()` removes known secret fields recursively before diagnostics are emitted. Production logging must call this helper for request/response metadata.
- The Admin UI uses short-lived HttpOnly SameSite session cookies, a separate CSRF token, no browser localStorage, masked/cleared secret inputs, restrictive CSP/security headers, and `Cache-Control: no-store` on all `/admin` routes.
