"""Is the council's conviction informative — and where? Read-only.

    python -m tools.conviction_calibration --home desks/paper --horizon 3
    python -m tools.conviction_calibration --json

The desk gates trading on `min_council_conviction`. That number was chosen, not
measured. This grades every stored verdict against what the price actually did
next, bucketed by the conviction that produced it, so the gate can be set where
the signal starts paying instead of where it looked reasonable.

**Why it needs a schema change to be useful.** `council_log` recorded conviction
and direction but not the price the verdict was formed at, so a stored verdict
could never be graded — you knew what the council believed and never what
happened next. Hermes computes a decayed hit-rate per symbol in memory, but that
is one scalar, not a distribution, and it cannot answer "at what conviction does
this become worth trading". `price` is now recorded; rows written before that
have it NULL and are skipped rather than marked with an invented price.

**Read the output with the fee in mind.** A directional hit rate above 50% is not
an edge. The desk books 60 bps round-trip on crypto, so a bucket only pays if its
mean move in the predicted direction clears that. `edge_bps` is the number that
matters; `hit_rate` is the number that flatters.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUCKETS = [(0.0, 0.45), (0.45, 0.50), (0.50, 0.52), (0.52, 0.55),
            (0.55, 0.60), (0.60, 1.01)]


def _db(home: str) -> Optional[sqlite3.Connection]:
    path = os.path.join(_ROOT, home, "data", "sahjony.db") if home else \
        os.path.join(_ROOT, "data", "sahjony.db")
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)   # never write
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def observations(conn: sqlite3.Connection, horizon: int) -> Dict[str, Any]:
    """Pair each verdict with the same symbol's price `horizon` cycles later."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(council_log)").fetchall()}
    if "price" not in cols:
        # Distinguish "no data" from "data this cannot read". A DB written before
        # the price column exists is FULL of verdicts and none of them gradeable;
        # reporting that as "0 of 0" would hide the reason.
        try:
            n = conn.execute("SELECT COUNT(*) c FROM council_log").fetchone()["c"]
        except sqlite3.Error:
            n = 0
        return {"observations": [], "graded": 0, "ungradeable": int(n),
                "total": int(n), "no_price_column": True}
    try:
        rows = conn.execute(
            "SELECT cycle, symbol, conviction, direction, price FROM council_log "
            "ORDER BY symbol, cycle").fetchall()
    except sqlite3.Error:
        return {"observations": [], "graded": 0, "ungradeable": 0, "total": 0}

    by_symbol: Dict[str, Dict[int, float]] = {}
    for r in rows:
        if r["price"] and r["price"] > 0:
            by_symbol.setdefault(r["symbol"], {})[int(r["cycle"])] = float(r["price"])

    out, ungradeable = [], 0
    for r in rows:
        sym, cyc = r["symbol"], int(r["cycle"])
        entry = r["price"]
        later = by_symbol.get(sym, {}).get(cyc + horizon)
        direction = str(r["direction"] or "").lower()
        if not entry or entry <= 0 or later is None or direction not in ("long", "short"):
            ungradeable += 1
            continue
        move = later / entry - 1.0
        signed = move if direction == "long" else -move
        out.append({"symbol": sym, "cycle": cyc,
                    "conviction": float(r["conviction"] or 0.0),
                    "direction": direction, "signed_return": signed})
    return {"observations": out, "graded": len(out), "ungradeable": ungradeable,
            "total": len(rows)}


def calibrate(obs: List[Dict[str, Any]], fee_bps: float) -> List[Dict[str, Any]]:
    """Hit rate and net edge per conviction bucket. Net of the round-trip fee,
    because a directional call the desk cannot afford to act on is not a signal."""
    table = []
    for lo, hi in _BUCKETS:
        sel = [o for o in obs if lo <= o["conviction"] < hi]
        n = len(sel)
        if not n:
            table.append({"bucket": f"{lo:.2f}-{hi:.2f}", "n": 0, "hit_rate": None,
                          "mean_bps": None, "edge_bps": None})
            continue
        hits = sum(1 for o in sel if o["signed_return"] > 0)
        mean_bps = 10_000.0 * sum(o["signed_return"] for o in sel) / n
        table.append({"bucket": f"{lo:.2f}-{hi:.2f}", "n": n,
                      "hit_rate": round(hits / n, 3),
                      "mean_bps": round(mean_bps, 1),
                      "edge_bps": round(mean_bps - fee_bps, 1)})
    return table


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Grade council conviction against what happened next")
    ap.add_argument("--home", default="", help="desk home, e.g. desks/paper")
    ap.add_argument("--horizon", type=int, default=3, help="cycles ahead to grade against")
    ap.add_argument("--fee-bps", type=float, default=None,
                    help="round-trip cost in bps (default: config fee_bps_crypto)")
    ap.add_argument("--min-n", type=int, default=30,
                    help="bucket sample below which no conclusion is drawn")
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args(argv)

    fee = args.fee_bps
    if fee is None:
        try:
            from config import load_config
            fee = load_config().fee_bps_crypto
        except Exception:
            fee = 60.0

    conn = _db(args.home)
    if conn is None:
        print(f"no database for home '{args.home or '(root)'}'")
        return 2
    try:
        data = observations(conn, args.horizon)
    finally:
        conn.close()

    table = calibrate(data["observations"], fee)
    payload = {"home": args.home or "(root)", "horizon_cycles": args.horizon,
               "fee_bps": fee, "graded": data["graded"],
               "ungradeable": data["ungradeable"], "total_verdicts": data["total"],
               "buckets": table}

    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{payload['home']}  horizon {args.horizon} cycle(s)  "
              f"round-trip fee {fee:.0f} bps")
        print(f"graded {data['graded']} of {data['total']} verdicts "
              f"({data['ungradeable']} ungradeable — no price recorded, no forward "
              f"price yet, or a flat call)\n")
        print(f"{'conviction':<14}{'n':>7}{'hit rate':>11}{'mean bps':>11}{'net of fee':>13}")
        for b in table:
            if not b["n"]:
                print(f"{b['bucket']:<14}{0:>7}{'—':>11}{'—':>11}{'—':>13}")
                continue
            flag = "" if b["n"] >= args.min_n else "  (thin)"
            print(f"{b['bucket']:<14}{b['n']:>7}{b['hit_rate']:>11.3f}"
                  f"{b['mean_bps']:>11.1f}{b['edge_bps']:>13.1f}{flag}")
        solid = [b for b in table if b["n"] >= args.min_n and (b["edge_bps"] or 0) > 0]
        print()
        if data.get("no_price_column"):
            print(f"NO CONCLUSION — this database predates council_log.price, so all "
                  f"{data['total']} stored\nverdicts are ungradeable. The column is added "
                  f"on the next write; grading needs\n{args.horizon}+ cycles recorded "
                  f"after that.")
        elif not data["graded"]:
            print("NO CONCLUSION — nothing gradeable yet. council_log.price is only "
                  "populated\nfrom the cycle this column shipped, so this needs "
                  f"{args.horizon}+ cycles of new data.")
        elif solid:
            lo = min(float(b["bucket"].split("-")[0]) for b in solid)
            print(f"Buckets clearing the fee with n>={args.min_n} start at conviction "
                  f"{lo:.2f}.\nThat is where the evidence puts the gate — not a "
                  f"recommendation to move it today.")
        else:
            print(f"NO BUCKET clears the {fee:.0f} bps round-trip cost at n>="
                  f"{args.min_n}.\nOn this data the council's direction call is not "
                  f"worth acting on at any conviction,\nwhich is a result about the "
                  f"signal, not about where to put the gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
