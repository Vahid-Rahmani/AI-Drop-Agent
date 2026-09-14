# ADR 0001: simulation-first operating boundary

## Decision

The default runtime mode is simulation. The end-to-end workflow uses explicit fixtures and can exercise business logic without external credentials or irreversible actions.

## Rationale

It makes policy, financial, order, support, and audit behavior testable before marketplace accounts, supplier credentials, payment authorization, or legal review exist. Live mode remains a separately reviewed deployment concern.
