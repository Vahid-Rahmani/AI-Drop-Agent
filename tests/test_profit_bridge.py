from app.profit_engine.bridge import calculate_market_supplier_profit


MARKET = {"name": "Children's pink hoodie", "price": 25.0, "currency": "EUR"}
SUPPLIER = {"name": "Children's light pink hoodie", "price": 8.60, "currency": "USD"}
MATCH = {"match_score": 75.6, "match_quality": "probable"}
FREE = {"shipping_cost": 0.0, "currency": None, "free_shipping": True}


def bridge(shipping=FREE, rate=0.92, match=MATCH):
    return calculate_market_supplier_profit(MARKET, SUPPLIER, shipping, rate, 3.0, 0.5, 0, match)


def test_valid_fx_bridge_calculates_profit():
    result = bridge()
    assert result["profit_calculation_allowed"]
    assert result["supplier_converted_price"] == 7.91
    assert 0 <= result["profit_score"] <= 100


def test_missing_fx_rate_blocks():
    result = bridge(rate=None)
    assert not result["profit_calculation_allowed"]
    assert result["reason"] == "currency_conversion_required"


def test_unreliable_match_blocks():
    result = bridge(match={"match_score": 0, "match_quality": "reject"})
    assert result["reason"] == "unreliable_product_match"


def test_unknown_positive_shipping_currency_blocks():
    result = bridge(shipping={"shipping_cost": 4.99, "currency": None})
    assert result["reason"] == "shipping_currency_unknown"
