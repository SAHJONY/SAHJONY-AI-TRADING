#!/usr/bin/env bash
# Inject browser-side API keys into public/config.js at DEPLOY time.
#
# public/config.js is committed with these keys BLANK, because this repository is
# public and a key committed there is a published key. Vercel runs this as its
# buildCommand, so the deployed dashboard gets the keys while git never sees them.
#
# Honest scope: these are browser keys. On a zero-build static site, anything the
# page calls a vendor with is visible to whoever loads the page. This keeps the
# keys out of git history and out of the public repo; it does not make them
# secret. Anything that must actually stay private belongs behind api/.
#
# The Supabase values stay committed on purpose — the anon key is RLS-scoped and
# designed to be public.
#
# Never fails the build: a missing key just leaves that feature dark (the
# dashboard already degrades to GDELT + CoinGecko, which need no key).
set -uo pipefail

# The owner dashboard is intentionally pinned to the canonical UI from
# f51362ff14388547034592a36c14f6ae43b6497b. Live status JSON may change, but
# the production shell must not be replaced or deleted by snapshot publishers.
DASHBOARD="public/index.html"
EXPECTED_DASHBOARD_BLOB="d50b3f9711415d0e1d0a0fc633f2e2cb2552d5f3"
if [ ! -f "$DASHBOARD" ]; then
  echo "dashboard_integrity: $DASHBOARD is missing — refusing deployment"
  exit 1
fi
ACTUAL_DASHBOARD_BLOB="$(git hash-object "$DASHBOARD" 2>/dev/null || true)"
if [ "$ACTUAL_DASHBOARD_BLOB" != "$EXPECTED_DASHBOARD_BLOB" ]; then
  echo "dashboard_integrity: canonical dashboard mismatch — refusing deployment"
  echo "  expected: $EXPECTED_DASHBOARD_BLOB"
  echo "  actual:   ${ACTUAL_DASHBOARD_BLOB:-unavailable}"
  exit 1
fi
echo "dashboard_integrity: canonical f51362f dashboard verified"

CONFIG="public/config.js"
[ -f "$CONFIG" ] || { echo "build_public_config: $CONFIG not found — skipping."; exit 0; }

inject() {
  local name="$1" value="${2:-}"
  if [ -z "$value" ]; then
    echo "  · ${name}: not set — feature stays dark"
    return 0
  fi
  # Reject anything that could break out of the JS string literal.
  case "$value" in
    *\"*|*\\*|*$'\n'*|*$'\r'*)
      echo "  ✗ ${name}: contains quote/backslash/newline — refusing to inject"
      return 0 ;;
  esac
  if VALUE="$value" NAME="$name" python3 - "$CONFIG" <<'PY'
import os, re, sys
path, name, value = sys.argv[1], os.environ["NAME"], os.environ["VALUE"]
src = open(path, encoding="utf-8").read()
pattern = re.compile(r'(\b%s\s*:\s*)"[^"]*"' % re.escape(name))
if not pattern.search(src):
    sys.exit(1)
open(path, "w", encoding="utf-8").write(pattern.sub(lambda m: m.group(1) + '"' + value + '"', src, count=1))
PY
  then
    echo "  ✓ ${name}: injected (${#value} chars)"
  else
    echo "  ✗ ${name}: no matching key in $CONFIG — skipped"
  fi
}

echo "SAHJONY CAPITAL LLC — static owner dashboard, injecting browser config"
inject FINNHUB_API_KEY    "${FINNHUB_API_KEY:-}"
inject MARKETAUX_API_KEY  "${MARKETAUX_API_KEY:-}"
inject CRYPTOPANIC_API_KEY "${CRYPTOPANIC_API_KEY:-}"
echo "build_public_config: done."
exit 0
