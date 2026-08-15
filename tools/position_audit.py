"""Audit every desk's books against the risk invariants. Read-only.

    python -m tools.position_audit                 # all desks under desks/ + the root
    python -m tools.position_audit --home desks/stocks
    python -m tools.position_audit --json          # machine-readable, for CI

Exit code is 0 when every desk is clean and 1 when anything is wrong, so this can
gate a pipeline instead of being a report someone remembers to read.

**It never trades and never writes.** The audit is reconciliation-aware: when the
published broker account is online and the local/broker position reconciliation is
explicitly clean, broker equity becomes the denominator for portfolio caps. When
reconciliation is not clean, the audit deliberately falls back to local equity and
adds a reconciliation finding instead of mixing broker capital with a local book
that may not represent the same positions.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any, Dict, List, Tuple

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


def _equity_context(home: str) -> Tuple[float, str, bool]:
    """Return (equity, source, reconciliation_ok).

    Broker equity is authoritative only when the broker snapshot is online and the
    same published snapshot says local/broker reconciliation is clean. Otherwise
    using broker equity to cap local positions could hide a mismatch, so we keep
    local equity and force the discrepancy to remain visible.
    """
    status = _read_status(home)
    local = status.get("account") or {}
    broker = status.get("broker_account") or {}
    recon = status.get("reconciliation") or {}
    reconciliation_ok = recon.get("ok") is True
    broker_online = broker.get("online") is True

    def _number(value: Any) -> float:
        try:
            out = float(value or 0.0)
            return out if math.isfinite(out) else 0.0
        except (TypeError, ValueError):
            return 0.0

    broker_equity = _number(broker.get("equity"))
    local_equity = _number(local.get("equity"))
    if broker_online and reconciliation_ok and broker_equity > 0:
        return broker_equity, "broker_account", True
    return local_equity, "local_account", reconciliation_ok


def audit(home: str, max_allocation_pct: float) -> Dict[str, Any]:
    equity, equity_source, reconciliation_ok = _equity_context(home)
    rows = _positions(home)
    cap = equity * max_allocation_pct if equity > 0 else 0.0
    findings: List[Dict[str, Any]] = []

    status = _read_status(home)
    recon = status.get("reconciliation") or {}
    if recon and recon.get("ok") is False:
        mismatched = recon.get("mismatched") or []
        findings.append({"kind": "reconciliation", "detail":
                         f"local/broker books do not reconcile ({len(mismatched)} mismatch(es)); "
                         "broker equity is not used for cap calculations"})

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
            "equity_source": equity_source, "reconciliation_ok": reconciliation_ok,
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
                f"cap ${r['cap']:>10,.2f}  {r['positions']} position(s)  "
                f"equity={r['equity_source']}")
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
