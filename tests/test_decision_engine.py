from app.decision_engine.engine import make_product_decision


def profit(net=10, margin=30, score=80, **extra):
    return {"profit_calculation_allowed": True, "profit_score": score, "net_profit": net, "profit_margin_percent": margin, "roi_percent": 50, **extra}


def test_sell():
    result = make_product_decision(85, {"match_score": 90, "match_quality": "strong"}, 90, profit(margin=40, score=92), 300, "4-5")
    assert result["decision"] == "SELL"


def test_watch():
    result = make_product_decision(65, {"match_score": 75, "match_quality": "probable"}, 65, profit(net=2, margin=10, score=65), 15, 8)
    assert result["decision"] == "WATCH"


def test_bad_match_zero_inventory_negative_profit_and_currency_block():
    assert make_product_decision(100, {"match_score": 100, "match_quality": "reject"}, 100, profit(), 300, 4)["decision"] == "REJECT"
    assert make_product_decision(100, {"match_score": 90, "match_quality": "strong"}, 100, profit(net=-1, margin=-1), 300, 4)["decision"] == "REJECT"
    result = make_product_decision(100, {"match_score": 90, "match_quality": "strong"}, 100, profit(reason="currency_conversion_required", profit_calculation_allowed=False), 300, 4)
    assert result["decision"] == "REJECT"
    assert "Currency conversion required" in result["blocking_reasons"]
    assert make_product_decision(100, {"match_score": 90, "match_quality": "strong"}, 100, profit(), 0, 4)["decision"] == "REJECT"


def test_boundaries_and_clamping():
    at_sell = make_product_decision(80, {"match_score": 80, "match_quality": "probable"}, 80, profit(margin=20, score=80), 100, 5)
    below_sell = make_product_decision(79.9, {"match_score": 79.9, "match_quality": "probable"}, 79.9, profit(margin=20, score=79.9), 100, 5)
    watch = make_product_decision(66.25, {"match_score": 75, "match_quality": "probable"}, 60, profit(margin=1, score=60), 100, 5)
    assert at_sell["decision"] == "SELL"
    assert below_sell["decision"] != "SELL"
    assert watch["decision"] == "WATCH"
    assert 0 <= at_sell["decision_score"] <= 100


def test_missing_metrics_reject():
    result = make_product_decision(100, {"match_score": 100, "match_quality": "strong"}, 100, {"profit_calculation_allowed": True}, 100, 5)
    assert result["decision"] == "REJECT"
    assert "Required profit metrics missing" in result["blocking_reasons"]
