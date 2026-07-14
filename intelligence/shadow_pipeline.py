"""Autonomous shadow-observation recorder and resolver.

This module records bounded AI advisory outputs without creating orders, then
resolves them against later market prices to produce evaluator-compatible
ShadowObservation rows. It is deliberately execution-isolated: no broker write
methods are imported or called.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from intelligence.shadow_eval import ShadowObservation


@dataclass(frozen=True)
class PendingShadow:
    id: str
    created_ts: float
    created_iso: str
    provider: str
    symbol: str
    entry_price: float
    base_conviction: float
    adjustment: float
    risk_multiplier: float
    horizon_seconds: int
    turnover_cost_bps: float = 0.0
    latency_ms: float = 0.0
    schema_valid: bool = True
    fallback_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ShadowPipeline:
    def __init__(
        self,
        pending_path: str | os.PathLike = "data/ai_shadow_pending.jsonl",
        resolved_path: str | os.PathLike = "data/ai_shadow_observations.jsonl",
    ):
        self.pending_path = Path(pending_path)
        self.resolved_path = Path(resolved_path)
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)
        self.resolved_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(value)))

    @staticmethod
    def _append(path: Path, row: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(row), separators=(",", ":"), sort_keys=True) + "\n")

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def record(
        self,
        *,
        provider: str,
        symbol: str,
        entry_price: float,
        base_conviction: float,
        adjustment: float,
        risk_multiplier: float,
        horizon_seconds: int = 1800,
        turnover_cost_bps: float = 0.0,
        latency_ms: float = 0.0,
        schema_valid: bool = True,
        fallback_used: bool = False,
        metadata: Mapping[str, Any] | None = None,
        now: float | None = None,
    ) -> PendingShadow:
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if horizon_seconds < 60:
            raise ValueError("horizon_seconds must be at least 60")
        ts = float(time.time() if now is None else now)
        row = PendingShadow(
            id=uuid.uuid4().hex,
            created_ts=ts,
            created_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            provider=str(provider).strip().lower(),
            symbol=str(symbol).strip().upper(),
            entry_price=float(entry_price),
            base_conviction=self._clamp(base_conviction, 0.0, 1.0),
            adjustment=self._clamp(adjustment, -0.15, 0.15),
            risk_multiplier=self._clamp(risk_multiplier, 0.5, 1.2),
            horizon_seconds=int(horizon_seconds),
            turnover_cost_bps=max(0.0, float(turnover_cost_bps)),
            latency_ms=max(0.0, float(latency_ms)),
            schema_valid=bool(schema_valid),
            fallback_used=bool(fallback_used),
            metadata=dict(metadata or {}),
        )
        self._append(self.pending_path, asdict(row))
        return row

    def resolve_due(
        self,
        price_lookup: Callable[[str], float],
        *,
        now: float | None = None,
    ) -> dict[str, int]:
        current = float(time.time() if now is None else now)
        pending = self._read(self.pending_path)
        keep: list[dict[str, Any]] = []
        resolved = 0
        failed = 0

        for row in pending:
            due = float(row.get("created_ts", 0.0)) + int(row.get("horizon_seconds", 0))
            if current < due:
                keep.append(row)
                continue
            try:
                exit_price = float(price_lookup(str(row["symbol"])))
                entry_price = float(row["entry_price"])
                if exit_price <= 0 or entry_price <= 0:
                    raise ValueError("invalid market price")
                forward_return = exit_price / entry_price - 1.0
                obs = ShadowObservation(
                    ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current)),
                    provider=str(row["provider"]),
                    symbol=str(row["symbol"]),
                    base_conviction=float(row["base_conviction"]),
                    adjustment=float(row["adjustment"]),
                    risk_multiplier=float(row["risk_multiplier"]),
                    forward_return=float(forward_return),
                    turnover_cost_bps=float(row.get("turnover_cost_bps", 0.0)),
                    latency_ms=float(row.get("latency_ms", 0.0)),
                    schema_valid=bool(row.get("schema_valid", True)),
                    fallback_used=bool(row.get("fallback_used", False)),
                )
                self._append(self.resolved_path, asdict(obs))
                resolved += 1
            except Exception:
                row["resolve_attempts"] = int(row.get("resolve_attempts", 0)) + 1
                if row["resolve_attempts"] < 5:
                    keep.append(row)
                failed += 1

        tmp = self.pending_path.with_suffix(self.pending_path.suffix + ".tmp")
        tmp.write_text("".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in keep), encoding="utf-8")
        tmp.replace(self.pending_path)
        return {"resolved": resolved, "pending": len(keep), "failed": failed}

    def counts(self) -> dict[str, int]:
        return {
            "pending": len(self._read(self.pending_path)),
            "resolved": len(self._read(self.resolved_path)),
        }
