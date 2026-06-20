"""Native CRM for SAHJONY CAPITAL LLC — investor relationship management.

A thin domain layer over the SQLite datastore (database/db.py) plus a CLI so the
owner can manage the book of investors/leads, record capital contributions, and
print statements. Units are tracked at the NAV-per-unit on contribution date, so
each investor's share of the fund is auditable.

CLI:
  python -m crm.crm add    --name "Jane Doe" --email jane@x.com --phone +1... --kind investor
  python -m crm.crm contribute --id 1 --amount 25000 --nav 1.0
  python -m crm.crm list
  python -m crm.crm statement --id 1
  python -m crm.crm summary
"""
from __future__ import annotations

import argparse
import secrets
from typing import Any, Dict, List, Optional

from config import load_config
from database import Database
from utils.logger import get_logger

log = get_logger("crm")


def _build_url(base_url: str, token: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    path = f"/investor?t={token}"
    return (base + path) if base else path


class CRM:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def add_client(self, name: str, email: str = None, phone: str = None,
                   kind: str = "lead", notes: str = None) -> int:
        cid = self.db.upsert_investor(name, email, phone, kind, notes)
        log.info("CRM upsert: #%s %s (%s)", cid, name, kind)
        return cid

    def contribute(self, investor_id: int, amount: float, nav_per_unit: float = 1.0,
                   kind: str = "deposit", note: str = None) -> None:
        self.db.record_contribution(investor_id, amount, nav_per_unit, kind, note)
        log.info("CRM contribution: investor #%s %+.2f @ NAV %.4f", investor_id, amount, nav_per_unit)

    def list_clients(self) -> List[Dict[str, Any]]:
        return self.db.list_investors()

    def statement(self, investor_id: int, nav_per_unit: float = 1.0) -> Dict[str, Any]:
        inv = self.db.get_investor(investor_id)
        if not inv:
            return {"error": f"investor #{investor_id} not found"}
        units = inv.get("units", 0.0)
        current_value = units * nav_per_unit
        contributed = inv.get("contributed", 0.0)
        return {
            "id": inv["id"], "name": inv["name"], "email": inv.get("email"),
            "kind": inv.get("kind"), "units": round(units, 4),
            "contributed": round(contributed, 2),
            "current_value": round(current_value, 2),
            "unrealized_pnl": round(current_value - contributed, 2),
            "nav_per_unit": nav_per_unit,
        }

    def fund_summary(self) -> Dict[str, Any]:
        return self.db.fund_summary()

    # ── read-only share links ─────────────────────────────────────────────────
    def share_link(self, investor_id: int, base_url: str = "") -> Dict[str, Any]:
        """Get (or mint) an investor's unguessable read-only link token."""
        inv = self.db.get_investor(investor_id)
        if not inv:
            return {"error": f"investor #{investor_id} not found"}
        token = (inv.get("share_token") or "").strip()
        if not token:
            token = secrets.token_urlsafe(24)
            self.db.set_share_token(investor_id, token)
            log.info("CRM share link issued for investor #%s", investor_id)
        return {"id": inv["id"], "name": inv["name"], "token": token,
                "url": _build_url(base_url, token)}

    def revoke_share(self, investor_id: int) -> Dict[str, Any]:
        inv = self.db.get_investor(investor_id)
        if not inv:
            return {"error": f"investor #{investor_id} not found"}
        self.db.clear_share_token(investor_id)
        log.info("CRM share link revoked for investor #%s", investor_id)
        return {"id": inv["id"], "name": inv["name"], "revoked": True}

    def list_links(self, base_url: str = "") -> List[Dict[str, Any]]:
        return [{"id": i["id"], "name": i["name"], "url": _build_url(base_url, i["share_token"])}
                for i in self.db.shared_investors()]


# ── CLI ───────────────────────────────────────────────────────────────────────
def _main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="crm", description="SAHJONY CAPITAL LLC — CRM")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="add or update a client/lead")
    a.add_argument("--name", required=True)
    a.add_argument("--email")
    a.add_argument("--phone")
    a.add_argument("--kind", default="lead", choices=["lead", "investor", "client"])
    a.add_argument("--notes")

    c = sub.add_parser("contribute", help="record a contribution/withdrawal")
    c.add_argument("--id", type=int, required=True)
    c.add_argument("--amount", type=float, required=True)
    c.add_argument("--nav", type=float, default=1.0)
    c.add_argument("--kind", default="deposit", choices=["deposit", "withdrawal"])
    c.add_argument("--note")

    sub.add_parser("list", help="list all clients")
    s = sub.add_parser("statement", help="print an investor statement")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--nav", type=float, default=1.0)
    sub.add_parser("summary", help="fund-level CRM summary")

    sh = sub.add_parser("share", help="issue/print an investor's read-only link")
    sh.add_argument("--id", type=int, required=True)
    sh.add_argument("--base-url", help="override PUBLIC_BASE_URL for the printed link")
    un = sub.add_parser("unshare", help="revoke an investor's read-only link")
    un.add_argument("--id", type=int, required=True)
    lk = sub.add_parser("links", help="list all active investor share links")
    lk.add_argument("--base-url", help="override PUBLIC_BASE_URL for the printed links")

    args = p.parse_args(argv)
    crm = CRM()
    base_url = getattr(args, "base_url", None) or load_config().public_base_url

    if args.cmd == "add":
        cid = crm.add_client(args.name, args.email, args.phone, args.kind, args.notes)
        print(f"✓ client #{cid}: {args.name} ({args.kind})")
    elif args.cmd == "contribute":
        amt = args.amount if args.kind == "deposit" else -abs(args.amount)
        crm.contribute(args.id, amt, args.nav, args.kind, args.note)
        print(f"✓ recorded {args.kind} {amt:+.2f} for investor #{args.id}")
    elif args.cmd == "list":
        rows = crm.list_clients()
        if not rows:
            print("(no clients yet)")
        for r in rows:
            print(f"#{r['id']:<3} {r['name']:<24} {r.get('kind',''):<9} "
                  f"contributed=${r.get('contributed',0):,.0f} units={r.get('units',0):.2f} "
                  f"{r.get('email') or ''}")
    elif args.cmd == "statement":
        import json
        print(json.dumps(crm.statement(args.id, args.nav), indent=2))
    elif args.cmd == "summary":
        import json
        print(json.dumps(crm.fund_summary(), indent=2))
    elif args.cmd == "share":
        res = crm.share_link(args.id, base_url)
        if res.get("error"):
            print("✗", res["error"])
        else:
            print(f"✓ read-only link for #{res['id']} {res['name']}:\n  {res['url']}")
            if not base_url:
                print("  (set PUBLIC_BASE_URL or pass --base-url for a full shareable URL)")
    elif args.cmd == "unshare":
        res = crm.revoke_share(args.id)
        print("✗ " + res["error"] if res.get("error") else f"✓ revoked link for #{res['id']} {res['name']}")
    elif args.cmd == "links":
        rows = crm.list_links(base_url)
        if not rows:
            print("(no active share links — issue one with: crm share --id N)")
        for r in rows:
            print(f"#{r['id']:<3} {r['name']:<24} {r['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
