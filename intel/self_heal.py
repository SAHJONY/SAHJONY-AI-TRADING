"""Self-healing: autonomous recovery with a hard safety line.

The watchdog observes every cycle and grades four subsystems —
broker API auth, price feeds, data freshness, cycle exceptions — as
healthy / degraded / critical.

Recovery ladder (automatic, with backoff):
- price feeds: retry, then FAIL OVER sources
  (venue → CoinGecko → Kraken → Coinbase public feeds)
- single bad symbols: skip-and-continue (extends the existing per-symbol guard)
- cycle exceptions: count, back off, keep the desk observing

Circuit breaker: on CRITICAL (broker auth broken, ALL feeds dead) the desk
halts NEW order placement automatically, keeps observing, and resumes trading
only after health returns to healthy for _HEALTHY_STREAK consecutive checks.

3-strike escalation: after 3 failed auto-recoveries on one subsystem, the desk
stands down to dry-run and writes a clear escalation note into status.json (and
the daily brief) telling Juan exactly what broke and what HE needs to do
(e.g. "Robinhood API key rejected — recreate credentials"). The healer NEVER
attempts to fix credentials itself — it only reports.

All healing actions append to an auditable `healing_log` (bounded, surfaced in
status.json). The healer never raises: a broken healer degrades to "unknown",
never to a trading halt it didn't earn.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from utils.logger import get_logger

log = get_logger("self_heal")

_STATES = ("healthy", "degraded", "critical", "unknown")
_HEALTHY_STREAK = 3        # consecutive healthy checks to lift a circuit breaker
_MAX_STRIKES = 3           # failed recoveries before dry-run stand-down
_LOG_CAP = 50
_FEED_TIMEOUT = 8

# Price failover order after the venue feed: all keyless public feeds.
_CG_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
           "ADA": "cardano", "XRP": "ripple", "LTC": "litecoin", "AVAX": "avalanche-2",
           "LINK": "chainlink", "DOT": "polkadot", "MATIC": "matic-network",
           "ATOM": "cosmos", "NEAR": "near", "UNI": "uniswap", "ARB": "arbitrum",
           "OP": "optimism", "INJ": "injective-protocol", "SUI": "sui", "APT": "aptos"}
_KRAKEN = {"BTC": "XBTUSD", "ETH": "ETHUSD", "SOL": "SOLUSD", "DOGE": "DOGEUSD",
           "ADA": "ADAUSD", "XRP": "XRPUSD", "LTC": "LTCUSD", "LINK": "LINKUSD",
           "DOT": "DOTUSD", "MATIC": "MATICUSD", "ATOM": "ATOMUSD", "NEAR": "NEARUSD",
           "UNI": "UNIUSD", "AVAX": "AVAXUSD"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base(symbol: str) -> str:
    s = str(symbol or "").upper()
    for sep in ("/", "-", ":"):
        if sep in s:
            s = s.split(sep)[0]
    return s.strip()


def robust_price(symbol: str, client=None, state: Optional[Dict] = None,
                 timeout: int = _FEED_TIMEOUT) -> Dict[str, Any]:
    """Best-effort price with source failover. Returns {price, source} or
    {price: None, source: None, error}. Never raises."""
    base = _base(symbol)
    # 1) venue client
    if client is not None:
        try:
            p = float(client.get_price(symbol))
            if math.isfinite(p) and p > 0:
                return {"price": p, "source": "venue"}
        except Exception:
            pass
    # 2) CoinGecko (keyless)
    cg = _CG_IDS.get(base)
    if cg:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                             params={"ids": cg, "vs_currencies": "usd"},
                             timeout=timeout)
            p = float(r.json()[cg]["usd"])
            if math.isfinite(p) and p > 0:
                return {"price": p, "source": "coingecko"}
        except Exception:
            pass
    # 3) Kraken (keyless)
    kp = _KRAKEN.get(base)
    if kp:
        try:
            r = requests.get("https://api.kraken.com/0/public/Ticker",
                             params={"pair": kp}, timeout=timeout)
            p = float(r.json()["result"][next(iter(r.json()["result"]))]["c"][0])
            if math.isfinite(p) and p > 0:
                return {"price": p, "source": "kraken"}
        except Exception:
            pass
    # 4) Coinbase (keyless)
    try:
        r = requests.get(f"https://api.coinbase.com/v2/prices/{base}-USD/spot",
                         timeout=timeout)
        p = float(r.json()["data"]["amount"])
        if math.isfinite(p) and p > 0:
            return {"price": p, "source": "coinbase"}
    except Exception:
        pass
    return {"price": None, "source": None, "error": f"all price sources failed for {base}"}


class SelfHeal:
    """Cycle watchdog + recovery ladder + circuit breaker + escalation."""

    SUBSYSTEMS = ("broker_api", "price_feeds", "data_freshness", "cycle_health")

    def __init__(self, cfg=None):
        import os
        self.enabled = str(os.getenv("SELF_HEAL_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        self.cfg = cfg

    # ── main entry: called once per cycle with the cycle's observations ───────
    def observe(self, state: Dict[str, Any], obs: Dict[str, Any]) -> Dict[str, Any]:
        """obs: {account_ok, account_error, price_errors: {sym: err},
                  exceptions: [str], feed_ok, cycle}. Fault-isolated."""
        try:
            mem = state.setdefault("self_heal", {})
            health: Dict[str, Dict[str, Any]] = mem.setdefault("health", {})
            strikes: Dict[str, int] = mem.setdefault("strikes", {})
            log_list: List[Dict[str, Any]] = mem.setdefault("log", [])

            def _log(sub: str, action: str, result: str) -> None:
                log_list.append({"ts": _now(), "subsystem": sub,
                                 "action": action, "result": result})
                del log_list[:-_LOG_CAP]

            # grade each subsystem
            grades = self._grade(obs)
            for sub in self.SUBSYSTEMS:
                prev = health.get(sub, {})
                new_state = grades[sub]["state"]
                if new_state == "healthy":
                    if prev.get("state") != "healthy":
                        _log(sub, "recovered", grades[sub].get("detail", "ok"))
                    strikes[sub] = 0
                    health[sub] = {"state": "healthy",
                                   "healthy_streak": int(prev.get("healthy_streak", 0)) + 1,
                                   "detail": grades[sub].get("detail", "ok")}
                else:
                    strikes[sub] = int(strikes.get(sub, 0)) + 1
                    health[sub] = {"state": new_state, "healthy_streak": 0,
                                   "strikes": strikes[sub],
                                   "detail": grades[sub].get("detail", "")}
                    _log(sub, f"auto-recovery attempt {strikes[sub]}",
                         self._recover(sub, grades[sub], state))

            # circuit breaker: critical broker or all-feeds-dead halts new orders
            breaker = mem.setdefault("breaker", {"tripped": False})
            critical = [s for s in self.SUBSYSTEMS
                        if health.get(s, {}).get("state") == "critical"]
            hard_critical = any(s in ("broker_api", "price_feeds") for s in critical)
            if hard_critical and not breaker["tripped"]:
                breaker.update({"tripped": True, "since": _now(),
                                "reason": "; ".join(
                                    f"{s}: {health[s].get('detail', '')}" for s in critical)})
                _log("breaker", "CIRCUIT BREAKER TRIPPED — new orders halted, "
                                "desk keeps observing", breaker["reason"])
                log.error("SELF-HEAL circuit breaker tripped: %s", breaker["reason"])
            if breaker["tripped"]:
                # resume only after EVERY previously-critical subsystem is healthy
                # for _HEALTHY_STREAK consecutive checks
                clear = all(health.get(s, {}).get("healthy_streak", 0) >= _HEALTHY_STREAK
                            for s in ("broker_api", "price_feeds"))
                if clear:
                    breaker.update({"tripped": False, "resumed_at": _now()})
                    _log("breaker", "circuit breaker LIFTED — health green for "
                                    f"{_HEALTHY_STREAK} checks, trading resumes", "ok")

            # 3-strike escalation → dry-run stand-down + plain-language note
            esc = mem.get("escalation")
            for sub in self.SUBSYSTEMS:
                if strikes.get(sub, 0) >= _MAX_STRIKES and not (
                        esc and esc.get("subsystem") == sub and esc.get("active")):
                    note = self._escalation_note(sub, health.get(sub, {}))
                    mem["escalation"] = {"active": True, "subsystem": sub,
                                         "ts": _now(), "note": note,
                                         "dry_run_standdown": True}
                    _log(sub, "3-STRIKE ESCALATION — desk stood down to dry-run", note)
                    log.error("SELF-HEAL escalation: %s", note)
            esc = mem.get("escalation")
            if esc and esc.get("active"):
                # auto-clear the escalation when the subsystem recovers
                sub = esc.get("subsystem")
                if health.get(sub, {}).get("state") == "healthy":
                    esc["active"] = False
                    esc["cleared_at"] = _now()
                    _log(sub, "escalation cleared — subsystem healthy", "ok")

            mem["last_check"] = _now()
            return self.snapshot(state)
        except Exception as exc:  # the healer never breaks the desk
            log.warning("self-heal observe failed: %s", exc)
            return {"enabled": self.enabled, "error": str(exc)[:120]}

    # ── grading ───────────────────────────────────────────────────────────────
    @staticmethod
    def _grade(obs: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        out: Dict[str, Dict[str, str]] = {}
        # broker API
        if obs.get("account_ok"):
            out["broker_api"] = {"state": "healthy", "detail": "account read ok"}
        else:
            err = str(obs.get("account_error") or "unknown")
            auth_words = ("401", "403", "unauthorized", "forbidden", "invalid api",
                          "authentication", "api key")
            state = "critical" if any(w in err.lower() for w in auth_words) else "degraded"
            out["broker_api"] = {"state": state, "detail": f"account read failed: {err[:100]}"}
        # price feeds
        perrs = obs.get("price_errors") or {}
        total = int(obs.get("price_symbols") or max(1, len(perrs)))
        if not perrs:
            out["price_feeds"] = {"state": "healthy", "detail": "all symbols priced"}
        elif len(perrs) >= total:
            out["price_feeds"] = {"state": "critical",
                                  "detail": f"all {total} price feeds failed"}
        else:
            out["price_feeds"] = {"state": "degraded",
                                  "detail": f"{len(perrs)}/{total} symbols unpriceable: "
                                            f"{', '.join(sorted(perrs)[:4])}"}
        # data freshness
        if obs.get("feed_ok") is False:
            out["data_freshness"] = {"state": "degraded", "detail": "feed guard flagged stale data"}
        else:
            out["data_freshness"] = {"state": "healthy", "detail": "feeds fresh"}
        # cycle exceptions
        excs = obs.get("exceptions") or []
        if not excs:
            out["cycle_health"] = {"state": "healthy", "detail": "no cycle exceptions"}
        elif len(excs) >= 5:
            out["cycle_health"] = {"state": "critical",
                                   "detail": f"{len(excs)} exceptions this cycle"}
        else:
            out["cycle_health"] = {"state": "degraded",
                                   "detail": f"{len(excs)} exceptions: "
                                             f"{'; '.join(excs[:2])[:100]}"}
        return out

    # ── recovery ladder (no credential touching, ever) ────────────────────────
    @staticmethod
    def _recover(sub: str, grade: Dict[str, str], state: Dict[str, Any]) -> str:
        detail = grade.get("detail", "")
        if sub == "price_feeds":
            return ("backoff + failover: venue → CoinGecko → Kraken → Coinbase; "
                    f"single bad symbols skipped ({detail})")
        if sub == "broker_api":
            # HARD LINE: never attempt to fix credentials. Only report.
            return ("NO credential action taken (policy) — will re-probe with "
                    "backoff; escalation tells the owner exactly what to do")
        if sub == "data_freshness":
            return "serving last-good quotes; quarantine already blocks new risk on stale feeds"
        return f"exception counted, cycle continues in observe-only posture ({detail})"

    @staticmethod
    def _escalation_note(sub: str, health: Dict[str, Any]) -> str:
        detail = health.get("detail", "")
        if sub == "broker_api":
            return ("🔧 ACTION NEEDED: the broker API is rejecting us "
                    f"({detail}). The bot CANNOT fix credentials itself — "
                    "recreate the API key/secret on the broker's website and "
                    "update the stored secret. The desk is in dry-run until the "
                    "API answers again; it will resume automatically.")
        if sub == "price_feeds":
            return ("🔧 ACTION NEEDED: every price source is down "
                    f"({detail}). Check internet/API status; no credential can "
                    "fix this. The desk is observing only (dry-run) until a "
                    "feed returns.")
        return (f"🔧 ACTION NEEDED: '{sub}' failed 3 auto-recoveries ({detail}). "
                "The desk stood down to dry-run. Review the healing log, fix "
                "the underlying issue, and the desk resumes on green health.")

    # ── queries used by the trading loop ──────────────────────────────────────
    def trading_blocked(self, state: Dict[str, Any]) -> tuple:
        """(blocked: bool, reason: str) — consulted before any new risk."""
        try:
            mem = state.get("self_heal") or {}
            if (mem.get("breaker") or {}).get("tripped"):
                return True, f"self-heal circuit breaker: {(mem['breaker'].get('reason') or '')[:160]}"
            esc = mem.get("escalation") or {}
            if esc.get("active") and esc.get("dry_run_standdown"):
                return True, f"self-heal escalation stand-down: {(esc.get('note') or '')[:160]}"
            return False, ""
        except Exception:
            return False, ""

    def snapshot(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            mem = state.get("self_heal") or {}
            return {
                "enabled": self.enabled,
                "health": {s: {"state": (mem.get("health") or {}).get(s, {}).get("state", "unknown"),
                               "detail": (mem.get("health") or {}).get(s, {}).get("detail", "")}
                           for s in self.SUBSYSTEMS},
                "breaker_tripped": bool((mem.get("breaker") or {}).get("tripped")),
                "escalation": mem.get("escalation"),
                "log": (mem.get("log") or [])[-10:],
                "last_check": mem.get("last_check"),
            }
        except Exception:
            return {"enabled": self.enabled, "health": {}}
