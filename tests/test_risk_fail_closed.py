"""Regression tests for malformed numeric inputs at execution risk boundaries."""
from types import SimpleNamespace

import pytest

from config import Config
from risk.account_risk import AccountRiskEngine
from risk.risk_engine import RiskEngine


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    ["equity", "deployed_value", "intended_notional", "conviction"],
)
def test_portfolio_risk_rejects_non_finite_values(field, bad):
    values = {
        "equity": 100_000.0,
        "deployed_value": 0.0,
        "intended_notional": 1_000.0,
        "conviction": 1.0,
    }
    values[field] = bad

    decision = RiskEngine(Config()).approve(symbol="SPY", **values)

    assert decision.approved is False
    assert decision.reason.startswith("invalid ")


def test_portfolio_risk_rejects_negative_exposure_and_missing_symbol():
    engine = RiskEngine(Config())

    assert not engine.approve(100_000, -1, 1_000, 1.0, "SPY").approved
    assert not engine.approve(100_000, 0, -1, 1.0, "SPY").approved
    assert not engine.approve(100_000, 0, 1_000, 1.0, " ").approved


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["equity", "proposed_notional", "daily_pnl"])
def test_account_risk_rejects_non_finite_values(field, bad):
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    values = {
        "equity": 100_000.0,
        "proposed_notional": 1_000.0,
        "daily_pnl": 0.0,
    }
    values[field] = bad

    decision = AccountRiskEngine().approve(account, **values)

    assert decision.approved is False
    assert decision.reason.startswith("invalid ")


def test_account_risk_rejects_non_positive_equity_and_negative_notional():
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    engine = AccountRiskEngine()

    assert not engine.approve(account, 0, 0).approved
    assert not engine.approve(account, 100_000, -1).approved


@pytest.mark.parametrize("field", ["max_risk", "max_position", "max_daily_loss"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.01, 0.0, 1.01])
def test_account_risk_rejects_invalid_policy_limits(field, bad):
    account = SimpleNamespace(
        id="paper",
        enabled=True,
        max_daily_loss=0.05,
        max_position=0.10,
        max_risk=0.10,
        paper=True,
    )
    setattr(account, field, bad)

    decision = AccountRiskEngine().approve(account, 100_000, 1_000)

    assert decision.approved is False
    assert decision.reason == f"invalid account {field}"


def _eng(**over):
    """Risk engine with the desks/stocks configuration: $2,000 and a 12% cap."""
    return RiskEngine(Config(max_allocation_pct=0.12, min_council_conviction=0.40,
                             max_total_deployed_pct=0.70, **over))


def test_per_position_cap_counts_the_position_not_just_the_order():
    """The regression that produced 12,104 AMPY shares on a $2,000 account.

    Each order was individually inside the $240 per-position cap; the cap only
    ever saw the increment, so averaging in compounded a position without limit.
    """
    eng = _eng()
    equity = 2_000.0                      # cap = $240
    # A lone $200 order is fine.
    assert eng.approve(equity, 0.0, 200.0, 0.9, "AMPY").approved
    # The same $200 order on top of $200 already held is not: $400 > $240.
    dec = eng.approve(equity, 200.0, 200.0, 0.9, "AMPY", existing_position_value=200.0)
    assert dec.approved is False
    assert "per-position cap" in dec.reason
    assert dec.max_notional == pytest.approx(40.0)     # room left, never negative


def test_repeated_adds_cannot_compound_past_the_cap():
    """Simulate the loop that actually ran: add every cycle, always approved."""
    eng, equity, held = _eng(), 2_000.0, 0.0
    for _ in range(200):
        dec = eng.approve(equity, held, 200.0, 0.9, "AMPY", existing_position_value=held)
        if not dec.approved:
            break
        held += 200.0
    assert held <= equity * 0.12 + 1e-9, f"position compounded to ${held:,.0f}"


def test_room_is_never_negative_when_already_over_the_cap():
    """An inherited over-cap position must block new risk, not report negative room."""
    dec = _eng().approve(2_000.0, 49_384.0, 100.0, 0.9, "AMPY",
                         existing_position_value=49_384.0)
    assert dec.approved is False
    assert dec.max_notional == 0.0


def test_existing_value_defaults_to_zero_for_old_callers():
    assert _eng().approve(2_000.0, 0.0, 200.0, 0.9, "SPY").approved


def test_negative_existing_value_is_rejected():
    dec = _eng().approve(2_000.0, 0.0, 10.0, 0.9, "SPY", existing_position_value=-1.0)
    assert dec.approved is False
    assert dec.reason == "negative existing position value"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_existing_value_fails_closed(bad):
    dec = _eng().approve(2_000.0, 0.0, 10.0, 0.9, "SPY", existing_position_value=bad)
    assert dec.approved is False
    assert dec.reason.startswith("invalid ")


# ── the gates must agree on what one symbol is worth ────────────────────────────
class _Client:
    """A venue that cannot quote some symbols — the desks/stocks situation."""
    def __init__(self, prices): self.prices = prices
    def get_price(self, sym): return self.prices.get(sym, 0.0)


def _firm(prices, **over):
    from workforce.workforce import Firm
    f = Firm.__new__(Firm)                     # no broker/DB wiring needed
    f.client = _Client(prices)
    f.cfg = Config(max_allocation_pct=0.12, **over)
    return f


def test_unpriceable_position_still_counts_against_deployed_capital():
    """A 0.0 price must not make a position weigh nothing against the caps."""
    from workforce.workforce import gross_symbol_value
    state = {"positions": {"BTCUSD": {"shares": 2.0, "cost_basis": 65_000.0}}}
    f = _firm({})                              # venue quotes nothing
    assert gross_symbol_value(f.client, state, "BTCUSD") == pytest.approx(130_000.0)
    assert f._gross_exposure(state) == pytest.approx(130_000.0)


def test_shorts_count_gross_not_net():
    from workforce.workforce import gross_symbol_value
    state = {"positions": {"DIA": {"shares": -9.935112, "cost_basis": 516.18}}}
    f = _firm({"DIA": 537.92})
    assert gross_symbol_value(f.client, state, "DIA") == pytest.approx(9.935112 * 537.92)


def test_gross_value_never_goes_negative_or_non_finite():
    from workforce.workforce import gross_symbol_value
    for pos in ({"shares": 1.0, "cost_basis": -5.0},
                {"shares": float("nan"), "cost_basis": 10.0},
                {"shares": 1.0, "cost_basis": float("inf")}):
        v = gross_symbol_value(_Client({}), {"positions": {"X": pos}}, "X")
        assert v >= 0.0 and v == v and v != float("inf")


def test_a_raising_broker_does_not_break_the_gate():
    from workforce.workforce import gross_symbol_value
    class Boom:
        def get_price(self, sym): raise RuntimeError("venue down")
    v = gross_symbol_value(Boom(), {"positions": {"X": {"shares": 3.0,
                                                        "cost_basis": 7.0}}}, "X")
    assert v == pytest.approx(21.0)            # falls back to basis, not to zero


def test_cap_breaches_report_the_over_cap_position():
    f = _firm({"AMPY": 1.69})
    state = {"positions": {"AMPY": {"shares": 12_104.0, "cost_basis": 4.08},
                           "GOOGL": {"shares": 6.0, "cost_basis": 350.09}}}
    rows = f.cap_breaches(state, 2_000.0)      # cap = $240
    assert [r["symbol"] for r in rows] == ["AMPY", "GOOGL"]
    assert rows[0]["value"] == pytest.approx(12_104.0 * 1.69, rel=1e-6)
    assert rows[0]["over_pct"] > 0


def test_cap_breaches_are_silent_when_everything_is_inside_the_cap():
    f = _firm({"GOOGL": 366.53})
    state = {"positions": {"GOOGL": {"shares": 1.0, "cost_basis": 350.09}}}
    assert f.cap_breaches(state, 100_000.0) == []


@pytest.mark.parametrize("equity", [0.0, -26_414.14, float("nan")])
def test_cap_breaches_fail_quiet_on_unusable_equity(equity):
    assert _firm({"AMPY": 1.69}).cap_breaches(
        {"positions": {"AMPY": {"shares": 12_104.0, "cost_basis": 4.08}}}, equity) == []
