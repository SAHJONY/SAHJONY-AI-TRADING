"""Read-only hosted Parquet snapshot projection."""
from http.server import BaseHTTPRequestHandler
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import json

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("parquet_snapshot", ROOT / "parquet/bridge/snapshot.py")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        desk = parse_qs(urlparse(self.path).query).get("desk", ["live"])[0]
        if desk not in {"live", "crypto", "trainer", "stocks"}:
            desk = "live"
        try:
            try:
                raw = json.loads(MODULE.source_for(desk).read_text())
            except FileNotFoundError:
                host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "")
                if not host or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:" for char in host):
                    raise ValueError("invalid deployment host")
                static_name = "status.json"
                req = Request(f"https://{host}/{static_name}", headers={"User-Agent": "ParquetSnapshot/1.0"})
                with urlopen(req, timeout=5) as response:
                    raw = json.loads(response.read())
            payload = MODULE.project(raw, desk, {})
            body, status = json.dumps(payload, separators=(",", ":")).encode(), 200
        except Exception as exc:
            body, status = json.dumps({"error": type(exc).__name__, "executionAuthority": False}).encode(), 503
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
