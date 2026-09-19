"""Trade memory and post-mortems.

Every closed trade gets a structured post-mortem persisted to JSONL:
entry rationale, regime at entry, what worked, what did not. Unknowns are
recorded explicitly as "unknown" — never invented.

Query API answers questions like: "what happened the last five times we
bought ETH in a high-volatility regime?"

Storage: data/trade_postmortems.jsonl under SAHJONY_HOME (isolated per desk).
Fault-isolated: any I/O problem degrades to a no-op in-memory store.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from paths import home
from utils.logger import get_logger

log = get_logger("trade_memory")

_UNKNOWN = "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


class TradeMemory:
    """Append-only JSONL post-mortem store with a small query engine."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(home(), "data", "trade_postmortems.jsonl")
        self.enabled = str(os.getenv("TRADE_MEMORY_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        self._mem: List[Dict[str, Any]] = []   # in-memory mirror (I/O may fail)

    # ── recording ─────────────────────────────────────────────────────────────
    def record_close(self, *, symbol: str, side: str, qty: float,
                     entry_price: float, exit_price: float, realized_pnl: float,
                     strategy: str = _UNKNOWN, regime_at_entry: str = _UNKNOWN,
                     entry_rationale: str = "", entry_ts: str = "",
                     cycles_held: int = 0,
                     entry_conviction: Optional[float] = None) -> Dict[str, Any]:
        """Persist one post-mortem. worked/didnt are derived ONLY from measured
        features; anything not recorded is 'unknown', never invented."""
        entry_price = _finite(entry_price)
        exit_price = _finite(exit_price)
        realized_pnl = _finite(realized_pnl)
        qty = _finite(qty)
        pnl_pct = (exit_price / entry_price - 1.0) if entry_price > 0 else 0.0
        if side == "sell":  # closing a short: invert the sign convention
            pnl_pct = -pnl_pct
        if not math.isfinite(pnl_pct):
            pnl_pct = 0.0

        worked: List[str] = []
        didnt: List[str] = []
        if realized_pnl > 0:
            worked.append(f"profitable exit: {pnl_pct:+.2%} over {cycles_held} cycles")
        elif realized_pnl < 0:
            didnt.append(f"losing exit: {pnl_pct:+.2%} over {cycles_held} cycles")
            if abs(pnl_pct) <= 0.02:
                worked.append("loss contained to <=2% (cut stayed small)")
            else:
                didnt.append("loss exceeded 2% — exit discipline under review")
        else:
            worked.append("flat exit (no P&L impact)")

        rationale = (entry_rationale or "").strip() or _UNKNOWN
        regime = (regime_at_entry or "").strip() or _UNKNOWN

        try:
            _ec = float(entry_conviction) if entry_conviction is not None else None
            _ec = _ec if _ec is not None and math.isfinite(_ec) else None
        except (TypeError, ValueError):
            _ec = None
        pm = {
            "ts": _now(),
            "symbol": str(symbol),
            "side": str(side or _UNKNOWN),
            "strategy": str(strategy or _UNKNOWN),
            "qty": round(qty, 8),
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "realized_pnl": round(realized_pnl, 4),
            "pnl_pct": round(pnl_pct, 6),
            "cycles_held": int(cycles_held or 0),
            "regime_at_entry": regime,
            "entry_rationale": rationale,
            "entry_ts": entry_ts or _UNKNOWN,
            "entry_conviction": round(_ec, 3) if _ec is not None else None,
            "worked": worked,
            "didnt": didnt,
        }
        self._mem.append(pm)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(pm) + "\n")
        except Exception as exc:
            log.warning("post-mortem persist failed (kept in memory): %s", exc)
        return pm

    # ── queries ───────────────────────────────────────────────────────────────
    def _all(self) -> List[Dict[str, Any]]:
        if self._mem:
            return list(self._mem)
        # cold start: load from disk once
        rows: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass
        self._mem = rows
        return list(rows)

    def query(self, *, symbol: Optional[str] = None, regime: Optional[str] = None,
              side: Optional[str] = None, strategy: Optional[str] = None,
              outcome: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Recent-first filtered post-mortems. outcome: 'win' | 'loss' | 'flat'."""
        rows = self._all()
        out: List[Dict[str, Any]] = []
        for pm in reversed(rows):
            if symbol and str(pm.get("symbol")) != str(symbol):
                continue
            if regime and str(pm.get("regime_at_entry")) != str(regime):
                continue
            if side and str(pm.get("side")) != str(side):
                continue
            if strategy and str(pm.get("strategy")) != str(strategy):
                continue
            if outcome:
                pnl = _finite(pm.get("realized_pnl"))
                want = {"win": pnl > 0, "loss": pnl < 0, "flat": pnl == 0}.get(outcome)
                if not want:
                    continue
            out.append(pm)
            if len(out) >= max(1, int(limit)):
                break
        return out

    def stats(self) -> Dict[str, Any]:
        rows = self._all()
        wins = sum(1 for r in rows if _finite(r.get("realized_pnl")) > 0)
        losses = sum(1 for r in rows if _finite(r.get("realized_pnl")) < 0)
        return {
            "post_mortems": len(rows),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(1, wins + losses), 3) if (wins + losses) else None,
            "total_realized": round(sum(_finite(r.get("realized_pnl")) for r in rows), 2),
        }

    def lessons(self, limit: int = 20) -> List[str]:
        """Evidence-based lesson strings for the knowledge base / self-review."""
        rows = self._all()[-max(1, int(limit)):]
        lessons: List[str] = []
        by_regime: Dict[str, List[float]] = {}
        for r in rows:
            by_regime.setdefault(str(r.get("regime_at_entry") or _UNKNOWN), []).append(
                _finite(r.get("realized_pnl")))
        for regime, pnls in by_regime.items():
            if len(pnls) >= 3:
                wr = sum(1 for p in pnls if p > 0) / len(pnls)
                lessons.append(
                    f"last {len(pnls)} closes entered in '{regime}' regime: "
                    f"{wr:.0%} win-rate, ${sum(pnls):+.2f} total")
        for r in rows:
            for d in r.get("didnt") or []:
                lessons.append(f"{r.get('symbol')}: {d}")
        return lessons[:50]
