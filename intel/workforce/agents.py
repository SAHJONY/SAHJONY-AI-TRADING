"""The Intel Workforce agents — 8 advisory-only analysts.

Each agent reads real data sources and emits one ``IntelFinding``: a
plain-language, dashboard-ready note with a small bounded conviction tilt.
Advisory ONLY — they never emit orders, never change risk caps, and never
touch the live-trading arming chain.

Honesty discipline (copied from intelligence/agents.py ``AgentVerdict.clamp``):
a broken input fails to NEUTRAL (delta 0, confidence 0), never to max-bullish.
A dead data source makes the affected agent ABSTAIN with a reason; no numbers
are ever invented.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

# Per-agent HTTP timeout — no network call in this module runs without one.
HTTP_TIMEOUT_S = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ── finding ──────────────────────────────────────────────────────────────────
@dataclass
class IntelFinding:
    name: str
    role: str
    status: str            # "active" | "abstained" | "disabled"
    finding: str           # one paragraph, plain language
    conviction_delta: float  # [-1, 1]; 0 when abstained
    confidence: float      # [0, 1]
    rationale: str         # short
    inputs: List[str]      # data sources actually used
    ts: str                # UTC iso
    abstain_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def clamp(self) -> "IntelFinding":
        # Guard non-finite FIRST (same discipline as AgentVerdict.clamp): a NaN
        # or inf delta must fail to NEUTRAL (0), never to a max-bullish or
        # max-bearish tilt.
        d, c = self.conviction_delta, self.confidence
        self.conviction_delta = 0.0 if not math.isfinite(d) else _clamp(float(d), -1.0, 1.0)
        self.confidence = 0.0 if not math.isfinite(c) else _clamp(float(c), 0.0, 1.0)
        if self.status == "abstained":
            self.conviction_delta = 0.0
            self.confidence = 0.0
        return self

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── base agent ───────────────────────────────────────────────────────────────
class IntelAgent:
    name = "Intel Agent"
    role = "Advisory"
    inputs_description = ""
    # When True, the desk zeroes any positive delta this agent returns: such an
    # agent may only de-risk, never add conviction. (RiskOfficer.)
    derisk_only = False

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:  # pragma: no cover - interface
        raise NotImplementedError

    def _finding(self, finding: str, conviction_delta: float, confidence: float,
                 rationale: str, inputs: List[str], status: str = "active",
                 abstain_reason: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None) -> IntelFinding:
        return IntelFinding(
            name=self.name,
            role=self.role,
            status=status,
            finding=finding,
            conviction_delta=conviction_delta,
            confidence=confidence,
            rationale=rationale,
            inputs=list(inputs),
            ts=_now(),
            abstain_reason=abstain_reason,
            details=dict(details or {}),
        ).clamp()

    def abstain(self, reason: str) -> IntelFinding:
        """Dead data source → abstain with a reason. Never invents numbers."""
        return self._finding(
            finding=(f"{self.name} abstained this cycle: {reason}. "
                     "No numbers were estimated in place of the missing data."),
            conviction_delta=0.0,
            confidence=0.0,
            rationale=reason[:220],
            inputs=[],
            status="abstained",
            abstain_reason=reason,
        )


# ── 1) regime ────────────────────────────────────────────────────────────────
class RegimeAnalyst(IntelAgent):
    name = "Regime Analyst"
    role = "Per-ticker regime classification"
    inputs_description = "client.get_history closes per ticker"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        client = ctx.get("client")
        tickers = ctx.get("tickers") or []
        per: Dict[str, Dict[str, Any]] = {}
        scores: List[float] = []
        failed = 0
        for sym in tickers:
            try:
                hist = client.get_history(sym, 60) or {}
                closes = [float(x) for x in (hist.get("closes") or [])]
            except Exception:
                failed += 1
                continue
            if len(closes) < 21:
                failed += 1
                continue
            price = closes[-1]
            sma20 = sum(closes[-20:]) / 20.0
            mom = price / closes[-21] - 1.0
            rets = [closes[i] / closes[i - 1] - 1.0
                    for i in range(1, len(closes)) if closes[i - 1]]
            # Crypto trades 365d/yr; equities would use 252 — the label below
            # says which annualization was applied.
            vol_ann = (sum(r * r for r in rets) / max(1, len(rets))) ** 0.5 * (365.0 ** 0.5)
            if mom > 0.05 and price > sma20:
                regime, score = "uptrend", 1.0
            elif mom < -0.05 and price < sma20:
                regime, score = "downtrend", -1.0
            elif vol_ann > 0.80:
                regime, score = "volatile", -0.15
            else:
                regime, score = "range", 0.0
            per[sym] = {"regime": regime, "mom_20d": round(mom, 4),
                        "vol_ann_365d": round(vol_ann, 3)}
            scores.append(score)
        if not per:
            return self.abstain(
                f"no usable price history for {len(tickers)} ticker(s)"
                + (f" ({failed} feed failures)" if failed else ""))
        delta = sum(scores) / len(scores)
        parts = [f"{s} {d['regime']} (20d {d['mom_20d']:+.1%}, vol {d['vol_ann_365d']:.0%})"
                 for s, d in sorted(per.items())]
        finding = (
            f"Regime read across {len(per)} ticker(s): " + "; ".join(parts) + ". "
            f"Aggregate tilt {delta:+.2f}. Regimes are descriptive labels from price "
            "history (365-day annualization), not trade instructions."
        )
        return self._finding(
            finding=finding,
            conviction_delta=delta,
            confidence=0.55,
            rationale=f"regimes={ {s: d['regime'] for s, d in per.items()} }",
            inputs=["client.get_history"],
            details={"per_ticker": per, "failed_tickers": failed},
        )


# ── 2) whales ────────────────────────────────────────────────────────────────
class WhaleWatcher(IntelAgent):
    name = "Whale Watcher"
    role = "Top-trader / whale flow alerts"
    inputs_description = "intel.top_traders.load_payload() cached top-trader payload"

    @staticmethod
    def _alert_direction(alert: Dict[str, Any]) -> float:
        side = str(alert.get("side") or alert.get("direction") or "").lower()
        if side in ("buy", "long", "inflow", "accumulate", "accumulation"):
            return 1.0
        if side in ("sell", "short", "outflow", "distribute", "distribution"):
            return -1.0
        return 0.0

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        try:
            from intel.top_traders import load_payload, summary_for_status
        except Exception as exc:
            return self.abstain(f"top-traders module unavailable ({type(exc).__name__})")
        try:
            payload = load_payload() or {}
        except Exception as exc:
            return self.abstain(f"top-traders payload unreadable ({type(exc).__name__})")
        if not payload:
            return self.abstain("top-traders payload empty or missing")
        try:
            summary = summary_for_status(payload) or {}
        except Exception:
            summary = {}
        alerts = payload.get("alerts") or payload.get("whale_alerts") or []
        if not isinstance(alerts, list):
            alerts = []
        dirs = [self._alert_direction(a) for a in alerts if isinstance(a, dict)]
        active = [d for d in dirs if d != 0.0]
        # Small delta by design — whale flow is a heads-up, not a trade signal.
        delta = 0.25 * (sum(active) / len(active)) if active else 0.0
        n = len(alerts)
        if n == 0:
            body = "No whale alerts in the top-traders payload this cycle."
        else:
            buys = sum(1 for d in dirs if d > 0)
            sells = sum(1 for d in dirs if d < 0)
            # Alerts may carry no direction (e.g. on-chain large transfers);
            # symbol may be spelled "asset" there.
            syms = sorted({str(a.get("symbol") or a.get("asset") or "?")
                           for a in alerts if isinstance(a, dict)})
            total_usd = 0.0
            for a in alerts:
                if isinstance(a, dict):
                    try:
                        total_usd += float(a.get("amount_usd") or 0.0)
                    except (TypeError, ValueError):
                        continue
            flow = (f"{buys} net-buying, {sells} net-selling" if active
                    else "large transfers with no direction data")
            body = (f"{n} whale alert(s) in the top-traders payload: {flow}"
                    + (f", ${total_usd:,.0f} total moved" if total_usd > 0 else "")
                    + (f" across {', '.join(syms[:6])}" if syms else "") + ".")
        tail = str(summary.get("headline") or summary.get("note") or "").strip()
        finding = body + (f" {tail}" if tail else "") + " Advisory only — flow context, not a position signal."
        return self._finding(
            finding=finding,
            conviction_delta=delta,
            confidence=0.5,
            rationale=f"{n} alert(s), {len(active)} directional, small tilt {delta:+.2f}",
            inputs=["intel.top_traders.load_payload"],
            details={"alert_count": n, "summary": summary},
        )


# ── 3) sentiment (buzz) ──────────────────────────────────────────────────────
_COIN_QUERIES = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin",
    "XRP": "xrp", "ADA": "cardano", "LTC": "litecoin", "BNB": "binance",
    "LINK": "chainlink", "AVAX": "avalanche",
}
_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class SentimentAnalyst(IntelAgent):
    name = "Sentiment Analyst"
    role = "Article-count buzz proxy (NOT true sentiment)"
    inputs_description = "GDELT doc API (keyless) article counts per major coin"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        tickers = ctx.get("tickers") or []
        coins: List[str] = []
        for sym in tickers:
            base = str(sym).split("/")[0].strip().upper()
            if base and base not in [c[0] for c in coins]:
                coins.append((base, _COIN_QUERIES.get(base, base.lower())))
        coins = coins[:6]
        if not coins:
            return self.abstain("no tickers to derive coin queries from")
        counts: Dict[str, int] = {}
        failed: List[str] = []
        for base, query in coins:
            try:
                r = requests.get(_GDELT_URL,
                                 params={"query": query, "mode": "ArtList",
                                         "maxrecords": 20, "format": "json"},
                                 timeout=HTTP_TIMEOUT_S)
                r.raise_for_status()
                data = r.json() or {}
                articles = data.get("articles") or []
                counts[base] = len(articles)
            except Exception as exc:
                failed.append(f"{base} ({type(exc).__name__})")
        if not counts:
            return self.abstain(
                "GDELT feed unreachable for all coins"
                + (f": {', '.join(failed)}" if failed else ""))
        parts = [f"{base} {n} article(s)" for base, n in sorted(counts.items())]
        note = f" Dropped: {', '.join(failed)}." if failed else ""
        finding = (
            "Article-count buzz (volume, NOT directional sentiment) from the GDELT "
            "doc API: " + "; ".join(parts) + "." + note +
            " A high article count means news volume, not bullishness — this agent "
            "takes no directional stance on buzz alone."
        )
        return self._finding(
            finding=finding,
            conviction_delta=0.0,
            confidence=0.5,
            rationale=f"buzz counts={counts}",
            inputs=["GDELT doc API (api.gdeltproject.org, keyless)"],
            details={"article_counts": counts, "failed": failed},
        )


# ── 4) macro ─────────────────────────────────────────────────────────────────
class MacroAnalyst(IntelAgent):
    name = "Macro Analyst"
    role = "Crypto macro: BTC dominance, funding, fear/greed"
    inputs_description = ("CoinGecko /api/v3/global (keyless), Hyperliquid "
                          "metaAndAssetCtxs funding (keyless), alternative.me fear/greed (keyless)")

    def _dominance(self) -> float:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        return float((r.json() or {}).get("data", {}).get("market_cap_percentage", {}).get("btc"))

    def _funding(self) -> float:
        """Mean per-hour funding rate across Hyperliquid's listed assets."""
        r = requests.post("https://api.hyperliquid.xyz/info",
                          json={"type": "metaAndAssetCtxs"}, timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        payload = r.json() or []
        meta, ctxs = (payload[0] if len(payload) > 0 else {}), (payload[1] if len(payload) > 1 else [])
        names = [u.get("name") for u in (meta or {}).get("universe") or []]
        vals: List[float] = []
        for _name, c in zip(names, ctxs or []):
            try:
                vals.append(float((c or {}).get("funding", 0.0)))
            except (TypeError, ValueError):
                continue
        if not vals:
            raise ValueError("no funding values in response")
        return sum(vals) / len(vals)

    def _fear_greed(self) -> "tuple[float, str]":
        r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        data = (r.json() or {}).get("data") or []
        if not data:
            raise ValueError("empty fear/greed payload")
        return float(data[0].get("value")), str(data[0].get("value_classification", ""))

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        ok: List[str] = []
        dropped: List[str] = []
        dom: Optional[float] = None
        funding: Optional[float] = None
        fng: Optional[float] = None
        fng_label = ""
        try:
            dom = self._dominance()
            ok.append("CoinGecko BTC dominance")
        except Exception as exc:
            dropped.append(f"BTC dominance ({type(exc).__name__})")
        try:
            funding = self._funding()
            ok.append("Hyperliquid funding")
        except Exception as exc:
            dropped.append(f"funding ({type(exc).__name__})")
        try:
            fng, fng_label = self._fear_greed()
            ok.append("fear/greed index")
        except Exception as exc:
            dropped.append(f"fear/greed ({type(exc).__name__})")
        if not ok:
            return self.abstain(
                "all macro feeds unreachable: " + "; ".join(dropped))
        # Bounded, mostly contrarian tilt. Extreme greed + crowded longs argue
        # for caution (small negative); deep fear argues for patience (small
        # positive). Nothing here is a trade trigger.
        delta = 0.0
        bits: List[str] = []
        if dom is not None:
            bits.append(f"BTC dominance {dom:.1f}%")
        if funding is not None:
            ann = funding * 24 * 365 * 100  # per-hour rate → %/yr
            bits.append(f"avg funding {funding * 100:.4f}%/h (~{ann:+.0f}%/yr)")
            if funding > 0.0001:
                delta -= 0.06
            elif funding < -0.0001:
                delta += 0.06
        if fng is not None:
            bits.append(f"fear/greed {fng:.0f} ({fng_label or 'n/a'})")
            if fng >= 60:
                delta -= 0.12
            elif fng <= 35:
                delta += 0.12
        note = f" Dropped this cycle: {'; '.join(dropped)}." if dropped else ""
        finding = (
            "Crypto macro read — " + "; ".join(bits) + "." + note +
            f" Net tilt {delta:+.2f} (contrarian lean on extremes only). "
            "Context for the dashboard, not a position signal."
        )
        return self._finding(
            finding=finding,
            conviction_delta=delta,
            confidence=0.55,
            rationale=f"sources={len(ok)}/3 ok; tilt {delta:+.2f}",
            inputs=ok,
            details={"btc_dominance": dom, "funding_per_hour": funding,
                     "fear_greed": fng, "dropped": dropped},
        )


# ── 5) risk officer (de-risk only, advisory only) ────────────────────────────
class RiskOfficer(IntelAgent):
    name = "Risk Officer"
    role = "Independent de-risk advisories"
    inputs_description = "state (positions, equity, breaker), cfg risk caps"
    derisk_only = True

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        state = ctx.get("state") or {}
        cfg = ctx.get("cfg")
        if cfg is None:
            return self.abstain("no config available for cap comparison")
        advisories: List[str] = []
        delta = 0.0
        equity = float(state.get("equity_last") or 0.0)
        positions = state.get("positions") or {}
        # 1) exposure vs the total-deployed cap (cost-basis view; advisory only —
        # the real gate lives in RiskEngine, untouched by this agent)
        gross = 0.0
        for pos in positions.values():
            try:
                gross += abs(float((pos or {}).get("shares", 0) or 0)) * \
                    float((pos or {}).get("cost_basis", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
        cap = float(getattr(cfg, "max_total_deployed_pct", 0.60) or 0.60)
        if equity > 0:
            usage = gross / equity
            if usage >= cap:
                advisories.append(
                    f"deployed {usage:.0%} is at/above the total-deployed cap "
                    f"({cap:.0%}) — consider reducing before adding")
                delta -= 0.20
            elif usage >= 0.8 * cap:
                advisories.append(
                    f"deployed {usage:.0%} is near the total-deployed cap ({cap:.0%})")
                delta -= 0.10
        else:
            advisories.append("equity unavailable — exposure cannot be verified")
            delta -= 0.10
        # 2) drawdown vs the daily breaker
        start = float(state.get("equity_day_start") or 0.0)
        limit = float(getattr(cfg, "max_daily_drawdown_pct", 0.06) or 0.06)
        if equity > 0 and start > 0:
            dd = equity / start - 1.0
            if dd <= -0.7 * limit:
                advisories.append(
                    f"day drawdown {dd:.1%} is near the {limit:.0%} breaker — "
                    "new risk may halt")
                delta -= 0.25
        if state.get("breaker_latched"):
            advisories.append("daily circuit breaker is latched — new risk halted")
            delta -= 0.20
        # 3) kill switch
        if bool(getattr(cfg, "trading_halt", False)):
            advisories.append("kill switch engaged (TRADING_HALT) — no new risk")
            delta -= 0.20
        # 4) reconciliation status, when the desk passes it in ctx
        recon = ctx.get("reconciliation")
        if isinstance(recon, dict) and recon:
            if "reconciled" in recon and not recon.get("reconciled"):
                advisories.append(
                    f"broker reconciliation not clean ({recon.get('status', 'unknown')})")
                delta -= 0.15
            elif "ok" in recon and not recon.get("ok"):
                advisories.append("broker state sync degraded")
                delta -= 0.15
        # De-risk only: this officer can never add conviction, only subtract it.
        # (The desk re-enforces this too via derisk_only.)
        delta = min(0.0, delta)
        if advisories:
            body = "Advisories: " + " ".join(f"• {a}" for a in advisories)
        else:
            body = ("All independent checks clear: exposure within caps, no breaker "
                    "trip, kill switch off, reconciliation clean.")
        finding = (
            f"{body} This officer is ADVISORY ONLY — it never blocks anything itself; "
            "the real gates (RiskEngine, the circuit breaker, the arming chain) are "
            "unchanged and owned by the desk."
        )
        return self._finding(
            finding=finding,
            conviction_delta=delta,
            confidence=0.7,
            rationale=f"{len(advisories)} advisor(ies), tilt {delta:+.2f} (de-risk only)",
            inputs=["state.positions", "state.equity_last", "state.equity_day_start",
                    "cfg.max_total_deployed_pct", "cfg.max_daily_drawdown_pct"],
            details={"advisories": advisories, "gross_cost_basis": round(gross, 2)},
        )


# ── 6) quant researcher ──────────────────────────────────────────────────────
class QuantResearcher(IntelAgent):
    name = "Quant Researcher"
    role = "Strategy attribution from realized outcomes"
    inputs_description = "state.hermes_events (strategy, realized), db.recent_trades"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        state = ctx.get("state") or {}
        db = ctx.get("db")
        rows: List[Dict[str, Any]] = []
        if db is not None:
            try:
                rows = db.recent_trades(100) or []
            except Exception:
                rows = []
        # Prefer realized outcomes recorded by the desk (strategy → $ realized).
        by_strat: Dict[str, Dict[str, float]] = {}
        for ev in state.get("hermes_events") or []:
            try:
                s = str((ev or {}).get("strategy") or "?")
                r = float((ev or {}).get("realized") or 0.0)
            except (TypeError, ValueError):
                continue
            d = by_strat.setdefault(s, {"events": 0.0, "realized": 0.0})
            d["events"] += 1.0
            d["realized"] += r
        # Fall back to trade-ledger counts when no realized events exist yet.
        if not by_strat and rows:
            for t in rows:
                s = str((t or {}).get("strategy") or "?")
                d = by_strat.setdefault(s, {"events": 0.0, "realized": 0.0})
                d["events"] += 1.0
        if not by_strat:
            return self.abstain("no trade history or realized outcomes recorded yet")
        ordered = sorted(by_strat.items(), key=lambda kv: kv[1]["realized"], reverse=True)
        parts = [f"{s}: {int(d['events'])} event(s), realized ${d['realized']:+.2f}"
                 for s, d in ordered]
        total = sum(d["realized"] for d in by_strat.values())
        finding = (
            "Strategy attribution from realized outcomes: " + "; ".join(parts) + ". "
            f"Combined realized {total:+.2f}. Attribution is descriptive — past "
            "contribution does not predict future results."
        )
        return self._finding(
            finding=finding,
            conviction_delta=0.0,
            confidence=0.6,
            rationale=f"{len(rows)} ledger row(s), {len(by_strat)} strategy(ies)",
            inputs=["state.hermes_events", "db.recent_trades"],
            details={"by_strategy": {s: {"events": int(d["events"]),
                                        "realized": round(d["realized"], 2)}
                                     for s, d in ordered}},
        )


# ── 7) execution optimizer ───────────────────────────────────────────────────
class ExecutionOptimizer(IntelAgent):
    name = "Execution Optimizer"
    role = "Cost analysis vs premium collected / realized P&L"
    inputs_description = "state.transaction_costs, state.premium_collected, state.realized_pnl"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        state = ctx.get("state") or {}
        costs = float(state.get("transaction_costs") or 0.0)
        premium = float(state.get("premium_collected") or 0.0)
        realized = float(state.get("realized_pnl") or 0.0)
        if costs <= 0 and premium <= 0 and realized == 0:
            return self.abstain("no cost or P&L data recorded yet")
        suggestions: List[str] = []
        if premium > 0 and costs > 0.2 * premium:
            suggestions.append(
                "transaction costs exceed 20% of premium collected — consider "
                "fewer rotations or larger per-trade size to dilute fixed costs")
        if realized < 0 and costs > 0:
            share = costs / abs(realized)
            suggestions.append(
                f"costs were {share:.0%} of the realized loss — execution "
                "friction is material to net results")
        if not suggestions:
            suggestions.append("cost profile within normal bounds — no execution changes indicated")
        finding = (
            f"Cumulative transaction costs ${costs:.2f} vs premium collected "
            f"${premium:.2f} vs realized P&L ${realized:+.2f}. " +
            " ".join(suggestions) + "."
        )
        return self._finding(
            finding=finding,
            conviction_delta=0.0,
            confidence=0.6,
            rationale=f"costs=${costs:.2f} premium=${premium:.2f} realized=${realized:+.2f}",
            inputs=["state.transaction_costs", "state.premium_collected",
                    "state.realized_pnl"],
            details={"transaction_costs": round(costs, 2),
                     "premium_collected": round(premium, 2),
                     "realized_pnl": round(realized, 2),
                     "suggestions": suggestions},
        )


# ── 8) copy-signal scout ─────────────────────────────────────────────────────
class CopySignalScout(IntelAgent):
    name = "Copy-Signal Scout"
    role = "Top-trader copy-signal translation (advisory)"
    inputs_description = "intel.top_traders.load_payload() copy_signal"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        try:
            from intel.top_traders import load_payload
        except Exception as exc:
            return self.abstain(f"top-traders module unavailable ({type(exc).__name__})")
        try:
            payload = load_payload() or {}
        except Exception as exc:
            return self.abstain(f"top-traders payload unreadable ({type(exc).__name__})")
        signal = payload.get("copy_signal")
        if not signal or not isinstance(signal, dict):
            return self.abstain("no copy signal in the top-traders payload")
        # The live sibling schema uses net_bias/assets; the contract's
        # direction/side/conviction spellings are accepted as fallbacks.
        direction = str(signal.get("direction") or signal.get("side")
                        or signal.get("net_bias") or "").lower()
        if direction in ("buy", "long"):
            d = 1.0
        elif direction in ("sell", "short"):
            d = -1.0
        else:
            d = 0.0  # "mixed", unknown, or no directional read
        try:
            strength = float(signal.get("conviction") or signal.get("strength") or 0.5)
        except (TypeError, ValueError):
            strength = 0.5
        assets = signal.get("assets") or {}
        if not signal.get("conviction") and not signal.get("strength") \
                and isinstance(assets, dict) and assets:
            # Derive strength from how far long-% sits from a neutral 50.
            try:
                pcts = [float(v) for v in assets.values()]
                strength = max(0.0, min(1.0, max(abs(p - 50.0) for p in pcts) / 50.0))
            except (TypeError, ValueError):
                pass
        strength = _clamp(strength, 0.0, 1.0)
        # Small delta by design — a translated signal is a nudge, not an order.
        delta = 0.2 * d * strength
        trader = str(signal.get("trader") or signal.get("source")
                     or "top-trader aggregate")
        symbol = str(signal.get("symbol") or "")
        asset_line = ""
        if isinstance(assets, dict) and assets:
            asset_line = " (" + ", ".join(
                f"{k} {float(v):.0f}% long" for k, v in list(assets.items())[:4]) + ")"
        reason = str(signal.get("reason") or signal.get("note")
                     or signal.get("label") or "")[:200]
        finding = (
            f"Top-trader copy signal translated for the council: {trader} — "
            f"{direction or 'no directional read'}{(' ' + symbol) if symbol else ''}"
            f"{asset_line} (signal strength {strength:.2f})."
            + (f" {reason}" if reason else "") +
            " intelligence only, not auto-copying — no order is emitted from this "
            "signal; the desk's own gates decide everything."
        )
        return self._finding(
            finding=finding,
            conviction_delta=delta,
            confidence=0.5,
            rationale=f"signal={trader}/{direction or 'mixed'}{asset_line}, tilt {delta:+.2f}",
            inputs=["intel.top_traders.load_payload"],
            details={"signal": {k: str(v)[:120] for k, v in signal.items()}},
        )


class FundingRateIntel(IntelAgent):
    name = "Funding-Rate Intel"
    role = "Funding-rate / open-interest crowding (contrarian advisory)"
    inputs_description = "intel.funding_intel.fetch(symbol): Hyperliquid/Binance public funding + OI"

    def evaluate(self, ctx: Dict[str, Any]) -> IntelFinding:
        symbol = str(ctx.get("symbol") or "").strip()
        if not symbol:
            return self.abstain("no symbol in context")
        try:
            from intel.funding_intel import fetch
        except Exception as exc:
            return self.abstain(f"funding-intel module unavailable ({type(exc).__name__})")
        try:
            data = fetch(symbol)
        except Exception as exc:
            return self.abstain(f"funding fetch raised ({type(exc).__name__})")
        if data.get("status") != "ok":
            return self.abstain(str(data.get("reason") or "funding/OI feeds unreachable"))
        tilt = float(data.get("contrarian_tilt") or 0.0)
        crowding = str(data.get("crowding") or "neutral")
        fr_pct = data.get("funding_8h_pct")
        source = str(data.get("source") or "unknown")
        oi = data.get("open_interest")
        finding = (
            f"Funding/OI read on {symbol} ({source}): 8h funding "
            f"{fr_pct:+.4f}% — {crowding.replace('_', ' ')}"
            + (f", OI {oi:,.0f}" if isinstance(oi, (int, float)) else "")
            + f". Contrarian tilt {tilt:+.2f}: crowded positioning leans against "
            f"the crowd (advisory only — a bounded nudge, never an order)."
        )
        return self._finding(
            finding=finding,
            conviction_delta=max(-0.15, min(0.15, tilt)),
            confidence=0.55 if abs(tilt) > 0 else 0.3,
            rationale=f"funding={fr_pct:+.4f}%/8h, crowding={crowding}, source={source}",
            inputs=[f"intel.funding_intel.fetch({symbol}) → {source}"],
            details={"funding_8h_pct": fr_pct, "crowding": crowding,
                     "open_interest": oi, "source": source},
        )


ALL_INTEL_AGENTS: List[IntelAgent] = [
    RegimeAnalyst(),
    WhaleWatcher(),
    SentimentAnalyst(),
    MacroAnalyst(),
    RiskOfficer(),
    QuantResearcher(),
    ExecutionOptimizer(),
    CopySignalScout(),
    FundingRateIntel(),
]
