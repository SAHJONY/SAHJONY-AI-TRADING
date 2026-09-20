"""SAHJONY CAPITAL LLC — off-council intelligence modules.

* ``intel.top_traders`` — cached top-trader / whale intelligence feed
  (whale alerts + copy signals), refreshed once per cycle from main.py.
* ``intel.congress`` — cached congressional trading intelligence feed
  (STOCK Act PTR disclosure activity, report-level), refreshed once per
  cycle from main.py.
* ``intel.workforce`` — the 9-agent advisory-only Intel Workforce that runs
  after the research block each cycle and reports plain-language findings to
  the dashboard.

Everything under this package is advisory-only: it never emits orders, never
changes risk caps, and never touches the live-trading arming chain.
"""
