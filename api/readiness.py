"""Institutional readiness scorecard for the hosted terminal.

The endpoint is intentionally read-only and can never arm trading. A 200 means
the endpoint itself evaluated successfully; readiness is conveyed by the JSON
body and may still be false.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
from urllib import request

from institutional_validation import readiness_report

RUNTIME_KEY = "sahjony:runtime-status:v1"
EVIDENCE_KEY = "sahjony:broker-evidence:v1"


def _redis_values():
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        raise RuntimeError("hosted runtime storage is not configured")
    body = json.dumps([["GET", RUNTIME_KEY], ["GET", EVIDENCE_KEY]]).encode()
    req = request.Request(
        url + "/pipeline",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("invalid Upstash pipeline response")
    return [row.get("result") if isinstance(row, dict) else None for row in payload]


def _load_json(value):
    if not value:
        return None
    return json.loads(value)


def _status_snapshot():
    path = Path(__file__).resolve().parents[1] / "public" / "status.json"
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _portfolio_from_status(status):
    account = status.get("account") if isinstance(status.get("account"), dict) else {}
    global_perf = status.get("global_performance") if isinstance(status.get("global_performance"), dict) else {}
    positions = status.get("positions") if isinstance(status.get("positions"), list) else []

    nav = float(account.get("equity", 0.0) or 0.0)
    deployed = abs(float(account.get("deployed", 0.0) or 0.0))
    largest = 0.0
    for row in positions:
        if isinstance(row, dict):
            largest = max(largest, abs(float(row.get("market_value", row.get("value", 0.0)) or 0.0)))

    # status snapshots historically store drawdown as either 0.08 or 8.0; normalize.
    raw_dd = abs(float(global_perf.get("max_drawdown", global_perf.get("max_drawdown_pct", 0.0)) or 0.0))
    portfolio_dd = raw_dd / 100.0 if raw_dd > 1.0 else raw_dd

    breaker = status.get("circuit_breaker") if isinstance(status.get("circuit_breaker"), dict) else {}
    day_return = float(breaker.get("day_return", 0.0) or 0.0)
    daily_dd = max(0.0, -day_return)
    return {
        "nav": nav,
        "gross_exposure": deployed,
        "largest_position_value": largest,
        "daily_drawdown_pct": daily_dd,
        "portfolio_drawdown_pct": portfolio_dd,
    }


def _strategy_from_status(status):
    consensus = status.get("ai_consensus") if isinstance(status.get("ai_consensus"), dict) else {}
    self_improvement = status.get("self_improvement") if isinstance(status.get("self_improvement"), dict) else {}
    global_perf = status.get("global_performance") if isinstance(status.get("global_performance"), dict) else {}

    observations = int(consensus.get("observations", self_improvement.get("observation_count", 0)) or 0)
    days = int(global_perf.get("oos_days", global_perf.get("trading_days", 0)) or 0)
    profit_factor = float(global_perf.get("profit_factor", 0.0) or 0.0)
    raw_dd = abs(float(global_perf.get("max_drawdown", global_perf.get("max_drawdown_pct", 0.0)) or 0.0))
    max_dd = raw_dd / 100.0 if raw_dd > 1.0 else raw_dd
    expectancy = float(global_perf.get("net_expectancy", global_perf.get("expectancy", 0.0)) or 0.0)

    return {
        "oos_observations": observations,
        "oos_days": days,
        "profit_factor": profit_factor,
        "net_expectancy": expectancy,
        "max_drawdown_pct": max_dd,
        "costs_included": bool(global_perf.get("costs_included", False)),
        "walk_forward_passed": bool(global_perf.get("walk_forward_passed", False)),
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status_code, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            runtime_raw, evidence_raw = _redis_values()
            runtime = _load_json(runtime_raw)
            evidence = _load_json(evidence_raw)
            status = _status_snapshot()
            report = readiness_report(
                runtime=runtime,
                evidence=evidence,
                portfolio=_portfolio_from_status(status),
                strategy_metrics=_strategy_from_status(status),
            )
            report["read_only"] = True
            report["execution_authority"] = False
            self._send(200, report)
        except Exception as exc:
            self._send(
                503,
                {
                    "institutional_10_10": False,
                    "score": 0.0,
                    "error": type(exc).__name__,
                    "blockers": ["readiness evidence unavailable"],
                    "read_only": True,
                    "execution_authority": False,
                },
            )
