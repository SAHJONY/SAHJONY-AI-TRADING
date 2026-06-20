"""Multi-account + 24/7 crypto verification — no pytest required.

    python -m tests.test_multi_market

Asserts:
  • SAHJONY_HOME isolates state/db/status/HALT under a per-account home dir,
  • a crypto universe auto-enables 24/7 (always_on, market always open), and
  • a crypto desk runs an offline-sim cycle and holds a FRACTIONAL position.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    # ── SAHJONY_HOME isolation ──
    home = tempfile.mkdtemp(prefix="sahjony-home-")
    os.environ["SAHJONY_HOME"] = home
    import paths
    importlib.reload(paths)
    _check(paths.home() == os.path.abspath(home), "SAHJONY_HOME becomes the desk home")
    _check(paths.state_path().startswith(home), "state.json isolated under home")
    _check(paths.db_path().startswith(home), "db isolated under home")
    _check(paths.status_path().startswith(home), "status.json isolated under home")
    _check(paths.halt_path() == os.path.join(home, "HALT"), "HALT isolated under home")

    # ── crypto desk: 24/7 + fractional ──
    os.environ["TICKERS"] = "BTC/USD,ETH/USD"
    from config import load_config
    cfg = load_config()
    _check(cfg.always_on, "all-crypto universe auto-enables 24/7 (always_on)")

    from database import Database
    from utils.alpaca_client import AlpacaClient
    from utils.state_store import default_state
    from workforce import Firm
    from workforce.workforce import PortfolioManager
    from risk.risk_engine import RiskEngine

    client = AlpacaClient(cfg)
    _check(client.is_market_open() is True, "crypto market is always open")
    _check(PortfolioManager(cfg, RiskEngine(cfg)).assign_strategy("BTC/USD", 0) == "ladder",
           "crypto routes to the ladder (never options)")

    # fractional sizing: a high-priced coin must size in fractions, not whole units
    from types import SimpleNamespace
    from strategies.trailing_ladder import TrailingLadder
    snap = SimpleNamespace(price=60000.0)                       # BTC ~ $60k
    verdict = SimpleNamespace(conviction=0.9, direction="long")
    intents = TrailingLadder(cfg).decide("BTC/USD", snap, None, verdict, budget=6000.0)
    buys = [i for i in intents if i.kind == "equity" and i.side == "buy"]
    _check(len(buys) == 1, "crypto ladder emits a buy on a high-conviction long")
    qty = buys[0].qty
    _check(0 < qty < 1, f"crypto sized FRACTIONALLY ({qty} BTC, not a whole coin)")

    # a full offline-sim cycle on a crypto desk must run without error
    db = Database(paths.db_path())
    firm = Firm(cfg, client, db)
    state = default_state()
    res = firm.run_cycle(state, trade=True)
    _check(res["cycle"] == 1 and res["equity"] > 0, "crypto desk completes a cycle")
    db.close()
    del os.environ["SAHJONY_HOME"]
    importlib.reload(paths)  # restore default paths for any later test in the process
    print("\nMULTI-MARKET CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
