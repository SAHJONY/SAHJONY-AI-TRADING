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
        iterable = ({"symbol": symbol, **(row if isinstance(row, Mapping) else {})}
                    for symbol, row in rows.items())
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


def reconcile_positions(internal_positions: Any, broker_positions: Any, *,
                        quantity_tolerance: float = 1e-6) -> dict[str, Any]:
    """Compare symbol identity and quantities, returning a stable audit payload."""
    observed_at = datetime.now(timezone.utc).isoformat()
    try:
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
    reconciled = not differences
    return {
        "status": "reconciled" if reconciled else "mismatch",
        "reconciled": reconciled, "execution_blocked": not reconciled,
        "observed_at": observed_at, "internal_position_count": len(internal),
        "broker_position_count": len(broker), "differences": differences,
    }


def unavailable_reconciliation(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reconciled": False, "execution_blocked": True,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "differences": [], "error": str(reason)}
