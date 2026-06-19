"""Wheel Strategy: Sell OTM puts, handle assignment, then sell covered calls.
Simplified example – real‑world code would need Greeks, expiration handling, etc.
"""
from utils.alpaca_client import get_client
import logging

logger = logging.getLogger(__name__)

def execute_wheel(symbol: str, cash_available: float, max_allocation: float = 0.1):
    """Execute a single wheel iteration for *symbol*.
    - Sell a 10% OTM put using 10% of available cash.
    - If assigned (put exercised), acquire the underlying and sell a covered call OTM.
    Returns a dict summarising actions performed.
    """
    client = get_client()
    actions = []
    try:
        # Determine strike 10% below market price (placeholder price fetch)
        market_price = 100  # placeholder – replace with real market data call
        put_strike = round(market_price * 0.9, 2)
        quantity = int((cash_available * max_allocation) // put_strike)
        if quantity <= 0:
            return {"status": "skip", "reason": "Insufficient cash for put"}
        # Submit put order
        order = client.submit_order(
            symbol=symbol,
            qty=quantity,
            side="sell",
            type="limit",
            time_in_force="gtc",
            order_class="simple",
            limit_price=put_strike,
            option_type="put",
            expiration="2026-12-31"  # placeholder
        )
        actions.append({"type": "put_sell", "symbol": symbol, "strike": put_strike, "qty": quantity, "order": str(order)})
        # Assignment handling – very simplified (check positions)
        positions = client.get_positions()
        for pos in positions:
            # Alpaca SDK returns objects; we convert to dict for safety
            pos_dict = pos._raw if hasattr(pos, "_raw") else pos
            if pos_dict.get("symbol") == symbol and pos_dict.get("side") == "short":
                # Assume assignment occurred; we now own underlying
                # Sell covered call 10% OTM
                call_strike = round(market_price * 1.1, 2)
                client.submit_order(
                    symbol=symbol,
                    qty=pos_dict.get("qty"),
                    side="sell",
                    type="limit",
                    time_in_force="gtc",
                    order_class="simple",
                    limit_price=call_strike,
                    option_type="call",
                    expiration="2026-12-31"
                )
                actions.append({"type": "call_sell", "symbol": symbol, "strike": call_strike, "qty": pos_dict.get("qty")})
                break
    except Exception as e:
        logger.exception("Wheel strategy error for %s", symbol)
        actions.append({"type": "error", "error": str(e)})
    return {"status": "executed", "actions": actions}
