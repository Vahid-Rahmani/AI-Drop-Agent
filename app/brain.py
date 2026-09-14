"""Central orchestrator boundary for the business workflow."""

from __future__ import annotations

from app.core.config import Settings
from app.core.approvals import ApprovalQueue
from app.core.policies import PolicyEngine
from app.core.postgres import PostgresStore
from app.core.providers import (
    BrainProvider,
    FallbackBrainProvider,
    LocalOpenWeightProvider,
    MockBrainProvider,
    OpenAICompatibleProvider,
)
from app.core.storage import SQLiteStore
from app.core.tools import ToolDefinition, ToolRegistry
from app.domain import PermissionLevel
from app.integrations.cj import CJSupplierProvider
from app.integrations.ebay import EbayMarketplaceProvider
from app.integrations.marketplace import ExternalDependencyError, ListingPayload
from app.security.webhooks import WebhookVerifier
from app.workflows.simulation import SimulationWorkflow


class Brain:
    """Coordinates specialists while keeping business state outside model history."""

    def __init__(self, settings: Settings | None = None, provider: BrainProvider | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = provider or self._provider_from_settings()
        self.policy = PolicyEngine(self.settings.policy())
        if self.settings.database_url.startswith(("postgresql://", "postgres://")):
            self.store = PostgresStore(self.settings.database_url)
        else:
            self.store = SQLiteStore(self.settings.database_path)
        self.approvals = ApprovalQueue(store=self.store)
        self.webhook_verifier = (
            WebhookVerifier(self.settings.webhook_secret, replay_guard=self.store.claim_webhook_event)
            if self.settings.webhook_secret and len(self.settings.webhook_secret) >= 32
            else None
        )
        self.workflow = SimulationWorkflow(policy=self.policy, provider=self.provider, store=self.store)
        self.marketplace = EbayMarketplaceProvider(
            client_id=self.settings.ebay_client_id,
            client_secret=self.settings.ebay_client_secret,
            refresh_token=self.settings.ebay_refresh_token,
            sandbox=self.settings.ebay_environment.lower() != "production",
        )
        self.supplier_provider = CJSupplierProvider(
            access_token=self.settings.cj_access_token or self.settings.cj_api_key,
            base_url=self.settings.cj_base_url,
        )
        self.tools = self._build_tools()
        self.agents = {
            "market_hunter": "researches observed market signals",
            "supplier_hunter": "finds and verifies supplier candidates",
            "product_matcher": "matches products with confidence and conflicts",
            "profit_engine": "calculates deterministic unit economics",
            "compliance": "flags risk and requires review",
            "listing": "creates grounded drafts only",
            "marketing": "creates bounded experiments",
            "order_fulfillment": "enforces lifecycle transitions",
            "customer_support": "answers from known order evidence",
            "analytics": "produces metrics and business review",
            "finance": "enforces budget and exposure policy",
        }

    def _provider_from_settings(self) -> BrainProvider:
        if self.settings.model_provider.lower() == "local" and self.settings.local_model_name:
            return LocalOpenWeightProvider(
                self.settings.local_model_base_url,
                self.settings.local_model_name,
                self.settings.local_model_timeout,
            )
        if self.settings.app_mode.value == "live" and self.settings.openai_api_key and self.settings.openai_model:
            return FallbackBrainProvider(
                OpenAICompatibleProvider(
                    self.settings.openai_base_url,
                    self.settings.openai_model,
                    self.settings.openai_api_key,
                ),
                MockBrainProvider(),
            )
        return MockBrainProvider()

    def _build_tools(self) -> ToolRegistry:
        registry = ToolRegistry()
        handlers = {
            "search_market": lambda query="hoodie": self.workflow.market.discover(query),
            "search_supplier": lambda query="hoodie": self.workflow.supplier.discover(query),
            "match_products": lambda market, suppliers: self.workflow.matcher.match(market, suppliers),
            "check_product_risk": lambda product: self.workflow.compliance.check(product),
            "create_listing_draft": lambda market, supplier: self.workflow.listing.draft(market, supplier),
            "calculate_profit": lambda payload: self._calculate_profit(payload),
            "publish_listing": lambda payload, idempotency_key, approved=False: self._publish_listing(
                payload, idempotency_key, approved
            ),
            "create_supplier_order": lambda product_id, quantity, address, idempotency_key, amount, approved=False: self._create_supplier_order(
                product_id, quantity, address, idempotency_key, amount, approved
            ),
            "refund_order": lambda order_id, approved=False: self._refund_order(order_id, approved),
        }
        for name, description, permission, mutating in (
            ("search_market", "read market signals", PermissionLevel.READ, False),
            ("search_supplier", "read supplier candidates", PermissionLevel.READ, False),
            ("match_products", "compare market and supplier products", PermissionLevel.READ, False),
            ("calculate_profit", "calculate deterministic economics", PermissionLevel.READ, False),
            ("check_product_risk", "run compliance checks", PermissionLevel.READ, False),
            ("create_listing_draft", "create a reversible listing draft", PermissionLevel.DRAFT, True),
            ("publish_listing", "publish a marketplace listing", PermissionLevel.REVERSIBLE_EXTERNAL, True),
            ("create_supplier_order", "create a supplier order", PermissionLevel.FINANCIAL, True),
            ("refund_order", "refund a customer order", PermissionLevel.FINANCIAL, True),
        ):
            registry.register(
                ToolDefinition(
                    name=name,
                    description=description,
                    permission_level=permission,
                    mutating=mutating,
                    handler=handlers.get(name),
                    timeout_seconds=15 if mutating else 10,
                    max_retries=1 if not mutating else 0,
                )
            )
        return registry

    @staticmethod
    def _calculate_profit(payload: dict) -> dict:
        from app.core.economics import calculate_unit_economics
        from app.domain import EconomicsInput

        return calculate_unit_economics(EconomicsInput.model_validate(payload))

    def _publish_listing(self, payload: dict, idempotency_key: str, approved: bool = False):
        decision = self.policy.authorize(PermissionLevel.REVERSIBLE_EXTERNAL, explicit_human_approval=approved)
        if not decision.allowed or decision.requires_approval and not approved:
            raise PermissionError(decision.reason)
        return self.marketplace.create_listing(ListingPayload.model_validate(payload), idempotency_key)

    def _create_supplier_order(
        self,
        product_id: str,
        quantity: int,
        address: dict[str, str],
        idempotency_key: str,
        amount,
        approved: bool = False,
    ):
        from decimal import Decimal

        decision = self.policy.authorize(
            PermissionLevel.FINANCIAL,
            amount=Decimal(str(amount)),
            explicit_human_approval=approved,
        )
        if not decision.allowed or decision.requires_approval and not approved:
            raise PermissionError(decision.reason)
        return self.supplier_provider.place_order(product_id, quantity, address, idempotency_key)

    def _refund_order(self, order_id: str, approved: bool = False):
        decision = self.policy.authorize(PermissionLevel.FINANCIAL, explicit_human_approval=approved)
        if not decision.allowed or decision.requires_approval and not approved:
            raise PermissionError(decision.reason)
        raise ExternalDependencyError(f"payment provider is not configured for refund {order_id}")

    def run_simulation(self, query: str = "hoodie") -> dict:
        if self.settings.app_mode.value != "simulation":
            raise RuntimeError("simulation endpoint requires APP_MODE=simulation")
        return self.workflow.run(query)

    def storage_health(self) -> bool:
        return self.store.healthcheck()
