"""Live-control logic verification — no pytest, no DB needed.

    python -m tests.test_controls

Asserts the worker's control translation: the kill switch halts new risk, the
'flatten' command closes every position (booking realized P&L and logging exits),
and command/halt resolution behaves correctly.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")

from config import load_config
from database import Database
from utils.alpaca_client import AlpacaClient
from utils.state_store import default_state
from worker.controls import flatten_positions, resolve_command
from workforce import Firm


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    # ── command/halt resolution ──
    _check(resolve_command(None, False) == (False, None), "no command, not halted → run normally")
    _check(resolve_command(None, True) == (True, None), "halt flag → halted, no action")
    _check(resolve_command("flatten", False) == (True, "flatten"), "flatten → halt + flatten action")
    _check(resolve_command("resume", True) == (False, None), "resume → clears halt")

    # ── kill switch halts new risk (TRADING_HALT honored by the engine) ──
    os.environ["TRADING_HALT"] = "true"
    cfg = load_config()
    _check(cfg.trading_halt is True, "TRADING_HALT env parsed")
    db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
    client = AlpacaClient(cfg)
    firm = Firm(cfg, client, db)
    h = firm._halt_check(default_state(), 100_000.0)
    _check(h["halted"] and "kill switch" in h["reason"], "kill switch halts new risk")
    del os.environ["TRADING_HALT"]

    # ── flatten closes every position and books P&L ──
    cfg = load_config()
    db2 = Database(os.path.join(tempfile.mkdtemp(), "t2.db"))
    client2 = AlpacaClient(cfg)
    sym = cfg.tickers[0]
    px = client2.get_price(sym)
    state = default_state()
    state["positions"] = {sym: {"strategy": "ladder", "shares": 10, "cost_basis": px * 0.9}}
    done = flatten_positions(client2, db2, state, cycle=1, mode="offline-sim")
    _check(len(done) == 1 and done[0]["symbol"] == sym, "flatten reported the closed position")
    _check(not state["positions"], "all positions cleared after flatten")
    _check(state["realized_pnl"] > 0, "realized P&L booked (sold above cost)")
    trades = db2.recent_trades(10)
    _check(any(t["purpose"] == "flatten" and t["side"] == "sell" for t in trades),
           "flatten exit logged as a sell trade")

    db.close(); db2.close()
    print("\nLIVE CONTROL CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
