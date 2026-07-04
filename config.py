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
HARD_MAX_DAILY_DRAWDOWN_PCT = 0.25    # daily-loss circuit breaker can be no looser than 25%


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
    # broker venue (see utils/broker.py). Default 'alpaca'.
    broker: str = "alpaca"
    # credentials
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    # Interactive Brokers (BROKER=ibkr) — connects to a running TWS / IB Gateway.
    # Paper ports: TWS 7497, Gateway 4002.  Live ports: TWS 7496, Gateway 4001.
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1
    ibkr_account: str = ""
    # CCXT (BROKER=ccxt) — worldwide crypto exchanges (Binance, Kraken, …).
    ccxt_exchange: str = "binance"
    ccxt_api_key: str = ""
    ccxt_secret: str = ""
    ccxt_password: str = ""        # some exchanges require an API passphrase
    ccxt_sandbox: bool = True      # testnet/paper by default
    ccxt_quote: str = "USDT"       # quote currency for equity valuation
    # Real-money safety: live orders are refused unless this is explicitly set.
    # Set LIVE_TRADING_ACK="I_UNDERSTAND_REAL_MONEY" to arm live (with ALPACA_PAPER=false).
    live_trading_ack: bool = False

    # universe
    tickers: List[str] = field(default_factory=lambda: ["AAPL", "MSFT", "SPY"])
    benchmark: str = "SPY"
    # 'us' = US cash-session hours; '24_7' = always open (crypto). Auto-detects
    # 24/7 when every ticker is a crypto pair (contains '/', e.g. BTC/USD).
    market_hours: str = "us"

    # risk (post-clamp)
    max_allocation_pct: float = 0.10
    max_total_deployed_pct: float = 0.60
    min_council_conviction: float = 0.55
    # Circuit breaker: halt NEW risk for the rest of the day if equity falls this
    # far below the day's opening equity. Exits/risk-reducing orders still flow.
    max_daily_drawdown_pct: float = 0.06
    # Kill switch: hard-stop all new risk regardless of P&L (env or a HALT file).
    trading_halt: bool = False
    # Volatility targeting: when realized portfolio vol (annualized, from the
    # equity curve) exceeds this, new-position budgets scale down proportionally
    # (never below ×0.5, never above ×1.0 — it de-risks, never levers up).
    # 0 disables. Hard ceilings still apply on top.
    vol_target_annual: float = 0.20
    # Virtual capital cap: trade as if the account were this many dollars, even when
    # the broker balance is larger (e.g. keep $100k paper but only risk $500). 0 =
    # use the full broker equity. All sizing/risk and the equity curve scale to this.
    trading_capital: float = 0.0
    # Dollar-based (fractional) equity orders — lets a small account buy a slice of
    # an expensive stock instead of rounding to 0 shares. Crypto is always fractional.
    allow_fractional: bool = True

    # wheel
    wheel_put_otm_pct: float = 0.10
    wheel_call_otm_pct: float = 0.10
    wheel_dte_min: int = 14
    wheel_dte_max: int = 28

    # credit spreads (defined-risk options desk — bull put spreads)
    credit_spreads_enabled: bool = True
    spread_short_otm_pct: float = 0.05   # short put this far below spot
    spread_width_pct: float = 0.05       # long (hedge) put this much further down

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

    # copy trading (mirror an external disclosure/signal feed)
    copy_trading_enabled: bool = False
    copy_trading_source_url: str = ""
    copy_trading_api_key: str = ""
    copy_trading_max_symbols: int = 10

    # pairs / statistical arbitrage (market-neutral desk)
    pairs_enabled: bool = True
    pairs: List[str] = field(default_factory=lambda: ["SPY:QQQ", "GLD:SLV"])
    pairs_entry_z: float = 2.0
    pairs_exit_z: float = 0.5
    pairs_stop_z: float = 4.0
    pairs_max_hold: int = 96      # cycles (~4 trading days at 15-min cadence)

    # day-trading / forex (intraday desk — never holds overnight)
    day_trading_enabled: bool = True
    forex_pairs: List[str] = field(default_factory=lambda: ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"])
    day_trade_symbols: List[str] = field(default_factory=list)   # extra intraday symbols (keep disjoint from tickers)
    day_trade_target_pct: float = 0.015
    day_trade_stop_pct: float = 0.01
    day_trade_max_units: int = 100
    day_trade_min_signal: float = 0.55

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
    # These are FALLBACK defaults. With auto_update_models on (default), the brain
    # autonomously resolves each provider's latest model at run time (latest Fable
    # for Claude, latest flagship GPT / Grok for the counsellors) and only falls
    # back to these IDs when the lookup can't run (no key / offline / API error).
    anthropic_model: str = "claude-fable-5"    # PRIMARY brain (Claude Fable 5)
    openai_model: str = "gpt-4o"               # counsellor (OpenAI / GPT)
    xai_model: str = "grok-4"                  # counsellor (Grok / xAI); grok-2 retired
    gemini_model: str = "gemini-2.5-pro"       # counsellor (Gemini / Google)
    # Autonomously keep every provider on its newest model (owner directive).
    auto_update_models: bool = True

    # scheduler / ops
    cycle_minutes: int = 15
    log_level: str = "INFO"

    @property
    def has_credentials(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def always_on(self) -> bool:
        """True for a 24/7 desk: explicit MARKET_HOURS=24_7, or an all-crypto universe."""
        if self.market_hours == "24_7":
            return True
        return bool(self.tickers) and all("/" in t for t in self.tickers)

    @property
    def mode(self) -> str:
        if not self.has_credentials:
            return "offline-sim"
        return "paper" if self.alpaca_paper else "LIVE"


def load_config() -> Config:
    """Build a Config from the environment, clamping all risk knobs to ceilings."""
    return Config(
        broker=(os.getenv("BROKER", "alpaca") or "alpaca").strip().lower(),
        alpaca_api_key=os.getenv("ALPACA_API_KEY", "").strip(),
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
        alpaca_paper=_b("ALPACA_PAPER", True),
        ibkr_host=(os.getenv("IBKR_HOST", "127.0.0.1") or "127.0.0.1").strip(),
        ibkr_port=_i("IBKR_PORT", 7497),
        ibkr_client_id=_i("IBKR_CLIENT_ID", 1),
        ibkr_account=(os.getenv("IBKR_ACCOUNT", "") or "").strip(),
        ccxt_exchange=(os.getenv("CCXT_EXCHANGE", "binance") or "binance").strip().lower(),
        ccxt_api_key=os.getenv("CCXT_API_KEY", "").strip(),
        ccxt_secret=os.getenv("CCXT_SECRET", "").strip(),
        ccxt_password=os.getenv("CCXT_PASSWORD", "").strip(),
        ccxt_sandbox=_b("CCXT_SANDBOX", True),
        ccxt_quote=(os.getenv("CCXT_QUOTE", "USDT") or "USDT").strip().upper(),
        live_trading_ack=(os.getenv("LIVE_TRADING_ACK", "").strip() == "I_UNDERSTAND_REAL_MONEY"),
        tickers=_list("TICKERS", "AAPL,MSFT,SPY"),
        benchmark=(os.getenv("BENCHMARK", "SPY") or "SPY").strip().upper(),
        market_hours=(os.getenv("MARKET_HOURS", "us") or "us").strip().lower(),
        max_allocation_pct=_clamp(_f("MAX_ALLOCATION_PCT", 0.10), 0.0, HARD_MAX_ALLOCATION_PCT),
        max_total_deployed_pct=_clamp(_f("MAX_TOTAL_DEPLOYED_PCT", 0.60), 0.0, HARD_MAX_TOTAL_DEPLOYED_PCT),
        min_council_conviction=_clamp(_f("MIN_COUNCIL_CONVICTION", 0.55), HARD_MIN_CONVICTION, 1.0),
        max_daily_drawdown_pct=_clamp(_f("MAX_DAILY_DRAWDOWN_PCT", 0.06), 0.01, HARD_MAX_DAILY_DRAWDOWN_PCT),
        trading_halt=_b("TRADING_HALT", False),
        vol_target_annual=_clamp(_f("VOL_TARGET_ANNUAL", 0.20), 0.0, 2.0),
        trading_capital=max(0.0, _f("TRADING_CAPITAL", 0.0)),
        allow_fractional=_b("ALLOW_FRACTIONAL", True),
        wheel_put_otm_pct=_clamp(_f("WHEEL_PUT_OTM_PCT", 0.10), 0.01, 0.40),
        wheel_call_otm_pct=_clamp(_f("WHEEL_CALL_OTM_PCT", 0.10), 0.01, 0.40),
        wheel_dte_min=max(1, _i("WHEEL_DTE_MIN", 14)),
        wheel_dte_max=max(2, _i("WHEEL_DTE_MAX", 28)),
        credit_spreads_enabled=_b("CREDIT_SPREADS_ENABLED", True),
        spread_short_otm_pct=_clamp(_f("SPREAD_SHORT_OTM_PCT", 0.05), 0.02, 0.20),
        spread_width_pct=_clamp(_f("SPREAD_WIDTH_PCT", 0.05), 0.02, 0.20),
        ladder_hard_floor_pct=_clamp(_f("LADDER_HARD_FLOOR_PCT", 0.10), 0.02, 0.50),
        ladder_ratchet_trigger_pct=_clamp(_f("LADDER_RATCHET_TRIGGER_PCT", 0.10), 0.02, 1.0),
        ladder_trail_pct=_clamp(_f("LADDER_TRAIL_PCT", 0.05), 0.01, 0.50),
        ladder_base_qty=max(1, _i("LADDER_BASE_QTY", 10)),
        ladder_enable_averaging=_b("LADDER_ENABLE_AVERAGING", True),
        ladder_catastrophic_pct=_clamp(_f("LADDER_CATASTROPHIC_PCT", 0.40), 0.15, 0.90),
        copy_trading_enabled=_b("COPY_TRADING_ENABLED", False),
        copy_trading_source_url=(os.getenv("COPY_TRADING_SOURCE_URL", "") or "").strip(),
        copy_trading_api_key=os.getenv("COPY_TRADING_API_KEY", "").strip(),
        copy_trading_max_symbols=max(1, _i("COPY_TRADING_MAX_SYMBOLS", 10)),
        pairs_enabled=_b("PAIRS_ENABLED", True),
        pairs=_list("PAIRS", "SPY:QQQ,GLD:SLV"),
        pairs_entry_z=_clamp(_f("PAIRS_ENTRY_Z", 2.0), 1.0, 5.0),
        pairs_exit_z=_clamp(_f("PAIRS_EXIT_Z", 0.5), 0.1, 2.0),
        pairs_stop_z=_clamp(_f("PAIRS_STOP_Z", 4.0), 2.0, 8.0),
        pairs_max_hold=max(4, _i("PAIRS_MAX_HOLD", 96)),
        day_trading_enabled=_b("DAY_TRADING_ENABLED", True),
        forex_pairs=_list("FOREX_PAIRS", "EUR/USD,GBP/USD,USD/JPY,AUD/USD"),
        day_trade_symbols=_list("DAY_TRADE_SYMBOLS", ""),
        day_trade_target_pct=_clamp(_f("DAY_TRADE_TARGET_PCT", 0.015), 0.002, 0.10),
        day_trade_stop_pct=_clamp(_f("DAY_TRADE_STOP_PCT", 0.01), 0.002, 0.10),
        day_trade_max_units=max(1, _i("DAY_TRADE_MAX_UNITS", 100)),
        day_trade_min_signal=_clamp(_f("DAY_TRADE_MIN_SIGNAL", 0.55), 0.50, 0.95),
        firm_name=(os.getenv("FIRM_NAME", "SAHJONY CAPITAL LLC") or "SAHJONY CAPITAL LLC").strip(),
        public_base_url=(os.getenv("PUBLIC_BASE_URL", "") or "").strip().rstrip("/"),
        voice_alerts=_b("VOICE_ALERTS", False),
        voice_language=(os.getenv("VOICE_LANGUAGE", "en") or "en").strip(),
        voice_name=(os.getenv("VOICE_NAME", "june") or "june").strip(),
        ai_brain_enabled=_b("AI_BRAIN_ENABLED", False),
        anthropic_model=(os.getenv("ANTHROPIC_MODEL", "claude-fable-5") or "claude-fable-5").strip(),
        openai_model=(os.getenv("OPENAI_MODEL", "gpt-4o") or "gpt-4o").strip(),
        xai_model=(os.getenv("XAI_MODEL", "grok-4") or "grok-4").strip(),
        gemini_model=(os.getenv("GEMINI_MODEL", "gemini-2.5-pro") or "gemini-2.5-pro").strip(),
        auto_update_models=_b("AUTO_UPDATE_MODELS", True),
        cycle_minutes=max(1, _i("CYCLE_MINUTES", 15)),
        log_level=(os.getenv("LOG_LEVEL", "INFO") or "INFO").strip().upper(),
    )


# module-level singleton for convenience
CONFIG = load_config()
