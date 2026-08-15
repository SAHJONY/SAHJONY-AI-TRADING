"""The flattening plan — see tools/remediate_positions.py. Dry-run is the default."""
import json
import os
import tempfile

import pytest

from tools import remediate_positions as rp


def _desk(root, home, equity, positions, *, broker_equity=None, recon_ok=None):
    d = os.path.join(root, home, "public")
    os.makedirs(d, exist_ok=True)
    payload = {"account": {"equity": equity}, "positions": positions}
    if broker_equity is not None:
        payload["broker_account"] = {"equity": broker_equity, "online": True}
    if recon_ok is not None:
        payload["reconciliation"] = {"ok": recon_ok, "mismatched": [] if recon_ok else [{"symbol": "X"}]}
    with open(os.path.join(d, "status.json"), "w") as fh:
        json.dump(payload, fh)


@pytest.fixture
def sandbox(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setattr(rp, "_ROOT", root)
        yield root


def test_flattening_a_long_is_a_sell(sandbox):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "EDRY", "shares": 492.0, "state": "long",
                                    "cost_basis": 24.57, "price": 26.62}])
    o = rp.plan("d", 0.10)["orders"][0]
    assert o["side"] == "sell" and o["qty"] == pytest.approx(492.0)


def test_reconciled_online_broker_equity_sets_the_cap(sandbox):
    _desk(sandbox, "d", 2_109.15,
          [{"symbol": "EDRY", "shares": 100.0, "state": "long",
            "cost_basis": 24.57, "price": 26.62}],
          broker_equity=100_000.0, recon_ok=True)
    p = rp.plan("d", 0.10)
    assert p["equity"] == 100_000.0
    assert p["equity_source"] == "broker_account"
    assert p["orders"] == []


def test_flattening_a_short_is_a_buy_of_the_absolute_size(sandbox):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "DIA", "shares": -9.935112, "state": "long",
                                    "cost_basis": 516.18, "price": 537.92}])
    o = rp.plan("d", 0.10)["orders"][0]
    assert o["side"] == "buy"
    assert o["qty"] == pytest.approx(9.935112)


def test_unpriceable_positions_are_skipped_not_guessed(sandbox):
    _desk(sandbox, "d", 2_000.0, [{"symbol": "BTCUSD", "shares": 0.00018354,
                                   "state": "long", "cost_basis": 65_034.70,
                                   "price": 0.0}])
    p = rp.plan("d", 0.10)
    assert p["orders"] == []
    assert p["skipped"][0]["symbol"] == "BTCUSD"


def test_positions_inside_the_cap_are_left_alone(sandbox):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "AMPY", "shares": 60.0, "state": "long",
                                    "cost_basis": 4.08, "price": 1.69}])
    assert rp.plan("d", 0.10)["orders"] == []


def test_a_contradictory_record_is_flattened_even_when_inside_the_cap(sandbox):
    _desk(sandbox, "d", 1_000_000.0, [{"symbol": "DIA", "shares": -1.0, "state": "long",
                                       "cost_basis": 516.18, "price": 537.92}])
    o = rp.plan("d", 0.10)["orders"][0]
    assert "recorded 'long'" in o["reason"]


def test_a_missing_cost_basis_is_flattened(sandbox):
    _desk(sandbox, "d", 1_000_000.0, [{"symbol": "X", "shares": 1.0, "state": "long",
                                       "cost_basis": 0.0, "price": 10.0}])
    assert "cost basis" in rp.plan("d", 0.10)["orders"][0]["reason"]


def test_a_clean_desk_plans_nothing(sandbox):
    _desk(sandbox, "d", 100_000.0, [{"symbol": "SPY", "shares": 1.0, "state": "long",
                                     "cost_basis": 500.0, "price": 520.0}])
    p = rp.plan("d", 0.10)
    assert p["home"] == "d" and p["equity"] == 100_000.0 and p["cap"] == 10_000.0
    assert p["orders"] == [] and p["skipped"] == []


def test_dry_run_is_the_default_and_sends_nothing(sandbox, capsys, monkeypatch):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "EDRY", "shares": 492.0, "state": "long",
                                    "cost_basis": 24.57, "price": 26.62}])

    def _boom(*a, **k):
        raise AssertionError("dry run must not reach the broker")
    monkeypatch.setattr("utils.broker.get_broker", _boom)

    assert rp.main(["--home", "d", "--max-allocation-pct", "0.10"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "NOT sent" in out


def test_apply_refuses_when_reconciliation_is_not_clean(sandbox, capsys, monkeypatch):
    _desk(sandbox, "d", 2_109.15,
          [{"symbol": "EDRY", "shares": 492.0, "state": "long",
            "cost_basis": 24.57, "price": 26.62}],
          broker_equity=100_000.0, recon_ok=False)

    def _boom(*a, **k):
        raise AssertionError("unreconciled apply must never reach broker")
    monkeypatch.setattr("utils.broker.get_broker", _boom)

    assert rp.main(["--home", "d", "--max-allocation-pct", "0.10", "--apply"]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_json_mode_emits_the_plan(sandbox, capsys):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "EDRY", "shares": 492.0, "state": "long",
                                    "cost_basis": 24.57, "price": 26.62}])
    rp.main(["--home", "d", "--max-allocation-pct", "0.10", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["orders"][0]["symbol"] == "EDRY"


def test_the_plan_never_writes_the_status_file(sandbox):
    _desk(sandbox, "d", 2_109.15, [{"symbol": "EDRY", "shares": 492.0, "state": "long",
                                    "cost_basis": 24.57, "price": 26.62}])
    path = os.path.join(sandbox, "d/public/status.json")
    before = open(path).read()
    rp.main(["--home", "d", "--max-allocation-pct", "0.10"])
    assert open(path).read() == before


def test_a_missing_desk_plans_nothing(sandbox):
    assert rp.plan("desks/nope", 0.10)["orders"] == []
