# ADR 0002: Thin FastAPI Admin UI

## Decision

Build the operator panel as FastAPI-served Jinja2 templates with a small same-origin JavaScript client and CSS. Keep the frontend in `app/ui/` and expose only thin `/admin/*` backend-for-frontend endpoints.

## Rationale

The repository has no existing frontend and the operator needs a small internal control panel, not a separate product. Jinja2 avoids a second build system, while a small browser client is enough for dashboard, setup, integration status, settings, simulation, and operational tables.

## Security implications

- The existing signed-token primitive issues a short-lived HttpOnly admin session cookie.
- A separate SameSite CSRF cookie/header pair protects state-changing UI requests.
- Secrets are accepted only as `SecretStr`, never persisted or returned by the UI; the panel reports `BLOCKED_EXTERNAL` until a real secret manager exists.
- All data routes require an admin session, and responses receive no-store, CSP, frame, MIME, and referrer headers.
- Business calculations, policy, approvals, order state, and agent decisions remain backend-owned.

## Maintenance implications

The UI deliberately has no frontend package or build step. The API contract and the backend remain authoritative; adding a new operator view should normally add one protected read endpoint and one small rendering function rather than duplicate domain logic in JavaScript.

