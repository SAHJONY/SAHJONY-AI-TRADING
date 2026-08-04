"""Flatten positions that the risk invariants say should not exist. Dry-run by default.

    python -m tools.remediate_positions --home desks/paper            # plan only
    python -m tools.remediate_positions --home desks/paper --apply    # send the orders

**Dry-run is the default and --apply is the only way to send an order.** This
exists because `tools.position_audit` found books that the desk itself will not
repair: the per-position cap fix stops an over-cap position growing, but nothing
unwinds one that is already there, and a desk that quietly liquidates a breach it
detected is doing something nobody asked it to. So the decision to flatten is a
human one, taken once, with the full plan printed first.

What it will flatten, and nothing else:

  over-cap        gross value above max_allocation_pct of equity
  contradiction   share sign disagrees with the recorded direction, or an open
                  position carries a non-positive cost basis

What it deliberately will NOT touch:

  unpriceable     the venue quotes no price, so neither the size of the order nor
                  its proceeds can be known. Selling into that is guessing. These
                  are listed and skipped, loudly.
  options legs    a 0-share short_put/spread leg is not flattened by selling
                  shares; unwinding it needs the options path, not this one.

Orders route through the SAME broker adapter the desk uses (utils.broker), so a
sim run exercises the real code path and a paper run behaves exactly as the desk
would. Every order is journalled to the desk's audit ledger with a
'remediation' kind, so the flattening is as auditable as any other trade.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _status(home: str) -> Dict[str, Any]:
    path = os.path.join(_ROOT, home, "public", "status.json") if home else \
        os.path.join(_ROOT, "public", "status.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def plan(home: str, max_allocation_pct: float) -> Dict[str, Any]:
    """Decide what to flatten. Pure: reads a snapshot, returns orders. No I/O out."""
    st = _status(home)
    try:
        equity = float((st.get("account") or {}).get("equity", 0.0) or 0.0)
    except (TypeError, ValueError):
        equity = 0.0
    cap = equity * max_allocation_pct if equity > 0 else 0.0

    orders: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for p in (st.get("positions") or []):
        sym = str(p.get("symbol") or "")
        try:
            shares = float(p.get("shares", 0) or 0)
            price = float(p.get("price", 0.0) or 0.0)
            basis = float(p.get("cost_basis", 0.0) or 0.0)
        except (TypeError, ValueError):
            skipped.append({"symbol": sym, "why": "unparseable position record"})
            continue
        if not sym or not shares or not math.isfinite(shares):
            continue

        if price <= 0:
            skipped.append({"symbol": sym, "why": "venue quotes no price — size and "
                                                  "proceeds are both unknown"})
            continue

        label = str(p.get("state") or "").lower()
        reasons = []
        if cap > 0 and abs(shares) * price > cap:
            reasons.append(f"over-cap ${abs(shares) * price:,.2f} vs ${cap:,.2f}")
        if (shares < 0 and label == "long") or (shares > 0 and label == "short"):
            reasons.append(f"{shares} shares recorded '{label}'")
        if not math.isfinite(basis) or basis <= 0:
            reasons.append("cost basis missing or non-positive")
        if not reasons:
            continue

        # Flattening a long is a sell; flattening a short is a buy. Quantity is
        # always the absolute size — signing the qty as well as the side would
        # double-negate and re-open the position in the opposite direction.
        orders.append({"symbol": sym, "side": "sell" if shares > 0 else "buy",
                       "qty": abs(shares), "price": price,
                       "est_proceeds": round(abs(shares) * price, 2),
                       "reason": "; ".join(reasons)})
    return {"home": home or "(root)", "equity": round(equity, 2),
            "cap": round(cap, 2), "orders": orders, "skipped": skipped}


def _render(p: Dict[str, Any]) -> str:
    out = [f"{p['home']}   equity ${p['equity']:,.2f}   per-position cap ${p['cap']:,.2f}", ""]
    if not p["orders"]:
        out.append("  nothing to flatten")
    for o in p["orders"]:
        out.append(f"  {o['side'].upper():<4} {o['qty']:>14,.6f} {o['symbol']:<8} "
                   f"@ ${o['price']:,.2f}  ≈ ${o['est_proceeds']:>12,.2f}   {o['reason']}")
    for s in p["skipped"]:
        out.append(f"  SKIP {s['symbol']:<8} {s['why']}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Flatten invariant-violating positions")
    ap.add_argument("--home", required=True, help="desk home, e.g. desks/paper")
    ap.add_argument("--max-allocation-pct", type=float, default=None)
    ap.add_argument("--apply", action="store_true",
                    help="actually send the orders (default: print the plan only)")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    pct = args.max_allocation_pct
    if pct is None:
        try:
            from config import load_config
            pct = load_config().max_allocation_pct
        except Exception:
            pct = 0.12

    p = plan(args.home, pct)
    if args.as_json:
        # The note belongs IN the payload in JSON mode — printing prose after the
        # document would make the whole stream unparseable.
        print(json.dumps(dict(p, dry_run=not args.apply), indent=2))
    else:
        print(_render(p))
        if not args.apply and p["orders"]:
            print(f"\nDRY RUN — {len(p['orders'])} order(s) NOT sent. "
                  f"Re-run with --apply to send them.")
    if not args.apply:
        return 0
    if not p["orders"]:
        return 0

    # --apply: route through the desk's own broker adapter so this is the same
    # code path, the same guards and the same audit trail as any other order.
    os.environ["SAHJONY_HOME"] = args.home
    from config import load_config
    from database import Database
    from utils.broker import get_broker
    cfg = load_config()
    client = get_broker(cfg)
    db = Database()
    print(f"\napplying against {getattr(client, 'mode', '?')} …")
    sent = failed = 0
    for o in p["orders"]:
        try:
            res = client.submit_equity_order(o["symbol"], o["qty"], o["side"])
            sent += 1
            print(f"  ok   {o['side']} {o['qty']} {o['symbol']} → {res}")
            db.append_audit("remediation", {"symbol": o["symbol"], "side": o["side"],
                                            "qty": o["qty"], "reason": o["reason"],
                                            "result": str(res)[:200]})
        except Exception as exc:
            failed += 1
            print(f"  FAIL {o['side']} {o['qty']} {o['symbol']}: {exc}", file=sys.stderr)
            db.append_audit("remediation_failed", {"symbol": o["symbol"],
                                                   "error": str(exc)[:200]})
    print(f"\n{sent} sent, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
