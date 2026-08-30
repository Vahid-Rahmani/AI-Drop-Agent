from typing import Any, TypedDict


class OpportunityHunterState(TypedDict, total=False):
    query: str
    market_products: list[dict]
    market_scores: dict[str, dict]
    supplier_products: list[dict]
    matches: list[dict]
    verified_suppliers: dict[str, dict]
    shipping_results: dict[str, list[dict]]
    profit_results: dict[str, dict]
    decisions: dict[str, dict]
    ranked_results: list[dict]
    errors: list[dict[str, Any]]

    # Runtime configuration.  Secrets are intentionally not part of state.
    fx_rates: dict[str, float]
    fx_mode: str
    fx_results: dict[str, dict]
    ebay_fee_results: dict[str, dict]
    marketplace_fee: float | None
    payment_fee: float | None
    other_costs: float | None
    fees_are_test_configuration: bool
    fee_mode: str
    fee_rate: float | None
    fixed_fee: float | None
    fixture_mode: bool

    # Small in-run caches prevent duplicate CJ calls.
    inventory_cache: dict[str, dict]
    shipping_cache: dict[str, list[dict]]
