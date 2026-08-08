"""Same-origin Finnhub proxy. The API key never reaches browser code."""
from datetime import date
from http.server import BaseHTTPRequestHandler
import json
from urllib import parse

from market_data.finnhub import FinnhubClient, FinnhubError


def _date(value: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise FinnhubError("invalid date") from exc


def route(params, client=None):
    provider = client or FinnhubClient()
    action = str(params.get("action", ["quote"])[0])
    if action == "quote":
        return provider.quote(str(params.get("symbol", [""])[0])), 30
    if action == "news":
        return provider.general_news(limit=40), 300
    if action == "company-news":
        symbol = str(params.get("symbol", [""])[0])
        return provider.company_news(symbol, _date(params.get("from", [""])[0]),
                                     _date(params.get("to", [""])[0]), limit=20), 300
    if action == "earnings":
        return provider.earnings(_date(params.get("from", [""])[0]),
                                 _date(params.get("to", [""])[0])), 300
    raise FinnhubError("unsupported action")


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload, max_age=0):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", f"public, s-maxage={max_age}, stale-while-revalidate=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            payload, max_age = route(parse.parse_qs(parse.urlparse(self.path).query))
            self._send(200, payload, max_age)
        except FinnhubError as exc:
            self._send(503, {"healthy": False, "provider": "finnhub",
                             "error": str(exc), "execution_authority": False})
        except Exception as exc:
            self._send(503, {"healthy": False, "provider": "finnhub",
                             "error": type(exc).__name__, "execution_authority": False})
