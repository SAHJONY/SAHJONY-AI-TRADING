"""Hosted, read-only broker telemetry backed by Upstash Redis REST."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import hmac
import json
import os
from urllib import request

KEY = "sahjony:runtime-status:v1"
TTL_SECONDS = 600


def redis(command):
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("hosted runtime storage is not configured")
    req = request.Request(url.rstrip("/") + "/pipeline", data=json.dumps(command).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read())
        if not isinstance(payload, list):
            raise ValueError("invalid Upstash pipeline response")
        return [item.get("result") if isinstance(item, dict) else None for item in payload]


def sanitize(payload):
    if payload.get("execution_authority") is not False or payload.get("read_only") is not True:
        raise ValueError("invalid safety declaration")
    agent = payload.get("agentic") or {}
    last4 = str(agent.get("account_number_last4", ""))[-4:]
    if len(last4) != 4 or not last4.isdigit() or not agent.get("identity_verified"):
        raise ValueError("verified masked identity is required")
    return {
        "schema_version": 1,
        "updated": str(payload.get("updated", "")),
        "source": "robinhood-trading-mcp",
        "read_only": True,
        "execution_authority": False,
        "live": True,
        "broker": "Robinhood",
        "account_mask": f"••••{last4}",
        "total_value": float(payload.get("total_value", 0.0) or 0.0),
        "equity_value": float(payload.get("equity_value", 0.0) or 0.0),
        "cash": float(payload.get("cash", 0.0) or 0.0),
        "buying_power": float(payload.get("buying_power", 0.0) or 0.0),
        "positions": list(payload.get("positions", []))[:100],
        "orders": [],
        "agentic": {
            "connected": bool(agent.get("connected")), "ok": bool(agent.get("ok")),
            "read_only": True, "identity_verified": True,
            "account_number_last4": last4,
            "account_type": str(agent.get("account_type", "Agentic"))[:80],
            "status": str(agent.get("status", ""))[:40],
            "equity": float(agent.get("equity", 0.0) or 0.0),
            "cash": float(agent.get("cash", 0.0) or 0.0),
            "buying_power": float(agent.get("buying_power", 0.0) or 0.0),
            "updated": str(payload.get("updated", "")),
        },
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
                return self._send(503, {"healthy": False, "error": "no_runtime_evidence",
                                        "execution_authority": False})
            payload = json.loads(result)
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    payload["updated"].replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = TTL_SECONDS + 1
            payload["fresh"] = 0 <= age <= TTL_SECONDS
            payload["age_seconds"] = max(0, round(age))
            self._send(200 if payload["fresh"] else 503, payload)
        except Exception as exc:
            self._send(503, {"healthy": False, "error": type(exc).__name__,
                            "execution_authority": False})

    def do_POST(self):
        expected = os.getenv("RUNTIME_STATUS_PUBLISH_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(supplied, expected):
            return self._send(401, {"error": "unauthorized"})
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 100_000)
            payload = sanitize(json.loads(self.rfile.read(length)))
            redis([["SET", KEY, json.dumps(payload, separators=(",", ":")), "EX", TTL_SECONDS]])
            self._send(202, {"accepted": True, "read_only": True,
                             "execution_authority": False})
        except Exception as exc:
            print(f"runtime-status POST failed: {type(exc).__name__}: {str(exc)[:160]}")
            self._send(400, {"error": type(exc).__name__, "execution_authority": False})
