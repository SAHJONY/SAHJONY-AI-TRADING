"""Institutional operating SLO and stage-readiness assessment."""
from __future__ import annotations

from typing import Any, Mapping


def assess_firm_health(*, mode: str, audit_chain: Mapping[str, Any],
                       reconciliation: Mapping[str, Any], producer_health: Mapping[str, Any],
                       quarantined: list[str], shadow_observations: int,
                       shadow_minimum: int, cost_model_enabled: bool,
                       broker_online: bool, pnl_broker_verified: bool,
                       production_policy_enabled: bool = False) -> dict[str, Any]:
    live = mode == "LIVE"
    producer_alerts = list(producer_health.get("alerts", []))
    producer_critical = any(
        isinstance(item, Mapping) and item.get("severity") == "critical"
        for item in producer_alerts
    )
    controls = {
        "audit_integrity": bool(audit_chain.get("valid")),
        "data_quality": not quarantined,
        "cost_model": bool(cost_model_enabled),
        "evidence_delivery": not producer_critical,
        "broker_connection": bool(broker_online),
        "position_reconciliation": bool(reconciliation.get("reconciled")) if live else None,
        "shadow_coverage": int(shadow_observations) >= int(shadow_minimum),
        "pnl_broker_verified": bool(pnl_broker_verified),
    }
    weights = {"audit_integrity": 20, "data_quality": 20, "cost_model": 15,
               "evidence_delivery": 15, "broker_connection": 10,
               "position_reconciliation": 10, "shadow_coverage": 10}
    score = 0
    for name, weight in weights.items():
        value = controls[name]
        if value is True or (name == "position_reconciliation" and value is None):
            score += weight

    incidents = []
    if not controls["audit_integrity"]:
        incidents.append({"severity": "critical", "code": "audit_chain_invalid"})
    if quarantined:
        incidents.append({"severity": "critical", "code": "market_data_quarantined",
                          "symbols": list(quarantined)})
    if live and not controls["position_reconciliation"]:
        incidents.append({"severity": "critical", "code": "positions_unreconciled"})
    if producer_critical:
        incidents.append({"severity": "critical", "code": "evidence_delivery_unhealthy"})
    if not controls["shadow_coverage"]:
        incidents.append({"severity": "warning", "code": "insufficient_shadow_evidence"})
    if not controls["pnl_broker_verified"]:
        incidents.append({"severity": "warning", "code": "pnl_not_broker_verified"})

    research_ready = controls["audit_integrity"] and controls["data_quality"]
    paper_ready = research_ready and controls["cost_model"] and controls["evidence_delivery"]
    canary_ready = bool(
        paper_ready and controls["shadow_coverage"] and broker_online
        and controls["position_reconciliation"] is True and pnl_broker_verified
    )
    production_ready = bool(canary_ready and production_policy_enabled)
    return {
        "score": score, "controls": controls, "incidents": incidents,
        "stages": {"research_ready": research_ready, "paper_ready": paper_ready,
                   "canary_ready": canary_ready, "production_ready": production_ready},
        "execution_authority": False,
    }
