"""The Intel Workforce — 9-agent advisory-only analyst team.

Runs after the Research Desk's council block each cycle. Every agent emits an
``IntelFinding`` (plain-language, dashboard-ready); the desk is fault-isolated
per agent and never raises. Advisory only: no orders, no risk-cap changes, no
arming-chain contact.
"""
from intel.workforce.agents import (
    ALL_INTEL_AGENTS,
    CopySignalScout,
    ExecutionOptimizer,
    FundingRateIntel,
    IntelAgent,
    IntelFinding,
    MacroAnalyst,
    QuantResearcher,
    RegimeAnalyst,
    RiskOfficer,
    SentimentAnalyst,
    WhaleWatcher,
)
from intel.workforce.desk import IntelDesk

__all__ = [
    "IntelAgent",
    "IntelFinding",
    "IntelDesk",
    "ALL_INTEL_AGENTS",
    "RegimeAnalyst",
    "WhaleWatcher",
    "SentimentAnalyst",
    "MacroAnalyst",
    "RiskOfficer",
    "QuantResearcher",
    "ExecutionOptimizer",
    "CopySignalScout",
]
