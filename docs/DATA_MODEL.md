# Data model

Typed Pydantic contracts live in `app/domain.py`. Important records are `Evidence`, `ProductCandidate`, `MatchResult`, `EconomicsInput`, `PolicyDecision`, `ApprovalRequest`, `ListingDraft`, `MarketingExperiment`, `Order`, `AuditEvent`, `BusinessMetrics`, and `BusinessReview`.

SQLite persistence stores orders, approval requests, audit events, and claimed webhook IDs for development. `PostgresStore` provides the same transactional repository contract for production and stores JSON payloads in JSONB columns. IDs are UUIDs where lifecycle identity matters. Both stores preserve idempotency keys, immutable audit events, policy-version references, and webhook duplicate protection.
