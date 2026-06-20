"""Live-control logic the worker applies per desk (pure — no DB import).

The dashboard sets control fields on a desk; the worker translates them into
engine behavior here. Kept free of psycopg so it is unit-testable offline.
"""
from __future__ import annotations

from typing import Any, Dict, List


def flatten_positions(client, db, state: Dict[str, Any], cycle: int, mode: str) -> List[Dict]:
    """Close every open share position at market (the 'flatten' command).

    Mutates state (clears positions, books realized P&L) and logs each exit.
    Returns the list of flattened symbols. Risk-reducing only — always allowed,
    even when the desk is halted."""
    done: List[Dict] = []
    positions = state.setdefault("positions", {})
    for sym, pos in list(positions.items()):
        shares = float(pos.get("shares", 0) or 0)
        if shares > 0:
            px = client.get_price(sym)
            res = client.submit_equity_order(sym, shares, "sell")
            cost = float(pos.get("cost_basis", px) or px)
            realized = (px - cost) * shares
            state["realized_pnl"] = state.get("realized_pnl", 0.0) + realized
            db.log_trade({
                "cycle": cycle, "symbol": sym, "strategy": pos.get("strategy", ""),
                "kind": "equity", "side": "sell", "qty": shares, "price": px,
                "premium": 0.0, "notional": shares * px, "purpose": "flatten",
                "reason": f"flatten command: sell {shares} @ {px:.2f}", "mode": mode,
                "simulated": res.get("simulated", True),
            })
            done.append({"symbol": sym, "shares": shares, "price": px, "realized": realized})
        positions.pop(sym, None)
    return done


def resolve_command(command, halt: bool):
    """Normalize a desk's control fields into (effective_halt, action).

    action is 'flatten' | None. 'resume' clears the halt; 'flatten' also halts
    new risk for the run so we don't re-enter what we just closed."""
    cmd = (command or "").strip().lower()
    if cmd == "resume":
        return False, None
    if cmd in ("flatten", "square_off", "close_all"):
        return True, "flatten"
    return bool(halt), None
