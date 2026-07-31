from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json

import pytest

from observability.broker_evidence import (EvidenceVerdict, build_mcp_evidence,
                                           evidence_digest, parse_crypto_holding_observation,
                                           parse_ui_observation,
                                           reconcile_evidence)
from scripts import broker_evidence as cli


NOW = datetime(2026, 7, 21, 4, 0, tzinfo=timezone.utc)


def mcp(*, equity=25.99, cash=19.99, buying_power=19.99, positions=None,
        observed_at=None, verified=True):
    return build_mcp_evidence(
        {"account_number_last4": "1131", "equity": equity, "cash": cash,
         "buying_power": buying_power},
        positions if positions is not None else [],
        observed_at=(observed_at or NOW.isoformat()), identity_verified=verified,
    )


def ui(**overrides):
    raw = {"source_id": "robinhood-ui-manual", "observed_at": NOW.isoformat(),
           "equity": 25.99, "cash": 19.99, "buying_power": 19.99,
           "human_notes": "observed in Robinhood UI", **overrides}
    raw["digest"] = evidence_digest(raw)
    return parse_ui_observation(raw)


def crypto_observation(**overrides):
    raw = {"source": "robinhood-ui-agentic", "timestamp": NOW.isoformat(),
           "account": "***1131", "symbol": "BTC", "quantity": 0.00005,
           "market_value": 5.91, **overrides}
    raw["digest"] = evidence_digest(raw)
    return parse_crypto_holding_observation(raw)


def test_unexplained_six_dollars_with_no_positions_is_blocked():
    report = reconcile_evidence(mcp(), now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert report.unexplained_value == pytest.approx(6.0)
    assert report.mcp.positions == ()
    assert "unexplained non-cash value exceeds tolerance" in report.blockers
    assert report.execution_authority is False
    assert report.trading_armed is False
    assert report.trading_ready is False


def test_conflicting_ui_buying_power_is_blocked():
    report = reconcile_evidence(mcp(equity=19.99), ui(equity=19.99, buying_power=0.0), now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert "UI and MCP buying_power conflict" in report.conflicts


def test_ui_evidence_cannot_create_a_holding():
    raw = {"source_id": "robinhood-ui-manual", "observed_at": NOW.isoformat(),
           "equity": 25.99, "cash": 19.99, "buying_power": 0.0,
           "positions": [{"symbol": "GIFT", "qty": 1}], "human_notes": "gift"}
    raw["digest"] = evidence_digest(raw)
    with pytest.raises(ValueError, match="unsupported fields"):
        parse_ui_observation(raw)
    assert reconcile_evidence(mcp(), now=NOW).mcp.positions == ()


def test_missing_mcp_positions_is_evidence_unavailable():
    report = reconcile_evidence(None, ui(), now=NOW)
    assert report.verdict is EvidenceVerdict.EVIDENCE_UNAVAILABLE
    assert report.execution_authority is False
    assert report.trading_ready is False


def test_matching_evidence_may_reconcile():
    position = {"symbol": "VTI", "qty": 1.0, "market_value": 6.0}
    report = reconcile_evidence(mcp(positions=[position]), ui(), now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILED
    assert report.unexplained_value == pytest.approx(0.0)
    assert report.trading_ready is False


def test_classified_crypto_without_exact_position_rows_is_blocked():
    account = {"account_number_last4": "1131", "equity": 25.90, "cash": 19.99,
               "buying_power": 19.99, "equity_value": 0, "options_value": 0,
               "crypto_value": 5.91, "total_value": 25.90}
    evidence = build_mcp_evidence(account, [], observed_at=NOW.isoformat(),
                                  identity_verified=True)
    report = reconcile_evidence(evidence, now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert "crypto holdings are not fully enumerated" in report.blockers
    assert report.unexplained_value == pytest.approx(5.91)


def test_exact_crypto_position_reconciles_total_value():
    account = {"account_number_last4": "1131", "equity": 25.90, "cash": 19.99,
               "buying_power": 19.99, "equity_value": 0, "options_value": 0,
               "crypto_value": 5.91, "total_value": 25.90}
    positions = [{"symbol": "BTC", "qty": 0.00005, "market_value": 5.91,
                  "asset_type": "crypto"}]
    evidence = build_mcp_evidence(account, positions, observed_at=NOW.isoformat(),
                                  identity_verified=True)
    report = reconcile_evidence(evidence, crypto_observation=crypto_observation(), now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILED
    assert report.crypto_authenticated is True
    assert report.unexplained_value == pytest.approx(0)


def test_crypto_candidate_without_authenticated_row_cannot_reconcile():
    account = {"account_number_last4": "1131", "equity": 25.90, "cash": 19.99,
               "buying_power": 19.99, "equity_value": 0, "options_value": 0,
               "crypto_value": 5.91, "total_value": 25.90}
    evidence = build_mcp_evidence(account, [], observed_at=NOW.isoformat(),
                                  identity_verified=True)
    report = reconcile_evidence(evidence, crypto_observation=crypto_observation(), now=NOW)
    assert report.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert report.crypto_authenticated is False
    assert "crypto observation lacks authenticated position confirmation" in report.blockers


def test_crypto_observation_accepts_only_exact_schema_and_agentic_account():
    raw = {"source": "robinhood-ui-agentic", "timestamp": NOW.isoformat(),
           "account": "***9999", "symbol": "BTC", "quantity": 0.00005,
           "market_value": 5.91}
    raw["digest"] = evidence_digest(raw)
    with pytest.raises(ValueError, match="Agentic"):
        parse_crypto_holding_observation(raw)
    raw["account"] = "***1131"
    raw["notes"] = "untrusted extra field"
    raw["digest"] = evidence_digest(raw)
    with pytest.raises(ValueError, match="incomplete or unsupported"):
        parse_crypto_holding_observation(raw)


def test_manual_digest_and_staleness_fail_closed():
    raw = {"source_id": "robinhood-ui-manual", "observed_at": NOW.isoformat(),
           "equity": 19.99, "cash": 19.99, "buying_power": 19.99,
           "human_notes": "observed"}
    raw["digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest verification failed"):
        parse_ui_observation(raw)
    stale = reconcile_evidence(mcp(equity=19.99, observed_at=(NOW - timedelta(hours=1)).isoformat()),
                               now=NOW, max_age_seconds=60)
    assert stale.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert "MCP evidence is stale" in stale.blockers


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -1])
def test_invalid_reconciliation_tolerance_fails_closed(tolerance):
    report = reconcile_evidence(mcp(equity=19.99), now=NOW, value_tolerance=tolerance)
    assert report.verdict is EvidenceVerdict.RECONCILIATION_BLOCKED
    assert report.execution_authority is False


def test_verdict_and_evidence_are_immutable():
    report = reconcile_evidence(mcp(), now=NOW)
    with pytest.raises(FrozenInstanceError):
        report.verdict = EvidenceVerdict.RECONCILED
    with pytest.raises(FrozenInstanceError):
        report.mcp.account = None


def test_cli_writes_private_and_redacted_public_evidence(tmp_path, monkeypatch):
    evidence = mcp()
    monkeypatch.setattr(cli, "collect_mcp", lambda: (evidence, []))
    manual = {"source_id": "robinhood-ui-manual", "observed_at": NOW.isoformat(),
              "equity": 25.99, "cash": 19.99, "buying_power": 0.0,
              "human_notes": "observed zero buying power in Robinhood UI"}
    manual["digest"] = evidence_digest(manual)
    ui_path = tmp_path / "ui.json"
    ui_path.write_text(json.dumps(manual), encoding="utf-8")
    public_path, private_dir = tmp_path / "public.json", tmp_path / "private"

    public = cli.produce(ui_path=ui_path, public_path=public_path, private_dir=private_dir, now=NOW)

    encoded = public_path.read_text(encoding="utf-8")
    assert public["verdict"] == "RECONCILIATION_BLOCKED"
    assert public["ui"]["human_notes"] == "[REDACTED]"
    assert "observed zero buying power" not in encoded
    assert public["mcp"]["account_last4"] == "1131"
    assert public["execution_authority"] is False
    assert public["trading_armed"] is False
    assert public["trading_ready"] is False
    private_files = list(private_dir.glob("*.json"))
    assert len(private_files) == 1
    assert "observed zero buying power" in private_files[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("notes", [
    "client secret abcdefghijklmnopqrstuvwxyz1234",
    "full account 123456789",
    "-----BEGIN PRIVATE KEY-----",
])
def test_credentials_and_full_account_numbers_are_rejected_from_notes(notes):
    raw = {"source_id": "robinhood-ui-manual", "observed_at": NOW.isoformat(),
           "equity": 25.99, "cash": 19.99, "buying_power": 0.0, "human_notes": notes}
    raw["digest"] = evidence_digest(raw)
    with pytest.raises(ValueError, match="prohibited credential or account data"):
        parse_ui_observation(raw)


def test_cli_collects_only_read_routes_and_never_calls_orders(monkeypatch):
    monkeypatch.setattr(cli.broker_diagnostics, "_config", lambda: {
        "url": "http://gateway", "token": "x" * 32, "expected_last4": "1131", "symbols": "",
    })
    calls = []

    def get(base, token, path, timeout):
        calls.append((path, timeout))
        if path == "/health":
            return 200, {"identity_verified": True, "account_number_last4": "1131"}
        if path == "/account":
            return 200, {"account_number_last4": "1131", "equity": 19.99,
                         "cash": 19.99, "buying_power": 19.99,
                         "equity_value": 0, "options_value": 0,
                         "crypto_value": 0, "total_value": 19.99}
        if path == "/positions":
            return 200, {"positions": []}
        if path == "/capabilities/crypto-positions":
            return 200, {"supported": False, "reason": "tool_unavailable", "positions": []}
        raise AssertionError(path)

    monkeypatch.setattr(cli.broker_diagnostics, "_get", get)
    evidence, blockers = cli.collect_mcp()
    assert blockers == ["authenticated crypto enumeration capability unsupported"]
    assert evidence.identity_verified is True
    assert calls == [("/health", 90), ("/account", 90), ("/positions", 285),
                     ("/capabilities/crypto-positions", 120)]
    assert not any(any(word in path for word in ("order", "preview", "modify", "cancel"))
                   for path, _ in calls)


def test_cli_missing_positions_fails_closed(monkeypatch):
    monkeypatch.setattr(cli.broker_diagnostics, "_config", lambda: {
        "url": "http://gateway", "token": "x" * 32, "expected_last4": "1131", "symbols": "",
    })
    payloads = {
        "/health": (200, {"identity_verified": True, "account_number_last4": "1131"}),
        "/account": (200, {"account_number_last4": "1131", "equity": 19.99,
                            "cash": 19.99, "buying_power": 19.99,
                            "equity_value": 0, "options_value": 0,
                            "crypto_value": 0, "total_value": 19.99}),
        "/positions": (503, {"error": "unavailable"}),
    }
    monkeypatch.setattr(cli.broker_diagnostics, "_get",
                        lambda base, token, path, timeout: payloads[path])
    evidence, blockers = cli.collect_mcp()
    assert evidence is None
    assert blockers == ["authenticated MCP account or positions evidence unavailable"]


def test_cli_malformed_positions_payload_fails_closed(monkeypatch):
    monkeypatch.setattr(cli.broker_diagnostics, "_config", lambda: {
        "url": "http://gateway", "token": "x" * 32, "expected_last4": "1131", "symbols": "",
    })
    payloads = {
        "/health": (200, {"identity_verified": True, "account_number_last4": "1131"}),
        "/account": (200, {"account_number_last4": "1131", "equity": 19.99,
                            "cash": 19.99, "buying_power": 19.99,
                            "equity_value": 0, "options_value": 0,
                            "crypto_value": 0, "total_value": 19.99}),
        "/positions": (200, {}),
    }
    monkeypatch.setattr(cli.broker_diagnostics, "_get",
                        lambda base, token, path, timeout: payloads[path])
    evidence, blockers = cli.collect_mcp()
    assert evidence is None
    assert blockers == ["authenticated MCP positions evidence is invalid"]


def test_hosted_publisher_is_optional_and_never_leaks_token(monkeypatch):
    monkeypatch.delenv("BROKER_EVIDENCE_API_URL", raising=False)
    monkeypatch.delenv("RUNTIME_STATUS_URL", raising=False)
    monkeypatch.delenv("BROKER_EVIDENCE_PUBLISH_TOKEN", raising=False)
    monkeypatch.delenv("RUNTIME_STATUS_PUBLISH_TOKEN", raising=False)
    assert cli.publish_hosted({"execution_authority": False}) is False

    monkeypatch.setenv("BROKER_EVIDENCE_API_URL", "https://example.test/api/broker-evidence")
    monkeypatch.setenv("BROKER_EVIDENCE_PUBLISH_TOKEN", "publisher-secret")
    seen = {}

    class Response:
        status = 202
        def __enter__(self): return self
        def __exit__(self, *args): return None

    def open_request(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(cli, "urlopen", open_request)
    assert cli.publish_hosted({"execution_authority": False}) is True
    assert seen["url"].endswith("/api/broker-evidence")
    assert seen["authorization"] == "Bearer publisher-secret"
    assert "publisher-secret" not in json.dumps(seen["body"])


def test_operations_dashboard_panel_javascript_parses(tmp_path):
    from pathlib import Path
    import subprocess
    html = Path("public/operations.html").read_text(encoding="utf-8")
    assert "Dual-Source Broker Evidence" in html
    assert "UI observations are evidence only" in html
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    path = tmp_path / "operations.js"
    path.write_text(script, encoding="utf-8")
    subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)


def test_generated_evidence_is_excluded_from_git_and_vercel_deployments():
    from pathlib import Path
    assert "public/broker_evidence.json" in Path(".gitignore").read_text(encoding="utf-8")
    assert "public/broker_evidence.json" in Path(".vercelignore").read_text(encoding="utf-8")
