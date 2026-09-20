"""SAHJONY CAPITAL LLC — autonomous trading desk runtime.

Loads persistent state, runs the agentic workforce for one or more cycles,
persists state + the dashboard snapshot, and prints a health board. Designed to
be driven by cron/launchd at `--once` per tick during market hours; `--cycles N`
walks the offline simulator for a verifiable dry run; `--loop` runs an internal
loop.

Examples:
  python main.py --preflight          # read-only readiness check (no orders)
  python main.py --once               # one cycle (cron entry point)
  python main.py --cycles 12          # dry-run: 12 sim cycles, walks the market
  python main.py --loop               # internal loop every CYCLE_MINUTES
  python main.py --once --force       # trade even if the market clock says closed
"""
from __future__ import annotations

import argparse
import time
from contextlib import contextmanager

from dotenv import load_dotenv
load_dotenv(".env")
from config import HARD_MAX_ALLOCATION_PCT, HARD_MAX_TOTAL_DEPLOYED_PCT, load_config
from database import Database
from utils.broker import get_broker
from utils.logger import get_logger
from utils.state_store import load_state, save_state
from workforce import Firm
from paths import halt_path, status_path
from workforce.reporter import build_status, console_board, write_investor_views, write_status


# ── Segmented latency telemetry (telemetry/latency.py) ───────────────────────
# Advisory/measurement ONLY: wall-clock timing of the desk cycle's named
# segments. Fault-isolated and additive — if telemetry fails, is disabled, or
# the import breaks, everything below degrades to a no-op and the cycle runs
# exactly as before. It never emits orders, never touches credentials, never
# clears the breaker, and never changes the $10/order, 12%, 70%,
# 10%-halt risk envelope.
try:
    from telemetry import latency as _latency_mod
except Exception:  # telemetry must never break the desk at import time
    _latency_mod = None


@contextmanager
def _cycle_telemetry():
    """Wrap one desk cycle in a latency recorder; no-op when unavailable."""
    if _latency_mod is None:
        yield None
    else:
        with _latency_mod.cycle() as rec:
            yield rec


def _seg(name):
    """Time one cycle segment; no-op when telemetry is unavailable."""
    if _latency_mod is None:
        @contextmanager
        def _noop():
            yield None
        return _noop()
    return _latency_mod.segment(name)

log = get_logger("main")


def readiness_states(*, client_online: bool, identity_verified: bool,
                     quote_coverage_complete: bool, market_data_fresh: bool,
                     buying_power: float, equity: float, positions_reconciled: bool,
                     trading_armed: bool, execution_authority: bool) -> dict:
    data_ready = bool(client_online and identity_verified
                      and quote_coverage_complete and market_data_fresh)
    funding_ready = bool(buying_power > 0 and equity > 0)
    trading_ready = bool(data_ready and funding_ready and positions_reconciled
                         and trading_armed and execution_authority)
    return {"data_ready": data_ready, "funding_ready": funding_ready,
            "trading_ready": trading_ready}


def preflight(cfg, client) -> int:
    """Read-only readiness report — places NO orders. Returns 0 when ready.

    Run this before adding funds / arming live: it confirms the broker connects,
    the account is reachable (and funded, for live), market data flows, and shows
    exactly which mode and risk caps are active."""
    mode = getattr(client, "mode", cfg.mode)
    bar = "=" * 64
    print(bar)
    print(f"  SAHJONY PREFLIGHT — broker={cfg.broker} mode={mode}")
    print(bar)

    # connection
    if mode == "offline-sim":
        print(
            f"  • {cfg.broker}: OFFLINE-SIM (no real orders). "
            "Add credentials/connection for paper/live."
        )
        print("  ✗ broker is offline; balances and prices below are simulated.")
    else:
        print(f"  ✓ Connected to {cfg.broker} ({mode}).")

    # account
    acct = client.get_account()
    print(f"  Equity ${acct['equity']:,.2f} | Cash ${acct['cash']:,.2f} | "
          f"Buying power ${acct['buying_power']:,.2f}")

    if acct["equity"] <= 0:
        print("  ✗ TRADING NOT READY — account equity is zero.")

    if acct["buying_power"] <= 0:
        print("  ✗ TRADING NOT READY — buying power is zero.")

    # market clock + data feed
    try:
        print(f"  Market open: {client.is_market_open()}")
    except Exception:
        pass
    quote_failures = []

    for sym in cfg.tickers:
        try:
            px = client.get_price(sym)
            if px and px > 0:
                print(f"  ✓ data {sym}: ${px:,.2f}")
            else:
                print(f"  ✗ data {sym}: no valid price")
                quote_failures.append(sym)
        except Exception as exc:
            print(f"  ✗ data {sym}: unavailable ({type(exc).__name__})")
            log.warning("Preflight quote failed for %s: %s", sym, exc)
            quote_failures.append(sym)

    if quote_failures:
        print(
            "  ✗ Quote coverage incomplete: "
            + ", ".join(quote_failures)
            + ". No trading readiness should be inferred."
        )

    # Broker positions must reconcile with persisted internal state. An empty
    # broker snapshot cannot be accepted when account equity exceeds cash.
    positions_reconciled = False
    reconciliation_reason = "position snapshot unavailable"
    try:
        from observability.reconciliation import reconcile_positions
        internal_positions = (load_state().get("positions") or {})
        broker_positions = client.get_broker_positions()
        reconciliation = reconcile_positions(internal_positions, broker_positions)
        positions_reconciled = bool(reconciliation["reconciled"])
        if not broker_positions and float(acct["equity"]) > float(acct["cash"]) + 0.01:
            positions_reconciled = False
            reconciliation_reason = "equity exceeds cash but broker returned no positions"
        elif not positions_reconciled:
            reconciliation_reason = f"{len(reconciliation.get('differences', []))} difference(s)"
        else:
            reconciliation_reason = "broker and internal positions agree"
    except Exception as exc:
        reconciliation_reason = f"unavailable ({type(exc).__name__})"

    online = bool(getattr(client, "online", False))
    identity_verified = bool(getattr(client, "identity_verified", online))
    trading_armed = bool(getattr(
        client, "trading_armed",
        mode == "paper" or (mode == "LIVE" and cfg.live_trading_ack),
    ))
    execution_authority = bool(getattr(
        client, "execution_authority", mode in {"paper", "LIVE"},
    ))
    readiness = readiness_states(
        client_online=online,
        identity_verified=identity_verified,
        quote_coverage_complete=not quote_failures,
        market_data_fresh=not quote_failures,
        buying_power=float(acct["buying_power"]),
        equity=float(acct["equity"]),
        positions_reconciled=positions_reconciled,
        trading_armed=trading_armed,
        execution_authority=execution_authority,
    )
    print(f"  Position reconciliation: {'PASS' if positions_reconciled else 'INCOMPLETE'}"
          f" — {reconciliation_reason}")
    print(f"  Order authority: {'ENABLED' if execution_authority and trading_armed else 'DISABLED'}")

    # risk envelope
    print(f"  Caps: per-position {cfg.max_allocation_pct:.0%} (hard {HARD_MAX_ALLOCATION_PCT:.0%}) | "
          f"total-deployed {cfg.max_total_deployed_pct:.0%} (hard {HARD_MAX_TOTAL_DEPLOYED_PCT:.0%}) | "
          f"min conviction {cfg.min_council_conviction:.0%}")
    print(f"  Daily circuit breaker: halt new risk if down {cfg.max_daily_drawdown_pct:.0%} in a day")
    import os as _os
    if cfg.trading_halt or _os.path.exists(halt_path()):
        print("  ⛔ KILL SWITCH ACTIVE — new risk is suspended (TRADING_HALT / HALT file).")

    # live arming status
    if mode == "LIVE":
        if cfg.live_trading_ack:
            print("  ⚠ LIVE ARMED (LIVE_TRADING_ACK set) — real orders WILL be placed when you run.")
        else:
            print("  • LIVE venue connected but NOT armed — set LIVE_TRADING_ACK to trade real money.")

    print(bar)
    print(f"  DATA READY {'✓' if readiness['data_ready'] else '✗'} | "
          f"FUNDING READY {'✓' if readiness['funding_ready'] else '✗'} | "
          f"TRADING READY {'✓' if readiness['trading_ready'] else '✗'}")
    print(bar)
    return 0 if readiness["trading_ready"] else 1


def confirm_live(cfg, client) -> bool:
    """Gatekeeper for REAL-MONEY trading. Live orders are refused unless the
    operator has deliberately armed them (keys + ALPACA_PAPER=false + an explicit
    LIVE_TRADING_ACK). Returns False to abort, True to proceed (armed)."""
    if not cfg.live_trading_ack:
        log.error("LIVE venue connected but LIVE_TRADING_ACK is not set.")
        log.error("Refusing to place REAL-MONEY orders.")
        log.error('To deliberately enable live trading, set '
                  'LIVE_TRADING_ACK="I_UNDERSTAND_REAL_MONEY" in your .env —')
        log.error("or connect a paper venue instead.")
        return False
    acct = client.get_account()
    bar = "=" * 64
    print("\n".join([
        bar,
        " ⚠  LIVE REAL-MONEY TRADING ARMED — orders will use real funds",
        bar,
        f"  Broker equity          : ${acct.get('equity', 0):,.2f}",
        f"  Per-position cap        : {cfg.max_allocation_pct:.0%} "
        f"(hard ceiling {HARD_MAX_ALLOCATION_PCT:.0%})",
        f"  Total-deployed cap      : {cfg.max_total_deployed_pct:.0%} "
        f"(hard ceiling {HARD_MAX_TOTAL_DEPLOYED_PCT:.0%})",
        f"  Min conviction to trade : {cfg.min_council_conviction:.0%}",
        "  Ctrl-C within 5s to abort.",
        bar,
    ]))
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        log.info("Live trading aborted by operator.")
        return False
    return True


def _seed_shared_knowledge(firm: Firm, state) -> None:
    """Overwrite this desk's Hermes strategy pool with the shared cross-desk pool
    before the cycle, so its bounded capital weights reflect the COMBINED (paper +
    live) realized outcomes. The pool is canonical (both desks write back after
    adding their own events), so overwriting on load avoids double-counting.
    Fully fault-isolated — a miss just leaves the desk on its own local memory."""
    if not getattr(firm.cfg, "shared_knowledge", False):
        return
    try:
        from intelligence import knowledge
        pool = knowledge.load_strat()
        if pool:
            state.setdefault("hermes", {})["strat"] = pool
            log.info("Shared knowledge: seeded %d strategy record(s) from the pool.", len(pool))
    except Exception as exc:   # never let knowledge sharing break the loop
        log.warning("shared knowledge load skipped: %s", exc)


def _save_shared_knowledge(firm: Firm, state) -> None:
    """Persist the updated strategy pool (this desk's cycle added its realized
    outcomes) back to the shared file for the other desk to read next."""
    if not getattr(firm.cfg, "shared_knowledge", False):
        return
    try:
        from intelligence import knowledge
        mem = state.get("hermes") or {}
        hits = mem.get("hits") or {}
        hit_summary = {s: round(d["h"] / d["n"], 3) for s, d in hits.items()
                       if isinstance(d, dict) and d.get("n", 0) >= 8 and d.get("n")}
        knowledge.save(mem.get("strat") or {}, hit_summary,
                       role=firm.cfg.knowledge_role, cycle=int(state.get("cycle", 0) or 0),
                       ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    except Exception as exc:
        log.warning("shared knowledge save skipped: %s", exc)


def run_once(firm: Firm, state, force: bool) -> dict:
    # Remote kill switch (opt-in via REMOTE_HALT_URL): let a dashboard STOP on any
    # device reach this local desk by toggling the HALT file before we evaluate risk.
    from utils.remote_control import sync_remote_halt
    rc = sync_remote_halt(firm.cfg)
    if rc not in ("disabled", "trading"):
        log.info("remote control: %s", rc)
    with _cycle_telemetry() as _lat_rec:  # one latency cycle; commits on exit, never raises
        market_open = (not firm.client.online) or firm.client.is_market_open()
        trade = market_open or force
        if not trade:
            log.info("Market closed — research/report only (use --force to override).")
        _seed_shared_knowledge(firm, state)
        result = firm.run_cycle(state, trade=trade)
        _save_shared_knowledge(firm, state)
        # BTC options-flow refresh (intel/options_flow.py) — same placement and
        # guarantees as the top-traders feed: AFTER the trading pipeline, never
        # delaying research or execution; cache-first via OPTIONS_FLOW_MAX_AGE_S
        # (the book summary is a 15-min-cache product; the dashboard reads the
        # file, not the network); fault-isolated. Placed BEFORE build_status so
        # status.json carries this cycle's summary. INTELLIGENCE ONLY — the read
        # never emits orders, never changes risk caps, never touches the arming
        # chain; the $10/order, 12%, 70%, 10%-halt envelope is frozen and untouched.
        with _seg("intel_options_flow"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_options_flow_enabled", False):
                try:
                    from intel.options_flow import refresh as of_refresh
                    import os as _os_of
                    _of_path = _os_of.path.join(_os_of.path.dirname(status_path()),
                                                "options_flow.json")
                    _of_max_age = int(_os_of.getenv("OPTIONS_FLOW_MAX_AGE_S", "900") or 900)
                    _of_age = (time.time() - _os_of.path.getmtime(_of_path)
                               if _os_of.path.exists(_of_path) else float("inf"))
                    if _of_age < _of_max_age:
                        log.info("options-flow payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _of_age)
                    else:
                        of_refresh()
                except Exception as exc:
                    log.warning("options-flow refresh skipped: %s", exc)
        # Top-trader intelligence refresh (intel/top_traders.py) — runs AFTER the
        # trading pipeline so it can never delay research or execution. CACHE-FIRST:
        # when public/top_traders.json is younger than TOP_TRADERS_MAX_AGE_S (the
        # payload is a 6h-cache product; the dashboard reads the file, not the
        # network) the cycle skips the ~60s network rebuild entirely and serves the
        # cache — sources must never block the trading desk. Fault-isolated: any
        # failure skips with a warning and the desk keeps the previous payload.
        # Placed BEFORE build_status so status.json carries this cycle's summary.
        with _seg("intel_top_traders"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_top_traders_enabled", False):
                try:
                    from intel.top_traders import refresh as tt_refresh
                    import os as _os
                    _tt_path = _os.path.join(_os.path.dirname(status_path()),
                                             "top_traders.json")
                    _tt_max_age = int(_os.getenv("TOP_TRADERS_MAX_AGE_S", "21600") or 21600)
                    _tt_age = (time.time() - _os.path.getmtime(_tt_path)
                               if _os.path.exists(_tt_path) else float("inf"))
                    if _tt_age < _tt_max_age:
                        log.info("top-traders payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _tt_age)
                    else:
                        tt_refresh()
                except Exception as exc:
                    log.warning("top-traders refresh skipped: %s", exc)
        # News/sentiment intelligence refresh (intel/news.py) — same placement and
        # guarantees as the top-traders feed: AFTER the trading pipeline, never
        # delaying research or execution; cache-first via NEWS_MAX_AGE_S (the
        # payload is a 6h-cache product; the dashboard reads the file, not the
        # network) — sources must never block the trading desk. Fault-isolated.
        # Placed BEFORE build_status so status.json carries this cycle's summary.
        with _seg("intel_news"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_news_enabled", False):
                try:
                    from intel.news import refresh as news_refresh
                    import os as _os3
                    _nw_path = _os3.path.join(_os3.path.dirname(status_path()),
                                              "news_intel.json")
                    _nw_max_age = int(_os3.getenv("NEWS_MAX_AGE_S", "21600") or 21600)
                    _nw_age = (time.time() - _os3.path.getmtime(_nw_path)
                               if _os3.path.exists(_nw_path) else float("inf"))
                    if _nw_age < _nw_max_age:
                        log.info("news-intel payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _nw_age)
                    else:
                        news_refresh()
                except Exception as exc:
                    log.warning("news-intel refresh skipped: %s", exc)
        # On-chain network intelligence refresh (intel/onchain.py) — runs AFTER
        # the trading pipeline so it can never delay research or execution.
        # CACHE-FIRST: when public/onchain_intel.json is younger than
        # ONCHAIN_MAX_AGE_S (default 1h; the payload is a light gauge product and
        # the dashboard reads the file, not the network) the cycle skips the
        # network rebuild and serves the cache — sources must never block the
        # trading desk. Fault-isolated: any failure skips with a warning and the
        # desk keeps the previous payload. Placed BEFORE build_status so
        # status.json carries this cycle's summary. Advisory only: never emits
        # orders, never changes risk caps, never touches the arming chain.
        with _seg("intel_onchain"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_onchain_enabled", False):
                try:
                    from intel.onchain import refresh as oc_refresh
                    import os as _os
                    _oc_path = _os.path.join(_os.path.dirname(status_path()),
                                             "onchain_intel.json")
                    _oc_max_age = int(_os.getenv("ONCHAIN_MAX_AGE_S", "3600") or 3600)
                    _oc_age = (time.time() - _os.path.getmtime(_oc_path)
                               if _os.path.exists(_oc_path) else float("inf"))
                    if _oc_age < _oc_max_age:
                        log.info("on-chain payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _oc_age)
                    else:
                        oc_refresh()
                except Exception as exc:
                    log.warning("on-chain refresh skipped: %s", exc)
        # MACRO PULSE intelligence refresh (intel/macro.py) — same placement and
        # guarantees as the top-traders feed: AFTER the trading pipeline, never
        # delaying research or execution; cache-first via MACRO_MAX_AGE_S (macro
        # moves on a daily cadence; default 6h); fault-isolated. Advisory only.
        # Placed BEFORE build_status so status.json carries this cycle's summary.
        with _seg("intel_macro"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_macro_enabled", False):
                try:
                    from intel.macro import refresh as macro_refresh
                    import os as _os2
                    _mp_path = _os2.path.join(_os2.path.dirname(status_path()),
                                              "macro_pulse.json")
                    _mp_max_age = int(_os2.getenv("MACRO_MAX_AGE_S", "21600") or 21600)
                    _mp_age = (time.time() - _os2.path.getmtime(_mp_path)
                               if _os2.path.exists(_mp_path) else float("inf"))
                    if _mp_age < _mp_max_age:
                        log.info("macro-pulse payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _mp_age)
                    else:
                        macro_refresh()
                except Exception as exc:
                    log.warning("macro-pulse refresh skipped: %s", exc)
        # Congress intelligence refresh (intel/congress.py) — same placement and
        # guarantees as the top-traders feed: AFTER the trading pipeline, never
        # delaying research or execution; cache-first via CONGRESS_MAX_AGE_S
        # (disclosure filings move slowly; default 24h); fault-isolated.
        # Placed BEFORE build_status so status.json carries this cycle's summary.
        with _seg("intel_congress"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            if getattr(firm.cfg, "intel_congress_enabled", False):
                try:
                    from intel.congress import refresh as cg_refresh
                    import os as _os2
                    _cg_path = _os2.path.join(_os2.path.dirname(status_path()),
                                              "congress_trades.json")
                    _cg_max_age = int(_os2.getenv("CONGRESS_MAX_AGE_S", "86400") or 86400)
                    _cg_age = (time.time() - _os2.path.getmtime(_cg_path)
                               if _os2.path.exists(_cg_path) else float("inf"))
                    if _cg_age < _cg_max_age:
                        log.info("congress payload fresh (%.0fs old) — serving cache, "
                                 "skipping network refresh", _cg_age)
                    else:
                        cg_refresh()
                except Exception as exc:
                    log.warning("congress refresh skipped: %s", exc)
        # Council + portfolio diversity diagnostics (intel/diversity.py) — runs
        # AFTER the trading pipeline (the council has deliberated and execution
        # is done), so it can never delay research or execution; fault-isolated.
        # Advisory/measurement ONLY: reports vote crowding (bias–variance–
        # covariance decomposition) and Effective Number of Bets (Meucci); never
        # emits orders, never changes votes/weights/gates, never touches
        # credentials or the $10/order, 12%, 70%, 10%-halt envelope. The Risk
        # Officer may READ result["diversity"] via risk_officer_read(); nothing
        # wires it into any gate. Placed BEFORE build_status so status.json
        # carries this cycle's summary.
        if getattr(firm.cfg, "diversity_enabled", True):
            try:
                from intel import diversity as div_mod
                _div_research = result.get("research") or []
                _div_positions = state.get("positions") or {}
                _div_snaps = {r.get("symbol"): r.get("snap") for r in _div_research}
                div_report = div_mod.diversity_report(
                    state, _div_research, _div_positions,
                    {s: getattr(snap, "closes", []) for s, snap in _div_snaps.items()},
                    {s: float(getattr(snap, "price", 0) or 0) for s, snap in _div_snaps.items()},
                    enabled=True)
                div_report["cycle"] = int(state.get("cycle", 0) or 0)
                result["diversity"] = div_report
                # read-only snapshot for the Risk Officer (measurement only —
                # never fed back into gates by any caller).
                state["_diversity_last"] = div_report
                if div_report.get("flags"):
                    for _f in div_report["flags"]:
                        log.warning("DIVERSITY: %s", _f)
            except Exception as exc:
                log.warning("diversity report skipped: %s", exc)
        # Latency summary for the dashboard: rolling p50/p95/p99 per
        # segment + staleness flag (telemetry/latency.py, advisory only).
        # Attached before reporting so status.json carries this cycle.
        # (The final reporting tail is committed to the store on cycle exit.)
        if _lat_rec is not None:
            result["latency"] = _lat_rec.summary()
        with _seg("reporting"):  # latency telemetry (telemetry/latency.py) — advisory/measurement only; never raises, never alters trading
            status = build_status(firm, firm.cfg, state, result)
            write_status(status, status_path())
            shared = write_investor_views(firm.db, status)  # token-keyed read-only investor snapshots
            if shared:
                log.info("Refreshed %d investor share view(s).", shared)
            alert = firm.notifier.maybe_alert(status)
            if alert:
                log.info("Alert sent: %s", alert)
            # Risk alerts fire even on a silent cycle: a halted or bleeding desk is
            # exactly what the owner must hear about, and the trade alert above stays mute.
            try:
                risk_alert = firm.notifier.maybe_risk_alert(status, state)
                if risk_alert:
                    log.warning("RISK ALERT sent: %s", risk_alert.get("events"))
            except Exception as exc:
                log.error("risk alert failed: %s", exc)
            weekly = firm.notifier.maybe_weekly_summary(status, state)  # self-gates to once/7 days
            if weekly:
                log.info("Weekly performance summary sent to Telegram.")
            save_state(state)   # after weekly so last_weekly_report persists
            print(console_board(status))
        return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SAHJONY CAPITAL LLC trading desk")
    ap.add_argument("--once", action="store_true", help="run a single cycle (default)")
    ap.add_argument("--cycles", type=int, default=0, help="run N cycles (advances the sim each cycle)")
    ap.add_argument("--loop", action="store_true", help="loop every CYCLE_MINUTES")
    ap.add_argument("--force", action="store_true", help="trade even if market clock says closed")
    ap.add_argument("--preflight", action="store_true",
                    help="read-only readiness check (connection/funding/data); places NO orders")
    args = ap.parse_args(argv)

    cfg = load_config()
    log.info("Booting %s — mode=%s, tickers=%s", cfg.firm_name, cfg.mode, ",".join(cfg.tickers))
    db = Database()
    client = get_broker(cfg)
    firm = Firm(cfg, client, db)
    state = load_state()

    if args.preflight:
        rc = preflight(cfg, client)
        db.close()
        return rc

    if getattr(client, "mode", cfg.mode) == "LIVE" and not confirm_live(cfg, client):
        db.close()
        return 2

    try:
        if args.cycles and args.cycles > 0:
            for i in range(args.cycles):
                run_once(firm, state, force=True)
                client.advance_sim(1)  # walk the offline simulator
            return 0
        if args.loop:
            log.info("Entering loop (every %d min). Ctrl-C to stop.", cfg.cycle_minutes)
            while True:
                run_once(firm, state, force=args.force)
                client.advance_sim(1)
                time.sleep(cfg.cycle_minutes * 60)
        run_once(firm, state, force=args.force)  # default: one cycle
        return 0
    except KeyboardInterrupt:
        log.info("Stopped by user.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
