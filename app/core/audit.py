"""Append-only in-process audit log used by simulation and API reads."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.domain import AuditEvent, EventType
from app.core.storage import SQLiteStore


class AuditLog:
    def __init__(self, store: SQLiteStore | None = None) -> None:
        self.store = store
        self._events: list[AuditEvent] = store.load_events() if store else []

    def record(self, event_type: EventType, actor: str, workflow_id: UUID, **kwargs) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            workflow_id=workflow_id,
            correlation_id=kwargs.pop("correlation_id", uuid4()),
            **kwargs,
        )
        self._events.append(event)
        if self.store:
            self.store.save_event(event)
        return event

    def list(self, workflow_id: UUID | None = None) -> list[AuditEvent]:
        if workflow_id is None:
            return list(self._events)
        return [event for event in self._events if event.workflow_id == workflow_id]

    def clear(self) -> None:
        self._events.clear()
