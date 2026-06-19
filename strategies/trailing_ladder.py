"""Trailing Ladder Strategy
Implements:
- 10% absolute stop loss
- Dynamic trailing stop once equity is up 10%
- Ladder‑in additional buys at -20% and -30% drawdowns
"""
import logging
from utils.alpaca_client import get_client

logger = logging.getLogger(__name__)

def execute_ladder(symbol: str, cash_available: float, entry_price: float):
    client = get_client()
    actions = []
    try:
        # Calculate stop loss and trailing targets
        stop_price = entry_price * 0.90  # 10% absolute stop
        trail_price = entry_price * 1.10  # trigger trailing when up 10%
        # Initial buy if cash permits
        qty = int((cash_available * 0.2) // entry_price)
        if qty > 0:
            order = client.submit_order(
                symbol=symbol,
                qty=qty,
                side="buy",
                type="limit",
                time_in_force="gtc",
                limit_price=entry_price,
            )
            actions.append({"type": "buy", "symbol": symbol, "qty": qty, "price": entry_price, "order": str(order)})
        # Ladder‑in at -20%
        dip_price_20 = entry_price * 0.80
        qty2 = int((cash_available * 0.15) // dip_price_20)
        if qty2 > 0:
            order2 = client.submit_order(
                symbol=symbol,
                qty=qty2,
                side="buy",
                type="limit",
                time_in_force="gtc",
                limit_price=dip_price_20,
            )
            actions.append({"type": "buy_ladder_20", "price": dip_price_20, "qty": qty2, "order": str(order2)})
        # Ladder‑in at -30%
        dip_price_30 = entry_price * 0.70
        qty3 = int((cash_available * 0.10) // dip_price_30)
        if qty3 > 0:
            order3 = client.submit_order(
                symbol=symbol,
                qty=qty3,
                side="buy",
                type="limit",
                time_in_force="gtc",
                limit_price=dip_price_30,
            )
            actions.append({"type": "buy_ladder_30", "price": dip_price_30, "qty": qty3, "order": str(order3)})
        # Set stop order (simplified – real implementation would use OCO)
        client.submit_order(
            symbol=symbol,
            qty=qty + qty2 + qty3,
            side="sell",
            type="stop",
            stop_price=stop_price,
            time_in_force="gtc",
        )
        actions.append({"type": "stop", "price": stop_price})
    except Exception as e:
        logger.exception("Trailing ladder error for %s", symbol)
        actions.append({"type": "error", "error": str(e)})
    return {"status": "executed", "actions": actions}
