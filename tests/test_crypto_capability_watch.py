import json

from scripts import crypto_capability_watch as watch


def result(supported, count=0):
    return {"supported": supported, "reason": "available" if supported else "tool_unavailable",
            "position_count": count, "observed_at": "2026-07-24T01:00:00+00:00",
            "probe_ok": True}


def test_first_probe_establishes_baseline_without_notification(tmp_path, capsys):
    state, public = tmp_path / "state.json", tmp_path / "public.json"
    outcome = watch.run_once(state_path=state, public_path=public,
                             probe_fn=lambda: result(False))
    assert outcome["changed"] is False
    assert outcome["reconciliation_rerun"] is False
    assert capsys.readouterr().out == ""
    assert json.loads(public.read_text())["execution_authority"] is False


def test_unchanged_state_does_not_update_operations(tmp_path):
    state, public = tmp_path / "state.json", tmp_path / "public.json"
    watch.run_once(state_path=state, public_path=public, probe_fn=lambda: result(False))
    original = public.read_text()
    watch.run_once(state_path=state, public_path=public, probe_fn=lambda: result(False))
    assert public.read_text() == original


def test_probe_recovery_refreshes_operations_without_transition_notification(tmp_path, capsys):
    state, public = tmp_path / "state.json", tmp_path / "public.json"
    unavailable = {**result(False), "reason": "probe_unavailable", "probe_ok": False}
    watch.run_once(state_path=state, public_path=public, probe_fn=lambda: unavailable)
    outcome = watch.run_once(state_path=state, public_path=public,
                             probe_fn=lambda: result(False))
    assert outcome["changed"] is False
    assert json.loads(public.read_text())["reason"] == "tool_unavailable"
    assert capsys.readouterr().out == ""


def test_transition_to_supported_notifies_and_reruns_reconciliation(tmp_path, capsys):
    state, public = tmp_path / "state.json", tmp_path / "public.json"
    calls = []
    watch.run_once(state_path=state, public_path=public, probe_fn=lambda: result(False))
    outcome = watch.run_once(
        state_path=state, public_path=public, probe_fn=lambda: result(True, 1),
        reconcile_fn=lambda: calls.append("reconciled"),
    )
    assert outcome["changed"] is True
    assert outcome["reconciliation_rerun"] is True
    assert calls == ["reconciled"]
    assert "crypto_capability_transition" in capsys.readouterr().out
    projection = json.loads(public.read_text())
    assert projection["supported"] is True
    assert projection["trading_ready"] is False


def test_transition_without_rows_stays_fail_closed(tmp_path):
    state, public = tmp_path / "state.json", tmp_path / "public.json"
    calls = []
    watch.run_once(state_path=state, public_path=public, probe_fn=lambda: result(False))
    outcome = watch.run_once(
        state_path=state, public_path=public, probe_fn=lambda: result(True, 0),
        reconcile_fn=lambda: calls.append("unexpected"),
    )
    assert outcome["changed"] is True
    assert outcome["reconciliation_rerun"] is False
    assert calls == []
