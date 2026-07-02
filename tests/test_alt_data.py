"""QuiverQuant alt-data overlay tests — no pytest, no network.

    python -m tests.test_alt_data

Mocks QuiverQuant's insider/congress endpoints and asserts the overlay:
  • is OFF (empty signals) with no key,
  • turns net insider/congress BUYS into a positive tilt and SELLS into a negative
    one, clamped to [-0.15, 0.15],
  • skips FX/crypto pairs (no disclosures),
  • degrades a failing symbol to a neutral tilt without crashing,
  • caches within its TTL (no second network call).
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from datetime import datetime, timezone

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-alt-")

from config import load_config  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload
    status_code = 200


def _install_fake_requests(router, counter):
    fake = types.ModuleType("requests")
    def _get(url, timeout=0, headers=None):
        counter["n"] += 1
        return _Resp(router(url))
    fake.get = _get
    sys.modules["requests"] = fake


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    import importlib
    import intelligence.alt_data as ad
    importlib.reload(ad)

    # ── 1) OFF with no key ──
    os.environ.pop("QUIVER_API_KEY", None)
    os.environ.pop("QUIVERQUANT_API_KEY", None)
    cfg = load_config()
    off = ad.AltData(cfg)
    _check(not off.enabled, "disabled when no QUIVER_API_KEY is set")
    _check(off.signals(["AAPL"]) == {}, "no key → empty signals")

    # ── 2) net buys → positive tilt; sells → negative; clamped ──
    os.environ["QUIVER_API_KEY"] = "qk"
    cfg = load_config()
    engine = ad.AltData(cfg)
    _check(engine.enabled, "enabled once a key is present")

    day = _today()

    def router(url):
        if "insiders/AAPL" in url:
            return [{"Date": day, "TransactionCode": "P", "Shares": 10000},
                    {"Date": day, "TransactionCode": "P", "Shares": 5000}]
        if "congresstrading/AAPL" in url:
            return [{"Date": day, "Transaction": "Purchase", "Amount": 100000}]
        if "insiders/XYZ" in url:
            return [{"Date": day, "TransactionCode": "S", "Shares": 9000}]
        if "congresstrading/XYZ" in url:
            return [{"Date": day, "Transaction": "Sale", "Amount": 50000}]
        return []

    counter = {"n": 0}
    _install_fake_requests(router, counter)

    sigs = engine.signals(["AAPL", "XYZ", "EUR/USD"])
    _check("EUR/USD" not in sigs, "FX pair skipped (no disclosures)")
    _check(sigs["AAPL"].tilt > 0, f"net buys → positive tilt (got {sigs['AAPL'].tilt})")
    _check(sigs["XYZ"].tilt < 0, f"net sells → negative tilt (got {sigs['XYZ'].tilt})")
    _check(-0.15 <= sigs["AAPL"].tilt <= 0.15, "tilt clamped to [-0.15, 0.15]")
    _check(sigs["AAPL"].summary and "buy" in sigs["AAPL"].summary.lower(),
           "summary describes the disclosure direction")

    # ── 3) cache: a second call inside the TTL makes no new network calls ──
    calls_before = counter["n"]
    engine.signals(["AAPL", "XYZ"])
    _check(counter["n"] == calls_before, "cache hit serves without new API calls")

    # ── 4) a failing symbol degrades to a neutral tilt, never crashes ──
    def boom(url):
        raise RuntimeError("network down")
    engine2 = ad.AltData(load_config())
    _install_fake_requests(boom, {"n": 0})
    sigs2 = engine2.signals(["AAPL"])
    _check(sigs2["AAPL"].tilt == 0.0, "failure degrades to neutral tilt (0.0)")
    _check(engine2.status["enabled"] is True, "status still reports enabled")

    print("\nALT-DATA CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
