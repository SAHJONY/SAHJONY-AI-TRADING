"""Fail-closed, provider-neutral DEX quote and transaction preparation.

The router deliberately does not accept private keys and never signs or
broadcasts transactions. Aggregators provide broad DEX liquidity coverage; a
wallet, multisig, or policy signer remains the final authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional


class DEXSafetyError(ValueError):
    pass


def _requests_get(*args, **kwargs):
    # requests is a declared runtime dependency, but keeping this import lazy
    # allows offline safety/conformance tests to run in the minimal environment.
    import requests
    return requests.get(*args, **kwargs)


@dataclass(frozen=True)
class DEXQuote:
    provider: str
    chain_id: int
    sell_token: str
    buy_token: str
    sell_amount: int
    buy_amount: int
    minimum_buy_amount: int
    allowance_target: str
    transaction: Dict[str, Any]
    liquidity_sources: tuple[str, ...]

    @property
    def executable(self) -> bool:
        tx = self.transaction
        return bool(tx.get("to") and tx.get("data"))


class DEXRouter:
    """Routes swaps through audited aggregators while enforcing local policy."""

    ZEROX_BASE = "https://api.0x.org"

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        chain_id: int,
        wallet_address: str,
        token_allowlist: Iterable[str],
        max_slippage_bps: int,
        http_get: Optional[Callable[..., Any]] = None,
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.chain_id = int(chain_id)
        self.wallet_address = wallet_address
        self.allowlist = {t.lower() for t in token_allowlist}
        self.max_slippage_bps = int(max_slippage_bps)
        self.http_get = http_get or _requests_get
        if self.provider not in {"0x"}:
            raise DEXSafetyError(f"Unsupported DEX provider: {provider}")
        if not (1 <= self.max_slippage_bps <= 100):
            raise DEXSafetyError("slippage must be between 1 and 100 bps")

    def _validate(self, sell_token: str, buy_token: str, sell_amount: int) -> None:
        if not self.api_key:
            raise DEXSafetyError("DEX API key is required for network quotes")
        if not self.wallet_address:
            raise DEXSafetyError("wallet address is required")
        if sell_amount <= 0:
            raise DEXSafetyError("sell amount must be positive")
        for token in (sell_token, buy_token):
            if self.allowlist and token.lower() not in self.allowlist:
                raise DEXSafetyError(f"token is not allowlisted: {token}")

    def quote(self, sell_token: str, buy_token: str, sell_amount: int) -> DEXQuote:
        self._validate(sell_token, buy_token, sell_amount)
        if self.provider == "0x":
            return self._quote_0x(sell_token, buy_token, sell_amount)
        raise DEXSafetyError("no provider available")

    def _quote_0x(self, sell_token: str, buy_token: str, sell_amount: int) -> DEXQuote:
        response = self.http_get(
            f"{self.ZEROX_BASE}/swap/allowance-holder/quote",
            params={
                "chainId": self.chain_id,
                "sellToken": sell_token,
                "buyToken": buy_token,
                "sellAmount": str(sell_amount),
                "taker": self.wallet_address,
                "slippageBps": self.max_slippage_bps,
            },
            headers={"0x-api-key": self.api_key, "0x-version": "v2"},
            timeout=15,
        )
        response.raise_for_status()
        raw = response.json()
        tx = raw.get("transaction") or {}
        allowance = ((raw.get("issues") or {}).get("allowance") or {}).get("spender")
        allowance = allowance or raw.get("allowanceTarget") or ""
        sources = tuple(
            item.get("name", "")
            for item in (raw.get("route") or {}).get("fills", [])
            if item.get("name")
        )
        quote = DEXQuote(
            provider="0x",
            chain_id=self.chain_id,
            sell_token=sell_token,
            buy_token=buy_token,
            sell_amount=int(raw.get("sellAmount", sell_amount)),
            buy_amount=int(raw["buyAmount"]),
            minimum_buy_amount=int(raw.get("minBuyAmount", raw["buyAmount"])),
            allowance_target=str(allowance),
            transaction={
                "to": tx.get("to"),
                "data": tx.get("data"),
                "value": tx.get("value", "0"),
                "gas": tx.get("gas"),
                "gasPrice": tx.get("gasPrice"),
                "chainId": self.chain_id,
            },
            liquidity_sources=sources,
        )
        if not quote.executable or quote.buy_amount <= 0 or quote.minimum_buy_amount <= 0:
            raise DEXSafetyError("provider returned an incomplete or unsafe quote")
        return quote
