"""Immutable, fail-closed reconciliation of MCP and manual UI evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping


class EvidenceVerdict(str, Enum):
    RECONCILED = "RECONCILED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


def evidence_digest(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "digest"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _timestamp(value: Any, name: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{name} timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class AccountTotals:
    equity: float
    cash: float
    buying_power: float
    equity_value: float
    options_value: float
    crypto_value: float
    total_value: float


@dataclass(frozen=True)
class PositionEvidence:
    symbol: str
    qty: float
    market_value: float
    asset_type: str


@dataclass(frozen=True)
class MCPSourceEvidence:
    source_id: str
    observed_at: str
    account_last4: str
    identity_verified: bool
    account: AccountTotals
    positions: tuple[PositionEvidence, ...]
    digest: str


@dataclass(frozen=True)
class UIObservation:
    source_id: str
    observed_at: str
    equity: float | None
    cash: float | None
    buying_power: float | None
    human_notes: str
    digest: str


@dataclass(frozen=True)
class ReconciliationReport:
    report_version: int
    generated_at: str
    mcp: MCPSourceEvidence | None
    ui: UIObservation | None
    unexplained_value: float | None
    conflicts: tuple[str, ...]
    blockers: tuple[str, ...]
    verdict: EvidenceVerdict
    report_digest: str
    execution_authority: bool = False
    trading_armed: bool = False
    trading_ready: bool = False

    def private_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["verdict"] = self.verdict.value
        value["source_status"] = {
            "mcp": "VERIFIED" if self.mcp and self.mcp.identity_verified else "UNAVAILABLE",
            "ui": "OBSERVED" if self.ui else "NOT_PROVIDED",
        }
        value["conflict_status"] = "SOURCE_CONFLICT" if self.conflicts else "NONE"
        return value

    def public_dict(self) -> dict[str, Any]:
        value = self.private_dict()
        if value.get("ui"):
            value["ui"]["human_notes"] = "[REDACTED]" if self.ui and self.ui.human_notes else ""
        # Public output carries only the pinned suffix, never a full identifier.
        if value.get("mcp"):
            value["mcp"]["account_last4"] = str(value["mcp"]["account_last4"])[-4:]
        return value


def parse_ui_observation(raw: Mapping[str, Any]) -> UIObservation:
    allowed = {"source_id", "observed_at", "equity", "cash", "buying_power", "human_notes", "digest"}
    if set(raw) - allowed:
        raise ValueError("manual evidence contains unsupported fields")
    supplied = str(raw.get("digest", ""))
    if len(supplied) != 64 or supplied != evidence_digest(raw):
        raise ValueError("manual evidence digest verification failed")
    source_id = str(raw.get("source_id", "")).strip()
    if source_id != "robinhood-ui-manual":
        raise ValueError("manual evidence source_id is invalid")
    _timestamp(raw.get("observed_at"), "manual evidence")
    values = {}
    for name in ("equity", "cash", "buying_power"):
        values[name] = None if raw.get(name) is None else _number(raw[name], f"UI {name}")
    notes = str(raw.get("human_notes", ""))
    if (re.search(r"BEGIN (?:RSA |EC )?PRIVATE KEY|api[_ -]?key|client[_ -]?secret|bearer|token", notes,
                  flags=re.IGNORECASE)
            or re.search(r"\b\d{8,}\b", notes)
            or re.search(r"\b[A-Za-z0-9_-]{24,}\b", notes)):
        raise ValueError("manual human notes contain prohibited credential or account data")
    return UIObservation(source_id, str(raw["observed_at"]), values["equity"], values["cash"],
                         values["buying_power"], notes, supplied)


def build_mcp_evidence(account: Mapping[str, Any], positions: list[Mapping[str, Any]], *,
                       observed_at: str, identity_verified: bool,
                       expected_last4: str = "1131") -> MCPSourceEvidence:
    _timestamp(observed_at, "MCP evidence")
    last4 = str(account.get("account_number_last4", ""))[-4:]
    equity = _number(account.get("equity"), "MCP equity")
    cash = _number(account.get("cash"), "MCP cash")
    buying_power = _number(account.get("buying_power"), "MCP buying_power")
    totals = AccountTotals(
        equity, cash, buying_power,
        _number(account.get("equity_value", 0), "MCP equity_value"),
        _number(account.get("options_value", 0), "MCP options_value"),
        _number(account.get("crypto_value", 0), "MCP crypto_value"),
        _number(account.get("total_value", equity), "MCP total_value"),
    )
    rows: list[PositionEvidence] = []
    for raw in positions:
        if not isinstance(raw, Mapping):
            raise ValueError("MCP position row is invalid")
        symbol = str(raw.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("MCP position symbol is missing")
        asset_type = str(raw.get("asset_type", "equity")).strip().lower()
        if asset_type not in {"equity", "option", "crypto"}:
            raise ValueError("MCP position asset_type is invalid")
        rows.append(PositionEvidence(symbol, _number(raw.get("qty"), "MCP qty"),
                                     _number(raw.get("market_value"), "MCP market_value"),
                                     asset_type))
    if "equity_value" not in account:
        totals = AccountTotals(
            totals.equity, totals.cash, totals.buying_power,
            sum(row.market_value for row in rows if row.asset_type == "equity"),
            sum(row.market_value for row in rows if row.asset_type == "option"),
            sum(row.market_value for row in rows if row.asset_type == "crypto"),
            totals.total_value,
        )
    base = {"source_id": "robinhood-trading-mcp", "observed_at": observed_at,
            "account_last4": last4, "identity_verified": bool(identity_verified),
            "account": asdict(totals), "positions": [asdict(row) for row in rows]}
    verified = bool(identity_verified and last4 == expected_last4)
    base["identity_verified"] = verified
    return MCPSourceEvidence(base["source_id"], observed_at, last4, verified, totals,
                             tuple(rows), evidence_digest(base))


def reconcile_evidence(mcp: MCPSourceEvidence | None, ui: UIObservation | None = None, *,
                       now: datetime | None = None, value_tolerance: float = 1.0,
                       max_age_seconds: int = 900,
                       evidence_blockers: tuple[str, ...] = ()) -> ReconciliationReport:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    blockers: list[str] = list(evidence_blockers)
    conflicts: list[str] = []
    unexplained = None
    try:
        value_tolerance = _number(value_tolerance, "value_tolerance")
        max_age_seconds = int(max_age_seconds)
        if value_tolerance < 0 or max_age_seconds < 0:
            raise ValueError("evidence tolerances must be non-negative")
    except (TypeError, ValueError) as exc:
        blockers.append(str(exc))
        value_tolerance = 0.0
        max_age_seconds = 0
    if mcp is None:
        blockers.append("authenticated MCP account or positions evidence unavailable")
    else:
        try:
            observed = _timestamp(mcp.observed_at, "MCP evidence")
            if abs((current - observed).total_seconds()) > max_age_seconds:
                blockers.append("MCP evidence is stale")
            if evidence_digest({key: value for key, value in asdict(mcp).items() if key != "digest"}) != mcp.digest:
                blockers.append("MCP evidence integrity failed")
        except ValueError as exc:
            blockers.append(str(exc))
        if not mcp.identity_verified or mcp.account_last4 != "1131":
            blockers.append("Agentic account identity is not verified")
        visible_by_type = {
            asset_type: sum(row.market_value for row in mcp.positions
                            if row.asset_type == asset_type)
            for asset_type in ("equity", "option", "crypto")
        }
        classified = {
            "equity": mcp.account.equity_value,
            "option": mcp.account.options_value,
            "crypto": mcp.account.crypto_value,
        }
        for asset_type, broker_value in classified.items():
            if abs(broker_value - visible_by_type[asset_type]) > value_tolerance:
                blockers.append(f"{asset_type} holdings are not fully enumerated")
        visible_value = sum(visible_by_type.values())
        unexplained = mcp.account.total_value - mcp.account.cash - visible_value
        if abs(unexplained) > value_tolerance:
            blockers.append("unexplained non-cash value exceeds tolerance")
    if ui is not None:
        try:
            observed = _timestamp(ui.observed_at, "manual evidence")
            if abs((current - observed).total_seconds()) > max_age_seconds:
                blockers.append("manual UI evidence is stale")
            if evidence_digest({key: value for key, value in asdict(ui).items() if key != "digest"}) != ui.digest:
                blockers.append("manual evidence integrity failed")
        except ValueError as exc:
            blockers.append(str(exc))
        if mcp is not None:
            for name in ("equity", "cash", "buying_power"):
                ui_value = getattr(ui, name)
                if ui_value is not None and abs(ui_value - getattr(mcp.account, name)) > value_tolerance:
                    conflicts.append(f"UI and MCP {name} conflict")
    if conflicts:
        blockers.extend(conflicts)
    if mcp is None:
        verdict = EvidenceVerdict.EVIDENCE_UNAVAILABLE
    elif blockers:
        verdict = EvidenceVerdict.RECONCILIATION_BLOCKED
    else:
        verdict = EvidenceVerdict.RECONCILED
    generated = current.isoformat()
    core = {"report_version": 1, "generated_at": generated,
            "mcp_digest": mcp.digest if mcp else None, "ui_digest": ui.digest if ui else None,
            "unexplained_value": unexplained, "conflicts": conflicts, "blockers": blockers,
            "verdict": verdict.value, "execution_authority": False,
            "trading_armed": False, "trading_ready": False}
    return ReconciliationReport(1, generated, mcp, ui, unexplained, tuple(conflicts),
                                tuple(blockers), verdict, evidence_digest(core))
