from app.workflows.simulation import SimulationWorkflow


def test_complete_simulation_has_all_required_stages():
    result = SimulationWorkflow().run("hoodie")
    assert result["mode"] == "simulation"
    assert result["opportunities"][0]["decision"]["decision"] == "SELL"
    assert result["compliance"]["blocked"] is False
    assert result["approval"].allowed is True
    assert result["listing"].is_publishable is False
    assert result["experiment"].budget == 10
    assert result["order"].status.value == "DELIVERED"
    assert result["reinvestment"].requires_approval is True
    assert result["order"].tracking_number.startswith("SIM-")
    assert "Sendungsnummer" in result["support"]["message_de"]
    assert result["review"].recommended_next_actions
    event_types = {event.event_type.value for event in result["audit"]}
    assert {"MARKET_OPPORTUNITY_FOUND", "PRODUCT_MATCHED", "BUSINESS_REVIEWED"} <= event_types
