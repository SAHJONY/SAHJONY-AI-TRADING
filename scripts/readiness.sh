#!/usr/bin/env bash
# SAHJONY readiness gate — one command that proves the desk is safe to run.
# Runs the syntax gate, the full test suite (Python + headless UI), regenerates
# the dashboard snapshot, and finishes with a read-only broker preflight.
#   bash scripts/readiness.sh
# Exit code 0 == every gate green. Places NO orders; offline-sim unless you set keys.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
[ -d .venv ] && source .venv/bin/activate || true

fail=0
step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓ %s\033[0m\n' "$1"; }
bad()  { printf '  \033[31m✗ %s\033[0m\n' "$1"; fail=1; }

step "1/5  Syntax gate (py_compile)"
if "$PY" -m py_compile $(git ls-files '*.py'); then ok "all Python compiles"; else bad "py_compile"; fi

step "2/5  Python test suite"
for t in test_dry_run test_circuit_breaker test_multi_market test_broker_factory \
         test_ibkr_adapter test_broker_conformance test_controls test_copy_trading \
         test_model_registry test_treasury; do
  if "$PY" -m "tests.$t" >/tmp/sahjony_$t.log 2>&1; then ok "$t"; else bad "$t  (see /tmp/sahjony_$t.log)"; fi
done

step "3/5  Dashboard UI + login tests (Node)"
if command -v node >/dev/null 2>&1; then
  if node tests/ui_test.js    >/tmp/sahjony_ui.log    2>&1; then ok "ui_test";    else bad "ui_test (see /tmp/sahjony_ui.log)"; fi
  if node tests/login_test.js >/tmp/sahjony_login.log 2>&1; then ok "login_test"; else bad "login_test (see /tmp/sahjony_login.log)"; fi
else
  printf '  (node not installed — skipping browser tests)\n'
fi

step "4/5  Regenerate dashboard snapshot (public/status.json)"
if "$PY" main.py --cycles 8 >/tmp/sahjony_cycles.log 2>&1; then ok "status.json refreshed"; else bad "cycle run (see /tmp/sahjony_cycles.log)"; fi

step "5/5  Broker preflight (read-only — NO orders)"
"$PY" main.py --preflight || bad "preflight did not report READY"

echo
if [ "$fail" -eq 0 ]; then
  printf '\033[1;32m════ READINESS: GREEN ✓  — engine is safe to run ════\033[0m\n'
else
  printf '\033[1;31m════ READINESS: FAILED ✗ — fix the items above ════\033[0m\n'
fi
exit "$fail"
