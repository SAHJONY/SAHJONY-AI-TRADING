"""SAHJONY CAPITAL LLC — off-council intelligence modules.

* ``intel.top_traders`` — cached top-trader / whale intelligence feed
  (whale alerts + copy signals), refreshed once per cycle from main.py.
* ``intel.onchain`` — keyless Bitcoin on-chain network intelligence
  (fee market, mempool congestion, hashrate/difficulty gauges), refreshed
  once per cycle from main.py.
* ``intel.macro`` — MACRO PULSE: keyless macro backdrop (dollar, 10y yield,
  gold, WTI) with a bounded risk-on/risk-off read, refreshed once per
  cycle from main.py. INTELLIGENCE ONLY.
* ``intel.congress`` — cached congressional trading intelligence feed
  (STOCK Act PTR disclosure activity, report-level), refreshed once per
  cycle from main.py.
* ``intel.workforce`` — the 9-agent advisory-only Intel Workforce that runs
  after the research block each cycle and reports plain-language findings to
  the dashboard.
* ``intel.shadow_learning`` — learn-while-halted: suppressed entry intents are
  recorded as paper decisions to a JSONL ledger and graded against realized
  moves. Measurement only; never emits orders, never touches risk caps.

Everything under this package is advisory-only: it never emits orders, never
changes risk caps, and never touches the live-trading arming chain.
"""
