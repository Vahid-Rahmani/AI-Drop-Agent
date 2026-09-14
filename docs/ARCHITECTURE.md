# Architecture

```text
FastAPI / CLI / Admin UI
    -> Brain (orchestrator)
        -> SimulationWorkflow
            -> research, supplier, matcher, economics, compliance
            -> policy decision
            -> listing and experiment drafts
            -> order state machine
            -> support and analytics review
        -> provider boundary (mock / OpenAI-compatible / future local model)
    -> append-only audit log
    -> protected `/admin/*` BFF routes
        -> Jinja2 templates + small same-origin browser client
        -> signed HttpOnly admin session + CSRF token
```

Business state is typed and persisted in workflow objects, not kept only in a model conversation. Read/research components can run automatically. Drafts are reversible. External, financial, legal, and account actions are either approval-gated or intentionally absent from the simulation path.

The Admin UI is a thin operator surface. It reads backend-owned status, products, orders, approvals, agent events, and metrics, and submits only validated configuration/actions back to the backend. It does not calculate profit, decide policy, mutate order state directly, or store secrets in the browser.
