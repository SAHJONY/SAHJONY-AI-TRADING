"""Hosted, redacted broker evidence backed by Upstash Redis REST."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import hmac
import json
import math
import os
import re
from urllib import request

KEY = "sahjony:broker-evidence:v1"
TTL_SECONDS = 900
VERDICTS = {"RECONCILED", "RECONCILIATION_BLOCKED", "EVIDENCE_UNAVAILABLE", "SOURCE_CONFLICT"}


def redis(command):
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("hosted runtime storage is not configured")
    req = request.Request(url.rstrip("/") + "/pipeline", data=json.dumps(command).encode(),
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"})
    with request.urlopen(req, timeout=8) as response:
        return json.loads(response.read())["result"]


def _finite(value, name, *, optional=False):
    if optional and value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _digest(value, name):
    text = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{name} is invalid")
    return text


def _timestamp(value, name):
    text = str(value or "")[:60]
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return text


def _strings(value, limit=25):
    if not isinstance(value, list):
        raise ValueError("evidence issue list is invalid")
    result = []
    for item in value[:limit]:
        text = str(item)[:240]
        if (re.search(r"private key|api[_ -]?key|secret|bearer|token", text, re.IGNORECASE)
                or re.search(r"\b\d{8,}\b|\b[A-Za-z0-9_-]{24,}\b", text)):
            raise ValueError("evidence issue contains prohibited sensitive data")
        result.append(text)
    return result


def sanitize(payload):
    if (payload.get("execution_authority") is not False
            or payload.get("trading_armed") is not False
            or payload.get("trading_ready") is not False):
        raise ValueError("invalid safety declaration")
    verdict = str(payload.get("verdict", ""))
    if verdict not in VERDICTS:
        raise ValueError("invalid reconciliation verdict")
    mcp = payload.get("mcp")
    clean_mcp = None
    if mcp is None:
        if verdict != "EVIDENCE_UNAVAILABLE":
            raise ValueError("MCP evidence is required")
    else:
        if not isinstance(mcp, dict):
            raise ValueError("MCP evidence is invalid")
        raw_identity = str(mcp.get("account_last4", ""))
        last4 = raw_identity[-4:]
        if (mcp.get("source_id") != "robinhood-trading-mcp" or last4 != "1131"
                or raw_identity != last4 or mcp.get("identity_verified") is not True):
            raise ValueError("verified masked Agentic identity is required")
        account = mcp.get("account")
        if not isinstance(account, dict):
            raise ValueError("MCP account totals are required")
        positions = mcp.get("positions")
        if not isinstance(positions, list):
            raise ValueError("MCP positions evidence is required")
        clean_positions = []
        for row in positions[:100]:
            if not isinstance(row, dict):
                raise ValueError("invalid MCP position row")
            symbol = str(row.get("symbol", ""))[:20].upper()
            if not re.fullmatch(r"[A-Z0-9./_-]{1,20}", symbol):
                raise ValueError("invalid MCP position symbol")
            clean_positions.append({"symbol": symbol, "qty": _finite(row.get("qty"), "qty"),
                                    "market_value": _finite(row.get("market_value"), "market_value")})
        clean_mcp = {"source_id": "robinhood-trading-mcp",
                     "observed_at": _timestamp(mcp.get("observed_at"), "MCP observed_at"),
                     "account_last4": last4, "identity_verified": True,
                     "account": {name: _finite(account.get(name), f"MCP {name}")
                                 for name in ("equity", "cash", "buying_power")},
                     "positions": clean_positions,
                     "digest": _digest(mcp.get("digest"), "MCP digest")}
    ui = payload.get("ui")
    clean_ui = None
    if ui is not None:
        if not isinstance(ui, dict) or ui.get("source_id") != "robinhood-ui-manual":
            raise ValueError("invalid UI evidence")
        clean_ui = {"source_id": "robinhood-ui-manual",
                    "observed_at": _timestamp(ui.get("observed_at"), "UI observed_at"),
                    "equity": _finite(ui.get("equity"), "UI equity", optional=True),
                    "cash": _finite(ui.get("cash"), "UI cash", optional=True),
                    "buying_power": _finite(ui.get("buying_power"), "UI buying power", optional=True),
                    "human_notes": "[REDACTED]" if ui.get("human_notes") else "",
                    "digest": _digest(ui.get("digest"), "UI digest")}
    return {
        "schema_version": 1,
        "generated_at": _timestamp(payload.get("generated_at"), "generated_at"),
        "source_status": {"mcp": "VERIFIED" if clean_mcp else "UNAVAILABLE",
                          "ui": "OBSERVED" if clean_ui else "NOT_PROVIDED"},
        "conflict_status": "SOURCE_CONFLICT" if payload.get("conflicts") else "NONE",
        "verdict": verdict,
        "mcp": clean_mcp,
        "ui": clean_ui,
        "unexplained_value": _finite(payload.get("unexplained_value"), "unexplained_value",
                                     optional=True),
        "conflicts": _strings(payload.get("conflicts", [])),
        "blockers": _strings(payload.get("blockers", [])),
        "report_digest": _digest(payload.get("report_digest"), "report digest"),
        "execution_authority": False, "trading_armed": False, "trading_ready": False,
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        try:
            result = redis([["GET", KEY]])[0]
            if not result:
                return self._send(503, {"verdict": "EVIDENCE_UNAVAILABLE",
                                        "execution_authority": False, "trading_ready": False})
            payload = json.loads(result)
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    payload["generated_at"].replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = TTL_SECONDS + 1
            payload["fresh"] = 0 <= age <= TTL_SECONDS
            payload["age_seconds"] = max(0, round(age))
            self._send(200 if payload["fresh"] else 503, payload)
        except Exception as exc:
            self._send(503, {"verdict": "EVIDENCE_UNAVAILABLE", "error": type(exc).__name__,
                            "execution_authority": False, "trading_ready": False})

    def do_POST(self):
        expected = (os.getenv("BROKER_EVIDENCE_PUBLISH_TOKEN", "")
                    or os.getenv("RUNTIME_STATUS_PUBLISH_TOKEN", ""))
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(supplied, expected):
            return self._send(401, {"error": "unauthorized", "execution_authority": False})
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 100_000)
            payload = sanitize(json.loads(self.rfile.read(length)))
            redis([["SET", KEY, json.dumps(payload, separators=(",", ":")), "EX", TTL_SECONDS]])
            self._send(202, {"accepted": True, "read_only": True,
                             "execution_authority": False, "trading_ready": False})
        except Exception as exc:
            self._send(400, {"error": type(exc).__name__, "execution_authority": False,
                            "trading_ready": False})
