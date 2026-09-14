from decimal import Decimal
import gc
from pathlib import Path

from app.core.approvals import ApprovalQueue
from app.core.postgres import PostgresStore
from app.core.storage import SQLiteStore
from app.domain import ApprovalStatus, PermissionLevel


def test_approval_queue_survives_store_reload():
    path = Path("work/test_state.db")
    path.unlink(missing_ok=True)
    try:
        store = SQLiteStore(str(path))
        queue = ApprovalQueue(store)
        request = queue.create(
            "publish_listing",
            "external marketplace write",
            PermissionLevel.REVERSIBLE_EXTERNAL,
            Decimal("5"),
        )
        queue.decide(request.request_id, ApprovalStatus.APPROVED, "operator")

        reloaded = ApprovalQueue(SQLiteStore(str(path)))
        restored = reloaded.get(request.request_id)
        assert restored is not None
        assert restored.status == ApprovalStatus.APPROVED
        assert restored.decided_by == "operator"
    finally:
        gc.collect()
        path.unlink(missing_ok=True)


def test_postgres_store_contract_can_be_fixture():
    class Cursor:
        rowcount = 1

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.statements = []
            self.committed = False
            self.closed = False

        def execute(self, statement, params=None):
            self.statements.append((statement, params))
            return Cursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.committed = False

        def close(self):
            self.closed = True

    connections = []

    def connect(_dsn):
        connection = Connection()
        connections.append(connection)
        return connection

    store = PostgresStore("postgresql://fixture/db", connect_factory=connect)
    assert store.claim_webhook_event("evt-1") is True
    assert len(connections) == 2
    assert all(connection.committed and connection.closed for connection in connections)
