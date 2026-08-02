from types import SimpleNamespace

from database import Database
from execution.idempotency import execution_intent_id


def intent():
    return SimpleNamespace(symbol="vti", strategy="momentum", kind="equity",
                           purpose="entry", side="buy", qty=1.5, contract="",
                           strike=0, premium=0, est_notional=150)


def test_execution_intent_identity_is_stable_and_cycle_scoped():
    first, payload = execution_intent_id(intent(), 7)
    duplicate, _ = execution_intent_id(intent(), 7)
    next_cycle, _ = execution_intent_id(intent(), 8)
    assert first == duplicate
    assert first != next_cycle
    assert payload["symbol"] == "VTI"


def test_database_reservation_blocks_duplicate(tmp_path):
    db = Database(str(tmp_path / "governance.db"))
    key, payload = execution_intent_id(intent(), 7)
    assert db.reserve_execution_intent(key, 7, payload) is True
    assert db.reserve_execution_intent(key, 7, payload) is False
    db.update_execution_intent(key, "filled", broker_ref="sim-1")
    assert db.reserve_execution_intent(key, 7, payload) is False


def test_audit_chain_detects_tampering(tmp_path):
    db = Database(str(tmp_path / "audit.db"))
    db.append_audit("risk_decision", {"allowed": False, "reason": "test"})
    db.append_audit("execution", {"intent_id": "abc", "status": "blocked"})
    assert db.verify_audit_chain()["valid"] is True
    db.conn.execute("UPDATE audit_ledger SET payload='{}' WHERE sequence=1")
    db.conn.commit()
    result = db.verify_audit_chain()
    assert result["valid"] is False
    assert result["failed_sequence"] == 1
