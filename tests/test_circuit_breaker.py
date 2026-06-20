"""Circuit breaker + kill switch verification — no pytest required.

    python -m tests.test_circuit_breaker

Asserts that:
  • a risk-ADDING intent is blocked when new risk is suspended, but
  • an exit (risk-reducing) intent still executes,
  • the daily-drawdown breaker latches once equity falls past the limit, and
  • the config clamps MAX_DAILY_DRAWDOWN_PCT to its hard ceiling.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")

from config import HARD_MAX_DAILY_DRAWDOWN_PCT, load_config
from database import Database
from strategies.base import OrderIntent
from utils.alpaca_client import AlpacaClient
from utils.state_store import default_state
from workforce import Firm
from workforce.workforce import ExecutionTrader


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="sahjony-cb-")

    # config clamp: even an absurd .env value is capped at the hard ceiling
    os.environ["MAX_DAILY_DRAWDOWN_PCT"] = "0.99"
    cfg = load_config()
    _check(cfg.max_daily_drawdown_pct <= HARD_MAX_DAILY_DRAWDOWN_PCT,
           "daily-drawdown clamped to hard ceiling")
    del os.environ["MAX_DAILY_DRAWDOWN_PCT"]
    cfg = load_config()

    db = Database(os.path.join(tmp, "t.db"))
    client = AlpacaClient(cfg)
    trader = ExecutionTrader(client, Firm(cfg, client, db).risk, db, cfg)
    state = default_state()
    sym = cfg.tickers[0]

    add = OrderIntent(symbol=sym, strategy="ladder", kind="equity", purpose="ladder_entry",
                      side="buy", qty=1, est_notional=10.0, risk_check=True)
    exit_ = OrderIntent(symbol=sym, strategy="ladder", kind="equity", purpose="trail_exit",
                        side="sell", qty=1, est_notional=10.0, risk_check=False)

    # halted: new risk blocked, exit still flows
    done, _ = trader.execute([add, exit_], state, 1, equity=100_000.0, deployed=0.0,
                             conviction=0.99, allow_new_risk=False)
    purposes = [d["purpose"] for d in done]
    _check("ladder_entry" not in purposes, "new-risk order BLOCKED when halted")
    _check("trail_exit" in purposes, "exit order ALLOWED when halted")

    # not halted: new risk flows (high conviction clears the risk gate)
    done2, _ = trader.execute([add], state, 2, equity=100_000.0, deployed=0.0,
                              conviction=0.99, allow_new_risk=True)
    _check("ladder_entry" in [d["purpose"] for d in done2], "new-risk order ALLOWED when not halted")

    # daily breaker latches when equity drops past the limit
    firm = Firm(cfg, client, db)
    s = default_state()
    h0 = firm._halt_check(s, 100_000.0)
    _check(not h0["halted"], "breaker not tripped at day open")
    drop = 100_000.0 * (1 - cfg.max_daily_drawdown_pct - 0.01)
    h1 = firm._halt_check(s, drop)
    _check(h1["halted"], "breaker trips after daily loss exceeds limit")
    h2 = firm._halt_check(s, 99_999.0)  # equity recovers same day
    _check(h2["halted"], "breaker stays LATCHED for the rest of the day")

    db.close()
    print("\nCIRCUIT BREAKER CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
