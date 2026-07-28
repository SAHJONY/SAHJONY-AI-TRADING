"""Signal-funnel instrumentation.

The single most useful diagnostic for this book is not P&L — it is *where the
signals go*. Every strategy in the playbook is a deep conjunction of conditions,
and when a strategy produces 3 trades in 6 months you need to know which gate
ate the other 3,000 before you can decide what to widen.

A strategy routes each of its conditions through `self._g(name, cond)`. Because
`signal()` returns early on the first failure, the counters form a funnel: each
row is "evaluations that reached this gate **and** passed it". The drop between
consecutive rows is the cost of that gate.

Counts are per *evaluation*, not per bar: strategies that test a long branch and
then a short branch increment shared gate names twice on such bars. That is the
right denominator for "how selective is this condition", which is the question
the funnel exists to answer.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Optional


class Funnel:
    def __init__(self, strategy_id: str = ""):
        self.strategy_id = strategy_id
        self.counts: "OrderedDict[str, int]" = OrderedDict()
        self.reached: "OrderedDict[str, int]" = OrderedDict()
        self.signals = 0

    def gate(self, name: str, cond) -> bool:
        cond = bool(cond)
        self.reached[name] = self.reached.get(name, 0) + 1
        self.counts[name] = self.counts.get(name, 0) + (1 if cond else 0)
        return cond

    def emitted(self) -> None:
        self.signals += 1

    def rows(self) -> List[Dict]:
        out = []
        prev: Optional[int] = None
        for name, passed in self.counts.items():
            reached = self.reached[name]
            out.append({
                "gate": name,
                "reached": reached,
                "passed": passed,
                "pass_rate": round(passed / reached, 4) if reached else 0.0,
                # share of everything that reached this gate and died here
                "killed": reached - passed,
            })
            prev = passed
        del prev
        return out

    def report(self) -> str:
        rows = self.rows()
        if not rows:
            return f"{self.strategy_id}: no gates evaluated"
        w = max(len(r["gate"]) for r in rows) + 2
        lines = [f"{self.strategy_id} funnel  ({self.signals} setups emitted)",
                 "  " + "gate".ljust(w) + "reached    passed     pass%    killed"]
        worst = max(rows, key=lambda r: r["killed"])
        for r in rows:
            mark = "  <-- biggest drop" if r is worst and r["killed"] else ""
            lines.append("  " + r["gate"].ljust(w)
                         + f"{r['reached']:<10,}{r['passed']:<10,}"
                         + f"{r['pass_rate'] * 100:>6.2f}%   {r['killed']:<8,}{mark}")
        return "\n".join(lines)
