from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_and_simulation_endpoints():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "simulation"

    response = client.post("/simulate", json={"query": "hoodie"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "simulation"
    assert payload["order"]["status"] == "DELIVERED"
    assert payload["listing"]["is_publishable"] is False


def test_profit_endpoint_returns_break_even_metrics():
    response = client.post(
        "/profit/calculate",
        json={
            "selling_price": "25",
            "supplier_price": "8",
            "shipping_cost": "2",
            "marketplace_fee_rate": "0.1",
            "payment_fee_rate": "0.02",
            "advertising_rate": "0.05",
            "expected_return_rate": "0.04",
            "operating_cost": "0.5",
            "vat_rate": "0.19",
            "discount_rate": "0",
            "currency": "EUR",
        },
    )
    assert response.status_code == 200
    assert response.json()["is_profitable"] is True
    assert "break_even_roas" in response.json()
