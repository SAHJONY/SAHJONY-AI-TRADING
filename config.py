"""Secure configuration ingestion.

Loads a .env file (if present) and exposes a single immutable Config object.
Every risk-relevant value passes through a HARD-CODED ceiling here, so a fat-
fingered .env can never widen the risk envelope beyond what the code allows.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()  # no-op if .env is absent
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

# ── Hard ceilings the operator can NEVER exceed via .env ─────────────────────
HARD_MAX_ALLOCATION_PCT = 0.15        # no single position may risk >15% equity
HARD_MAX_TOTAL_DEPLOYED_PCT = 0.80    # no more than 80% of equity deployed
HARD_MIN_CONVICTION = 0.50            # never trade below 50% council conviction


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return int(default)


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default) or ""
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class Config:
    # credentials
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True

    # universe
    tickers: List[str] = field(default_factory=lambda: ["AAPL", "MSFT", "SPY"])
    benchmark: str = "SPY"

    # risk (post-clamp)
    max_allocation_pct: float = 0.10
    max_total_deployed_pct: float = 0.60
    min_council_conviction: float = 0.55

    # wheel
    wheel_put_otm_pct: float = 0.10
    wheel_call_otm_pct: float = 0.10
    wheel_dte_min: int = 14
    wheel_dte_max: int = 28

    # trailing ladder
    ladder_hard_floor_pct: float = 0.10
    ladder_ratchet_trigger_pct: float = 0.10
    ladder_trail_pct: float = 0.05
    ladder_base_qty: int = 10
    # Reconciliation: the spec's -10% hard stop and the -20%/-30% averaging-in are
    # mutually exclusive regimes. With averaging ON, the -10% stop is replaced by a
    # catastrophic floor below the deepest rung so the ladder can actually fill.
    ladder_enable_averaging: bool = True
    ladder_catastrophic_pct: float = 0.40

    # firm / branding
    firm_name: str = "SAHJONY CAPITAL LLC"
    # public base URL of the deployed dashboard, used to build investor share links
    # (e.g. https://your-app.vercel.app). No trailing slash needed.
    public_base_url: str = ""

    # voice comms (Bland.ai) — owner/investor phone alerts
    voice_alerts: bool = False
    voice_language: str = "en"
    voice_name: str = "june"

    # AI brain & counsellors (advisory overlay on the quant council)
    ai_brain_enabled: bool = False
    anthropic_model: str = "claude-opus-4-8"   # PRIMARY brain (Claude)
    openai_model: str = "gpt-4o"               # counsellor
    xai_model: str = "grok-2-latest"           # counsellor (Grok / xAI)

    # scheduler / ops
    cycle_minutes: int = 15
    log_level: str = "INFO"

    @property
    def has_credentials(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def mode(self) -> str:
        if not self.has_credentials:
            return "offline-sim"
        return "paper" if self.alpaca_paper else "LIVE"


def load_config() -> Config:
    """Build a Config from the environment, clamping all risk knobs to ceilings."""
    return Config(
        alpaca_api_key=os.getenv("ALPACA_API_KEY", "").strip(),
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
        alpaca_paper=_b("ALPACA_PAPER", True),
        tickers=_list("TICKERS", "AAPL,MSFT,SPY"),
        benchmark=(os.getenv("BENCHMARK", "SPY") or "SPY").strip().upper(),
        max_allocation_pct=_clamp(_f("MAX_ALLOCATION_PCT", 0.10), 0.0, HARD_MAX_ALLOCATION_PCT),
        max_total_deployed_pct=_clamp(_f("MAX_TOTAL_DEPLOYED_PCT", 0.60), 0.0, HARD_MAX_TOTAL_DEPLOYED_PCT),
        min_council_conviction=_clamp(_f("MIN_COUNCIL_CONVICTION", 0.55), HARD_MIN_CONVICTION, 1.0),
        wheel_put_otm_pct=_clamp(_f("WHEEL_PUT_OTM_PCT", 0.10), 0.01, 0.40),
        wheel_call_otm_pct=_clamp(_f("WHEEL_CALL_OTM_PCT", 0.10), 0.01, 0.40),
        wheel_dte_min=max(1, _i("WHEEL_DTE_MIN", 14)),
        wheel_dte_max=max(2, _i("WHEEL_DTE_MAX", 28)),
        ladder_hard_floor_pct=_clamp(_f("LADDER_HARD_FLOOR_PCT", 0.10), 0.02, 0.50),
        ladder_ratchet_trigger_pct=_clamp(_f("LADDER_RATCHET_TRIGGER_PCT", 0.10), 0.02, 1.0),
        ladder_trail_pct=_clamp(_f("LADDER_TRAIL_PCT", 0.05), 0.01, 0.50),
        ladder_base_qty=max(1, _i("LADDER_BASE_QTY", 10)),
        ladder_enable_averaging=_b("LADDER_ENABLE_AVERAGING", True),
        ladder_catastrophic_pct=_clamp(_f("LADDER_CATASTROPHIC_PCT", 0.40), 0.15, 0.90),
        firm_name=(os.getenv("FIRM_NAME", "SAHJONY CAPITAL LLC") or "SAHJONY CAPITAL LLC").strip(),
        public_base_url=(os.getenv("PUBLIC_BASE_URL", "") or "").strip().rstrip("/"),
        voice_alerts=_b("VOICE_ALERTS", False),
        voice_language=(os.getenv("VOICE_LANGUAGE", "en") or "en").strip(),
        voice_name=(os.getenv("VOICE_NAME", "june") or "june").strip(),
        ai_brain_enabled=_b("AI_BRAIN_ENABLED", False),
        anthropic_model=(os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8") or "claude-opus-4-8").strip(),
        openai_model=(os.getenv("OPENAI_MODEL", "gpt-4o") or "gpt-4o").strip(),
        xai_model=(os.getenv("XAI_MODEL", "grok-2-latest") or "grok-2-latest").strip(),
        cycle_minutes=max(1, _i("CYCLE_MINUTES", 15)),
        log_level=(os.getenv("LOG_LEVEL", "INFO") or "INFO").strip().upper(),
    )


# module-level singleton for convenience
CONFIG = load_config()
