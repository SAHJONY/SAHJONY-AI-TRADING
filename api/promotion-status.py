"""Authenticated hosted producer-health status backed by Upstash Redis REST."""
from http.server import BaseHTTPRequestHandler
import json
import os
from urllib import request

KEY = "sahjony:promotion-producer-health"


def redis(command):
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("hosted status storage is not configured")
    req = request.Request(url.rstrip("/") + "/pipeline", data=json.dumps(command).encode(),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with request.urlopen(req, timeout=8) as response:
        return json.loads(response.read())["result"]


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        try:
            result = redis([["GET", KEY]])[0]
            self._send(200, json.loads(result) if result else {"healthy": False, "alerts": [{"code": "no_evidence"}]})
        except Exception as exc:
            self._send(503, {"healthy": False, "error": type(exc).__name__, "execution_authority": False})

    def do_POST(self):
        expected = os.getenv("PROMOTION_STATUS_PUBLISH_TOKEN", "")
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or supplied != expected:
            return self._send(401, {"error": "unauthorized"})
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 100_000)
            payload = json.loads(self.rfile.read(length))
            if payload.get("execution_authority") is not False:
                raise ValueError("invalid safety declaration")
            redis([["SET", KEY, json.dumps(payload, separators=(",", ":"))]])
            self._send(202, {"accepted": True, "execution_authority": False})
        except Exception as exc:
            self._send(400, {"error": type(exc).__name__})
