import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("broker_evidence_api", Path("api/broker-evidence.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def payload():
    return {
        "generated_at": "2026-07-21T04:20:20Z", "verdict": "RECONCILIATION_BLOCKED",
        "source_status": {"mcp": "VERIFIED", "ui": "OBSERVED"},
        "conflicts": ["UI and MCP buying_power conflict"],
        "blockers": ["unexplained non-cash value exceeds tolerance"],
        "unexplained_value": 6.0, "report_digest": "a" * 64,
        "execution_authority": False, "trading_armed": False, "trading_ready": False,
        "mcp": {"source_id": "robinhood-trading-mcp", "observed_at": "2026-07-21T04:20:20Z",
                "account_last4": "1131", "identity_verified": True, "digest": "b" * 64,
                "account": {"equity": 25.99, "cash": 19.99, "buying_power": 19.99},
                "positions": []},
        "ui": {"source_id": "robinhood-ui-manual", "observed_at": "2026-07-21T04:18:38Z",
               "equity": None, "cash": None, "buying_power": 0.0,
               "human_notes": "private operator note", "digest": "c" * 64},
    }


def test_hosted_evidence_is_redacted_and_permanently_read_only():
    result = MODULE.sanitize(payload())
    assert result["ui"]["human_notes"] == "[REDACTED]"
    assert result["mcp"]["account_last4"] == "1131"
    assert result["verdict"] == "RECONCILIATION_BLOCKED"
    assert result["conflict_status"] == "SOURCE_CONFLICT"
    assert result["execution_authority"] is False
    assert result["trading_armed"] is False
    assert result["trading_ready"] is False


@pytest.mark.parametrize("field", ["execution_authority", "trading_armed", "trading_ready"])
def test_hosted_evidence_rejects_any_enabled_execution_flag(field):
    raw = payload(); raw[field] = True
    with pytest.raises(ValueError, match="safety declaration"):
        MODULE.sanitize(raw)


def test_hosted_evidence_rejects_unverified_or_full_identity():
    raw = payload(); raw["mcp"]["identity_verified"] = False
    with pytest.raises(ValueError, match="verified masked"):
        MODULE.sanitize(raw)
    raw = payload(); raw["mcp"]["account_last4"] = "12345671131"
    # A full identifier must not be accepted merely because its suffix matches.
    with pytest.raises(ValueError, match="verified masked"):
        MODULE.sanitize(raw)


def test_hosted_evidence_rejects_nonfinite_values_and_invalid_digests():
    raw = payload(); raw["mcp"]["account"]["equity"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        MODULE.sanitize(raw)
    raw = payload(); raw["report_digest"] = "not-a-digest"
    with pytest.raises(ValueError, match="digest"):
        MODULE.sanitize(raw)


def test_hosted_evidence_requires_source_timestamps_and_redacts_issue_text():
    raw = payload(); raw["mcp"]["observed_at"] = "not-a-time"
    with pytest.raises(ValueError, match="observed_at"):
        MODULE.sanitize(raw)
    raw = payload(); raw["blockers"] = ["token abcdefghijklmnopqrstuvwxyz"]
    with pytest.raises(ValueError, match="sensitive"):
        MODULE.sanitize(raw)


def test_hosted_evidence_accepts_explicit_fail_closed_unavailable_state():
    raw = payload()
    raw.update({"verdict": "EVIDENCE_UNAVAILABLE", "mcp": None, "ui": None,
                "unexplained_value": None, "conflicts": [],
                "blockers": ["authenticated MCP account or positions evidence unavailable"]})
    result = MODULE.sanitize(raw)
    assert result["source_status"]["mcp"] == "UNAVAILABLE"
    assert result["verdict"] == "EVIDENCE_UNAVAILABLE"
    assert result["execution_authority"] is False
    assert result["trading_ready"] is False


def test_hosted_evidence_never_reconciles_without_verified_mcp():
    raw = payload(); raw["mcp"] = None
    with pytest.raises(ValueError, match="MCP evidence is required"):
        MODULE.sanitize(raw)
