# Workflows

`SimulationWorkflow.run()` is the reference workflow. It runs every business stage using deterministic fixtures and records events with workflow/correlation IDs. The existing `opportunity_hunter` LangGraph remains the research/economics pipeline and is reused by the simulation rather than reimplemented.

The order path is strictly monotonic for fulfillment: `CREATED -> PAYMENT_CONFIRMED -> FULFILLMENT_PENDING -> SUPPLIER_ORDER_CREATED -> SHIPPED -> DELIVERED`, with explicit return/refund branches. Duplicate transition requests are idempotent when their key repeats; a new key cannot bypass the state machine.
