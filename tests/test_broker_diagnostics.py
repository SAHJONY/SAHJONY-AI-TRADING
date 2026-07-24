import json
from pathlib import Path
import subprocess

from scripts import broker_diagnostics as diagnostics


def test_dashboard_javascript_parses(tmp_path):
    html = Path("public/broker-diagnostics.html").read_text(encoding="utf-8")
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    path = tmp_path / "broker-diagnostics.js"
    path.write_text(script, encoding="utf-8")
    subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)


def test_collector_is_read_only_and_fails_closed(monkeypatch):
    monkeypatch.setattr(diagnostics, "_config", lambda: {
        "url": "http://127.0.0.1:8787",
        "token": "x" * 32,
        "expected_last4": "1131",
        "symbols": "VTI",
    })
    calls = []

    def fake_get(base, token, path, timeout=60.0):
        calls.append(path)
        payloads = {
            "/health": (200, {"identity_verified": True, "account_number_last4": "1131"}),
            "/account": (200, {"account_number_last4": "1131", "equity": 26, "cash": 19.99, "buying_power": 19.99}),
            "/positions": (200, {"positions": []}),
            "/capabilities/crypto-positions": (
                200, {"supported": False, "reason": "tool_unavailable", "positions": []}
            ),
            "/quotes/VTI": (200, {"symbol": "VTI", "price": 370.33, "as_of": "2026-07-15T15:00:00Z"}),
        }
        return payloads[path]

    monkeypatch.setattr(diagnostics, "_get", fake_get)
    result = diagnostics.collect()
    assert result["execution_authority"] is False
    assert result["reconciliation"]["trading_ready"] is False
    assert result["reconciliation"]["status"] == "blocked"
    assert "broker reports no visible positions" in result["reconciliation"]["blockers"]
    assert all(path.startswith(("/health", "/account", "/positions",
                                "/capabilities/crypto-positions", "/quotes/")) for path in calls)
    assert not any("order" in path.lower() for path in calls)


def test_missing_token_never_calls_gateway(monkeypatch):
    monkeypatch.setattr(diagnostics, "_config", lambda: {
        "url": "http://127.0.0.1:8787",
        "token": "",
        "expected_last4": "1131",
        "symbols": "VTI",
    })
    monkeypatch.setattr(diagnostics, "_get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call")))
    result = diagnostics.collect()
    assert result["gateway"]["reachable"] is False
    assert result["execution_authority"] is False
    assert result["reconciliation"]["blockers"] == ["gateway token missing"]


def test_snapshot_has_no_token_field(monkeypatch):
    monkeypatch.setattr(diagnostics, "_config", lambda: {
        "url": "http://127.0.0.1:8787",
        "token": "super-secret-token",
        "expected_last4": "1131",
        "symbols": "",
    })
    monkeypatch.setattr(diagnostics, "_get", lambda base, token, path, timeout=60.0: (200, {
        "identity_verified": True,
        "account_number_last4": "1131",
        "positions": [],
    }))
    encoded = json.dumps(diagnostics.collect())
    assert "super-secret-token" not in encoded
    assert '"execution_authority": false' in encoded
