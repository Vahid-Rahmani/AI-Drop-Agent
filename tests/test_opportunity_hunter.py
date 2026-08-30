from app.opportunity_hunter.graph import opportunity_graph


def test_controlled_graph_reaches_sell():
    state = {
        "query": "hoodie",
        "market_products": [{
            "product_id": "m1", "name": "Children pink hoodie", "price": 25, "currency": "EUR",
            "condition": "New", "category": "children clothing", "seller": "fixture", "shipping_cost": 0,
            "url": "", "source": "fixture", "marketplace": "TEST",
        }],
        "supplier_products": [{
            "product_id": "s1", "name": "Children light pink hoodie", "price": 8.6, "currency": "USD",
            "inventory": 300, "category": "children clothing",
            "shipping_options": [{"logistic_name": "GLS", "shipping_cost": 0, "currency": None, "free_shipping": True, "delivery_days": "4-5"}],
        }],
        "fx_rates": {"USD->EUR": 0.92}, "marketplace_fee": 0, "payment_fee": 0, "other_costs": 0,
        "fees_are_test_configuration": True, "fixture_mode": True, "errors": [],
        "inventory_cache": {}, "shipping_cache": {}, "ranked_results": [],
    }
    result = opportunity_graph.invoke(state)
    assert result["ranked_results"][0]["decision"]["decision"] == "SELL"


def test_unreliable_match_is_preserved_as_reject():
    state = {
        "query": "hoodie",
        "market_products": [{
            "product_id": "m1", "name": "Motorcycle aramid hoodie", "price": 50, "currency": "EUR",
            "condition": "New", "category": "motorcycle clothing", "seller": "fixture", "shipping_cost": 0,
            "url": "", "source": "fixture", "marketplace": "TEST",
        }],
        "supplier_products": [{"product_id": "s1", "name": "Children pink hoodie", "price": 8.6, "currency": "USD", "inventory": 300}],
        "fx_rates": {"USD->EUR": 0.92}, "marketplace_fee": 0, "payment_fee": 0, "other_costs": 0,
        "fixture_mode": True, "errors": [], "inventory_cache": {}, "shipping_cache": {},
    }
    result = opportunity_graph.invoke(state)
    item = result["ranked_results"][0]
    assert item["decision"]["decision"] == "REJECT"
    assert item["reason"] == "no_reliable_supplier_match"
