"""The standing books check — see tools/position_audit.py."""
import json
import os
import tempfile

import pytest

from tools import position_audit as pa


def _desk(root, home, equity, positions):
    d = os.path.join(root, home, "public")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "status.json"), "w") as fh:
        json.dump({"account": {"equity": equity}, "positions": positions}, fh)


@pytest.fixture
def sandbox(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        monkeypatch.setattr(pa, "_ROOT", root)
        yield root


def test_a_clean_desk_reports_nothing(sandbox):
    _desk(sandbox, "desks/ok", 10_000.0,
          [{"symbol": "SPY", "shares": 1.0, "state": "long",
            "cost_basis": 500.0, "price": 520.0}])
    assert pa.audit("desks/ok", 0.12)["findings"] == []


def test_over_cap_position_is_reported_with_the_multiple(sandbox):
    _desk(sandbox, "desks/x", 2_109.15,
          [{"symbol": "EDRY", "shares": 492.0, "state": "long",
            "cost_basis": 24.57, "price": 26.62}])
    f = pa.audit("desks/x", 0.12)["findings"]
    assert [x["kind"] for x in f] == ["over-cap"]
    # $13,097.04 held against a 12% cap on $2,109.15 equity ($253.10) = 51.7x
    assert "51.7x" in f[0]["detail"] and "621% of equity" in f[0]["detail"]


def test_unpriceable_position_is_marked_at_basis_not_dropped(sandbox):
    _desk(sandbox, "desks/x", 2_000.0,
          [{"symbol": "BTCUSD", "shares": 0.00018354, "state": "long",
            "cost_basis": 65_034.70, "price": 0.0}])
    f = pa.audit("desks/x", 0.12)["findings"]
    assert f[0]["kind"] == "unpriceable" and "basis" in f[0]["detail"]


def test_sign_contradiction_is_reported(sandbox):
    _desk(sandbox, "desks/x", 100_000.0,
          [{"symbol": "DIA", "shares": -9.935112, "state": "long",
            "strategy": "ladder", "cost_basis": 516.18, "price": 537.92}])
    f = pa.audit("desks/x", 0.12)["findings"]
    assert f[0]["kind"] == "contradiction" and "long" in f[0]["detail"]


def test_negative_equity_is_reported_as_insolvent(sandbox):
    _desk(sandbox, "desks/x", -26_414.14, [])
    assert pa.audit("desks/x", 0.12)["findings"][0]["kind"] == "insolvent"


def test_exit_code_is_nonzero_when_anything_is_wrong(sandbox, capsys):
    _desk(sandbox, "desks/bad", 2_000.0,
          [{"symbol": "AMPY", "shares": 12_104.0, "state": "long",
            "cost_basis": 4.08, "price": 1.69}])
    assert pa.main(["--home", "desks/bad", "--max-allocation-pct", "0.12"]) == 1
    assert "over-cap" in capsys.readouterr().out


def test_exit_code_is_zero_when_clean(sandbox, capsys):
    _desk(sandbox, "desks/ok", 10_000.0,
          [{"symbol": "SPY", "shares": 1.0, "state": "long",
            "cost_basis": 500.0, "price": 520.0}])
    assert pa.main(["--home", "desks/ok", "--max-allocation-pct", "0.12"]) == 0
    assert "CLEAN" in capsys.readouterr().out


def test_json_mode_is_machine_readable(sandbox, capsys):
    _desk(sandbox, "desks/bad", 2_000.0,
          [{"symbol": "AMPY", "shares": 12_104.0, "state": "long",
            "cost_basis": 4.08, "price": 1.69}])
    pa.main(["--home", "desks/bad", "--max-allocation-pct", "0.12", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["clean"] is False
    assert payload["reports"][0]["findings"][0]["symbol"] == "AMPY"


def test_a_missing_desk_is_not_an_error(sandbox):
    assert pa.audit("desks/nope", 0.12)["positions"] == 0


def test_the_audit_never_writes(sandbox):
    _desk(sandbox, "desks/x", 2_000.0,
          [{"symbol": "AMPY", "shares": 12_104.0, "state": "long",
            "cost_basis": 4.08, "price": 1.69}])
    path = os.path.join(sandbox, "desks/x/public/status.json")
    before = open(path).read()
    pa.main(["--home", "desks/x", "--max-allocation-pct", "0.12"])
    assert open(path).read() == before
