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
    print("\nVOL TARGETING CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
