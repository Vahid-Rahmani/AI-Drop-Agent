from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.admin_ui import UI_ROOT
from app.api import app, brain
from app.brain import Brain
from app.core.config import Settings
from app.domain import AppMode, PermissionLevel
from app.security.session import CSRF_COOKIE


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setattr(brain.settings, "app_mode", AppMode.SIMULATION)
    monkeypatch.setattr(brain.settings, "admin_api_key", "ui-admin-key")
    monkeypatch.setattr(brain.settings, "auth_secret", "u" * 32)
    monkeypatch.setattr(brain.settings, "kill_switch", False)
    client = TestClient(app)
    response = client.post("/admin/session", json={"admin_api_key": "ui-admin-key"})
    assert response.status_code == 200
    return client


def csrf_headers(client):
    return {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}


def test_admin_ui_requires_session_and_serves_login_page(monkeypatch):
    monkeypatch.setattr(brain.settings, "auth_secret", "u" * 32)
    client = TestClient(app)
    assert client.get("/admin/status").status_code == 401
    page = client.get("/admin")
    assert page.status_code == 200
    assert "Operator control panel" in page.text
    assert "/admin/static/styles.css" in page.text


def test_admin_headers_and_login_errors_do_not_expose_configuration(monkeypatch):
    monkeypatch.setattr(brain.settings, "auth_secret", "u" * 32)
    monkeypatch.setattr(brain.settings, "admin_api_key", "ui-admin-key")
    client = TestClient(app)
    response = client.get("/admin")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    failed = client.post("/admin/session", json={"admin_api_key": "wrong"})
    assert failed.status_code == 401
    assert "ui-admin-key" not in failed.text


def test_admin_login_dashboard_setup_and_static_assets(admin_client):
    page = admin_client.get("/admin")
    assert page.status_code == 200
    assert "Dashboard" in page.text
    status = admin_client.get("/admin/status")
    assert status.status_code == 200
    assert status.json()["readiness"] in {"READY", "CONFIGURATION_MISSING", "KILL_SWITCH_ACTIVE"}
    setup = admin_client.get("/admin/setup")
    assert setup.status_code == 200
    assert any(item["provider"] == "secret_manager" for item in setup.json()["checks"])
    static = admin_client.get("/admin/static/app.js")
    assert static.status_code == 200
    assert "localStorage" not in static.text
    assert UI_ROOT.joinpath("templates", "index.html").exists()


def test_admin_csrf_kill_switch_and_business_validation(admin_client):
    missing_csrf = admin_client.post("/admin/kill-switch", json={"enabled": True, "confirm": True})
    assert missing_csrf.status_code == 403
    enabled = admin_client.post(
        "/admin/kill-switch",
        json={"enabled": True, "confirm": True},
        headers=csrf_headers(admin_client),
    )
    assert enabled.status_code == 200
    assert enabled.json()["kill_switch"] is True
    disabled = admin_client.post(
        "/admin/kill-switch",
        json={"enabled": False, "confirm": True},
        headers=csrf_headers(admin_client),
    )
    assert disabled.status_code == 200
    invalid = admin_client.post(
        "/admin/business-settings",
        json={"marketplace_fee_rate": "0.8", "payment_fee_rate": "0.3"},
        headers=csrf_headers(admin_client),
    )
    assert invalid.status_code == 422


def test_admin_secret_submission_is_not_stored_or_returned(admin_client, monkeypatch):
    monkeypatch.setattr(brain.settings, "ebay_client_secret", None)
    secret = "do-not-return-this-secret"
    response = admin_client.post(
        "/admin/integrations",
        json={
            "provider": "ebay",
            "environment": "sandbox",
            "client_id": "public-client-id",
            "client_secret": secret,
            "token": "refresh-token-secret",
        },
        headers=csrf_headers(admin_client),
    )
    assert response.status_code == 200
    assert secret not in response.text
    assert "refresh-token-secret" not in response.text
    assert brain.settings.ebay_client_secret is None
    assert brain.settings.ebay_refresh_token is None
    assert response.json()["secret_status"] == "BLOCKED_EXTERNAL"


def test_admin_simulation_products_metrics_and_approvals(admin_client):
    simulation = admin_client.post(
        "/admin/simulation",
        json={"query": "hoodie"},
        headers=csrf_headers(admin_client),
    )
    assert simulation.status_code == 200
    assert simulation.json()["order"]["status"] == "DELIVERED"
    products = admin_client.get("/admin/products")
    assert products.status_code == 200
    assert products.json()[0]["decision"] == "SELL"
    metrics = admin_client.get("/admin/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["orders"] >= 1

    approval = brain.approvals.create(
        "publish_listing",
        "Admin UI test",
        PermissionLevel.REVERSIBLE_EXTERNAL,
        amount=Decimal("1"),
    )
    approvals = admin_client.get("/admin/approvals")
    assert any(item["request_id"] == str(approval.request_id) for item in approvals.json())
    decision = admin_client.post(
        f"/admin/approvals/{approval.request_id}",
        json={"status": "REJECTED"},
        headers=csrf_headers(admin_client),
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"


def test_safe_admin_settings_persist_without_persisting_secrets(tmp_path):
    database_path = str(tmp_path / "admin-settings.db")
    settings = Settings(database_path=database_path, auth_secret="p" * 32, admin_api_key="admin")
    first = Brain(settings=settings)
    first.settings.marketplace_fee_rate = 0.17
    first.store.save_setting("finance_config", first.settings.finance_config().model_dump(mode="json"))
    first.store.save_setting("integration_config", {"ebay_client_id": "public-id"})
    restored = Brain(settings=Settings(database_path=database_path, auth_secret="p" * 32, admin_api_key="admin"))
    assert restored.settings.marketplace_fee_rate == 0.17
    assert restored.settings.ebay_client_id == "public-id"
    assert restored.settings.ebay_client_secret is None
