"""Deterministic, read-only broker-versus-internal position reconciliation."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping


def _finite(value: Any) -> float:
    number = float(value or 0.0)
    if not math.isfinite(number):
        raise ValueError("portfolio snapshot contains a non-finite number")
    return number


def _position_map(rows: Any, *, quantity_keys: tuple[str, ...]) -> dict[str, float]:
    if isinstance(rows, Mapping):
        iterable = []
        for symbol, row in rows.items():
            if not isinstance(row, Mapping):
                raise ValueError("portfolio snapshot contains an invalid position")
            iterable.append({"symbol": symbol, **row})
    else:
        iterable = rows or []
    result: dict[str, float] = {}
    for row in iterable:
        if not isinstance(row, Mapping):
            raise ValueError("portfolio snapshot contains an invalid position")
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("portfolio snapshot contains a position without a symbol")
        quantity = 0.0
        for key in quantity_keys:
            if key in row:
                quantity = _finite(row.get(key))
                break
        if abs(quantity) > 1e-12:
            result[symbol] = result.get(symbol, 0.0) + quantity
    return result


def _visible_market_value(rows: Any) -> float:
    iterable = rows.values() if isinstance(rows, Mapping) else rows or []
    total = 0.0
    for row in iterable:
        if not isinstance(row, Mapping):
            raise ValueError("portfolio snapshot contains an invalid position")
        if "market_value" not in row:
            raise ValueError("broker position is missing market_value")
        total += _finite(row.get("market_value"))
    return total


def reconcile_positions(internal_positions: Any, broker_positions: Any, *,
                        quantity_tolerance: float = 1e-6,
                        account_equity: Any = None, account_cash: Any = None,
                        value_tolerance: float = 1.0) -> dict[str, Any]:
    """Compare symbol identity and quantities, returning a stable audit payload."""
    observed_at = datetime.now(timezone.utc).isoformat()
    try:
        quantity_tolerance = _finite(quantity_tolerance)
        value_tolerance = _finite(value_tolerance)
        if quantity_tolerance < 0 or value_tolerance < 0:
            raise ValueError("reconciliation tolerances must be non-negative")
        internal = _position_map(internal_positions, quantity_keys=("shares", "qty", "quantity"))
        broker = _position_map(broker_positions, quantity_keys=("qty", "shares", "quantity"))
    except (TypeError, ValueError) as exc:
        return {"status": "error", "reconciled": False, "execution_blocked": True,
                "observed_at": observed_at, "differences": [], "error": str(exc)}

    differences = []
    for symbol in sorted(set(internal) | set(broker)):
        expected, actual = internal.get(symbol, 0.0), broker.get(symbol, 0.0)
        delta = actual - expected
        if abs(delta) > quantity_tolerance:
            differences.append({"symbol": symbol, "internal_qty": expected,
                                "broker_qty": actual, "delta_qty": delta})
    unexplained_value = None
    if account_equity is not None or account_cash is not None:
        try:
            if account_equity is None or account_cash is None:
                raise ValueError("both account equity and cash are required")
            equity, cash = _finite(account_equity), _finite(account_cash)
            visible_value = _visible_market_value(broker_positions)
            unexplained_value = equity - cash - visible_value
            if abs(unexplained_value) > value_tolerance:
                differences.append({"kind": "unexplained_account_value",
                                    "unexplained_value": unexplained_value})
        except (TypeError, ValueError) as exc:
            return {"status": "error", "reconciled": False, "execution_blocked": True,
                    "observed_at": observed_at, "differences": differences,
                    "error": str(exc)}
    reconciled = not differences
    return {
        "status": "reconciled" if reconciled else "mismatch",
        "reconciled": reconciled, "execution_blocked": not reconciled,
        "observed_at": observed_at, "internal_position_count": len(internal),
        "broker_position_count": len(broker), "differences": differences,
        "unexplained_value": unexplained_value,
        "value_tolerance": value_tolerance,
    }


def unavailable_reconciliation(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reconciled": False, "execution_blocked": True,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "differences": [], "error": str(reason)}
