"""Deterministic decision engine for verified product opportunities."""

from __future__ import annotations

import math
import re
from typing import Any


MARKET_WEIGHT = 0.20
MATCH_WEIGHT = 0.25
SUPPLIER_WEIGHT = 0.20
PROFIT_WEIGHT = 0.35

RELIABLE_MATCH_THRESHOLD = 75.0
SELL_SCORE_THRESHOLD = 80.0
SELL_MARGIN_THRESHOLD = 20.0
WATCH_SCORE_THRESHOLD = 65.0

ALLOWED_MATCH_QUALITIES = {"strong", "probable"}
DELIVERY_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _bounded_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score):
        return None
    return max(0.0, min(100.0, score))


def _delivery_max_days(value: str | int | None) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) and value >= 0 else None
    numbers = [float(item) for item in DELIVERY_NUMBER_RE.findall(str(value))]
    return max(numbers) if numbers else None


def _metric(profit_result: dict, key: str) -> float | None:
    value = profit_result.get(key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def make_product_decision(
    market_score: float,
    match_result: dict,
    supplier_score: float,
    profit_result: dict,
    inventory: int | None = None,
    delivery_days: str | int | None = None,
) -> dict[str, Any]:
    """Return an explainable SELL, WATCH, or REJECT decision.

    Safety gates are evaluated before the weighted decision score.  A high
    market opportunity cannot compensate for an unsafe match or profit result.
    """
    match_result = match_result if isinstance(match_result, dict) else {}
    profit_result = profit_result if isinstance(profit_result, dict) else {}
    market_value = _bounded_score(market_score)
    match_value = _bounded_score(match_result.get("match_score"))
    supplier_value = _bounded_score(supplier_score)
    profit_value = _bounded_score(profit_result.get("profit_score"))
    quality = str(match_result.get("match_quality", "")).lower()

    net_profit = _metric(profit_result, "net_profit")
    margin = _metric(profit_result, "profit_margin_percent")
    roi = _metric(profit_result, "roi_percent")

    reasons: list[str] = []
    warnings: list[str] = []
    blocking_reasons: list[str] = []

    if quality not in ALLOWED_MATCH_QUALITIES or match_value is None or match_value < RELIABLE_MATCH_THRESHOLD:
        blocking_reasons.append("Unreliable product match")
    else:
        reasons.append("Reliable product match")

    if profit_result.get("profit_calculation_allowed") is not True:
        blocking_reasons.append("Profit calculation not allowed")
    if profit_result.get("currency_conversion_required") is True or profit_result.get("reason") == "currency_conversion_required":
        blocking_reasons.append("Currency conversion required")

    if market_value is None or supplier_value is None:
        blocking_reasons.append("Required decision metrics missing")

    if inventory is not None and inventory <= 0:
        blocking_reasons.append("No verified supplier inventory")
    elif inventory is not None:
        reasons.append("Verified German supplier inventory")
        if inventory >= 100:
            reasons.append("Healthy supplier inventory")
        elif inventory < 20:
            warnings.append("Low supplier inventory")
    else:
        warnings.append("Supplier inventory unavailable")

    required_metrics = {
        "profit_score": profit_value,
        "net_profit": net_profit,
        "profit_margin_percent": margin,
        "roi_percent": roi,
    }
    missing_metrics = [key for key, value in required_metrics.items() if value is None]
    if missing_metrics:
        blocking_reasons.append("Required profit metrics missing")
    if net_profit is not None and net_profit <= 0:
        blocking_reasons.append("Net profit is not positive")
    if margin is not None and margin <= 0:
        blocking_reasons.append("Profit margin is not positive")

    max_delivery = _delivery_max_days(delivery_days)
    if max_delivery is None:
        warnings.append("Delivery time unavailable")
    elif max_delivery <= 5:
        reasons.append("Fast domestic delivery")

    score: float | None = None
    decision = "REJECT"
    if not blocking_reasons and market_value is not None and supplier_value is not None:
        score = max(
            0.0,
            min(
                100.0,
                market_value * MARKET_WEIGHT
                + match_value * MATCH_WEIGHT
                + supplier_value * SUPPLIER_WEIGHT
                + profit_value * PROFIT_WEIGHT,
            ),
        )
        score = round(score, 1)
        if score >= SELL_SCORE_THRESHOLD and margin >= SELL_MARGIN_THRESHOLD:
            decision = "SELL"
            reasons.append("Profit margin above SELL threshold")
        elif score >= WATCH_SCORE_THRESHOLD and margin > 0:
            decision = "WATCH"
            warnings.append("Decision score does not meet SELL threshold")

    return {
        "decision": decision,
        "decision_score": score,
        "market_score": market_value,
        "match_score": match_value,
        "supplier_score": supplier_value,
        "profit_score": profit_value,
        "net_profit": net_profit,
        "profit_margin_percent": margin,
        "roi_percent": roi,
        "reasons": reasons,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
    }


def _profit(net_profit: float, margin: float, profit_score: float) -> dict[str, Any]:
    return {
        "profit_calculation_allowed": True,
        "profit_score": profit_score,
        "net_profit": net_profit,
        "profit_margin_percent": margin,
        "roi_percent": 100.0,
    }


def _base_inputs() -> tuple[dict, dict]:
    match = {"match_score": 90, "match_quality": "strong"}
    profit = _profit(13.59, 40, 92)
    return match, profit


def _print_tests() -> None:
    match, profit = _base_inputs()
    scenarios = (
        ("TEST A - SELL", 85, match, 90, profit, 300, "4-5"),
        ("TEST B - WATCH", 65, {"match_score": 75, "match_quality": "probable"}, 65, _profit(2, 10, 65), 15, "6-8"),
        ("TEST C - BAD MATCH", 100, {"match_score": 100, "match_quality": "reject"}, 100, profit, 300, 4),
        ("TEST D - NO PROFIT", 100, match, 100, _profit(-1, -4, 0), 300, 4),
        ("TEST E - CURRENCY BLOCK", 100, match, 100, {**profit, "profit_calculation_allowed": False, "reason": "currency_conversion_required"}, 300, 4),
        ("TEST F - ZERO INVENTORY", 100, match, 100, profit, 0, 4),
    )
    print("DECISION ENGINE TESTS")
    for label, market, match_data, supplier, profit_data, inventory, delivery in scenarios:
        result = make_product_decision(market, match_data, supplier, profit_data, inventory, delivery)
        print(f"\n{label}: {result['decision']} ({result['decision_score']})")
        print(f"  Reasons: {result['reasons']}")
        print(f"  Warnings: {result['warnings']}")
        print(f"  Blocking: {result['blocking_reasons']}")

    boundaries = (
        ("SELL boundary", make_product_decision(80, {"match_score": 80, "match_quality": "probable"}, 80, _profit(1, 20, 80), 100, 5)),
        ("Below SELL", make_product_decision(79.9, {"match_score": 79.9, "match_quality": "probable"}, 79.9, _profit(1, 20, 79.9), 100, 5)),
        ("WATCH boundary", make_product_decision(66.25, {"match_score": 75, "match_quality": "probable"}, 60, _profit(1, 1, 60), 100, 5)),
    )
    print("\nBOUNDARY TESTS")
    for label, result in boundaries:
        print(f"{label}: {result['decision']} ({result['decision_score']})")


if __name__ == "__main__":
    _print_tests()
