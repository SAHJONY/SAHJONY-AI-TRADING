"""Autonomous-profit guard tests (upgrade/autonomous-profit).

Small but load-bearing guarantees:
- auto_update_models defaults OFF (models pinned; unreviewed drift is a loss).
- Risk pages fire for halt-flatten events and de-duplicate per reason per day.
- maybe_risk_alert is a no-op when no channel is configured.
- Firm._maybe_notify actually invokes the notifier at cycle end.
"""
from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace

from config import load_config
from database.db import Database
from utils.notify import Notifier
from workforce.workforce import Firm


def _cfg(**over):
    base = load_config()
    return replace(base, **over)


def test_models_pinned_by_default(monkeypatch):
    monkeypatch.delenv("AUTO_UPDATE_MODELS", raising=False)
    cfg = load_config()
    assert cfg.auto_update_models is False, \
        "models must stay pinned until the owner explicitly opts in"
    print("✓ auto_update_models defaults to False")


def test_models_opt_in_via_env(monkeypatch):
    monkeypatch.setenv("AUTO_UPDATE_MODELS", "true")
    assert load_config().auto_update_models is True
    print("✓ AUTO_UPDATE_MODELS=true still opts in")


def _notifier_with_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    return Notifier(_cfg())


def test_risk_alert_fires_on_flatten_events(monkeypatch):
    n = _notifier_with_telegram(monkeypatch)
    sent = []
    monkeypatch.setattr(n, "telegram_send", lambda m: sent.append(m) or {"ok": True})
    status = {"cycle": 7, "account": {"equity": 90000.0}, "pnl": {},
              "health": {"broker_online": True, "circuit_breaker": {"halted": False},
                         "hermes": {}},
              "extra_risk_events": [("flatten", "🔻 HALT FLATTEN — kill switch")] }
    state = {}
    result = n.maybe_risk_alert(status, state)
    assert result is not None and "flatten" in result["events"]
    assert "HALT FLATTEN" in sent[0]
    print("✓ flatten events page the owner")


def test_risk_alert_dedups_per_day(monkeypatch):
    n = _notifier_with_telegram(monkeypatch)
    sent = []
    monkeypatch.setattr(n, "telegram_send", lambda m: sent.append(m) or {"ok": True})
    status = {"cycle": 7, "account": {"equity": 90000.0}, "pnl": {},
              "health": {"broker_online": True, "circuit_breaker": {"halted": False},
                         "hermes": {}},
              "extra_risk_events": [("flatten", "🔻 HALT FLATTEN — kill switch")]}
    state = {}
    first = n.maybe_risk_alert(status, state)
    second = n.maybe_risk_alert(status, state)
    assert first is not None and second is None, "one page per reason per day"
    assert len(sent) == 1
    print("✓ risk pages de-duplicate per reason per day")


def test_risk_alert_silent_without_channel(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    n = Notifier(_cfg())
    status = {"cycle": 1, "account": {"equity": 1.0}, "pnl": {},
              "health": {"broker_online": False, "circuit_breaker": {"halted": True,
                                                                      "reason": "x"}},
              "extra_risk_events": [("flatten", "msg")]}
    assert n.maybe_risk_alert(status, {}) is None
    print("✓ silent with no channel configured")


class FakeBroker:
    mode = "offline-sim"


def test_firm_maybe_notify_invokes_notifier(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    firm = Firm(_cfg(voice_alerts=True), FakeBroker(), Database(str(tmp_path / "nt.db")))
    calls = []
    fake = SimpleNamespace(
        telegram_configured=True, whatsapp_configured=False, configured=False,
        maybe_risk_alert=lambda status, state: calls.append(("risk", status)) or None,
        maybe_alert=lambda status: calls.append(("alert", status)) or None,
    )
    firm.notifier = fake
    state = {"cycle_risk_events": []}
    firm._maybe_notify(state, 3,
                       {"halted": False, "reason": ""},
                       {"broker_online": True}, {"hermes": {}},
                       SimpleNamespace(posture="neutral", conviction=0.5,
                                       conviction_breakdown={}),
                       [], 100_000.0)
    kinds = [k for k, _ in calls]
    assert "risk" in kinds and "alert" in kinds, \
        "cycle end must consult the notifier for risk and routine alerts"
    risk_status = [s for k, s in calls if k == "risk"][0]
    assert risk_status["cycle"] == 3 and "account" in risk_status
    print("✓ Firm._maybe_notify consults the notifier at cycle end")


if __name__ == "__main__":
    raise SystemExit("run under pytest")
