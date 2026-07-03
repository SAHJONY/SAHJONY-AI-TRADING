"""Dry-run verification — no pytest required.

    python -m tests.test_dry_run

Runs several offline-sim cycles and asserts the persistent state and dashboard
snapshot update correctly: cycle increments, equity recorded, council produced
for every ticker, DB rows written, and status.json valid. Exits non-zero on any
failure so CI can gate on it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

# isolate state/db/status into a temp dir so the test never touches real data
_TMP = tempfile.mkdtemp(prefix="sahjony-test-")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from config import load_config
from database import Database
from utils.alpaca_client import AlpacaClient
from utils.state_store import default_state, save_state, load_state
from workforce import Firm
from workforce.reporter import build_status, write_status, write_investor_views


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    cfg = load_config()
    _check(cfg.mode == "offline-sim", "runs in offline-sim with no credentials")
    _check(cfg.max_allocation_pct <= 0.15, "per-position cap clamped to hard ceiling")

    db = Database(os.path.join(_TMP, "t.db"))
    client = AlpacaClient(cfg)
    firm = Firm(cfg, client, db)

    state_path = os.path.join(_TMP, "state.json")
    status_path = os.path.join(_TMP, "status.json")
    state = default_state()

    last_cycle = 0
    for i in range(8):
        result = firm.run_cycle(state, trade=True)
        status = build_status(firm, cfg, state, result)
        write_status(status, status_path)
        save_state(state, state_path)
        client.advance_sim(1)
        _check(state["cycle"] == last_cycle + 1, f"cycle incremented to {state['cycle']}")
        last_cycle = state["cycle"]

    reloaded = load_state(state_path)
    _check(reloaded["cycle"] == 8, "state.json persisted 8 cycles across reload")
    _check(reloaded["equity_start"] is not None, "equity_start recorded")

    st = json.load(open(status_path))
    _check(len(st["council"]) == len(cfg.tickers), "council covers every ticker")
    _check(all(len(c["agents"]) == 12 for c in st["council"]), "all 12 agents voted per ticker")
    _check(len(st["env_catalog"]) >= 17, "env catalog exposed for dashboard")
    _check(st["health"]["voice"] is not None, "voice comms status reported")

    _check(len(db.equity_history()) == 8, "equity curve has 8 points in DB")
    _check(len(db.recent_trades()) >= 0, "trades table queryable")

    # Sanity on positions: a finite, real share count (no NaN/inf garbage).
    # NOTE: negative shares are VALID — the Pairs/StatArb desk sells short, so the
    # old `shares >= 0` assertion contradicted that feature and tripped whenever a
    # short happened to be open at cycle-end.
    for pos in st["positions"]:
        sh = pos["shares"]
        _check(isinstance(sh, (int, float)) and sh == sh and abs(sh) < 1e12,
               f"position {pos['symbol']} has a finite share count (shorts allowed)")

    # ── investor read-only share links ──
    inv_id = db.upsert_investor("Test Investor", "test@example.com", kind="investor")
    db.record_contribution(inv_id, 50000.0, 1.0)
    token = "tok_test_0123456789abcdef"
    db.set_share_token(inv_id, token)
    _check(db.get_investor_by_token(token)["id"] == inv_id, "investor resolvable by share token")
    inv_status = build_status(firm, cfg, state, result)  # rebuild with the new investor in CRM
    inv_dir = os.path.join(_TMP, "investors")
    n = write_investor_views(db, inv_status, out_dir=inv_dir)
    _check(n == 1, "one investor share view written")
    iv = json.load(open(os.path.join(inv_dir, token + ".json")))
    _check(iv["investor"]["name"] == "Test Investor", "share view carries the investor's name")
    _check(iv["investor"]["contributed"] == 50000.0, "share view shows contribution")
    _check("disclaimer" in iv, "share view carries the paper-trading disclaimer")
    blob = json.dumps(iv)
    _check(token not in blob and "test@example.com" not in blob, "share view leaks no token or email")

    db.close()
    print("\nALL DRY-RUN CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
