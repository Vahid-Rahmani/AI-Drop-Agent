"""End-to-end simulation without real spend, orders, or marketplace writes."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.agents.specialists import (
    AnalyticsAgent,
    ComplianceAgent,
    CustomerSupportAgent,
    ListingAgent,
    MarketHunterAgent,
    MarketingAgent,
    ProductMatcherAgent,
    SupplierHunterAgent,
    FinanceAgent,
)
from app.core.audit import AuditLog
from app.core.orders import OrderRepository
from app.core.policies import PolicyEngine
from app.core.providers import BrainProvider, MockBrainProvider
from app.core.storage import SQLiteStore
from app.domain import BusinessMetrics, EventType, Order, OrderStatus, PolicyConfig
from app.opportunity_hunter.graph import opportunity_graph


class SimulationWorkflow:
    """Runs research through post-sale review using only controlled fixtures."""

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        provider: BrainProvider | None = None,
        store: SQLiteStore | None = None,
    ) -> None:
        self.policy = policy or PolicyEngine(PolicyConfig())
        self.provider = provider or MockBrainProvider()
        self.audit = AuditLog(store=store)
        self.orders = OrderRepository(store=store)
        self.market = MarketHunterAgent()
        self.supplier = SupplierHunterAgent()
        self.matcher = ProductMatcherAgent()
        self.compliance = ComplianceAgent()
        self.listing = ListingAgent()
        self.marketing = MarketingAgent()
        self.support = CustomerSupportAgent()
        self.analytics = AnalyticsAgent()
        self.finance = FinanceAgent()

    def run(self, query: str = "hoodie") -> dict:
        workflow_id = uuid4()
        market_products = self.market.discover(query)
        supplier_products = self.supplier.discover(query)
        self.audit.record(EventType.MARKET_OPPORTUNITY_FOUND, self.market.name, workflow_id, output_refs=["market-1"])
        self.audit.record(EventType.SUPPLIER_FOUND, self.supplier.name, workflow_id, output_refs=["supplier-1"])

        state = {
            "query": query,
            "market_products": market_products,
            "supplier_products": supplier_products,
            "fixture_mode": True,
            "fx_mode": "EXPLICIT",
            "fx_rates": {"USD->EUR": 0.92},
            "fee_mode": "EXPLICIT",
            "fee_rate": 10.0,
            "fixed_fee": 0.35,
            "payment_fee": 0.0,
            "marketplace_fee": 0.0,
            "other_costs": 0.0,
            "fees_are_test_configuration": True,
            "errors": [],
            "inventory_cache": {},
            "shipping_cache": {},
        }
        researched = opportunity_graph.invoke(state)
        ranked = researched.get("ranked_results", [])
        if not ranked:
            raise RuntimeError("simulation produced no opportunity result")
        best = ranked[0]
        market = best["market_product"]
        supplier = best.get("supplier_product") or supplier_products[0]
        match = self.matcher.match(market, supplier_products)
        self.audit.record(EventType.PRODUCT_MATCHED, self.matcher.name, workflow_id, output_refs=[str(match.get("supplier_product_id"))], confidence=match["confidence"])

        risk = self.compliance.check(market)
        if risk["blocked"]:
            self.audit.record(EventType.RISK_DETECTED, self.compliance.name, workflow_id, status="BLOCKED", metadata=risk)
        profit = best.get("profit_result") or {}
        self.audit.record(
            EventType.PROFIT_CALCULATED,
            "profit_engine",
            workflow_id,
            output_refs=[market["product_id"]],
            metadata={"profit_calculation_allowed": bool(profit.get("profit_calculation_allowed"))},
        )
        margin = Decimal(str(profit.get("profit_margin_percent") or 0))
        approval = self.policy.product_approval(margin, risk["blocked"])
        self.audit.record(EventType.PRODUCT_APPROVED if approval.allowed else EventType.ACTION_BLOCKED, "policy_engine", workflow_id, metadata=approval.model_dump(mode="json"))

        listing = self.listing.draft(market, supplier)
        experiment = self.marketing.draft(market["product_id"])
        self.audit.record(EventType.LISTING_DRAFTED, self.listing.name, workflow_id, output_refs=[market["product_id"]])
        self.audit.record(EventType.EXPERIMENT_CREATED, self.marketing.name, workflow_id, output_refs=[str(experiment.experiment_id)])

        order = self.orders.create(Order(product_id=market["product_id"], amount=Decimal(str(market["price"]))))
        self.audit.record(EventType.ORDER_RECEIVED, "simulation", workflow_id, output_refs=[str(order.order_id)])
        for status in (
            OrderStatus.PAYMENT_CONFIRMED,
            OrderStatus.FULFILLMENT_PENDING,
            OrderStatus.SUPPLIER_ORDER_CREATED,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            self.orders.transition(order.order_id, status, f"simulation-{status}")
        support = self.support.draft_reply(order, "What is the order status?")
        self.audit.record(EventType.ORDER_SHIPPED, "simulation", workflow_id, output_refs=[order.tracking_number or ""])
        self.audit.record(EventType.SUPPORT_REQUIRED, self.support.name, workflow_id, output_refs=[str(order.order_id)])

        metrics = BusinessMetrics(
            revenue=Decimal(str(market["price"])),
            estimated_profit=Decimal(str(profit.get("net_profit") or 0)),
            available_cash=Decimal("975.00"),
            active_products=1 if approval.allowed else 0,
            orders=1,
        )
        review = self.analytics.review(metrics, self.provider)
        reinvestment = self.finance.authorize_reinvestment(
            metrics.available_cash,
            metrics.reserved_cash,
            Decimal("0"),
            experiment.budget,
            self.policy,
        )
        self.audit.record(EventType.BUSINESS_REVIEWED, self.analytics.name, workflow_id, output_refs=["business-review"])
        return {
            "workflow_id": workflow_id,
            "mode": "simulation",
            "market_products": market_products,
            "supplier_products": supplier_products,
            "opportunities": ranked,
            "match": match,
            "compliance": risk,
            "approval": approval,
            "listing": listing,
            "experiment": experiment,
            "order": order,
            "support": support,
            "review": review,
            "reinvestment": reinvestment,
            "audit": self.audit.list(workflow_id),
        }
