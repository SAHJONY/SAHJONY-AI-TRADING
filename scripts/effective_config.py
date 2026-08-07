"""Which repository Variables are actually steering the desk, and which are dead?

**The failure this makes visible.** Four times now a stale repository Variable has
silently beaten a corrected default in `desk.yml`, and each time it was found by
accident, from a symptom, days or weeks later:

  ANTHROPIC_MODEL         set to the refusal fallback — the desk never once ran
                          the model it was documented to run.
  CYCLE_MINUTES           set to 15 against a '5' default — the evaluation window
                          starved for trades and the bar recorder logged 98.9%
                          single-tick bars, both of which the '5' was meant to fix.
  MIN_COUNCIL_CONVICTION  the floor the live desk actually traded on.
  TICKERS_LIVE            the live universe itself.

Nothing about a stale Variable looks wrong. The workflow resolves it, the job is
green, the desk runs — it just runs something other than what the file says.

Each of those four was fixed by renaming the knob to `*_OVERRIDE`, which means
the old Variables are still sitting in repository settings doing nothing at all.
That is its own trap: someone edits `CYCLE_MINUTES` expecting the desk to
change, and nothing happens.

So this prints, every run:
  RETIRED  — set, but no longer read by anything. Delete them.
  ACTIVE   — set, and overriding a default. Confirm each is deliberate.

**Secret-safe by construction.** It reads a curated allowlist of non-sensitive
risk and behaviour knobs — numbers, booleans, symbol lists, model ids. Variables
that can carry personal data (WHATSAPP_TO, COPY_TRADING_SOURCE_URL, HERMES_GOAL)
are deliberately absent: repository Variables are not secrets, this repository is
public, and Actions logs on a public repository are world-readable. Same rule
`public/status.json` follows — names and set/missing booleans, never payloads.

Read-only. Never fails a build.
"""
from __future__ import annotations

import json
import os
import sys

# Renamed to *_OVERRIDE. If any of these is still set it is inert, and its
# presence is actively misleading.
RETIRED = {
    "CYCLE_MINUTES": "CYCLE_MINUTES_OVERRIDE",
    "MIN_COUNCIL_CONVICTION": "MIN_COUNCIL_CONVICTION_OVERRIDE",
    "TICKERS_LIVE": "TICKERS_LIVE_OVERRIDE",
    "ANTHROPIC_MODEL": "ANTHROPIC_MODEL_OVERRIDE",
}

# Still read. Setting one is legitimate — BROKER selects the live venue and
# TRADING_HALT is the kill switch — but each should be a decision someone
# remembers making.
ACTIVE_DEFAULTS = {
    "BROKER": "alpaca",
    "TRADING_HALT": "false",
    "ROBINHOOD_LIVE": "false",
    "ROBINHOOD_MAX_ORDER_USD": "10",
    "ALPACA_LIVE_ENABLED": "(unset)",
    "MAX_ALLOCATION_PCT": "0.12",
    "MAX_TOTAL_DEPLOYED_PCT": "0.70",
    "MAX_DAILY_DRAWDOWN_PCT": "0.10",
    "VOL_TARGET_ANNUAL": "0.20",
    "LIVE_TRADING_CAPITAL": "0",
    "MARKET_HOURS": "24_7",
    "PAPER_TRAINER_ENABLED": "(unset)",
    "STOCK_DESK_ENABLED": "(unset — defaults on)",
    "ROBINHOOD_DESK_ENABLED": "(unset — defaults on)",
    "CYCLE_MINUTES_OVERRIDE": "5",
    "MIN_COUNCIL_CONVICTION_OVERRIDE": "0.51",
    "TICKERS_LIVE_OVERRIDE": "13 crypto names",
    "ANTHROPIC_MODEL_OVERRIDE": "claude-fable-5",
}


def main(argv=None) -> int:
    raw = os.getenv("DESK_VARS_JSON", "").strip()
    if not raw:
        print("effective-config: DESK_VARS_JSON not provided — skipping.")
        return 0
    try:
        variables = json.loads(raw)
    except ValueError as exc:
        print(f"effective-config: DESK_VARS_JSON is not valid JSON ({exc}) — skipping.")
        return 0
    if not isinstance(variables, dict):
        print("effective-config: DESK_VARS_JSON is not an object — skipping.")
        return 0

    def is_set(name):
        return str(variables.get(name, "") or "").strip() != ""

    print("=" * 70)
    print("  EFFECTIVE CONFIG — repository Variables vs desk.yml defaults")
    print("=" * 70)

    dead = [(old, new) for old, new in RETIRED.items() if is_set(old)]
    if dead:
        print(f"\n  RETIRED — set but NO LONGER READ ({len(dead)}). Safe to delete;")
        print("  leaving them means editing one changes nothing:")
        for old, new in dead:
            print(f"    ! {old:32} superseded by {new}")
    else:
        print("\n  RETIRED — none of the four renamed Variables is still set. Clean.")

    live = [n for n in ACTIVE_DEFAULTS if is_set(n)]
    if live:
        print(f"\n  ACTIVE — overriding a default ({len(live)}). Each should be deliberate:")
        for name in live:
            print(f"    · {name:32} set (default: {ACTIVE_DEFAULTS[name]})")
    else:
        print("\n  ACTIVE — no risk knob is overridden; the desk runs desk.yml's defaults.")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
