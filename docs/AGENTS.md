# Specialist organization

The runtime uses explicit modules and review ownership. The roles below are the internal workstreams required by the completion brief; each produces typed output and is reviewed by policy/tests before a high-impact action.

| Role | Runtime owner | Boundary |
| --- | --- | --- |
| Master orchestrator | `app.brain.Brain` | Coordinates workflow; cannot bypass policy. |
| Repository forensics | project docs/tests | Audits existing code and gaps. |
| Software architect | `app/core` and workflow boundaries | Keeps dependencies directional and small. |
| AI/provider engineer | `app/core/providers.py` | Normalizes model responses; no business arithmetic. |
| Local model engineer | `OpenAICompatibleProvider` + `docs/LOCAL_MODEL.md` | Supports future compatible servers. |
| Market hunter | `MarketHunterAgent` + existing eBay adapter | Returns observed candidates. |
| Supplier hunter | `SupplierHunterAgent` + existing CJ adapter | Returns supplier/inventory evidence. |
| Product matcher | `ProductMatcherAgent` + existing matcher | Emits confidence and conflicts. |
| Profit engine | existing profit modules + `core/economics.py` | Deterministic Decimal arithmetic. |
| Compliance/risk | `ComplianceAgent` | Blocks configured high-risk terms. |
| Listing/content | `ListingAgent` | Drafts only; evidence refs are required. |
| Marketing | `MarketingAgent` | Bounded experiments with stop criteria. |
| Order/fulfillment | `OrderRepository` | State transitions and idempotency. |
| Customer support | `CustomerSupportAgent` | Uses known order state only. |
| Analytics/finance | `AnalyticsAgent` + `PolicyEngine` | Metrics and controlled actions. |
| Security | policy and deployment review | Secrets excluded; live boundary explicit. |
| QA/adversarial review | `tests/` | Exercises malformed output, invalid transitions, risk and budgets. |
| DevOps/release | Docker/CI/docs | Reproducible setup and checks. |

Independent-agent execution is not exposed in this environment, so the organization is represented as isolated runtime workstreams and separate review gates in code and documentation.
