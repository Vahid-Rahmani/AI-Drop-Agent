"""Small SQLite persistence adapter for orders and immutable audit events."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.domain import ApprovalRequest, AuditEvent, Order


class SQLiteStore:
    """Durable local store; production deployments can replace this adapter."""

    def __init__(self, path: str = "data/ai_drop_agent.db") -> None:
        self.path = path
        self._lock = Lock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    request_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS admin_settings (
                    setting_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                """
            )

    def healthcheck(self) -> bool:
        with self._lock, self._connection() as connection:
            connection.execute("SELECT 1")
        return True

    def save_event(self, event: AuditEvent) -> None:
        payload = event.model_dump_json()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO audit_events(event_id, workflow_id, payload) VALUES (?, ?, ?)",
                (str(event.event_id), str(event.workflow_id), payload),
            )

    def load_events(self, workflow_id: UUID | None = None) -> list[AuditEvent]:
        with self._lock, self._connection() as connection:
            if workflow_id is None:
                rows = connection.execute("SELECT payload FROM audit_events ORDER BY rowid").fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload FROM audit_events WHERE workflow_id = ? ORDER BY rowid", (str(workflow_id),)
                ).fetchall()
        return [AuditEvent.model_validate_json(row["payload"]) for row in rows]

    def save_order(self, order: Order) -> None:
        payload = order.model_dump_json()
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO orders(order_id, payload) VALUES (?, ?)",
                (str(order.order_id), payload),
            )

    def load_orders(self) -> list[Order]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT payload FROM orders ORDER BY rowid").fetchall()
        return [Order.model_validate_json(row["payload"]) for row in rows]

    def save_approval(self, request: ApprovalRequest) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO approvals(request_id, payload) VALUES (?, ?)",
                (str(request.request_id), request.model_dump_json()),
            )

    def load_approvals(self) -> list[ApprovalRequest]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT payload FROM approvals ORDER BY rowid").fetchall()
        return [ApprovalRequest.model_validate_json(row["payload"]) for row in rows]

    def claim_webhook_event(self, event_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO webhook_events(event_id) VALUES (?)",
                (event_id,),
            )
            return cursor.rowcount == 1

    def save_setting(self, key: str, payload: dict) -> None:
        import json

        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO admin_settings(setting_key, payload) VALUES (?, ?)",
                (key, json.dumps(payload)),
            )

    def load_settings(self) -> dict[str, dict]:
        import json

        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT setting_key, payload FROM admin_settings").fetchall()
        return {row["setting_key"]: json.loads(row["payload"]) for row in rows}
