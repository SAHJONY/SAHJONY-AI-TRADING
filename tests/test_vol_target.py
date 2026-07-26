"""Volatility-targeting tests — no pytest, no network.

    python -m tests.test_vol_target

Asserts the risk engine's vol targeting:
  • calm equity curve (realized ≤ target) → neutral ×1.0,
  • wild curve → scaled down proportionally, floored at ×0.5,
  • never scales UP (leverage) even when vol is far below target,
  • VOL_TARGET_ANNUAL=0 disables it,
  • short history / bad data degrade to neutral, never crash.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-volt-")


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _engine(target):
    os.environ["VOL_TARGET_ANNUAL"] = str(target)
    from config import load_config
    from risk.risk_engine import RiskEngine
    return RiskEngine(load_config())


def main() -> int:
    import random
    random.seed(11)

    calm = [100000.0]
    for _ in range(59):
        calm.append(calm[-1] * (1 + random.gauss(0, 0.0004)))   # ≈ tiny per-cycle vol
    wild = [100000.0]
    for _ in range(59):
        wild.append(wild[-1] * (1 + random.gauss(0, 0.02)))     # violent per-cycle swings

    r = _engine(0.20)
    _check(r.vol_scalar(calm) == 1.0, "calm curve → neutral ×1.0 (no de-risking needed)")
    ws = r.vol_scalar(wild)
    _check(ws < 1.0, f"wild curve → budgets scaled down (×{ws:.2f})")
    _check(ws >= r.VOL_SCALE_MIN, f"scale floored at ×{r.VOL_SCALE_MIN} (got ×{ws:.2f})")
    _check(r.vol_scalar(calm) <= 1.0, "never scales above ×1.0 — de-risks only, no leverage")

    off = _engine(0)
    _check(off.vol_scalar(wild) == 1.0, "VOL_TARGET_ANNUAL=0 disables vol targeting")

    r2 = _engine(0.20)
    _check(r2.vol_scalar([]) == 1.0, "empty history → neutral")
    _check(r2.vol_scalar(calm[:5]) == 1.0, "short history → neutral")
    _check(r2.vol_scalar([100000, None, "x", -5, 100100] * 4) == 1.0,
           "garbage data degrades to neutral, never crashes")

    os.environ.pop("VOL_TARGET_ANNUAL", None)

    # ── venue minimum notional (small-account viability) ──
    os.environ["MIN_ORDER_NOTIONAL_USD"] = "1.0"
    os.environ["MAX_ALLOCATION_PCT"] = "0.12"
    from config import load_config as _lc
    from risk.risk_engine import RiskEngine as _RE
    rr = _RE(_lc())
    b = rr.position_budget(10.0, 0.75, 1.0)          # would be $0.90 raw
    _check(b >= 1.0, f"sub-minimum budget raised to the venue minimum (got ${b:.2f})")
    _check(b <= 10.0 * 0.12 + 1e-9, "raised budget still inside the per-position cap")
    _check(rr.position_budget(10.0, 0.0, 1.0) == 0.0, "zero conviction still means no order")
    tiny = rr.position_budget(2.0, 0.75, 1.0)        # cap $0.24 < $1 minimum
    _check(tiny == 0.0, "stands down when the minimum exceeds the per-position cap")
    big = rr.position_budget(100_000.0, 0.60, 0.80)
    _check(abs(big - 100_000.0 * 0.12 * 0.60 * 0.80) < 1e-6,
           "large accounts are unaffected by the minimum")
    os.environ.pop("MIN_ORDER_NOTIONAL_USD", None); os.environ.pop("MAX_ALLOCATION_PCT", None)

    # ── transaction costs (fee-aware scorecard) ──
    os.environ["FEE_BPS_CRYPTO"] = "60"; os.environ["FEE_BPS_EQUITY"] = "4"
    from config import load_config as _lc2
    from strategies.base import fee_cost as _fc
    c = _lc2()
    _check(abs(_fc("BTC/USD", 100.0, c) - 0.60) < 1e-9, "crypto round trip = 60bps of notional")
    _check(abs(_fc("SPY", 100.0, c) - 0.04) < 1e-9, "equity round trip = 4bps of notional")
    _check(_fc("BTC/USD", 0.0, c) == 0.0 and _fc("BTC/USD", None, c) == 0.0,
           "no notional / bad input → no cost, never crashes")
    # a $2 crypto round trip costs more than a 1% move on a $2 position earns
    _check(_fc("BTC/USD", 2.0, c) > 0, "small orders are not cost-free")
    os.environ.pop("FEE_BPS_CRYPTO", None); os.environ.pop("FEE_BPS_EQUITY", None)

    print("\nVOL TARGETING CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
