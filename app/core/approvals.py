"""Human approval queue for actions that policy marks as high impact."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.core.storage import SQLiteStore
from app.domain import ApprovalRequest, ApprovalStatus, PermissionLevel


class ApprovalQueue:
    def __init__(self, store: SQLiteStore | None = None) -> None:
        self.store = store
        self._requests = {request.request_id: request for request in store.load_approvals()} if store else {}

    def create(self, action: str, reason: str, permission_level: PermissionLevel, amount: Decimal = Decimal("0")) -> ApprovalRequest:
        request = ApprovalRequest(
            action=action,
            reason=reason,
            permission_level=permission_level,
            amount=amount,
        )
        self._requests[request.request_id] = request
        if self.store:
            self.store.save_approval(request)
        return request

    def get(self, request_id: UUID) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def list(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    def decide(self, request_id: UUID, status: ApprovalStatus, decided_by: str) -> ApprovalRequest:
        request = self._requests[request_id]
        if request.status != ApprovalStatus.PENDING:
            raise ValueError("approval request is already decided")
        request.status = status
        request.decided_by = decided_by
        if self.store:
            self.store.save_approval(request)
        return request
