"""Unified V1 opportunity workflow.

The graph orchestrates existing engines.  It does not reimplement matching,
profit formulas, FX conversion, or decision thresholds.
"""

from __future__ import annotations

import math
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.decision_engine.engine import make_product_decision
from app.fx.provider import FXProviderError, get_exchange_rate
from app.fees.ebay import calculate_ebay_fees
from app.market_hunter.scoring import score_products
from app.market_hunter.sources.ebay import normalize_products, search_products as ebay_search
from app.opportunity_hunter.state import OpportunityHunterState
from app.product_matcher.matcher import get_best_match, match_products
from app.profit_engine.bridge import calculate_market_supplier_profit
from app.supplier_hunter.cj_hunter import (
    calculate_supplier_score,
    get_product_id,
    get_product_price,
    get_verified_de_inventory,
)
from app.supplier_hunter.sources.cj import extract_products, get_access_token as cj_access_token
from app.supplier_hunter.sources.cj import search_products as cj_search
from app.supplier_hunter.sources.cj_shipping import calculate_shipping


RELIABLE_MATCH_THRESHOLD = 75.0
DELIVERY_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
DECISION_ORDER = {"SELL": 0, "WATCH": 1, "REJECT": 2}


def _error(stage: str, market_id: str = "", supplier_id: str = "", error: Any = "") -> dict[str, str]:
    return {
        "stage": stage,
        "market_product_id": market_id,
        "supplier_product_id": supplier_id,
        "error": str(error),
    }


def _id(product: dict) -> str:
    return str(product.get("product_id") or product.get("id") or product.get("pid") or product.get("productId") or "").strip()


def _delivery_max(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    numbers = [float(item) for item in DELIVERY_NUMBER_RE.findall(str(value))]
    return max(numbers) if numbers else None


def _choose_shipping(options: list[dict]) -> dict | None:
    """Choose known lowest cost, then shortest known delivery deterministically."""
    valid: list[tuple[float, float, int, dict]] = []
    for index, option in enumerate(options):
        cost = option.get("shipping_cost")
        try:
            cost_value = float(cost)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(cost_value) or cost_value < 0:
            continue
        # A zero cost is valid only when the shipping engine explicitly marked it free.
        if cost_value == 0 and option.get("free_shipping") is not True:
            continue
        delivery = _delivery_max(option.get("delivery_days"))
        valid.append((cost_value, delivery if delivery is not None else float("inf"), index, option))
    if not valid:
        return None
    return min(valid, key=lambda item: (item[0], item[1], item[2]))[3]


def _fx_pair(supplier: dict, market: dict, shipping: dict | None = None) -> tuple[str, str] | None:
    target = str(market.get("currency") or "").upper()
    source = str(supplier.get("currency") or "").upper()
    if source == target:
        source = str((shipping or {}).get("currency") or target).upper()
    if source == target:
        return None
    return source, target


def search_market_node(state: OpportunityHunterState) -> dict:
    if state.get("fixture_mode"):
        products = state.get("market_products", [])
        return {"market_products": products, "market_scores": score_products(products) if products else {}}
    results = ebay_search(query=state.get("query", "hoodie"), limit=5)
    products = normalize_products(results)
    return {
        "market_products": products,
        "market_scores": score_products(products),
    }


def search_suppliers_node(state: OpportunityHunterState) -> dict:
    if state.get("fixture_mode"):
        return {"supplier_products": state.get("supplier_products", [])}
    results = cj_search(keyword=state.get("query", "hoodie"), page=1, size=50, country_code="DE")
    return {"supplier_products": extract_products(results)}


def match_products_node(state: OpportunityHunterState) -> dict:
    suppliers = state.get("supplier_products", [])
    by_id = {_id(product): product for product in suppliers if _id(product)}
    matches: list[dict] = []
    for market in state.get("market_products", []):
        market_id = _id(market)
        ranked = match_products(market, suppliers)
        best = get_best_match(market, suppliers)
        selected = best or (ranked[0] if ranked else {"match_score": 0.0, "match_quality": "reject", "supplier_product_id": ""})
        supplier_id = str(selected.get("supplier_product_id", ""))
        matches.append(
            {
                "market_product_id": market_id,
                "market_product": market,
                "market_score": state.get("market_scores", {}).get(market_id, {}).get("opportunity_score"),
                "match_result": selected,
                "supplier_product": by_id.get(supplier_id),
                "reliable": best is not None and float(best.get("match_score", 0)) >= RELIABLE_MATCH_THRESHOLD,
                "reason": None if best else "no_reliable_supplier_match",
            }
        )
    return {"matches": matches}


def verify_suppliers_node(state: OpportunityHunterState) -> dict:
    cache = dict(state.get("inventory_cache", {}))
    verified = dict(state.get("verified_suppliers", {}))
    errors = list(state.get("errors", []))
    token: str | None = None
    for item in state.get("matches", []):
        if not item.get("reliable") or not item.get("supplier_product"):
            continue
        supplier = item["supplier_product"]
        supplier_id = _id(supplier)
        market_id = item["market_product_id"]
        if not supplier_id:
            errors.append(_error("inventory", market_id, error="supplier product ID missing"))
            continue
        try:
            if state.get("fixture_mode") and supplier.get("inventory") is not None:
                inventory = int(supplier["inventory"])
            else:
                if supplier_id not in cache:
                    if token is None:
                        token = cj_access_token()
                    cache[supplier_id] = {"inventory": get_verified_de_inventory(supplier_id, token)}
                inventory = int(cache[supplier_id]["inventory"])
            if inventory <= 0:
                errors.append(_error("inventory", market_id, supplier_id, "no verified German inventory"))
                continue
            price = get_product_price(supplier)
            if price is None and supplier.get("price") is not None:
                price = float(supplier["price"])
            supplier_score = supplier.get("supplier_score")
            if supplier_score is None:
                supplier_score = calculate_supplier_score(price, inventory)
            verified[supplier_id] = {
                "product": supplier,
                "inventory": inventory,
                "supplier_score": float(supplier_score),
            }
            item["verified_supplier"] = verified[supplier_id]
        except Exception as error:
            errors.append(_error("inventory", market_id, supplier_id, error))
    return {"matches": state.get("matches", []), "verified_suppliers": verified, "inventory_cache": cache, "errors": errors}


def calculate_shipping_node(state: OpportunityHunterState) -> dict:
    cache = dict(state.get("shipping_cache", {}))
    shipping_results = dict(state.get("shipping_results", {}))
    errors = list(state.get("errors", []))
    for item in state.get("matches", []):
        verified = item.get("verified_supplier")
        if not item.get("reliable") or not verified:
            continue
        supplier_id = _id(verified["product"])
        market_id = item["market_product_id"]
        try:
            if supplier_id not in cache:
                if state.get("fixture_mode") and verified["product"].get("shipping_options") is not None:
                    cache[supplier_id] = verified["product"]["shipping_options"]
                else:
                    cache[supplier_id] = calculate_shipping(supplier_id, destination_country="DE", source_country="DE")
            selected = _choose_shipping(cache[supplier_id])
            if selected is None:
                errors.append(_error("shipping", market_id, supplier_id, "no valid shipping option"))
                continue
            shipping_results[market_id] = selected
            item["shipping_option"] = selected
        except Exception as error:
            errors.append(_error("shipping", market_id, supplier_id, error))
    return {"matches": state.get("matches", []), "shipping_results": shipping_results, "shipping_cache": cache, "errors": errors}


def calculate_profit_node(state: OpportunityHunterState) -> dict:
    profits = dict(state.get("profit_results", {}))
    fx_results = dict(state.get("fx_results", {}))
    ebay_fee_results = dict(state.get("ebay_fee_results", {}))
    errors = list(state.get("errors", []))
    for item in state.get("matches", []):
        market_id = item["market_product_id"]
        match_result = item["match_result"]
        if not item.get("reliable"):
            profits[market_id] = {"profit_calculation_allowed": False, "reason": "no_reliable_supplier_match"}
            continue
        verified = item.get("verified_supplier")
        shipping = item.get("shipping_option")
        if not verified or not shipping:
            profits[market_id] = {"profit_calculation_allowed": False, "reason": "upstream_verification_failed"}
            continue
        market = item["market_product"]
        supplier = verified["product"]
        fee_mode = state.get("fee_mode", "UNKNOWN").upper()
        fee_result = calculate_ebay_fees(
            selling_price=market.get("price"),
            currency=market.get("currency"),
            category_id=market.get("category_id"),
            shipping_charged_to_buyer=market.get("shipping_cost") or 0,
            seller_plan=state.get("seller_plan"),
            fee_rate=state.get("fee_rate") if fee_mode == "EXPLICIT" else None,
            fixed_fee=state.get("fixed_fee") if fee_mode == "EXPLICIT" else None,
        )
        ebay_fee_results[market_id] = fee_result
        if not fee_result["fee_calculation_allowed"]:
            profits[market_id] = {"profit_calculation_allowed": False, "reason": "ebay_fee_unknown"}
            continue
        pair = _fx_pair(supplier, market, shipping)
        rate: float | None = None
        if pair is not None:
            pair_key = f"{pair[0]}->{pair[1]}"
            try:
                default_mode = "EXPLICIT" if state.get("fixture_mode") else "LIVE"
                if state.get("fx_mode", default_mode).upper() == "LIVE":
                    fx_result = fx_results.get(pair_key)
                    if fx_result is None:
                        fx_result = get_exchange_rate(pair[0], pair[1])
                        fx_results[pair_key] = fx_result
                    rate = fx_result["rate"]
                else:
                    rate = state.get("fx_rates", {}).get(pair_key)
            except FXProviderError as error:
                errors.append(_error("fx", market_id, _id(supplier), error))
                profits[market_id] = {"profit_calculation_allowed": False, "reason": "currency_conversion_required"}
                continue
        try:
            profits[market_id] = calculate_market_supplier_profit(
                market_product=market,
                supplier_product=supplier,
                shipping_option=shipping,
                fx_rate=rate,
                marketplace_fee=state.get("marketplace_fee"),
                payment_fee=state.get("payment_fee"),
                other_costs=state.get("other_costs", 0),
                match_result=match_result,
                fee_result=fee_result,
            )
        except Exception as error:
            errors.append(_error("profit", market_id, _id(supplier), error))
            profits[market_id] = {"profit_calculation_allowed": False, "reason": str(error)}
    return {"profit_results": profits, "fx_results": fx_results, "ebay_fee_results": ebay_fee_results, "errors": errors}


def make_decisions_node(state: OpportunityHunterState) -> dict:
    decisions: dict[str, dict] = {}
    for item in state.get("matches", []):
        market_id = item["market_product_id"]
        verified = item.get("verified_supplier") or {}
        profit = state.get("profit_results", {}).get(market_id, {})
        decision = make_product_decision(
            market_score=item.get("market_score"),
            match_result=item.get("match_result", {}),
            supplier_score=verified.get("supplier_score", 0),
            profit_result=profit,
            inventory=verified.get("inventory"),
            delivery_days=(item.get("shipping_option") or {}).get("delivery_days"),
        )
        decisions[market_id] = decision
    return {"decisions": decisions}


def rank_results_node(state: OpportunityHunterState) -> dict:
    results: list[dict] = []
    for item in state.get("matches", []):
        market = item["market_product"]
        market_id = item["market_product_id"]
        supplier = item.get("verified_supplier") or {}
        supplier_product = supplier.get("product")
        decision = state.get("decisions", {}).get(market_id, {})
        results.append(
            {
                "market_product_id": market_id,
                "market_product": market,
                "market_name": market.get("name", ""),
                "market_score": item.get("market_score"),
                "supplier_product": supplier_product,
                "matched_supplier": supplier_product.get("name", supplier_product.get("nameEn")) if supplier_product else None,
                "match_result": item.get("match_result"),
                "inventory": supplier.get("inventory"),
                "supplier_score": supplier.get("supplier_score"),
                "shipping_option": item.get("shipping_option"),
                "profit_result": state.get("profit_results", {}).get(market_id),
                "decision": decision,
                "reason": item.get("reason") or (decision.get("blocking_reasons") or [None])[0],
            }
        )
    results.sort(key=lambda result: (DECISION_ORDER.get(result["decision"].get("decision", "REJECT"), 2), result["decision"].get("decision_score") is None, -(result["decision"].get("decision_score") or 0)))
    return {"ranked_results": results}


def build_opportunity_graph():
    builder = StateGraph(OpportunityHunterState)
    builder.add_node("search_market", search_market_node)
    builder.add_node("search_suppliers", search_suppliers_node)
    builder.add_node("match_products", match_products_node)
    builder.add_node("verify_suppliers", verify_suppliers_node)
    builder.add_node("calculate_shipping", calculate_shipping_node)
    builder.add_node("calculate_profit", calculate_profit_node)
    builder.add_node("make_decisions", make_decisions_node)
    builder.add_node("rank_results", rank_results_node)
    builder.add_edge(START, "search_market")
    builder.add_edge("search_market", "search_suppliers")
    builder.add_edge("search_suppliers", "match_products")
    builder.add_edge("match_products", "verify_suppliers")
    builder.add_edge("verify_suppliers", "calculate_shipping")
    builder.add_edge("calculate_shipping", "calculate_profit")
    builder.add_edge("calculate_profit", "make_decisions")
    builder.add_edge("make_decisions", "rank_results")
    builder.add_edge("rank_results", END)
    return builder.compile()


opportunity_graph = build_opportunity_graph()


def _initial_state(query: str = "hoodie") -> OpportunityHunterState:
    return {
        "query": query,
        "market_products": [], "market_scores": {}, "supplier_products": [], "matches": [],
        "verified_suppliers": {}, "shipping_results": {}, "profit_results": {}, "decisions": {},
        "ranked_results": [], "errors": [], "fx_rates": {}, "fx_mode": "LIVE", "fx_results": {}, "ebay_fee_results": {},
        "marketplace_fee": None, "payment_fee": None, "other_costs": 0.0,
        "fees_are_test_configuration": False, "fee_mode": "UNKNOWN", "fee_rate": None, "fixed_fee": None, "fixture_mode": False,
        "inventory_cache": {}, "shipping_cache": {},
    }


def _controlled_state() -> OpportunityHunterState:
    market = {
        "product_id": "market-1", "name": "Children's pink hoodie", "price": 25.0, "currency": "EUR",
        "condition": "New", "category": "children clothing", "seller": "fixture", "shipping_cost": 0.0,
        "url": "", "source": "fixture", "marketplace": "TEST",
    }
    supplier = {
        "product_id": "supplier-1", "name": "Children's light pink hoodie, size 104", "price": 8.60,
        "currency": "USD", "inventory": 300, "category": "children clothing",
        "shipping_options": [{"logistic_name": "GLS DE to DE", "shipping_cost": 0.0, "currency": None, "free_shipping": True, "delivery_days": "4-5"}],
    }
    state = _initial_state("hoodie")
    state.update({"fixture_mode": True, "fx_mode": "EXPLICIT", "fx_rates": {"USD->EUR": 0.92}, "fee_mode": "EXPLICIT", "fee_rate": 10.0, "fixed_fee": 0.35, "payment_fee": 0.0, "market_products": [market], "supplier_products": [supplier]})
    return state


def _print_results(result: OpportunityHunterState) -> None:
    print("\n" + "=" * 60)
    print("FINAL OPPORTUNITIES")
    print("=" * 60)
    for index, item in enumerate(result.get("ranked_results", []), start=1):
        decision = item["decision"]
        profit = item.get("profit_result") or {}
        match = item.get("match_result") or {}
        shipping = item.get("shipping_option") or {}
        supplier = item.get("supplier_product") or {}
        print(f"\n{index}. {item['market_name']}")
        print(f"Market Score: {item.get('market_score')}")
        print(f"Matched Supplier: {item.get('matched_supplier') or 'None'}")
        print(f"Match Score: {match.get('match_score')}")
        print(f"CJ Price: {supplier.get('price', supplier.get('sellPrice'))}")
        print(f"DE Inventory: {item.get('inventory')}")
        print(f"Shipping: {shipping.get('logistic_name', 'None')} / {shipping.get('shipping_cost')}")
        print(f"Delivery: {shipping.get('delivery_days', 'None')}")
        print(f"Landed Cost: {profit.get('landed_cost')}")
        print(f"Net Profit: {profit.get('net_profit')}")
        print(f"Margin: {profit.get('profit_margin_percent')}")
        print(f"Profit Score: {profit.get('profit_score')}")
        print(f"Decision Score: {decision.get('decision_score')}")
        print(f"Decision: {decision.get('decision')}")
        print(f"Reason: {item.get('reason') or decision.get('blocking_reasons') or decision.get('reasons')}")
    print("\n" + "=" * 60)
    print("RUN CONFIGURATION")
    print("=" * 60)
    default_mode = "EXPLICIT" if result.get("fixture_mode") else "LIVE"
    if result.get("fx_mode", default_mode).upper() == "LIVE":
        fx_results = result.get("fx_results", {})
        if fx_results:
            for pair, fx in fx_results.items():
                print(f"FX: {pair.replace('->', ' -> ')} = {fx['rate']}")
                print(f"Source: {fx['source']}")
                print(f"Timestamp/Date: {fx['timestamp']}")
            print("Mode: LIVE")
        else:
            print("FX: LIVE mode (no cross-currency conversion was required)")
            print("Mode: LIVE")
    else:
        for pair, rate in result.get("fx_rates", {}).items():
            print(f"FX: {pair.replace('->', ' -> ')} = {rate}")
        print("Mode: EXPLICIT/TEST (not live FX)")
    fee_results = result.get("ebay_fee_results", {})
    if result.get("fee_mode", "UNKNOWN").upper() == "EXPLICIT":
        fee = next(iter(fee_results.values()), {})
        print(f"Marketplace Fee: {fee.get('total_marketplace_fee', 'UNKNOWN')}")
        print("Fee Source: Configured eBay Germany fee profile")
        print("Fee Verified: False")
        print("Configured test value - NOT VERIFIED EBAY FEE")
    else:
        print("Marketplace Fee: UNKNOWN")
        print("Fee Source: eBay fee data unavailable for exact account/category calculation")
        print("Fee Verified: False")
    print("Payment Fee: None (no separate verified payment fee; not double-counted)")
    counts = {decision: sum(item["decision"].get("decision") == decision for item in result.get("ranked_results", [])) for decision in DECISION_ORDER}
    print(f"\nDecision counts: {counts}")
    print(f"Errors: {result.get('errors', [])}")


if __name__ == "__main__":
    print("=" * 60)
    print("AI DROPSHIPPING OPPORTUNITY HUNTER")
    print("=" * 60)
    print("\nQuery: hoodie")
    try:
        output = opportunity_graph.invoke(_initial_state("hoodie"))
        print(f"\nMarket products found: {len(output.get('market_products', []))}")
        print(f"CJ Germany suppliers found: {len(output.get('supplier_products', []))}")
        _print_results(output)
    except Exception as error:
        print(f"\nOpportunity Hunter stopped: {error}")

    print("\nCONTROLLED SUCCESS INTEGRATION")
    controlled = opportunity_graph.invoke(_controlled_state())
    _print_results(controlled)
