"""PostgreSQL production store implementing the same repository contract as SQLite."""

from __future__ import annotations

from contextlib import contextmanager
import json
from threading import Lock
from uuid import UUID

from app.domain import ApprovalRequest, AuditEvent, Order


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    request_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresStore:
    """Synchronous transactional store; inject `connect_factory` in tests."""

    def __init__(self, dsn: str, connect_factory=None) -> None:
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgresStore requires a PostgreSQL DATABASE_URL")
        if connect_factory is None:
            try:
                import psycopg
            except ImportError as error:
                raise RuntimeError("psycopg is required for PostgreSQL persistence") from error
            connect_factory = psycopg.connect
        self.dsn = dsn
        self._connect_factory = connect_factory
        self._lock = Lock()
        self.initialize()

    @contextmanager
    def _connection(self):
        connection = self._connect_factory(self.dsn)
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._lock, self._connection() as connection:
            for statement in POSTGRES_SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(statement)

    def healthcheck(self) -> bool:
        with self._lock, self._connection() as connection:
            connection.execute("SELECT 1")
        return True

    def save_event(self, event: AuditEvent) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO audit_events(event_id, workflow_id, payload) VALUES (%s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (str(event.event_id), str(event.workflow_id), json.dumps(event.model_dump(mode="json"))),
            )

    def load_events(self, workflow_id: UUID | None = None) -> list[AuditEvent]:
        with self._lock, self._connection() as connection:
            if workflow_id is None:
                rows = connection.execute("SELECT payload FROM audit_events ORDER BY event_id").fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM audit_events WHERE workflow_id = %s ORDER BY event_id",
                    (str(workflow_id),),
                ).fetchall()
        return [AuditEvent.model_validate(row[0]) for row in rows]

    def save_order(self, order: Order) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO orders(order_id, payload) VALUES (%s, %s::jsonb) ON CONFLICT (order_id) DO UPDATE SET payload = EXCLUDED.payload",
                (str(order.order_id), json.dumps(order.model_dump(mode="json"))),
            )

    def load_orders(self) -> list[Order]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT payload FROM orders ORDER BY order_id").fetchall()
        return [Order.model_validate(row[0]) for row in rows]

    def save_approval(self, request: ApprovalRequest) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO approvals(request_id, payload) VALUES (%s, %s::jsonb) ON CONFLICT (request_id) DO UPDATE SET payload = EXCLUDED.payload",
                (str(request.request_id), json.dumps(request.model_dump(mode="json"))),
            )

    def load_approvals(self) -> list[ApprovalRequest]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT payload FROM approvals ORDER BY request_id").fetchall()
        return [ApprovalRequest.model_validate(row[0]) for row in rows]

    def claim_webhook_event(self, event_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO webhook_events(event_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (event_id,),
            )
            return cursor.rowcount == 1
