"""Alt-data intelligence — QuiverQuant insider & congressional trading overlay.

A fault-isolated ADVISORY signal, in the same spirit as the AI brain: it reads
QuiverQuant's public-disclosure alt-data (recent insider buys/sells and
congressional trades per symbol) and turns it into a small per-symbol conviction
*tilt* in [-0.15, 0.15]. Positive = net buying by insiders/politicians (mildly
constructive), negative = net selling. It NEVER invents trades — the deterministic
quant council remains the decision-maker; this only nudges conviction, and the
Risk Officer still gates every order.

Wiring (no secrets in the repo):
  QUIVER_API_KEY=…              # from .env locally / GitHub Actions secret in CI
  QUIVER_ENABLED=true           # optional; auto-on whenever a key is present
NOTE: the Python desk runs on GitHub Actions (not Vercel), so the key must live
as a GitHub Actions secret — a Vercel env var can't reach the trading loop.

Every call is wrapped: no key, no network, or a format change → empty signals and
a neutral tilt, so the trading loop never breaks. Results are cached per instance
for a short TTL so we don't hammer the API each cycle.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

from config import Config
from utils.logger import get_logger

log = get_logger("alt_data")

# Tilt is clamped small so alt-data can nudge conviction, never hijack it.
_MAX_TILT = 0.15
_DEFAULT_BASE = "https://api.quiverquant.com/beta"
_CACHE_TTL_S = 3600.0          # disclosures update slowly; one pull/hour is plenty
_LOOKBACK_DAYS = 90            # weigh only reasonably recent disclosures


@dataclass
class AltSignal:
    symbol: str
    tilt: float = 0.0                 # conviction nudge in [-0.15, 0.15]
    insider_net: float = 0.0          # normalized net insider buy(+)/sell(-)
    congress_net: float = 0.0         # normalized net congress buy(+)/sell(-)
    summary: str = ""


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


class AltData:
    """QuiverQuant alt-data overlay. Fault-isolated; neutral when unavailable."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.key = (os.getenv("QUIVER_API_KEY", "") or os.getenv("QUIVERQUANT_API_KEY", "")).strip()
        self.base = (os.getenv("QUIVER_BASE_URL", _DEFAULT_BASE) or _DEFAULT_BASE).strip().rstrip("/")
        # Auto-on whenever a key is present; QUIVER_ENABLED=false forces it off.
        env = os.getenv("QUIVER_ENABLED")
        self.enabled = bool(self.key) and (env is None or env.strip().lower() in ("1", "true", "yes", "on"))
        self._cache: Dict[str, AltSignal] = {}
        self._cache_ts = 0.0

    @property
    def status(self) -> Dict[str, object]:
        return {"enabled": self.enabled, "provider": "quiverquant",
                "key_set": bool(self.key), "cached_symbols": len(self._cache)}

    # ── public entry point ──────────────────────────────────────────────────────
    def signals(self, symbols: List[str]) -> Dict[str, AltSignal]:
        """Return {symbol: AltSignal} for the requested symbols. Empty if disabled;
        any per-symbol failure degrades that symbol to a neutral tilt."""
        if not self.enabled or not symbols:
            return {}
        now = time.time()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL_S:
            return {s: self._cache[s] for s in symbols if s in self._cache}
        out: Dict[str, AltSignal] = {}
        for sym in symbols:
            # FX pairs / crypto have no insider/congress disclosures — skip cleanly.
            if "/" in sym:
                continue
            try:
                out[sym] = self._for_symbol(sym)
            except Exception as exc:  # one symbol's failure never sinks the overlay
                log.warning("quiver alt-data failed for %s: %s", sym, exc)
                out[sym] = AltSignal(symbol=sym, summary="unavailable")
        self._cache = out
        self._cache_ts = now
        return out

    # ── per-symbol fetch + scoring ────────────────────────────────────────────────
    def _for_symbol(self, sym: str) -> AltSignal:
        insider = self._insider_net(sym)
        congress = self._congress_net(sym)
        # Blend: insiders know the company; politicians are noisier → weight insiders more.
        tilt = _clamp(0.6 * insider + 0.4 * congress, -_MAX_TILT, _MAX_TILT)
        bits = []
        if insider:
            bits.append(f"insider {'buys' if insider > 0 else 'sells'}")
        if congress:
            bits.append(f"congress {'buys' if congress > 0 else 'sells'}")
        summary = ", ".join(bits) or "no recent disclosures"
        return AltSignal(symbol=sym, tilt=tilt, insider_net=round(insider, 3),
                         congress_net=round(congress, 3), summary=summary)

    def _get(self, path: str) -> list:
        import requests
        # QuiverQuant accepts a Bearer token; some deployments use "Token <key>".
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.key}"}
        r = requests.get(self.base + path, headers=headers, timeout=12)
        if r.status_code in (401, 403):
            # retry with the legacy "Token" scheme before giving up
            headers["Authorization"] = f"Token {self.key}"
            r = requests.get(self.base + path, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else (data.get("data") or [])

    def _insider_net(self, sym: str) -> float:
        """Net insider sentiment from recent Form 4 disclosures, in [-1, 1]."""
        rows = self._get(f"/historical/insiders/{sym}")
        buys = sells = 0.0
        for row in self._recent(rows):
            amt = self._amount(row)
            code = str(row.get("TransactionCode") or row.get("AcquiredDisposedCode") or "").upper()
            txt = str(row.get("Transaction") or row.get("TransactionType") or "").lower()
            if code in ("P", "A") or "purchase" in txt or "buy" in txt:
                buys += amt
            elif code in ("S", "D") or "sale" in txt or "sell" in txt:
                sells += amt
        return self._ratio(buys, sells)

    def _congress_net(self, sym: str) -> float:
        """Net congressional-trading sentiment for the symbol, in [-1, 1]."""
        rows = self._get(f"/historical/congresstrading/{sym}")
        buys = sells = 0.0
        for row in self._recent(rows):
            amt = self._amount(row)
            txn = str(row.get("Transaction") or row.get("Type") or "").lower()
            if "purchase" in txn or "buy" in txn:
                buys += amt
            elif "sale" in txn or "sell" in txn:
                sells += amt
        return self._ratio(buys, sells)

    # ── helpers ───────────────────────────────────────────────────────────────────
    @staticmethod
    def _ratio(buys: float, sells: float) -> float:
        total = buys + sells
        if total <= 0:
            return 0.0
        return _clamp((buys - sells) / total, -1.0, 1.0)

    @staticmethod
    def _amount(row: dict) -> float:
        for k in ("Amount", "Value", "Range", "Shares", "Trade_Size_USD"):
            v = row.get(k)
            if isinstance(v, (int, float)) and v:
                return abs(float(v))
        return 1.0  # count the disclosure itself when no dollar amount is given

    @staticmethod
    def _recent(rows: list) -> list:
        """Keep rows whose date is within the lookback window (best-effort parse)."""
        from datetime import datetime, timedelta, timezone
        if not isinstance(rows, list):
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        kept = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw = (row.get("Date") or row.get("TransactionDate") or row.get("ReportDate") or "")
            try:
                d = datetime.fromisoformat(str(raw)[:10]).replace(tzinfo=timezone.utc)
                if d >= cutoff:
                    kept.append(row)
            except Exception:
                kept.append(row)  # undated → keep; scoring still bounded
        return kept
