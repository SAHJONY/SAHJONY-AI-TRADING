"""Audit every desk's books against the risk invariants. Read-only.

    python -m tools.position_audit                 # all desks under desks/ + the root
    python -m tools.position_audit --home desks/stocks
    python -m tools.position_audit --json          # machine-readable, for CI

Exit code is 0 when every desk is clean and 1 when anything is wrong, so this can
gate a pipeline instead of being a report someone remembers to read.

**It never trades and never writes.** Three of the four findings below were live
on desks/stocks and none of them announced themselves — the desk kept running,
the dashboard kept rendering, and the damage only showed up when someone summed
a position by hand. A standing check is the difference between "the books are
clean" being a belief and being a measurement.

What it checks, and why each one hid:

  over-cap        A position larger than max_allocation_pct of equity. Until the
                  cap counted the position instead of the increment, averaging in
                  compounded past it one approved order at a time.
  unpriceable     A holding the venue will not quote. Valued at 0.0 it weighs
                  nothing against the deployed-capital cap and silently widens it.
  contradiction   A record whose fields disagree — a short recorded as long, a
                  missing cost basis. Every downstream reader is then wrong about
                  direction or P&L.
  insolvent       Equity at or below zero. The risk engine fails closed here, so
                  the desk stops trading; that is correct, and it is also a state
                  nobody should learn about from a dashboard tile.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_state(home: str) -> Dict[str, Any]:
    path = os.path.join(_ROOT, home, "data", "state.json") if home else \
        os.path.join(_ROOT, "data", "state.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _read_status(home: str) -> Dict[str, Any]:
    path = os.path.join(_ROOT, home, "public", "status.json") if home else \
        os.path.join(_ROOT, "public", "status.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _positions(home: str) -> List[Dict[str, Any]]:
    """Prefer the published snapshot: it carries the mark the desk actually used."""
    status = _read_status(home)
    rows = status.get("positions")
    if isinstance(rows, list) and rows:
        return rows
    state = _read_state(home)
    return [dict(p or {}, symbol=sym)
            for sym, p in ((state.get("positions") or {}).items())]


def _equity(home: str) -> float:
    acct = (_read_status(home).get("account") or {})
    try:
        return float(acct.get("equity", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def audit(home: str, max_allocation_pct: float) -> Dict[str, Any]:
    equity = _equity(home)
    rows = _positions(home)
    cap = equity * max_allocation_pct if equity > 0 else 0.0
    findings: List[Dict[str, Any]] = []

    if not math.isfinite(equity) or equity <= 0:
        findings.append({"kind": "insolvent", "detail":
                         f"equity {equity:,.2f} — the risk engine refuses all new risk"})

    for p in rows:
        sym = str(p.get("symbol") or "?")
        try:
            shares = float(p.get("shares", 0) or 0)
        except (TypeError, ValueError):
            findings.append({"kind": "contradiction", "symbol": sym,
                             "detail": "shares is not a number"})
            continue
        if not shares:
            continue
        if not math.isfinite(shares):
            findings.append({"kind": "contradiction", "symbol": sym,
                             "detail": "shares is not finite"})
            continue

        label = str(p.get("state") or "").lower()
        if shares < 0 and label == "long":
            findings.append({"kind": "contradiction", "symbol": sym,
                             "detail": f"{shares} shares recorded as '{label}' "
                                       f"(strategy {p.get('strategy', '?')})"})
        if shares > 0 and label == "short":
            findings.append({"kind": "contradiction", "symbol": sym,
                             "detail": f"{shares} shares recorded as '{label}'"})

        try:
            price = float(p.get("price", 0.0) or 0.0)
            basis = float(p.get("cost_basis", 0.0) or 0.0)
        except (TypeError, ValueError):
            price, basis = 0.0, 0.0
        if price <= 0:
            findings.append({"kind": "unpriceable", "symbol": sym,
                             "detail": f"venue quotes no price; marking at basis "
                                       f"${basis:,.2f} → ${abs(shares) * basis:,.2f} gross"})
        mark = price if price > 0 else basis
        value = abs(shares) * mark
        if cap > 0 and value > cap:
            findings.append({"kind": "over-cap", "symbol": sym,
                             "detail": f"${value:,.2f} vs cap ${cap:,.2f} "
                                       f"({value / cap:.1f}x, {100 * value / equity:.0f}% of equity)"})

    return {"home": home or "(root)", "equity": round(equity, 2),
            "cap": round(cap, 2), "positions": len(rows), "findings": findings}


def discover_homes() -> List[str]:
    homes = [""]
    base = os.path.join(_ROOT, "desks")
    if os.path.isdir(base):
        homes += [os.path.join("desks", d) for d in sorted(os.listdir(base))
                  if os.path.isdir(os.path.join(base, d))]
    return homes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit desk books against the risk invariants")
    ap.add_argument("--home", action="append", default=None,
                    help="desk home to audit (repeatable); default = all discovered")
    ap.add_argument("--max-allocation-pct", type=float, default=None,
                    help="override the per-position cap (default: read from config)")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    pct = args.max_allocation_pct
    if pct is None:
        try:
            from config import load_config
            pct = load_config().max_allocation_pct
        except Exception:
            pct = 0.12

    reports = [audit(h, pct) for h in (args.home or discover_homes())]
    reports = [r for r in reports if r["positions"] or r["findings"]]
    bad = sum(len(r["findings"]) for r in reports)

    if args.as_json:
        print(json.dumps({"clean": bad == 0, "reports": reports}, indent=2))
        return 0 if bad == 0 else 1

    for r in reports:
        head = (f"{r['home']:<18} equity ${r['equity']:>12,.2f}  "
                f"cap ${r['cap']:>10,.2f}  {r['positions']} position(s)")
        print(head)
        if not r["findings"]:
            print("    clean")
        for f in r["findings"]:
            sym = f" {f['symbol']}" if f.get("symbol") else ""
            print(f"    [{f['kind']}]{sym} {f['detail']}")
        print()
    print(f"{'CLEAN' if bad == 0 else str(bad) + ' FINDING(S)'} across {len(reports)} desk(s)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
