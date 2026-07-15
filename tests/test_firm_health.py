from observability.firm_health import assess_firm_health


def base(**changes):
    values = dict(mode="offline-sim", audit_chain={"valid": True},
                  reconciliation={"reconciled": False}, producer_health={"alerts": []},
                  quarantined=[], shadow_observations=200, shadow_minimum=100,
                  cost_model_enabled=True, broker_online=False,
                  pnl_broker_verified=False, production_policy_enabled=False)
    values.update(changes)
    return assess_firm_health(**values)


def test_research_can_be_ready_without_claiming_production():
    result = base()
    assert result["stages"]["research_ready"] is True
    assert result["stages"]["paper_ready"] is True
    assert result["stages"]["canary_ready"] is False
    assert result["stages"]["production_ready"] is False
    assert result["execution_authority"] is False


def test_live_reconciliation_failure_is_critical():
    result = base(mode="LIVE", broker_online=True)
    assert result["controls"]["position_reconciliation"] is False
    assert {x["code"] for x in result["incidents"]} >= {"positions_unreconciled"}
    assert result["stages"]["canary_ready"] is False


def test_invalid_audit_chain_blocks_every_stage():
    result = base(audit_chain={"valid": False})
    assert result["stages"]["research_ready"] is False
    assert result["stages"]["paper_ready"] is False
    assert any(x["severity"] == "critical" for x in result["incidents"])


def test_production_policy_remains_an_independent_gate():
    kwargs = dict(mode="LIVE", broker_online=True, pnl_broker_verified=True,
                  reconciliation={"reconciled": True})
    assert base(**kwargs)["stages"]["production_ready"] is False
    assert base(**kwargs, production_policy_enabled=True)["stages"]["production_ready"] is True
