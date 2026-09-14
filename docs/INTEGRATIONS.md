# Integrations

The simulation does not call external integrations. The live boundaries are implemented in `app/integrations/ebay.py` and `app/integrations/cj.py`, with typed contracts in `marketplace.py` and `supplier.py`.

The eBay adapter covers OAuth refresh, inventory item upsert, offer create/update/end, inventory sync, order sync, bounded retries, normalized errors, and in-process idempotency. The CJ adapter covers product search/details, inventory, shipping quotes, order placement, tracking, cancellation, retries, and normalized errors. Both adapters accept a fixtureable HTTP client and fail clearly when credentials are absent.

Before activation, configure a secret manager, verify account-specific fees/tax/return rules, approve the marketplace/supplier accounts, run sandbox contract checks, and then perform a human-reviewed production canary. The final network execution is external by design.
