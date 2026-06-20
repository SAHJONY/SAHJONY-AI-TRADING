"""Postgres (Supabase) access for the multi-tenant worker.

Uses the service-role connection (SUPABASE_DB_URL) which bypasses RLS, so the
worker can read every active desk. The browser never uses this connection.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL (service-role Postgres URL) is not set")
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)


def list_active_desks(conn: psycopg.Connection) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM public.desks WHERE active = true ORDER BY created_at")
        return cur.fetchall()


def get_credentials(conn: psycopg.Connection, desk_id: str) -> Dict[str, str]:
    """Return {name: enc_value} for a desk (values are still ciphertext here)."""
    with conn.cursor() as cur:
        cur.execute("SELECT name, enc_value FROM public.broker_credentials WHERE desk_id = %s",
                    (desk_id,))
        return {r["name"]: r["enc_value"] for r in cur.fetchall()}


def append_equity(conn: psycopg.Connection, desk_id: str, point: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO public.equity_points
               (desk_id, cycle, equity, cash, deployed, realized_pnl, premium, mode)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (desk_id, point.get("cycle"), point.get("equity"), point.get("cash"),
             point.get("deployed"), point.get("realized_pnl"), point.get("premium"),
             point.get("mode")))


def insert_trades(conn: psycopg.Connection, desk_id: str, trades: List[Dict[str, Any]]) -> None:
    if not trades:
        return
    with conn.cursor() as cur:
        for t in trades:
            cur.execute(
                """INSERT INTO public.trades
                   (desk_id, cycle, symbol, strategy, kind, side, qty, price, premium,
                    notional, purpose, reason, mode, simulated)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (desk_id, t.get("cycle"), t.get("symbol"), t.get("strategy"), t.get("kind"),
                 t.get("side"), t.get("qty"), t.get("price"), t.get("premium"), t.get("notional"),
                 t.get("purpose"), t.get("reason"), t.get("mode"), bool(t.get("simulated", True))))


def equity_curve(conn: psycopg.Connection, desk_id: str, limit: int = 150) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT cycle, equity, cash, realized_pnl, premium, ts
               FROM public.equity_points WHERE desk_id = %s ORDER BY id DESC LIMIT %s""",
            (desk_id, limit))
        rows = cur.fetchall()
    out = []
    for r in reversed(rows):
        out.append({"cycle": r["cycle"], "equity": float(r["equity"] or 0),
                    "cash": float(r["cash"] or 0), "realized_pnl": float(r["realized_pnl"] or 0),
                    "premium": float(r["premium"] or 0), "ts": r["ts"].isoformat() if r["ts"] else None})
    return out


def recent_trades(conn: psycopg.Connection, desk_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT cycle, symbol, side, purpose, qty, price FROM public.trades
               WHERE desk_id = %s ORDER BY id DESC LIMIT %s""", (desk_id, limit))
        return cur.fetchall()


def save_desk_result(conn: psycopg.Connection, desk_id: str, state: Dict[str, Any],
                     status: Dict[str, Any], mode: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE public.desks
               SET state = %s, last_status = %s, mode = %s, last_run_at = now(), updated_at = now()
               WHERE id = %s""",
            (json.dumps(state), json.dumps(status), mode, desk_id))
