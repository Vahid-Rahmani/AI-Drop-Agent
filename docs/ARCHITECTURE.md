# Architecture

```text
FastAPI / CLI
    -> Brain (orchestrator)
        -> SimulationWorkflow
            -> research, supplier, matcher, economics, compliance
            -> policy decision
            -> listing and experiment drafts
            -> order state machine
            -> support and analytics review
        -> provider boundary (mock / OpenAI-compatible / future local model)
    -> append-only audit log
```

Business state is typed and persisted in workflow objects, not kept only in a model conversation. Read/research components can run automatically. Drafts are reversible. External, financial, legal, and account actions are either approval-gated or intentionally absent from the simulation path.
