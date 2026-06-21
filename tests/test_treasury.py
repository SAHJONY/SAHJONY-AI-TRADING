"""Treasury capital-ledger tests — no pytest, no network.

    python -m tests.test_treasury

Asserts deposits/withdrawals are recorded with the right sign, that net capital
and the trading-P&L separation are correct (a deposit is NOT a gain), that the
reporter's capital block matches, and that bad inputs are rejected.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")

from database import Database
from treasury.treasury import Treasury
from workforce.reporter import _capital_block


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    db = Database(":memory:")
    t = Treasury(db)

    # cold start: no flows → net capital 0, baseline accounting used
    s = t.summary()
    _check(s["net_capital"] == 0 and s["flows"] == 0, "cold ledger is empty")

    # deposits add (positive), withdrawals subtract (negative)
    t.deposit(10000, method="ach", note="initial")
    t.deposit(5000, method="wire")
    t.withdraw(2000, method="ach")
    s = t.summary()
    _check(s["deposits"] == 15000, "deposits sum correctly")
    _check(s["withdrawals"] == 2000, "withdrawals sum correctly")
    _check(s["net_capital"] == 13000, "net capital = deposits − withdrawals")
    _check(s["flows"] == 3, "every flow is recorded")

    # a deposit is NOT a trading gain: equity == net capital → 0% return
    cap = _capital_block(db, equity=13000.0, equity_start=10000.0)
    _check(cap["net_capital"] == 13000, "reporter net capital matches")
    _check(cap["trading_pnl"] == 0.0, "equity == net capital → trading P&L is ZERO (deposit ≠ gain)")
    _check(cap["trading_return_pct"] == 0.0, "trading return is 0% after pure funding")

    # now the strategy makes money: equity above net capital → positive P&L
    cap2 = _capital_block(db, equity=14300.0, equity_start=10000.0)
    _check(cap2["trading_pnl"] == 1300.0, "trading P&L = equity − net capital")
    _check(round(cap2["trading_return_pct"], 1) == 10.0, "trading return = +10% on $13k base")

    # withdrawal accounting: pulling capital lowers net, raises measured return on what's left
    t.withdraw(3000, method="ach")
    cap3 = _capital_block(db, equity=11300.0, equity_start=10000.0)  # 14300 − 3000 out
    _check(cap3["net_capital"] == 10000, "withdrawal reduces net capital")
    _check(round(cap3["trading_return_pct"], 1) == 13.0, "return measured against remaining net capital")

    # signed history + ordering (most recent first)
    hist = t.history()
    _check(len(hist) == 4, "history returns all flows")
    _check(hist[0]["amount"] == -3000 and hist[0]["kind"] == "withdrawal", "latest flow is the withdrawal, signed")

    # input validation
    for bad in (0, -5):
        try:
            t.deposit(bad); _check(False, "non-positive deposit should raise")
        except ValueError:
            _check(True, f"deposit({bad}) rejected")

    # no-flows fallback uses the equity_start baseline
    db2 = Database(":memory:")
    base = _capital_block(db2, equity=11000.0, equity_start=10000.0)
    _check(base["net_capital"] == 0 and round(base["trading_return_pct"], 1) == 10.0,
           "with no flows, accounting falls back to opening-equity baseline")

    db.close(); db2.close()
    print("\nTREASURY CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
