"""DEX routing policy and parsing checks — no network, no wallet, no pytest."""
from __future__ import annotations

import os
import sys

from config import load_config
from utils.dex import DEXRouter, DEXSafetyError
from utils.broker import get_broker


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "sellAmount": "1000000",
            "buyAmount": "500000000000000",
            "minBuyAmount": "497500000000000",
            "issues": {"allowance": {"spender": "0xspender"}},
            "transaction": {"to": "0xrouter", "data": "0x1234", "value": "0"},
            "route": {"fills": [{"name": "Uniswap_V3"}, {"name": "Curve"}]},
        }


def fake_get(*args, **kwargs):
    _check(kwargs["params"]["slippageBps"] == 50, "hard slippage policy reaches provider")
    _check(kwargs["timeout"] == 15, "quote request has bounded timeout")
    return FakeResponse()


def main() -> int:
    router = DEXRouter(
        provider="0x", api_key="test", chain_id=8453,
        wallet_address="0xwallet", token_allowlist=["0xusdc", "0xweth"],
        max_slippage_bps=50, http_get=fake_get,
    )
    quote = router.quote("0xusdc", "0xweth", 1_000_000)
    _check(quote.executable, "complete quote produces a signable transaction payload")
    _check(quote.minimum_buy_amount < quote.buy_amount, "minimum output is preserved")
    _check(quote.liquidity_sources == ("Uniswap_V3", "Curve"),
           "aggregated DEX liquidity sources are recorded")

    try:
        router.quote("0xunknown", "0xweth", 1)
        _check(False, "unapproved token should fail")
    except DEXSafetyError:
        _check(True, "token allowlist fails closed")

    os.environ["BROKER"] = "dex"
    for key in ("DEX_API_KEY", "DEX_WALLET_ADDRESS"):
        os.environ.pop(key, None)
    broker = get_broker(load_config())
    _check(not broker.online and broker.mode == "offline-sim",
           "DEX broker has no live path without configuration")
    result = broker.submit_equity_order("ETH/USDC", 1, "buy")
    _check(result.get("simulated") is True, "unconfigured DEX order is simulated")
    os.environ.pop("BROKER", None)
    print("\nDEX ROUTER CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
