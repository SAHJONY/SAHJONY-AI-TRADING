"""Autonomous, shadow-only learning pipeline for advisory models."""
from __future__ import annotations

import json
import os
import time
from calendar import month_name
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from intelligence.shadow_eval import evaluate_all, observations_from_dicts, score_provider
from paths import home


class AutonomousLearningPipeline:
    """Resolve prior forecasts, persist observations, rank models, publish status.

    This component has no broker reference and no order methods. Promotion output
    is a recommendation requiring manual approval; it cannot alter model weights.
    """

    def __init__(self, *, min_observations: int = 100, min_sharpe: float = 0.25,
                 max_drawdown: float = 0.10, database=None, clock=None) -> None:
        root = Path(home())
        self.pending_path = root / "data" / "ai_shadow_pending.json"
        self.observations_path = root / "data" / "ai_shadow_observations.jsonl"
        self.report_path = root / "public" / "ai_shadow.json"
        self.archive_root = root / "data" / "shadow"
        self.min_observations = max(1, int(min_observations))
        self.min_sharpe = float(min_sharpe)
        self.max_drawdown = float(max_drawdown)
        self.database = database
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def consensus(overlays: Dict[str, Dict[str, Any]], symbols: list[str]) -> Dict[str, Any]:
        available = [value for key, value in overlays.items()
                     if key not in {"neutral", "consensus"} and value]
        if not available:
            return {"per_symbol_adjust": {}, "risk_multiplier": 1.0,
                    "telemetry": {"schema_valid": True, "fallback_used": False}}
        adjustments = {
            symbol: sum(float(item.get("per_symbol_adjust", {}).get(symbol, 0.0))
                        for item in available) / len(available)
            for symbol in symbols
        }
        return {
            "per_symbol_adjust": adjustments,
            "risk_multiplier": sum(float(item.get("risk_multiplier", 1.0))
                                   for item in available) / len(available),
            "telemetry": {
                "schema_valid": all(item.get("telemetry", {}).get("schema_valid", True)
                                    for item in available),
                "fallback_used": any(item.get("telemetry", {}).get("fallback_used", False)
                                     for item in available),
                "latency_ms": sum(float(item.get("telemetry", {}).get("latency_ms", 0.0))
                                  for item in available),
            },
        }

    def run_cycle(self, cycle: int, portfolio: list[Dict[str, Any]],
                  overlays: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        now_dt = self.clock()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now = now_dt.astimezone(timezone.utc).isoformat()
        prices = {str(row["symbol"]).upper(): float(row.get("price", 0.0) or 0.0)
                  for row in portfolio}
        resolved = self._resolve_pending(prices, now)
        symbols = list(prices)
        complete = dict(overlays)
        complete["consensus"] = self.consensus(complete, symbols)
        complete["neutral"] = {"per_symbol_adjust": {}, "risk_multiplier": 1.0,
                               "telemetry": {"schema_valid": True, "fallback_used": False}}
        pending = {"cycle": cycle, "ts": now, "portfolio": portfolio, "overlays": complete}
        self._atomic_json(self.pending_path, pending)
        report = self._rank()
        report.update({
            "pipeline": "autonomous-learning", "last_cycle": cycle,
            "resolved_this_cycle": len(resolved), "pending_symbols": len(symbols),
            "orders_enabled": False,
        })
        archive_path = self._archive_cycle(now_dt, cycle, pending, resolved, report)
        report["archive_record"] = str(archive_path)
        self._atomic_json(self.report_path, report)
        return report

    def _resolve_pending(self, prices: Dict[str, float], resolved_ts: str) -> list[Dict[str, Any]]:
        try:
            pending = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows_by_symbol = {str(row.get("symbol", "")).upper(): row
                          for row in pending.get("portfolio", [])}
        observations = []
        for provider, overlay in (pending.get("overlays") or {}).items():
            telemetry = overlay.get("telemetry") or {}
            for symbol, row in rows_by_symbol.items():
                old = float(row.get("price", 0.0) or 0.0)
                new = prices.get(symbol, 0.0)
                if old <= 0 or new <= 0:
                    continue
                observations.append({
                    "ts": resolved_ts, "provider": provider, "symbol": symbol,
                    "base_conviction": float(row.get("conviction", 0.0) or 0.0),
                    "adjustment": float(overlay.get("per_symbol_adjust", {}).get(symbol, 0.0) or 0.0),
                    "risk_multiplier": float(overlay.get("risk_multiplier", 1.0) or 1.0),
                    "forward_return": new / old - 1.0,
                    "turnover_cost_bps": float(os.getenv("AI_SHADOW_TURNOVER_COST_BPS", "1.0")),
                    "latency_ms": float(telemetry.get("latency_ms", 0.0) or 0.0),
                    "schema_valid": bool(telemetry.get("schema_valid", True)),
                    "fallback_used": bool(telemetry.get("fallback_used", False)),
                    "direction": str(row.get("direction", "long")),
                    "asset_class": str(row.get("asset_class", "equity")),
                    "market_regime": str(row.get("market_regime", "unknown")),
                })
        if observations:
            self.observations_path.parent.mkdir(parents=True, exist_ok=True)
            with self.observations_path.open("a", encoding="utf-8") as handle:
                for observation in observations:
                    handle.write(json.dumps(observation, separators=(",", ":")) + "\n")
            if self.database is not None:
                self.database.log_ai_shadow_observations(observations)
        return observations

    def _archive_cycle(self, timestamp: datetime, cycle: int, pending: Dict[str, Any],
                       resolved: list[Dict[str, Any]], report: Dict[str, Any]) -> Path:
        """Create one immutable, monotonically numbered performance record."""
        directory = self.archive_root / f"{timestamp.year:04d}" / month_name[timestamp.month]
        directory.mkdir(parents=True, exist_ok=True)
        existing = [int(path.stem) for path in directory.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")
                    if path.stem.isdigit()]
        sequence = max(existing, default=0) + 1
        payload = {
            "schema_version": 1,
            "ts": timestamp.astimezone(timezone.utc).isoformat(),
            "cycle": cycle,
            "mode": "shadow-only",
            "orders_enabled": False,
            "automatic_promotion_enabled": False,
            "market_and_council": pending["portfolio"],
            "provider_overlays": pending["overlays"],
            "resolved_observations": resolved,
            "performance_ranking": report,
        }
        while True:
            target = directory / f"{sequence:06d}.json"
            temporary = directory / f".{sequence:06d}.{os.getpid()}.{time.time_ns()}.tmp"
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            try:
                # A hard link publishes atomically and fails if another process won
                # this sequence number. Published records are never overwritten.
                os.link(temporary, target)
                return target
            except FileExistsError:
                sequence += 1
            finally:
                temporary.unlink(missing_ok=True)

    def _rank(self) -> Dict[str, Any]:
        rows = []
        try:
            for line in self.observations_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            rows = []
        report = evaluate_all(
            observations_from_dicts(rows), min_observations=self.min_observations,
            min_sharpe=self.min_sharpe, max_drawdown=self.max_drawdown,
        )
        report["observations"] = len(rows)
        report["source"] = str(self.observations_path)
        report["leaders"] = self._leaders(rows)
        return report

    def _leaders(self, rows: list[Dict[str, Any]]) -> Dict[str, Any]:
        providers = {"claude", "openai", "gemini", "grok", "nvidia"}
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        def parsed_ts(row):
            try:
                return datetime.fromisoformat(str(row.get("ts", "")).replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)

        def winner(subset: list[Dict[str, Any]]):
            observations = observations_from_dicts(subset)
            scores = [score_provider(provider, observations, min_observations=1,
                                     min_sharpe=-1e9, max_drawdown=1.0)
                      for provider in providers
                      if any(row.get("provider") == provider for row in subset)]
            if not scores:
                return None
            best = max(scores, key=lambda score: (score.score, score.annualized_sharpe,
                                                  score.net_return))
            return {"provider": best.provider, "score": best.score,
                    "sharpe": best.annualized_sharpe, "observations": best.observations}

        today = winner([row for row in rows if parsed_ts(row).date() == now.date()])
        week = winner([row for row in rows if parsed_ts(row) >= now - timedelta(days=7)])
        month = winner([row for row in rows if parsed_ts(row) >= now - timedelta(days=30)])
        regimes = {}
        for regime in sorted({str(row.get("market_regime", "unknown")) for row in rows}):
            result = winner([row for row in rows if row.get("market_regime", "unknown") == regime])
            if result:
                regimes[regime] = result
        best_regime = None
        if regimes:
            regime, result = max(regimes.items(), key=lambda item: item[1]["score"])
            best_regime = dict(result, regime=regime)
        return {
            "today": today, "week": week, "month": month, "market_regime": best_regime,
            "crypto": winner([row for row in rows if row.get("asset_class") == "crypto"]),
            "equity": winner([row for row in rows if row.get("asset_class") == "equity"]),
            "options": winner([row for row in rows if row.get("asset_class") == "options"]),
        }

    @staticmethod
    def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
