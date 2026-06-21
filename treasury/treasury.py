"""Treasury — your trading account's capital ledger (deposits & withdrawals).

Real money moves through your BROKER, not this bot:
  • Live Alpaca account → fund/withdraw via the Alpaca app/website (linked bank,
    ACH/wire). The standard Trading API can't move money; only Alpaca's separate
    Broker API can, and that's a different product. See FUNDING.md.
  • Paper account → there is no real cash; reset/top-up the paper balance in the
    Alpaca dashboard.

What this module owns is the *accounting*: record each deposit/withdrawal so the
dashboard separates capital you ADDED from money the strategy MADE. Without it, a
$10k deposit looks like a $10k "gain". A top-tier desk always tracks external
cashflows so returns reflect trading, not funding.

CLI:
  python -m treasury.treasury deposit  --amount 10000 --method ach --note "initial funding"
  python -m treasury.treasury withdraw --amount 2500  --method ach
  python -m treasury.treasury summary
  python -m treasury.treasury history
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from database import Database
from utils.logger import get_logger

log = get_logger("treasury")

_METHODS = ("ach", "wire", "alpaca", "paper_reset", "manual")


class Treasury:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def deposit(self, amount: float, method: str = "ach", equity_after: float = None,
                note: str = None) -> float:
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        signed = self.db.record_capital(amount, "deposit", method, equity_after, note)
        log.info("DEPOSIT recorded: +$%.2f via %s", amount, method)
        return signed

    def withdraw(self, amount: float, method: str = "ach", equity_after: float = None,
                 note: str = None) -> float:
        if amount <= 0:
            raise ValueError("withdrawal amount must be positive")
        signed = self.db.record_capital(amount, "withdrawal", method, equity_after, note)
        log.info("WITHDRAWAL recorded: -$%.2f via %s", amount, method)
        return signed

    def summary(self, equity: float = None) -> Dict[str, Any]:
        s = self.db.capital_summary()
        if equity is not None:
            net = s["net_capital"]
            s["equity"] = round(equity, 2)
            s["trading_pnl"] = round(equity - net, 2)
            s["trading_return_pct"] = round((equity / net - 1.0) * 100, 3) if net > 0 else 0.0
        return s

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.db.capital_ledger(limit)


def _fmt(v: float) -> str:
    return f"${v:,.2f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="treasury", description="Owner account capital ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("deposit", "withdraw"):
        p = sub.add_parser(name, help=f"record a {name}")
        p.add_argument("--amount", type=float, required=True)
        p.add_argument("--method", default="ach", choices=_METHODS)
        p.add_argument("--equity-after", type=float, default=None,
                       help="account equity right after the flow (optional, improves accounting)")
        p.add_argument("--note", default=None)
    sub.add_parser("summary", help="net capital + trading P&L")
    h = sub.add_parser("history", help="recent capital flows")
    h.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)

    t = Treasury()
    if args.cmd in ("deposit", "withdraw"):
        fn = t.deposit if args.cmd == "deposit" else t.withdraw
        fn(args.amount, args.method, args.equity_after, args.note)
        s = t.summary()
        print(f"{args.cmd.upper()} {_fmt(args.amount)} via {args.method} — "
              f"net capital now {_fmt(s['net_capital'])} "
              f"(deposits {_fmt(s['deposits'])}, withdrawals {_fmt(s['withdrawals'])})")
    elif args.cmd == "summary":
        s = t.summary()
        print(f"Deposits     {_fmt(s['deposits'])}")
        print(f"Withdrawals  {_fmt(s['withdrawals'])}")
        print(f"Net capital  {_fmt(s['net_capital'])}   ({s['flows']} flow(s))")
        print("Tip: trading P&L = current equity − net capital. The dashboard shows it live.")
    elif args.cmd == "history":
        rows = t.history(args.limit)
        if not rows:
            print("no capital flows recorded yet")
        for r in rows:
            print(f"{r['ts'][:19]}  {r['kind']:<10} {_fmt(r['amount']):>14}  "
                  f"{(r['method'] or ''):<11} {r['note'] or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
