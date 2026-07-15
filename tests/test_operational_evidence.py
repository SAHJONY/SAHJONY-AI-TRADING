from database.db import Database
from scripts.produce_operational_evidence import paper_metrics


def test_paper_metrics_require_real_equity_transitions(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    assert paper_metrics(db) is None
    db.log_equity(1, 100, 100, 0, 0, 0, "paper")
    assert paper_metrics(db) is None
    db.log_equity(2, 101, 90, 11, 1, 0, "paper")
    result = paper_metrics(db)
    assert result["observations"] == 1
    assert result["max_drawdown"] == 0
