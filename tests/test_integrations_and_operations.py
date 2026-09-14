from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import app, brain
from app.core.config import Settings
from app.core.finance_config import FinanceConfig
from app.core.http import SafeHttpClient
from app.domain import AppMode
from app.integrations.cj import CJSupplierProvider
from app.integrations.ebay import EbayMarketplaceProvider
from app.integrations.marketplace import ExternalDependencyError, ListingPayload
from app.security.auth import Role, TokenService
from app.workers import Job, Worker


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/identity/v1/oauth2/token"):
            return FakeResponse(payload={"access_token": "fixture-token", "expires_in": 3600})
        if url.endswith("/inventory_item/sku-1"):
            return FakeResponse(payload={"ok": True})
        if url.endswith("/offer"):
            return FakeResponse(payload={"offerId": "offer-1"})
        if url.endswith("/inventory_item/sku-2"):
            return FakeResponse(
                payload={"availability": {"shipToLocationAvailability": {"quantity": 4}}}
            )
        if url.endswith("/order"):
            return FakeResponse(payload={"orders": [{"orderId": "order-1", "orderFulfillmentStatus": "NOT_STARTED"}]})
        if url.endswith("/product/list"):
            return FakeResponse(payload={"data": [{"pid": "cj-1", "productNameEn": "Fixture item", "stock": 8}]})
        if url.endswith("/product/stock"):
            return FakeResponse(payload={"data": {"stock": 8}})
        if url.endswith("/shopping/order/create"):
            return FakeResponse(payload={"data": {"orderId": "cj-order-1"}})
        if url.endswith("/shopping/order/getOrderDetail"):
            return FakeResponse(payload={"data": {"trackingNumber": "TRACK-1", "status": "SHIPPED"}})
        return FakeResponse(payload={"data": {}})


def test_ebay_fixture_adapter_refreshes_token_and_is_idempotent():
    transport = FakeTransport()
    client = SafeHttpClient({"api.sandbox.ebay.com"}, client=transport)
    provider = EbayMarketplaceProvider(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        client=client,
        sleep=lambda _: None,
    )
    payload = ListingPayload(
        sku="sku-1",
        title="Fixture item",
        description="Grounded fixture",
        price=Decimal("25"),
        currency="EUR",
        quantity=3,
        category_id="123",
    )
    first = provider.create_listing(payload, "request-1")
    second = provider.create_listing(payload, "request-1")
    assert first.listing_id == "offer-1"
    assert second == first
    assert [call[0] for call in transport.calls] == ["POST", "PUT", "POST"]
    assert provider.sync_inventory("sku-2").quantity == 4
    assert provider.sync_orders()[0].order_id == "order-1"


def test_ebay_missing_credentials_never_attempts_network():
    provider = EbayMarketplaceProvider(client=SafeHttpClient({"api.sandbox.ebay.com"}))
    with pytest.raises(ExternalDependencyError):
        provider.sync_inventory("sku-1")


def test_cj_fixture_adapter_covers_supplier_contract():
    transport = FakeTransport()
    client = SafeHttpClient({"developers.cjdropshipping.com"}, client=transport)
    provider = CJSupplierProvider(access_token="cj-token", client=client, sleep=lambda _: None)
    assert provider.search_products("fixture")[0].product_id == "cj-1"
    assert provider.get_inventory("cj-1") == 8
    order = provider.place_order("cj-1", 1, {"country": "DE"}, "order-key")
    assert order.order_id == "cj-order-1"
    assert provider.place_order("cj-1", 1, {"country": "DE"}, "order-key") == order
    assert provider.get_tracking(order.order_id).tracking_number == "TRACK-1"


def test_finance_config_rejects_unbounded_cost_rates_and_live_requires_verification():
    with pytest.raises(ValueError):
        FinanceConfig(
            version="bad",
            vat_rate=Decimal("0.19"),
            marketplace_fee_rate=Decimal("0.6"),
            payment_fee_rate=Decimal("0.3"),
            advertising_rate=Decimal("0.2"),
            expected_return_rate=Decimal("0"),
            shipping_cost=Decimal("1"),
            operating_cost=Decimal("0"),
            discount_rate=Decimal("0"),
        )
    settings = Settings(
        app_mode="live",
        auth_secret="a" * 32,
        admin_api_key="admin",
        webhook_secret="b" * 32,
        database_url="postgresql://db/app",
    )
    assert any("verified" in error for error in settings.production_errors())


def test_live_read_routes_require_signed_viewer_token(monkeypatch):
    monkeypatch.setattr(brain.settings, "app_mode", AppMode.LIVE)
    monkeypatch.setattr(brain.settings, "auth_secret", "a" * 32)
    client = TestClient(app)
    assert client.get("/metrics").status_code == 401
    token = TokenService("a" * 32).issue("viewer-1", Role.VIEWER)
    assert client.get("/metrics", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_worker_runs_registered_job_with_bounded_retry():
    attempts = []
    worker = Worker()

    def handler(payload):
        attempts.append(payload["id"])
        if len(attempts) == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    worker.register(Job("sync", handler, max_attempts=2))
    assert worker.run_once("sync", {"id": "job-1"}) == {"ok": True}
    assert attempts == ["job-1", "job-1"]


def test_brain_write_tools_require_permission_and_human_approval():
    payload = {
        "sku": "sku-1",
        "title": "Fixture item",
        "description": "Grounded fixture",
        "price": "25",
        "currency": "EUR",
        "quantity": 1,
        "category_id": "123",
    }
    with pytest.raises(PermissionError):
        brain.tools.invoke(
            "publish_listing",
            payload,
            "idempotency-1",
            caller_permission=2,
        )
    with pytest.raises(ExternalDependencyError):
        brain.tools.invoke(
            "publish_listing",
            payload,
            "idempotency-1",
            True,
            caller_permission=2,
        )
