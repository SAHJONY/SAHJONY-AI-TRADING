"""Broker factory + adapter-contract verification — no pytest required.

    python -m tests.test_broker_factory

Asserts that the factory returns a complete adapter for the default venue, that
an unknown venue fails fast with a clear error, that the template adapter
satisfies the BrokerAdapter contract (so copies start compliant), and that an
incomplete adapter is rejected.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("LOG_LEVEL", "WARNING")

from config import load_config
from utils.broker import REQUIRED, _verify, get_broker
from utils.brokers.template_adapter import TemplateBroker


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def main() -> int:
    cfg = load_config()
    _check(cfg.broker == "alpaca", "default broker is alpaca")

    client = get_broker(cfg)
    _check(all(hasattr(client, m) for m in REQUIRED), "alpaca adapter implements full contract")

    # unknown venue → clear error, never a silent default
    os.environ["BROKER"] = "doesnotexist"
    try:
        get_broker(load_config())
        _check(False, "unknown broker should raise")
    except ValueError as exc:
        _check("Unknown BROKER" in str(exc), "unknown broker raises a helpful ValueError")
    finally:
        del os.environ["BROKER"]

    # the template is contract-complete, so copies start compliant
    _check(_verify(TemplateBroker(cfg)) is not None, "template adapter satisfies the contract")

    # an incomplete adapter is rejected by the factory's verifier
    class Broken:
        mode = "x"
        online = False
    try:
        _verify(Broken())
        _check(False, "incomplete adapter should be rejected")
    except TypeError as exc:
        _check("not a complete BrokerAdapter" in str(exc), "incomplete adapter rejected with detail")

    print("\nBROKER FACTORY CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
