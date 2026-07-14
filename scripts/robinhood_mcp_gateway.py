"""Local, read-only HTTP gateway for the authenticated Robinhood MCP session.

The Robinhood OAuth token remains owned by Codex.  This process delegates a
small allowlist of read operations to ``codex exec`` and exposes only the GET
contract consumed by :mod:`utils.brokers.robinhood_mcp`.

No order endpoint exists in this server.  POST/PUT/PATCH/DELETE are rejected.
Bind to loopback only and protect every request with a random bearer token.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit


_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")
_READ_ONLY_PROMPT = """\
Use only the robinhood-trading MCP and only its read tools. Never call any tool
whose name starts with review_, place_, cancel_, replace_, create_, update_,
add_, remove_, delete_, follow_, or unfollow_. Do not preview, submit, modify,
or cancel orders. Do not change the account in any way.

Perform this operation: {operation}
Parameters: {parameters}

Return JSON only, matching this shape:
{{
  "account": {{
    "account_number_last4": "string",
    "account_type": "string containing Agentic for the agentic account",
    "status": "string",
    "cash": 0.0,
    "buying_power": 0.0,
    "equity": 0.0
  }},
  "positions": [
    {{"symbol": "string", "qty": 0.0, "market_value": 0.0,
      "avg_entry_price": 0.0, "asset_type": "string"}}
  ],
  "quote": {{"symbol": "string", "price": 0.0}}
}}

For account_snapshot: call get_accounts, select only the account with
agentic_allowed=true, then call get_portfolio for that exact account. Include
that account and leave positions/quote empty.
For positions: first select the agentic_allowed account with get_accounts, then
read its nonzero equity and option positions. Never read order history. Include
normalized positions and the selected account identity; leave quote empty.
For quote: call get_equity_quotes for the exact supplied symbol. Put the current
trade price, or mark/last price when the trade price is unavailable, in price;
leave account empty and positions empty.
Never expose a full account number, OAuth token, bearer token, or credential.
"""


class GatewayError(RuntimeError):
    """An upstream or validation failure safe to report as a gateway error."""


class CodexRobinhoodBridge:
    """Invoke the already-authenticated Codex MCP session for read operations."""

    def __init__(self, *, codex_bin: str = "codex", timeout: int = 90) -> None:
        self.codex_bin = codex_bin
        self.timeout = timeout
        self._lock = threading.Lock()

    def call(self, operation: str, **parameters: Any) -> dict[str, Any]:
        if operation not in {"account_snapshot", "positions", "quote"}:
            raise GatewayError("operation is not allowlisted")
        prompt = _READ_ONLY_PROMPT.format(
            operation=operation,
            parameters=json.dumps(parameters, separators=(",", ":")),
        )
        output_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="rh-mcp-", suffix=".json", delete=False) as output:
                output_path = output.name
            command = [
                self.codex_bin,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-last-message",
                output_path,
                prompt,
            ]
            # Serialize calls so one local bot cannot fan out costly agent runs.
            with self._lock:
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                    env=_minimal_environment(),
                )
            if completed.returncode != 0:
                detail = completed.stderr.strip().splitlines()[-1:] or ["unknown failure"]
                raise GatewayError(f"authenticated MCP call failed: {detail[0]}")
            raw = Path(output_path).read_text(encoding="utf-8").strip()
            payload = _parse_json_object(raw)
            return _validate_upstream_payload(operation, payload, parameters)
        except subprocess.TimeoutExpired as exc:
            raise GatewayError("authenticated MCP call timed out") from exc
        except OSError as exc:
            raise GatewayError(f"could not run Codex: {exc}") from exc
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except FileNotFoundError:
                    pass


def _minimal_environment() -> dict[str, str]:
    """Keep Codex auth/config while avoiding accidental broker secret leakage."""
    allowed = {"HOME", "PATH", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def _parse_json_object(raw: str) -> dict[str, Any]:
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1])
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GatewayError("Codex returned a non-JSON response") from exc
    if not isinstance(value, dict):
        raise GatewayError("Codex response was not an object")
    return value


def _number(value: Any, field: str) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise GatewayError(f"invalid numeric field: {field}") from exc


def _validate_upstream_payload(
    operation: str, payload: dict[str, Any], parameters: dict[str, Any]
) -> dict[str, Any]:
    if operation == "quote":
        quote = payload.get("quote")
        if not isinstance(quote, dict):
            raise GatewayError("quote response is missing")
        requested = str(parameters.get("symbol", "")).upper()
        returned = str(quote.get("symbol", "")).upper()
        price = _number(quote.get("price"), "price")
        if returned != requested or price <= 0:
            raise GatewayError("quote identity or price is invalid")
        return {"symbol": returned, "price": price}

    account = payload.get("account")
    if not isinstance(account, dict):
        raise GatewayError("agentic account identity is missing")
    normalized_account = {
        "account_number_last4": str(account.get("account_number_last4", ""))[-4:],
        "account_type": str(account.get("account_type", "")),
        "status": str(account.get("status", "")),
        "cash": _number(account.get("cash"), "cash"),
        "buying_power": _number(account.get("buying_power"), "buying_power"),
        "equity": _number(account.get("equity"), "equity"),
    }
    if operation == "account_snapshot":
        return normalized_account

    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise GatewayError("positions response is missing")
    rows: list[dict[str, Any]] = []
    for position in positions:
        if not isinstance(position, dict):
            raise GatewayError("invalid position row")
        symbol = str(position.get("symbol", "")).upper()
        if not _SYMBOL.fullmatch(symbol):
            raise GatewayError("invalid position symbol")
        rows.append(
            {
                "symbol": symbol,
                "qty": _number(position.get("qty"), "qty"),
                "market_value": _number(position.get("market_value"), "market_value"),
                "avg_entry_price": _number(position.get("avg_entry_price"), "avg_entry_price"),
                "asset_type": str(position.get("asset_type", "equity")),
            }
        )
    return {"account": normalized_account, "positions": rows}


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


class GatewayService:
    def __init__(
        self,
        bridge: CodexRobinhoodBridge,
        *,
        expected_last4: str,
        cache_seconds: float = 10.0,
    ) -> None:
        if not re.fullmatch(r"\d{4}", expected_last4):
            raise ValueError("expected_last4 must contain exactly four digits")
        self.bridge = bridge
        self.expected_last4 = expected_last4
        self.cache_seconds = cache_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = threading.Lock()

    def _cached(self, key: str, loader: Callable[[], Any], ttl: float | None = None) -> Any:
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and entry.expires_at > now:
                return entry.value
        value = loader()
        with self._cache_lock:
            self._cache[key] = _CacheEntry(now + (self.cache_seconds if ttl is None else ttl), value)
        return value

    def account(self) -> dict[str, Any]:
        account = self._cached("account", lambda: self.bridge.call("account_snapshot"))
        self._verify_identity(account)
        return account

    def positions(self) -> dict[str, Any]:
        payload = self._cached("positions", lambda: self.bridge.call("positions"))
        self._verify_identity(payload["account"])
        return {"positions": payload["positions"]}

    def quote(self, symbol: str) -> dict[str, Any]:
        normalized = symbol.strip().upper()
        if not _SYMBOL.fullmatch(normalized):
            raise ValueError("invalid symbol")
        return self._cached(
            f"quote:{normalized}",
            lambda: self.bridge.call("quote", symbol=normalized),
            ttl=min(self.cache_seconds, 2.0),
        )

    def health(self) -> dict[str, Any]:
        account = self.account()
        return {
            "ok": True,
            "read_only": True,
            "identity_verified": True,
            "account_number_last4": account["account_number_last4"],
            # Deliberately fail closed: this read-only gateway never advertises
            # a tradable market session to the broker.
            "market_open": False,
        }

    def _verify_identity(self, account: dict[str, Any]) -> None:
        last4 = str(account.get("account_number_last4", ""))[-4:]
        account_type = str(account.get("account_type", "")).lower()
        status = str(account.get("status", "")).lower()
        if last4 != self.expected_last4 or "agentic" not in account_type or status != "active":
            raise GatewayError("authenticated account identity does not match the configured Agentic account")


def make_handler(service: GatewayService, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "RobinhoodReadOnlyGateway/1"

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return hmac.compare_digest(supplied.encode(), expected.encode())

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/health":
                    payload = service.health()
                elif path == "/account":
                    payload = service.account()
                elif path == "/positions":
                    payload = service.positions()
                elif path.startswith("/quotes/"):
                    payload = service.quote(unquote(path.removeprefix("/quotes/")))
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._json(HTTPStatus.OK, payload)
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except GatewayError as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})

        def _read_only(self) -> None:
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read-only gateway"})

        do_POST = do_PUT = do_PATCH = do_DELETE = _read_only

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"{self.address_string()} - {fmt % args}")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Robinhood MCP localhost gateway")
    parser.add_argument("--host", default=os.getenv("ROBINHOOD_MCP_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ROBINHOOD_MCP_GATEWAY_PORT", "8787")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("the read-only gateway may bind only to loopback")
    token = os.getenv("ROBINHOOD_MCP_GATEWAY_TOKEN", "").strip()
    if len(token) < 32:
        parser.error("ROBINHOOD_MCP_GATEWAY_TOKEN must be at least 32 characters")
    expected_last4 = os.getenv("ROBINHOOD_MCP_EXPECTED_LAST4", "1131").strip()
    service = GatewayService(CodexRobinhoodBridge(), expected_last4=expected_last4)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service, token))
    print(f"Read-only Robinhood MCP gateway listening on http://{args.host}:{args.port}")
    print(f"Identity is pinned to Agentic account ending in {expected_last4}; no order routes exist.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
