"""Transaction cost analysis — Perold implementation-shortfall decomposition.

BLUNT TRUTH, READ FIRST
-----------------------
TCA measures what you paid. It cannot design a better execution schedule at
$10/order size — there is nothing to schedule, and no routing change this
module will ever suggest, because it never changes routing, scheduling, or
sizing. It is advisory/measurement ONLY: it never emits orders, never touches
credentials, never promises profit, and never clears the circuit breaker,
re-arms the data feed, or alters live trading behavior in any way.

At $10 per order, Q/ADV is on the order of one-in-a-million for anything
liquid, so EXPECT most legs to be ≈ 0:

* DELAY (decision → arrival) — needs a real decision price captured at signal
  time. The live path currently records the decision at order release, so in
  live wiring this leg is usually None with a reason, not 0. It is NOT
  backfilled or guessed.
* MARKET IMPACT — the square-root-law estimate from intel/impact_model.py
  (``estimate_impact``), import-guarded. When that module (or its inputs) is
  unavailable the leg is None with a reason — never an invented number. At
  this size it will print ≈ 0.000 bps, which IS the result: execution is
  provably not the bottleneck.
* TIMING/EXECUTION — the residual of the arrival → fill move after removing
  the model impact leg.
* OPPORTUNITY — drift on the UNFILLED portion from arrival to the
  post-execution reference price. This is usually the BIGGEST leg and the one
  desks most often ignore; it is always marked ``estimated`` because the
  reference price is a choice, not a fill.
* FEES — explicit fees only. Robinhood crypto charges none; a venue that does
  not report a fee is recorded as 0.0 with the reason stated, not assumed.

The value of this module is (1) honesty about costs and (2) a VERIFIED cost
model for the backtest path: every order records the pre-trade impact
estimate at decision time and the realized impact after the fill, and
``estimate_error_stats()`` tracks whether the cost model is honest over time.
A model that systematically underestimates its own impact is a model that
lies to the backtest — this ledger is how the desk catches it.

Decomposition (Perold-style implementation shortfall)
-----------------------------------------------------
For an order of Q shares, side sign s (+1 buy, −1 sell; positive = adverse
cost to the desk), decision price Pd, arrival price Pa, quantity-weighted
average fill price Pf over filled qty F, unfilled U = Q − F, post-execution
reference price Pafter, and explicit fees:

    total = s·[F·(Pf − Pd) + U·(Pafter − Pd)] + fees

decomposed (sums to total by construction) as:

    DELAY         = s·Q·(Pa − Pd)                    (decision → arrival)
    MARKET_IMPACT = est_bps/10000 · Pa · F           (model-attributed)
    TIMING        = s·F·(Pf − Pa) − MARKET_IMPACT    (residual)
    OPPORTUNITY   = s·U·(Pafter − Pa)                (unfilled drift, estimated)
    FEES          = explicit fees

All legs are also expressed in basis points against the paper portfolio's
decision notional Q·Pd, so the bps legs add up to the total bps. Every leg
carries the order's fill rate. Any leg that cannot be computed from real
recorded prices is None with a ``reason`` — never raised, never invented.

Conventions follow intel/execution_quality.py: JSONL ledger, in-memory
mirror, fault-isolated capture, env kill-switch TCA_ENABLED (default on).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from paths import home
from utils.logger import get_logger

log = get_logger("tca")

_UNSET = object()  # sentinel: "caller did not choose; use the guarded import"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_impact_fn():
    """Guarded import of the square-root-law impact model.

    Returns ``estimate_impact`` when intel/impact_model.py is importable,
    else None. The market-impact leg degrades to None-with-reason; nothing
    is ever invented in its place.
    """
    try:
        from intel.impact_model import estimate_impact  # type: ignore
        return estimate_impact
    except Exception:
        return None


def _side_sign(side: Any) -> float:
    s = str(side or "").strip().lower()
    return 1.0 if s.startswith("buy") else -1.0


class TCALedger:
    """Perold implementation-shortfall ledger. Measurement only."""

    def __init__(self, path: Optional[str] = None, impact_fn: Any = _UNSET):
        self.path = path or os.path.join(home(), "data", "tca.jsonl")
        self.enabled = str(os.getenv("TCA_ENABLED", "1")).strip().lower() not in (
            "0", "false", "no", "off")
        # Dependency injection seam: pass an impact callable (or explicit None)
        # in tests; default resolves the guarded import once.
        self._impact_fn = _load_impact_fn() if impact_fn is _UNSET else impact_fn
        self._pending: Dict[str, Dict[str, Any]] = {}   # order_id -> open order
        self._records: List[Dict[str, Any]] = []        # finalized (memory mirror)

    # ── capture ───────────────────────────────────────────────────────────────
    def record_decision(self, order_id: str, *, symbol: str, side: str, qty: float,
                        decision_price: Optional[float] = None,
                        decision_ts: Optional[str] = None,
                        adv: Optional[float] = None,
                        sigma_daily: Optional[float] = None,
                        provenance: str = "live") -> None:
        """Open a TCA record at decision time and snapshot the pre-trade
        impact estimate. ``decision_price`` may be None (live path records the
        decision at order release, where no separate decision price exists) —
        the delay leg then degrades to None with a reason instead of being
        guessed."""
        try:
            if not self.enabled:
                return
            q = _finite(qty)
            if q is None or q <= 0:
                return
            pd = _finite(decision_price)
            pre_bps, pre_reason = self._pre_trade_estimate(
                symbol, q, adv, sigma_daily, pd, provenance)
            self._pending[str(order_id)] = {
                "order_id": str(order_id), "symbol": str(symbol),
                "side": str(side), "qty": q,
                "decision_price": pd, "decision_ts": decision_ts or _now(),
                "arrival_price": None, "arrival_ts": None,
                "fills": [], "fees_usd": 0.0,
                "unfilled_qty": None, "unfilled_reason": None,
                "adv": _finite(adv), "sigma_daily": _finite(sigma_daily),
                "pre_trade_impact_bps": pre_bps,
                "pre_trade_reason": pre_reason,
                "provenance": str(provenance or "live"),
                "opened_ts": _now(),
            }
        except Exception as exc:
            log.warning("tca decision record failed: %s", exc)

    def _pre_trade_estimate(self, symbol: str, qty: float,
                            adv: Optional[float], sigma_daily: Optional[float],
                            price: Optional[float],
                            provenance: str) -> tuple:
        fn = self._impact_fn
        if fn is None:
            return None, "impact model unavailable (intel/impact_model not importable)"
        try:
            res = fn(str(symbol), qty, adv, sigma_daily,
                     price=price, provenance=provenance)
        except Exception as exc:
            return None, f"impact model call failed: {type(exc).__name__}"
        if not isinstance(res, dict):
            return None, "impact model returned no estimate (missing/invalid inputs)"
        bps = _finite(res.get("expected_impact_bps"))
        if bps is None:
            return None, "impact model returned no estimate (missing/invalid inputs)"
        return round(bps, 4), None

    def record_arrival(self, order_id: str, arrival_price: float,
                       arrival_ts: Optional[str] = None) -> None:
        """Capture the arrival price — the market price the moment the order
        is released to the venue."""
        try:
            if not self.enabled:
                return
            order = self._pending.get(str(order_id))
            pa = _finite(arrival_price)
            if order is None or pa is None or pa <= 0:
                return
            order["arrival_price"] = pa
            order["arrival_ts"] = arrival_ts or _now()
        except Exception as exc:
            log.warning("tca arrival record failed: %s", exc)

    def record_fill(self, order_id: str, fill_price: float,
                    fill_qty: Optional[float] = None,
                    fees_usd: Optional[float] = 0.0,
                    fill_ts: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Accumulate one fill. Returns the pending order state (not the
        finalized record — call finalize_order once fills stop)."""
        try:
            if not self.enabled:
                return None
            order = self._pending.get(str(order_id))
            pf = _finite(fill_price)
            if order is None or pf is None or pf <= 0:
                return None
            filled_so_far = sum(f["qty"] for f in order["fills"])
            fq = _finite(fill_qty)
            if fq is None or fq <= 0:
                fq = max(0.0, order["qty"] - filled_so_far)
            fee = _finite(fees_usd) or 0.0
            order["fills"].append({"price": pf, "qty": fq,
                                   "fees_usd": max(0.0, fee),
                                   "ts": fill_ts or _now()})
            order["fees_usd"] = round(order["fees_usd"] + max(0.0, fee), 6)
            return {"order_id": order["order_id"],
                    "filled_qty": round(filled_so_far + fq, 6),
                    "fills": len(order["fills"])}
        except Exception as exc:
            log.warning("tca fill record failed: %s", exc)
            return None

    def note_unfilled(self, order_id: str, *, unfilled_qty: Optional[float] = None,
                      reason: Optional[str] = None) -> None:
        """Mark an order (or its remainder) as unfilled — blocked, expired,
        or partially filled. The opportunity leg is computed at finalize."""
        try:
            if not self.enabled:
                return
            order = self._pending.get(str(order_id))
            if order is None:
                return
            filled = sum(f["qty"] for f in order["fills"])
            uq = _finite(unfilled_qty)
            if uq is None or uq < 0:
                uq = max(0.0, order["qty"] - filled)
            order["unfilled_qty"] = round(min(uq, max(0.0, order["qty"] - filled)), 6)
            if reason:
                order["unfilled_reason"] = str(reason)
        except Exception as exc:
            log.warning("tca unfilled note failed: %s", exc)

    # ── decomposition ─────────────────────────────────────────────────────────
    @staticmethod
    def _avg_fill(order: Dict[str, Any]) -> tuple:
        fills = order["fills"]
        tq = sum(f["qty"] for f in fills)
        if tq <= 0:
            return None, 0.0
        return sum(f["price"] * f["qty"] for f in fills) / tq, tq

    def _latency_attribution(self, order: Dict[str, Any],
                             delay_usd: Optional[float]) -> tuple:
        """Pro-rata split of the DELAY leg across pipeline stages, from
        telemetry/latency.py's current-cycle segment durations when available.
        Estimated — proportional allocation, not a causal claim. Anything
        missing → (None, reason)."""
        if delay_usd is None:
            return None, "no delay leg to attribute"
        if abs(delay_usd) < 1e-12:
            return None, "delay cost ≈ 0 — nothing to attribute"
        d_ts = _parse_ts(order.get("decision_ts"))
        a_ts = _parse_ts(order.get("arrival_ts"))
        if d_ts is None or a_ts is None:
            return None, "decision/arrival timestamps missing"
        window_s = (a_ts - d_ts).total_seconds()
        if window_s <= 0:
            return None, "non-positive decision→arrival window"
        try:
            import telemetry.latency as tl  # import-guarded: branch may be absent
            rec = tl._active()
            durations = dict(getattr(rec, "durations", None) or {})
        except Exception:
            return None, "latency telemetry unavailable (telemetry/latency not importable)"
        clean = {str(k): float(v) for k, v in durations.items()
                 if _finite(v) is not None and float(v) > 0}
        if not clean:
            return None, "no segment durations recorded this cycle"
        total = sum(clean.values())
        attribution = {seg: round(delay_usd * dur / total, 6)
                       for seg, dur in sorted(clean.items())}
        return {
            "segments_usd": attribution,
            "window_seconds": round(window_s, 3),
            "segments_seconds": round(total, 3),
            "estimated": True,
            "note": ("proportional split of the delay leg across overlapping "
                     "pipeline stages — allocation, not causation"),
        }, None

    def finalize_order(self, order_id: str, *,
                       reference_price_after: Optional[float] = None,
                       reference_ts: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Close the order and write the full Perold decomposition to the
        JSONL ledger. ``reference_price_after`` is the post-execution price
        used for the opportunity leg (estimated); without it the opportunity
        leg is None with a reason. Never raises."""
        try:
            if not self.enabled:
                return None
            order = self._pending.pop(str(order_id), None)
            if order is None:
                return None
            rec = self._decompose(order, reference_price_after, reference_ts)
            self._records.append(rec)
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            except Exception as exc:
                log.warning("tca persist failed (kept in memory): %s", exc)
            return rec
        except Exception as exc:
            log.warning("tca finalize failed: %s", exc)
            return None

    def _decompose(self, order: Dict[str, Any],
                   reference_price_after: Optional[float],
                   reference_ts: Optional[str]) -> Dict[str, Any]:
        sign = _side_sign(order["side"])
        q = order["qty"]
        pf, f_qty = self._avg_fill(order)
        u_qty = order["unfilled_qty"]
        if u_qty is None:
            u_qty = max(0.0, q - f_qty)
        fill_rate = round(f_qty / q, 6) if q > 0 else 0.0
        pd = order["decision_price"]
        pa = order["arrival_price"]
        p_after = _finite(reference_price_after)
        fees = order["fees_usd"]

        def leg(usd: Optional[float], bps: Optional[float],
                reason: Optional[str]) -> Dict[str, Any]:
            return {"usd": round(usd, 6) if usd is not None else None,
                    "bps": round(bps, 4) if bps is not None else None,
                    "reason": reason, "fill_rate": fill_rate}

        # DELAY: decision → arrival, full paper quantity.
        if pd is not None and pd > 0 and pa is not None and pa > 0:
            delay_usd = sign * q * (pa - pd)
            delay_bps = sign * (pa - pd) / pd * 10000.0
            delay_reason = None
        else:
            delay_usd, delay_bps = None, None
            delay_reason = ("decision price not captured (live path records the "
                            "decision at order release) — delay leg unknown, not zero")

        # MARKET IMPACT: pre-trade square-root-law estimate applied to fills.
        impact_bps_pre = order.get("pre_trade_impact_bps")
        if impact_bps_pre is None and self._impact_fn is not None and f_qty > 0:
            # Fallback: same model, same stored inputs, evaluated at finalize.
            impact_bps_pre, _fb_reason = self._pre_trade_estimate(
                order["symbol"], q, order.get("adv"), order.get("sigma_daily"),
                pa or pd, order.get("provenance") or "live")
            if impact_bps_pre is not None:
                order["pre_trade_impact_bps"] = impact_bps_pre
        if (impact_bps_pre is not None and pa is not None and pa > 0
                and f_qty > 0):
            mi_usd = impact_bps_pre / 10000.0 * pa * f_qty
            mi_bps = mi_usd / (q * pd) * 10000.0 if pd and pd > 0 else None
            mi_reason = None
        else:
            mi_usd, mi_bps = None, None
            mi_reason = (order.get("pre_trade_reason")
                         or "no fill quantity or no arrival price for the impact leg")

        # TIMING/EXECUTION: realized arrival → fill move, minus model impact.
        if pa is not None and pa > 0 and pf is not None and f_qty > 0:
            arrival_to_fill = sign * f_qty * (pf - pa)
            if mi_usd is not None:
                timing_usd = arrival_to_fill - mi_usd
                timing_reason = None
            else:
                timing_usd = arrival_to_fill
                timing_reason = ("impact leg unavailable — timing leg carries the "
                                 "full arrival→fill move")
            timing_bps = (timing_usd / (q * pd) * 10000.0
                          if pd and pd > 0 else None)
        else:
            timing_usd, timing_bps = None, None
            timing_reason = "no fills or no arrival price — timing leg unknown"

        # OPPORTUNITY: unfilled drift from arrival. Always estimated.
        if u_qty <= 0:
            opp_usd, opp_bps = 0.0, 0.0
            opp_reason = "fully filled — no opportunity cost"
        elif pa is not None and pa > 0 and p_after is not None and p_after > 0:
            opp_usd = sign * u_qty * (p_after - pa)
            opp_bps = (opp_usd / (q * pd) * 10000.0 if pd and pd > 0 else None)
            opp_reason = None
        else:
            opp_usd, opp_bps = None, None
            opp_reason = ("unfilled quantity with no post-execution reference price — "
                          "pass reference_price_after to finalize to estimate it")

        # FEES: explicit only.
        fees_reason = (None if fees > 0
                       else "no explicit fee reported by the venue")

        legs = {
            "delay": leg(delay_usd, delay_bps, delay_reason),
            "market_impact": leg(mi_usd, mi_bps, mi_reason),
            "timing": leg(timing_usd, timing_bps, timing_reason),
            "opportunity": leg(opp_usd, opp_bps, opp_reason),
            "fees": leg(round(fees, 6), (fees / (q * pd) * 10000.0
                                         if pd and pd > 0 and q > 0 else None),
                        fees_reason),
        }
        legs_complete = all(v["usd"] is not None for v in legs.values())
        total_usd = round(sum(v["usd"] for v in legs.values()
                              if v["usd"] is not None), 6)
        total_bps = round(sum(v["bps"] for v in legs.values()
                              if v["bps"] is not None), 4)

        # Pre-trade vs realized: is the cost model honest?
        realized_bps = None
        if pa is not None and pa > 0 and pf is not None and f_qty > 0:
            realized_bps = round(sign * (pf - pa) / pa * 10000.0, 4)
        pre_bps = order.get("pre_trade_impact_bps")
        err_bps = (round(realized_bps - pre_bps, 4)
                   if realized_bps is not None and pre_bps is not None else None)

        attribution, attr_reason = self._latency_attribution(order, delay_usd)

        return {
            "order_id": order["order_id"], "symbol": order["symbol"],
            "side": order["side"], "qty": q,
            "fill_rate": fill_rate,
            "decision_price": pd, "decision_ts": order.get("decision_ts"),
            "arrival_price": pa, "arrival_ts": order.get("arrival_ts"),
            "avg_fill_price": round(pf, 6) if pf is not None else None,
            "filled_qty": round(f_qty, 6), "unfilled_qty": round(u_qty, 6),
            "unfilled_reason": order.get("unfilled_reason"),
            "legs": legs,
            "legs_complete": legs_complete,
            "total_shortfall_usd": total_usd,
            "total_shortfall_bps": total_bps,
            "total_basis": ("full decomposition" if legs_complete
                            else "partial — some legs unknown (see leg reasons)"),
            "pre_trade_impact_bps": pre_bps,
            "pre_trade_reason": order.get("pre_trade_reason"),
            "realized_impact_bps": realized_bps,
            "estimate_error_bps": err_bps,
            "opportunity_estimated": True,
            "reference_price_after": p_after,
            "reference_ts": reference_ts,
            "latency_attribution": attribution,
            "latency_attribution_reason": attr_reason,
            "provenance": order.get("provenance"),
            "module": "tca",
            "ts": _now(),
        }

    # ── reporting ─────────────────────────────────────────────────────────────
    def _all(self) -> List[Dict[str, Any]]:
        if self._records:
            return list(self._records)
        rows: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            continue
        except OSError:
            pass
        self._records = rows
        return list(rows)

    @staticmethod
    def _mean(vals: List[float]) -> Optional[float]:
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def summary_for_status(self, last_n: int = 100) -> Dict[str, Any]:
        """Compact dashboard summary over the most recent finalized orders."""
        try:
            rows = self._all()[-max(1, int(last_n)):]
            legs = ("delay", "market_impact", "timing", "opportunity", "fees")
            leg_avg = {}
            for name in legs:
                vals = [_finite(r.get("legs", {}).get(name, {}).get("usd")) for r in rows]
                m = self._mean([v for v in vals if v is not None])
                leg_avg[name] = round(m, 6) if m is not None else None
            totals = [_finite(r.get("total_shortfall_usd")) for r in rows]
            totals = [t for t in totals if t is not None]
            total_bps = [_finite(r.get("total_shortfall_bps")) for r in rows]
            total_bps = [t for t in total_bps if t is not None]
            fill_rates = [_finite(r.get("fill_rate")) for r in rows]
            fill_rates = [f for f in fill_rates if f is not None]
            return {
                "enabled": self.enabled,
                "orders_measured": len(rows),
                "avg_fill_rate": (round(sum(fill_rates) / len(fill_rates), 4)
                                  if fill_rates else None),
                "avg_total_shortfall_usd": (round(sum(totals) / len(totals), 6)
                                            if totals else None),
                "avg_total_shortfall_bps": (round(sum(total_bps) / len(total_bps), 4)
                                            if total_bps else None),
                "worst_shortfall_usd": (round(max(totals, key=abs), 6)
                                        if totals else None),
                "legs_avg_usd": leg_avg,
                "orders_with_incomplete_legs": sum(
                    1 for r in rows if not r.get("legs_complete")),
                "estimate_error": self.estimate_error_stats(rows),
                "provenance": sorted({str(r.get("provenance") or "unknown")
                                      for r in rows}),
                "note": ("Perold implementation-shortfall decomposition. Positive = "
                         "adverse cost to the desk. Opportunity leg is always "
                         "estimated. At $10/order most legs print ≈ 0 — that is "
                         "the measurement, not a malfunction."),
            }
        except Exception as exc:
            log.warning("tca summary failed: %s", exc)
            return {"enabled": self.enabled, "orders_measured": 0,
                    "error": type(exc).__name__}

    def estimate_error_stats(self,
                             rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Pre-trade impact estimate vs realized impact — is the cost model
        honest? Positive error = model UNDER-estimated the realized cost."""
        try:
            rows = self._all() if rows is None else rows
            errs = [_finite(r.get("estimate_error_bps")) for r in rows]
            errs = [e for e in errs if e is not None]
            if not errs:
                return {"comparisons": 0,
                        "note": "no orders with both a pre-trade estimate and a "
                                "realized impact yet — the model's honesty is untested"}
            mean_err = sum(errs) / len(errs)
            mean_abs = sum(abs(e) for e in errs) / len(errs)
            under = sum(1 for e in errs if e > 0)
            over = sum(1 for e in errs if e < 0)
            if mean_abs < 1.0:
                verdict = "model honest within ±1 bps on average"
            elif mean_err > 0:
                verdict = (f"model UNDER-estimates realized impact by "
                           f"{mean_err:.2f} bps on average — backtest costs are "
                           f"optimistic")
            else:
                verdict = (f"model OVER-estimates realized impact by "
                           f"{abs(mean_err):.2f} bps on average — backtest costs "
                           f"are conservative")
            return {
                "comparisons": len(errs),
                "mean_error_bps": round(mean_err, 4),
                "mean_abs_error_bps": round(mean_abs, 4),
                "under_estimates": under,
                "over_estimates": over,
                "verdict": verdict,
            }
        except Exception as exc:
            log.warning("tca estimate-error stats failed: %s", exc)
            return {"comparisons": 0, "error": type(exc).__name__}

    def period_report(self, days: int = 30,
                      symbol: Optional[str] = None) -> Dict[str, Any]:
        """Per-period TCA report: totals, per-leg and per-symbol breakdown,
        plus plain-language lines for the dashboard."""
        try:
            days = max(1, int(days))
            cutoff = datetime.now(timezone.utc).timestamp() - days * 86400.0
            rows = [r for r in self._all()
                    if (_parse_ts(r.get("ts")) or datetime.now(timezone.utc)
                        ).timestamp() >= cutoff]
            if symbol:
                rows = [r for r in rows
                        if str(r.get("symbol")) == str(symbol)]
            legs = ("delay", "market_impact", "timing", "opportunity", "fees")
            legs_total = {}
            for name in legs:
                vals = [_finite(r.get("legs", {}).get(name, {}).get("usd")) for r in rows]
                legs_total[name] = round(sum(v for v in vals if v is not None), 6)
            totals = [_finite(r.get("total_shortfall_usd")) for r in rows]
            total = round(sum(t for t in totals if t is not None), 6)
            by_symbol: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                s = str(r.get("symbol"))
                bucket = by_symbol.setdefault(
                    s, {"orders": 0, "total_shortfall_usd": 0.0,
                        "avg_fill_rate": 0.0})
                bucket["orders"] += 1
                t = _finite(r.get("total_shortfall_usd")) or 0.0
                bucket["total_shortfall_usd"] = round(
                    bucket["total_shortfall_usd"] + t, 6)
                fr = _finite(r.get("fill_rate")) or 0.0
                bucket["avg_fill_rate"] = round(
                    (bucket["avg_fill_rate"] * (bucket["orders"] - 1) + fr)
                    / bucket["orders"], 4)
            n = len(rows)
            lines = [
                f"TCA — last {days}d: {n} order{'s' if n != 1 else ''} measured, "
                f"total implementation shortfall ${total:,.4f} "
                f"(positive = adverse cost).",
                "Legs (USD): " + ", ".join(
                    f"{name} ${legs_total[name]:,.4f}" for name in legs) + ".",
            ]
            opp = legs_total["opportunity"]
            if n and abs(opp) >= abs(total) * 0.5 and abs(total) > 1e-9:
                lines.append(
                    "Opportunity cost dominates — the unfilled portion's drift is "
                    "where this desk's execution cost actually lives, not in "
                    "market impact (which prints ≈ 0 at $10/order).")
            err = self.estimate_error_stats(rows)
            if err.get("comparisons"):
                lines.append("Cost-model honesty: " + err["verdict"] + ".")
            else:
                lines.append("Cost-model honesty: " + err.get("note", "untested") + ".")
            if symbol:
                lines.append(f"Filtered to symbol {symbol}.")
            return {
                "period_days": days, "symbol": symbol, "orders": n,
                "total_shortfall_usd": total,
                "legs_total_usd": legs_total,
                "by_symbol": by_symbol,
                "estimate_error": err,
                "lines": lines,
            }
        except Exception as exc:
            log.warning("tca period report failed: %s", exc)
            return {"period_days": days, "symbol": symbol, "orders": 0,
                    "lines": [f"TCA report unavailable: {type(exc).__name__}"]}
