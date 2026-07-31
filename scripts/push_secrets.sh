#!/usr/bin/env bash
# Push desk configuration from a LOCAL .env into GitHub Actions, so the scheduled
# paper desk (.github/workflows/desk.yml) can run. Values are read from your
# gitignored .env and sent straight to GitHub via `gh` — they never leave your
# machine and are never printed.
#
#   Usage:  gh auth login          # once
#           scripts/push_secrets.sh [path-to-.env]   # defaults to ./.env
#
# API keys become encrypted SECRETS; non-sensitive knobs become repo VARIABLES
# (readable in Settings, matching how desk.yml reads `vars.*`).
#
# SAFETY: real-money arming flags (LIVE_TRADING_ACK, ROBINHOOD_LIVE, ALPACA_PAPER,
# and the Robinhood keys) are DELIBERATELY refused here — the CI desk is paper-only
# by design. Arm live only on the host you control, never from CI. See GO_LIVE.md.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || { echo "✗ $ENV_FILE not found. Copy .env.template → .env and fill it in."; exit 1; }
command -v gh >/dev/null || { echo "✗ GitHub CLI (gh) not found — https://cli.github.com/"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "✗ Run 'gh auth login' first."; exit 1; }

# Encrypted secrets (sensitive).
SECRETS="ALPACA_API_KEY ALPACA_SECRET_KEY ANTHROPIC_API_KEY OPENAI_API_KEY \
XAI_API_KEY GEMINI_API_KEY NVIDIA_API_KEY VOICE_API_KEY VOICE_FROM_NUMBER \
OWNER_PHONE VERCEL_DEPLOY_HOOK"

# Plain repo variables (non-sensitive knobs desk.yml reads via vars.*).
VARIABLES="TICKERS BENCHMARK MARKET_HOURS CYCLE_MINUTES LOG_LEVEL \
ANTHROPIC_MODEL OPENAI_MODEL XAI_MODEL GEMINI_MODEL NVIDIA_MODEL \
AI_BRAIN_ENABLED AUTO_UPDATE_MODELS MAX_ALLOCATION_PCT MAX_TOTAL_DEPLOYED_PCT \
MIN_COUNCIL_CONVICTION MAX_DAILY_DRAWDOWN_PCT DAY_TRADING_ENABLED FOREX_PAIRS \
DAY_TRADE_SYMBOLS DAY_TRADE_TARGET_PCT DAY_TRADE_STOP_PCT BROKER"

# NEVER push these to CI — real-money arming stays on your own host only.
BLOCKED="LIVE_TRADING_ACK ROBINHOOD_LIVE ALPACA_PAPER ROBINHOOD_API_KEY ROBINHOOD_PRIVATE_KEY"

_get() { # read KEY from the .env without sourcing it (avoids executing the file)
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" | tail -n1 \
    | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/";
}
_contains() { case " $2 " in *" $1 "*) return 0;; *) return 1;; esac; }

pushed=0; skipped=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue;; esac
  key="${line%%=*}"; key="$(echo "$key" | tr -d '[:space:]')"
  [ -n "$key" ] || continue
  val="$(_get "$key")"
  if _contains "$key" "$BLOCKED"; then
    echo "⛔ $key — refused (real-money/CI safety; set it only on your host)"; skipped=$((skipped+1)); continue
  fi
  [ -n "$val" ] || { skipped=$((skipped+1)); continue; }
  if _contains "$key" "$SECRETS"; then
    gh secret set "$key" --body "$val" >/dev/null && echo "🔒 secret   $key" && pushed=$((pushed+1))
  elif _contains "$key" "$VARIABLES"; then
    gh variable set "$key" --body "$val" >/dev/null && echo "•  variable $key" && pushed=$((pushed+1))
  else
    echo "?  $key — unknown key, skipped (add it to SECRETS/VARIABLES if intended)"; skipped=$((skipped+1))
  fi
done < "$ENV_FILE"

echo "── pushed $pushed, skipped $skipped. Verify: Settings → Secrets and variables → Actions."
echo "   Vercel only needs Supabase keys (if you use login) — not broker/LLM keys."
