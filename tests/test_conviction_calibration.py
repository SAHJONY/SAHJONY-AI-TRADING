"""Grading council conviction against what happened next."""
import json
import os
import sqlite3
import tempfile

import pytest

from tools import conviction_calibration as cc


def _db(root, home, rows, with_price=True):
    d = os.path.join(root, home, "data")
    os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(os.path.join(d, "sahjony.db"))
    cols = "cycle INTEGER, symbol TEXT, conviction REAL, direction TEXT"
    if with_price:
        cols += ", price REAL"
    conn.execute(f"CREATE TABLE council_log (id INTEGER PRIMARY KEY, ts TEXT, {cols})")
    for r in rows:
        if with_price:
            conn.execute("INSERT INTO council_log (ts,cycle,symbol,conviction,direction,price)"
                         " VALUES ('t',?,?,?,?,?)", r)
        else:
            conn.execute("INSERT INTO council_log (ts,cycle,symbol,conviction,direction)"
                         " VALUES ('t',?,?,?,?)", r[:4])
    conn.commit(); conn.close()


@pytest.fixture
def sandbox(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setattr(cc, "_ROOT", root)
        yield root


def _obs(root, home, horizon=1):
    conn = cc._db(home)
    try:
        return cc.observations(conn, horizon)
    finally:
        conn.close()


def test_a_correct_long_call_grades_positive(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", 100.0), (2, "BTC", 0.60, "long", 110.0)])
    o = _obs(sandbox, "d")["observations"]
    assert o[0]["signed_return"] == pytest.approx(0.10)


def test_a_correct_short_call_grades_positive(sandbox):
    """A short that wins must score POSITIVE — the sign is the whole point."""
    _db(sandbox, "d", [(1, "BTC", 0.60, "short", 100.0), (2, "BTC", 0.60, "short", 90.0)])
    assert _obs(sandbox, "d")["observations"][0]["signed_return"] == pytest.approx(0.10)


def test_a_wrong_short_call_grades_negative(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.60, "short", 100.0), (2, "BTC", 0.60, "short", 110.0)])
    assert _obs(sandbox, "d")["observations"][0]["signed_return"] == pytest.approx(-0.10)


def test_flat_calls_are_not_graded(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.50, "flat", 100.0), (2, "BTC", 0.50, "flat", 110.0)])
    d = _obs(sandbox, "d")
    assert d["graded"] == 0 and d["ungradeable"] == 2


def test_symbols_do_not_bleed_into_each_other(sandbox):
    """ETH's move must never grade a BTC verdict."""
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", 100.0), (2, "ETH", 0.60, "long", 999.0)])
    assert _obs(sandbox, "d")["graded"] == 0


def test_rows_without_a_forward_price_are_ungradeable(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", 100.0)])
    assert _obs(sandbox, "d")["graded"] == 0


def test_a_pre_price_database_is_reported_as_such_not_as_empty(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", None)] * 5, with_price=False)
    d = _obs(sandbox, "d")
    assert d["no_price_column"] is True
    assert d["total"] == 5 and d["graded"] == 0


def test_edge_is_reported_net_of_the_round_trip_fee(sandbox):
    """A 50 bps win is a LOSS once a 60 bps round trip is paid."""
    obs = [{"conviction": 0.60, "signed_return": 0.005}] * 40
    row = [b for b in cc.calibrate(obs, 60.0) if b["n"]][0]
    assert row["hit_rate"] == 1.0            # every call directionally right
    assert row["mean_bps"] == pytest.approx(50.0)
    assert row["edge_bps"] == pytest.approx(-10.0)   # and still not worth trading


def test_buckets_partition_conviction_without_gaps_or_overlap(sandbox):
    obs = [{"conviction": c / 100.0, "signed_return": 0.0} for c in range(0, 101)]
    assert sum(b["n"] for b in cc.calibrate(obs, 0.0)) == len(obs)


def test_a_missing_database_exits_two(sandbox, capsys):
    assert cc.main(["--home", "nope"]) == 2
    assert "no database" in capsys.readouterr().out


def test_json_mode_is_parseable(sandbox, capsys):
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", 100.0), (2, "BTC", 0.60, "long", 110.0)])
    cc.main(["--home", "d", "--horizon", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["graded"] == 1


def test_the_tool_opens_the_database_read_only(sandbox):
    _db(sandbox, "d", [(1, "BTC", 0.60, "long", 100.0)])
    conn = cc._db("d")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO council_log (ts,cycle) VALUES ('x',9)")
    conn.close()
