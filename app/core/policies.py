"""Deterministic permission, budget, and kill-switch policy gates."""

from __future__ import annotations

from decimal import Decimal

from app.domain import PermissionLevel, PolicyConfig, PolicyDecision


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    def authorize(
        self,
        permission: PermissionLevel,
        *,
        amount: Decimal = Decimal("0"),
        contribution_margin_percent: Decimal | None = None,
        explicit_human_approval: bool = False,
    ) -> PolicyDecision:
        if self.config.kill_switch:
            return PolicyDecision(allowed=False, reason="kill_switch_active", permission_level=permission)
        if amount < 0:
            return PolicyDecision(allowed=False, reason="negative_amount_rejected", permission_level=permission)
        if permission >= PermissionLevel.LEGAL_ACCOUNT and not explicit_human_approval:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                reason="explicit_human_approval_required",
                permission_level=permission,
            )
        if permission >= PermissionLevel.FINANCIAL and amount > self.config.max_product_exposure:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                reason="max_product_exposure_exceeded",
                permission_level=permission,
            )
        if contribution_margin_percent is not None and contribution_margin_percent < self.config.min_contribution_margin_percent:
            return PolicyDecision(
                allowed=False,
                reason="minimum_contribution_margin_not_met",
                permission_level=permission,
            )
        if permission >= PermissionLevel.FINANCIAL and amount > self.config.max_experiment_loss:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                reason="financial_action_exceeds_experiment_loss_limit",
                permission_level=permission,
            )
        if permission >= PermissionLevel.REVERSIBLE_EXTERNAL:
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                reason="policy_allows_action_pending_approval",
                permission_level=permission,
            )
        return PolicyDecision(allowed=True, reason="policy_allows_action", permission_level=permission)

    def product_approval(self, margin_percent: Decimal, risk_blocked: bool) -> PolicyDecision:
        if risk_blocked:
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                reason="compliance_risk_requires_review",
                permission_level=PermissionLevel.DRAFT,
            )
        return self.authorize(PermissionLevel.DRAFT, contribution_margin_percent=margin_percent)
