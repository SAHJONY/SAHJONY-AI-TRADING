"""Paper-trading runner: lab signal strategies -> Alpaca PAPER.

What this is
-----------
A slow, signal-based poller (default: one decision per 60 seconds) that
feeds recent Alpaca minute bars into
:class:`hft.strategies.MultiLevelFlowStrategy`, routes every resulting
order intent through the v2 :class:`hft.risk.RiskGateway` first, and then
either logs it (dry-run, the default) or submits it to
:class:`hft.venue.AlpacaPaperVenue`. Every intent, risk decision,
submission, error, and account snapshot goes to the JSONL audit log.

What this is NOT
---------------
* **Not HFT.** Alpaca paper allows roughly 200 requests/minute and
  exposes no L2 feed, so this is a signal poller, not a quoting loop.
  Microsecond-scale strategies cannot run here.
* **Not a validated strategy.** The signal is the lab's research
  plumbing (demonstration only); nothing here claims an edge or
  profitability.
* **Not real trading.** Alpaca paper fills are simulated by Alpaca,
  not real executions. The adapter cannot place live orders: the live
  endpoint is refused at construction and asserted again at request
  time.
* **Read-only by default.** ``--mode account`` (the default) only
  fetches account info and places no orders. In ``--mode trade``,
  dry-run is on unless explicitly disabled.

Credentials
-----------
Paper API key id / secret are read from the environment ONLY
(``APCA_API_KEY_ID`` / ``APCA_API_SECRET_KEY``). Missing keys abort
before any network activity. Keys are never printed, logged, or
embedded in error messages, the audit log, or exceptions.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .book import BUY, SELL
from .matching import IncomingOrder
from .risk import RiskGateway, RiskLimits
from .strategies import NEW, MarketSnapshot, MultiLevelFlowStrategy, OrderIntent
from .venue import PAPER_BASE_URL, AlpacaPaperVenue

DATA_BASE_URL = "https://data.alpaca.markets"

# Cent ticks: the AlpacaPaperVenue adapter prices limit orders as
# ``price_ticks * 0.01`` dollars, so the runner works in cent ticks.
TICK = 0.01

ENV_KEY_ID = "APCA_API_KEY_ID"
ENV_SECRET = "APCA_API_SECRET_KEY"


class PaperRunnerError(Exception):
    """Fail-closed runner error. Never carries credential values."""


# ----------------------------------------------------------------------
# credentials + paper-only guards
# ----------------------------------------------------------------------
def _read_keys(env: Optional[Dict[str, str]] = None) -> tuple:
    """Read paper API keys from the environment only.

    Raises :class:`PaperRunnerError` naming the missing variable (never
    the value) when either is absent or empty.
    """
    src = env if env is not None else os.environ
    key_id = (src.get(ENV_KEY_ID) or "").strip()
    secret = (src.get(ENV_SECRET) or "").strip()
    missing = [name for name, val in ((ENV_KEY_ID, key_id),
                                      (ENV_SECRET, secret)) if not val]
    if missing:
        raise PaperRunnerError(
            "missing Alpaca paper credentials in the environment: "
            + ", ".join(missing)
            + ". Set them as environment variables (paper keys only); "
              "they are never read from files and never logged."
        )
    return key_id, secret


def _assert_paper_url(base_url: str) -> None:
    """Refuse anything that is not the Alpaca paper endpoint."""
    if base_url != PAPER_BASE_URL:
        raise PaperRunnerError(
            f"refusing non-paper Alpaca endpoint {base_url!r}; "
            f"this runner talks only to {PAPER_BASE_URL}."
        )


def _new_venue(key_id: str, secret: str) -> AlpacaPaperVenue:
    _assert_paper_url(PAPER_BASE_URL)
    venue = AlpacaPaperVenue(api_key=key_id, secret_key=secret)
    if not venue.paper_mode:
        raise PaperRunnerError("venue is not in paper mode; aborting.")
    return venue


# ----------------------------------------------------------------------
# Alpaca HTTP (stdlib urllib only)
# ----------------------------------------------------------------------
def _headers(key_id: str, secret: str) -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }


def _alpaca_get(key_id: str, secret: str, host: str, path: str,
                timeout: int = 15) -> Any:
    """GET ``host + path`` with the paper keys. Any failure raises
    :class:`PaperRunnerError` (fail-closed); the message never includes
    credentials."""
    req = urllib.request.Request(host + path, headers=_headers(key_id, secret),
                                 method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise PaperRunnerError(
            f"Alpaca GET {path} failed: HTTP {exc.code}") from exc
    except Exception as exc:  # timeouts, DNS, TLS, connection errors
        raise PaperRunnerError(
            f"Alpaca GET {path} failed: {type(exc).__name__}") from exc


def fetch_account(key_id: str, secret: str) -> Dict[str, Any]:
    """Read-only paper account snapshot. No orders are possible here."""
    return _alpaca_get(key_id, secret, PAPER_BASE_URL, "/v2/account")


def fetch_position_qty(key_id: str, secret: str, symbol: str) -> int:
    """Current paper position in ``symbol`` (shares, signed). 404 -> 0."""
    try:
        pos = _alpaca_get(key_id, secret, PAPER_BASE_URL,
                          f"/v2/positions/{symbol}")
    except PaperRunnerError as exc:
        if "HTTP 404" in str(exc):
            return 0
        raise
    try:
        return int(float(pos.get("qty", 0)))
    except (TypeError, ValueError):
        raise PaperRunnerError("unparseable position response") from None


@dataclass(frozen=True)
class MinuteBar:
    ts: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_bars(key_id: str, secret: str, symbol: str,
               limit: int = 60) -> List[MinuteBar]:
    """Recent minute bars from the Alpaca data API. Any failure raises
    :class:`PaperRunnerError` and the caller must place no orders."""
    path = (f"/v2/stocks/{symbol}/bars?timeframe=1Min"
            f"&limit={max(1, int(limit))}")
    payload = _alpaca_get(key_id, secret, DATA_BASE_URL, path)
    raw = payload.get("bars") or []
    bars: List[MinuteBar] = []
    for b in raw:
        try:
            ts = int(datetime.fromisoformat(
                str(b["t"]).replace("Z", "+00:00")).replace(
                    tzinfo=timezone.utc).timestamp())
            bars.append(MinuteBar(
                ts=ts,
                open=float(b["o"]), high=float(b["h"]),
                low=float(b["l"]), close=float(b["c"]),
                volume=float(b.get("v", 0))))
        except (KeyError, TypeError, ValueError):
            raise PaperRunnerError("unparseable bar in data response") from None
    return bars


# ----------------------------------------------------------------------
# market-data -> strategy snapshot (no L2 from Alpaca: top of book only)
# ----------------------------------------------------------------------
def snapshot_from_bars(bars: List[MinuteBar]) -> MarketSnapshot:
    """Build a :class:`MarketSnapshot` from minute bars.

    Alpaca exposes no L2 feed, so depth fields stay empty and the touch
    is synthesized as one tick around the last close. The strategy falls
    back to the top-level imbalance field (fraction of up bars).
    """
    last = bars[-1]
    mid_ticks = int(round(last.close / TICK))
    ups = sum(1 for b in bars if b.close >= b.open)
    imb = (ups / len(bars)) * 2.0 - 1.0
    return MarketSnapshot(
        ts_ns=time.time_ns(),
        bid=mid_ticks - 1,
        ask=mid_ticks + 1,
        bid_qty=1,
        ask_qty=1,
        mid=float(mid_ticks),
        microprice=float(mid_ticks),
        imbalance=imb,
    )


# ----------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------
class PaperRunner:
    """Signal-based Alpaca paper runner.

    Parameters mirror the CLI flags. ``venue`` may be injected (tests);
    otherwise the caller builds it with :func:`_new_venue` from env keys.
    """

    def __init__(self, symbol: str, key_id: str, secret: str,
                 interval: float = 60.0, max_orders: int = 5,
                 max_notional: float = 25.0, bars: int = 60,
                 dry_run: bool = True, daily_loss: float = 50.0,
                 audit: Optional[AuditLog] = None,
                 audit_path: str = "hft/paper-run-audit.jsonl",
                 venue=None, strategy=None, risk=None) -> None:
        self.symbol = symbol
        self._key_id = key_id
        self._secret = secret
        self.interval = max(1.0, float(interval))
        self.max_orders = max(1, int(max_orders))
        self.max_notional = max(1.0, float(max_notional))
        self.bars = max(5, int(bars))
        self.dry_run = bool(dry_run)
        self.audit = audit or AuditLog(audit_path)
        self.venue = venue
        self.strategy = strategy or MultiLevelFlowStrategy(
            window=60, entry_threshold=0.35, max_position=4, order_size=1,
            tick_size=TICK)
        self.risk = risk or RiskGateway(
            RiskLimits(max_order_notional=self.max_notional,
                       max_notional_per_minute=self.max_notional * 4,
                       max_position=10, max_orders_per_sec=2,
                       max_orders_per_sec_per_symbol=2,
                       daily_loss_limit=daily_loss, allow_shorts=True),
            tick_size=TICK, audit=self.audit)
        self.orders_submitted = 0
        self._seq = 0
        self._stop = False
        self._interrupted = False

    # -- read-only ------------------------------------------------------
    def run_account(self) -> int:
        """Fetch and print the paper account. Places no orders."""
        account = fetch_account(self._key_id, self._secret)
        equity = account.get("equity", "?")
        bp = account.get("buying_power", "?")
        cash = account.get("cash", "?")
        self.audit.log("account_snapshot", {
            "symbol": self.symbol, "equity": equity,
            "buying_power": bp, "cash": cash})
        print(f"Alpaca paper account — equity: ${equity}  "
              f"buying_power: ${bp}  cash: ${cash}")
        print("(read-only mode: no orders placed)")
        return 0

    # -- signal loop ----------------------------------------------------
    def run_trade(self) -> int:
        try:
            signal.signal(signal.SIGINT, self._on_sigint)
        except (OSError, ValueError, RuntimeError):
            pass  # not the main thread / no signal support: Ctrl-C still works via KeyboardInterrupt
        self.audit.log("run_start", {
            "symbol": self.symbol, "dry_run": self.dry_run,
            "interval_s": self.interval, "max_orders": self.max_orders,
            "max_notional": self.max_notional})
        print(f"paper_run: mode=trade symbol={self.symbol} "
              f"dry_run={self.dry_run} interval={self.interval:g}s "
              f"max_orders={self.max_orders} "
              f"max_notional=${self.max_notional:g} (Ctrl-C stops)")
        try:
            while not self._stop:
                self._trade_iteration()
                if self.orders_submitted >= self.max_orders:
                    self.audit.log("run_stop",
                                   {"reason": "max_orders_reached",
                                    "orders_submitted": self.orders_submitted})
                    print("paper_run: max orders reached; stopping.")
                    break
                self._sleep()
        except PaperRunnerError as exc:
            print(f"paper_run: stopped ({exc})", file=sys.stderr)
            self.audit.log("run_stop", {"reason": str(exc)})
            return 1
        finally:
            if self._interrupted or self.risk.kill_switch:
                self._cancel_all_open(
                    "SIGINT" if self._interrupted else "kill switch")
            self.audit.close()
            if self.venue is not None:
                self.venue.close()
        return 0

    def _on_sigint(self, signum, frame) -> None:  # noqa: ARG002
        self._stop = True
        self._interrupted = True

    def _sleep(self) -> None:
        deadline = time.time() + self.interval
        while time.time() < deadline and not self._stop:
            time.sleep(0.5)

    def _cancel_all_open(self, reason: str) -> None:
        open_ids = self.risk.kill(reason)
        for cid in open_ids:
            try:
                ok = self.venue.cancel(cid) if self.venue else False
            except Exception:
                ok = False
            self.risk.note_order_closed(cid)
            self.audit.log("order_cancelled" if ok else "cancel_failed",
                           {"client_order_id": cid, "reason": reason})
        print(f"paper_run: kill switch ({reason}): "
              f"cancelled {len(open_ids)} open order(s).")

    def _trade_iteration(self) -> None:
        # Any data failure raises PaperRunnerError -> no orders, run stops.
        bars = fetch_bars(self._key_id, self._secret, self.symbol, self.bars)
        if not bars:
            raise PaperRunnerError("empty bar response from data API")
        snap = snapshot_from_bars(bars)
        for b in bars:
            self.strategy.on_trade_print(
                BUY if b.close >= b.open else SELL, max(1, int(b.volume)))
        self.strategy.on_market(snap)
        ts_ns = time.time_ns()

        account = fetch_account(self._key_id, self._secret)
        try:
            equity = float(account["equity"])
        except (KeyError, TypeError, ValueError):
            raise PaperRunnerError("unparseable account response") from None
        position = fetch_position_qty(self._key_id, self._secret, self.symbol)
        self.strategy.position = position  # strategy tracks paper truth
        self.risk.mark(equity)  # trips the kill switch on daily-loss breach
        self.audit.log("iteration", {
            "symbol": self.symbol, "equity": equity, "position": position,
            "mid": snap.mid, "imbalance": snap.imbalance})
        if self.risk.kill_switch:
            raise PaperRunnerError(
                f"kill switch tripped: {self.risk.kill_reason}")

        intents = self.strategy.decide(ts_ns)
        ref_mid = snap.mid if snap.mid is not None else 0.0
        for intent in intents:
            if self._stop or self.orders_submitted >= self.max_orders:
                break
            self._submit_intent(intent, ref_mid, position, ts_ns)

    def _submit_intent(self, intent: OrderIntent, ref_mid_ticks: float,
                       position: int, ts_ns: int) -> bool:
        if intent.action != NEW:
            return False
        price_ticks = intent.price
        if price_ticks is None or price_ticks <= 0:
            self.audit.log("order_skipped", {
                "tag": intent.tag,
                "reason": "paper runner uses limit orders only (no price)"})
            return False
        px_dollars = price_ticks * TICK
        qty = min(intent.qty, int(self.max_notional // px_dollars)) \
            if px_dollars > 0 else 0
        if qty < 1:
            self.audit.log("order_skipped", {
                "tag": intent.tag, "side": intent.side,
                "reason": (f"notional cap: {intent.qty} sh @ ${px_dollars:.2f} "
                           f"exceeds ${self.max_notional:.2f}")})
            return False
        self._seq += 1
        cid = f"paper-{self._seq}-{ts_ns // 1_000_000}"
        self.audit.log("order_intent", {
            "client_order_id": cid, "symbol": self.symbol,
            "side": "buy" if intent.side == BUY else "sell",
            "qty": qty, "price_ticks": price_ticks, "tag": intent.tag,
            "dry_run": self.dry_run})
        decision = self.risk.check_new_order(
            cid, intent.side, qty, price_ticks, position,
            ref_mid_ticks, ts_ns, symbol=self.symbol)
        if not decision.approved:
            self.audit.log("order_blocked",
                           {"client_order_id": cid, "reason": decision.reason})
            return False
        if self.dry_run:
            # Count the simulated intent so a dry-run terminates: the audit
            # log records dry_run=True on the order_intent event, so the
            # counter here means "intents processed", not "orders placed".
            self.orders_submitted += 1
            return False  # logged above; nothing submitted
        order = IncomingOrder(client_order_id=cid, owner="self",
                              side=intent.side, qty=qty,
                              order_type=intent.order_type,
                              price=price_ticks, ts_ns=ts_ns)
        try:
            result = self.venue.submit(order, symbol=self.symbol)
        except Exception as exc:
            self.audit.log("submit_error", {
                "client_order_id": cid, "error": type(exc).__name__})
            self.risk.note_order_closed(cid)
            return False
        self.audit.log("order_submitted", {
            "client_order_id": cid, "status": result.status,
            "reason": result.reason})
        if result.status == "rejected":
            self.risk.note_order_closed(cid)
            return False
        self.orders_submitted += 1
        return True


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "t", "yes", "y")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="HFT Lab paper-trading runner (Alpaca PAPER only). "
                    "Signal-based, not HFT; read-only by default.")
    p.add_argument("--mode", choices=["account", "trade"], default="account",
                   help="account: read-only account check (default). "
                        "trade: run the signal loop.")
    p.add_argument("--symbol", default="SPY",
                   help="Alpaca symbol for the trade loop (default SPY).")
    p.add_argument("--interval", type=float, default=60.0,
                   help="seconds between signal polls (default 60).")
    p.add_argument("--max-orders", type=int, default=5,
                   help="max paper orders submitted per run (default 5).")
    p.add_argument("--max-notional", type=float, default=25.0,
                   help="max dollars per paper order (default 25).")
    p.add_argument("--bars", type=int, default=60,
                   help="minute bars fetched per poll (default 60).")
    p.add_argument("--daily-loss", type=float, default=50.0,
                   help="daily loss limit in dollars; trips the kill switch "
                        "(default 50).")
    p.add_argument("--dry-run", nargs="?", const=True, default=True,
                   type=_parse_bool,
                   help="log intents without submitting (default true). "
                        "Use --dry-run=false to actually submit to Alpaca PAPER.")
    p.add_argument("--audit-path", default="hft/paper-run-audit.jsonl",
                   help="JSONL audit log path (default hft/paper-run-audit.jsonl).")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    audit = AuditLog(args.audit_path)
    try:
        key_id, secret = _read_keys()
    except PaperRunnerError as exc:
        print(f"paper_run: {exc}", file=sys.stderr)
        audit.close()
        return 2

    if args.mode == "account":
        runner = PaperRunner(symbol=args.symbol, key_id=key_id, secret=secret,
                             audit=audit)
        try:
            return runner.run_account()
        except PaperRunnerError as exc:
            print(f"paper_run: {exc}", file=sys.stderr)
            return 1
        finally:
            audit.close()

    # trade mode: paper-only venue, risk gateway, audit log
    venue = _new_venue(key_id, secret)
    runner = PaperRunner(symbol=args.symbol, key_id=key_id, secret=secret,
                         interval=args.interval, max_orders=args.max_orders,
                         max_notional=args.max_notional, bars=args.bars,
                         dry_run=args.dry_run, daily_loss=args.daily_loss,
                         audit=audit, venue=venue)
    return runner.run_trade()


if __name__ == "__main__":
    sys.exit(main())
