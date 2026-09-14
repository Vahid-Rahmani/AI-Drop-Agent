"""Small specialist agents that return reviewable, evidence-backed outputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain import BusinessMetrics, BusinessReview, ListingDraft, MarketingExperiment, Order
from app.core.providers import BrainProvider, MockBrainProvider
from app.core.policies import PolicyEngine
from app.domain import PermissionLevel, PolicyDecision
from app.product_matcher.matcher import get_best_match


class MarketHunterAgent:
    name = "market_hunter"

    def discover(self, query: str) -> list[dict[str, Any]]:
        return [
            {
                "product_id": "market-1",
                "name": f"Children's pink {query}",
                "price": 25.0,
                "currency": "EUR",
                "condition": "New",
                "category": "children clothing",
                "seller": "simulation-fixture",
                "shipping_cost": 0.0,
                "url": "fixture://market-1",
                "source": "simulation",
                "marketplace": "TEST",
            }
        ]


class SupplierHunterAgent:
    name = "supplier_hunter"

    def discover(self, query: str) -> list[dict[str, Any]]:
        return [
            {
                "product_id": "supplier-1",
                "name": f"Children's light pink {query}, size 104",
                "price": 8.60,
                "currency": "USD",
                "inventory": 300,
                "category": "children clothing",
                "supplier": "simulation-fixture",
                "shipping_options": [
                    {
                        "logistic_name": "GLS DE to DE",
                        "shipping_cost": 0.0,
                        "currency": None,
                        "free_shipping": True,
                        "delivery_days": "4-5",
                    }
                ],
            }
        ]


class ProductMatcherAgent:
    name = "product_matcher"

    def match(self, market: dict[str, Any], suppliers: list[dict[str, Any]]) -> dict[str, Any]:
        result = get_best_match(market, suppliers)
        if result is None:
            return {
                "market_product_id": str(market.get("product_id", "")),
                "supplier_product_id": None,
                "match_score": 0,
                "confidence": 0,
                "match_quality": "reject",
                "evidence": [],
                "conflicts": ["no reliable supplier match"],
            }
        score = float(result.get("match_score", 0))
        return {
            "market_product_id": str(market.get("product_id", "")),
            "supplier_product_id": result.get("supplier_product_id"),
            "match_score": score,
            "confidence": round(score / 100, 3),
            "match_quality": result.get("match_quality", "reject"),
            "evidence": ["normalized title token overlap", "category compatibility"],
            "conflicts": result.get("conflicts", []),
        }


class ComplianceAgent:
    name = "compliance"
    HIGH_RISK_TERMS = ("counterfeit", "replica", "weapon", "medical claim", "prescription", "miracle cure")

    def check(self, product: dict[str, Any]) -> dict[str, Any]:
        text = str(product.get("name", "")).lower()
        findings = [term for term in self.HIGH_RISK_TERMS if term in text]
        return {
            "blocked": bool(findings),
            "findings": findings,
            "risk_level": "HIGH" if findings else "LOW",
            "reason": "human review required" if findings else "no configured high-risk term detected",
        }


class ListingAgent:
    name = "listing"

    def draft(self, market: dict[str, Any], supplier: dict[str, Any]) -> ListingDraft:
        title = str(market.get("name", "")).strip()
        evidence = [f"market:{market.get('product_id')}", f"supplier:{supplier.get('product_id')}"]
        return ListingDraft(
            product_id=str(market.get("product_id", "")),
            title_de=title,
            description_de=f"Produktentwurf auf Basis der belegten Bezeichnung: {title}.",
            bullets_de=["Neue Ware", "Versandoption und Lieferzeit vor Veröffentlichung prüfen"],
            specifications={"Kategorie": str(market.get("category", ""))},
            evidence_refs=evidence,
            is_publishable=False,
        )


class MarketingAgent:
    name = "marketing"

    def draft(self, product_id: str) -> MarketingExperiment:
        return MarketingExperiment(
            product_id=product_id,
            channel="simulation",
            audience_hypothesis="German parents looking for affordable children's casual wear",
            budget=Decimal("10.00"),
            kpi="qualified_clicks",
            success_criteria="at least 3 qualified clicks within the test window",
            stop_criteria="stop at EUR 10 spend or any policy/risk signal",
        )


class CustomerSupportAgent:
    name = "customer_support"

    def draft_reply(self, order: Order, question: str) -> dict[str, Any]:
        if "track" in question.lower() or "status" in question.lower():
            message = f"Ihre Bestellung befindet sich im Status {order.status}."
            if order.tracking_number:
                message += f" Die Sendungsnummer lautet {order.tracking_number}."
        else:
            message = "Ihre Anfrage wurde erfasst und wird bei Bedarf an eine Person eskaliert."
        return {"message_de": message, "evidence": [f"order:{order.order_id}"]}


class AnalyticsAgent:
    name = "analytics"

    def review(self, metrics: BusinessMetrics, provider: BrainProvider | None = None) -> BusinessReview:
        provider = provider or MockBrainProvider()
        result = provider.structured("business_review", {"metrics": metrics.model_dump(mode="json")})
        return BusinessReview(
            metrics=metrics,
            risks=[str(item) for item in result.get("risks", [])],
            recommended_next_actions=[str(item) for item in result.get("recommended_next_actions", [])],
            generated_by=provider.name,
        )


class FinanceAgent:
    """Keeps reinvestment decisions inside deterministic cash and policy limits."""

    name = "finance"

    def authorize_reinvestment(
        self,
        available_cash: Decimal,
        reserved_cash: Decimal,
        committed_cost: Decimal,
        amount: Decimal,
        policy: PolicyEngine,
    ) -> PolicyDecision:
        if available_cash - reserved_cash - committed_cost < amount:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                reason="available_cash_after_reserves_is_insufficient",
                permission_level=PermissionLevel.FINANCIAL,
            )
        return policy.authorize(PermissionLevel.FINANCIAL, amount=amount)
