"""Native SQLite datastore for SAHJONY CAPITAL LLC.

A single file-based database (no server) that is the firm's system of record:
  • investors / contributions   — the CRM ledger (AUM, units, contact)
  • trades                       — every executed order (paper or sim)
  • equity_curve                 — per-cycle NAV / cash / realized P&L
  • position_snapshots           — per-cycle open positions
  • council_log                  — the 12-agent verdict per symbol per cycle
  • events                       — operational audit log

All writes are wrapped by the caller's try/except; this layer keeps the schema,
connection, and typed helpers. Uses WAL for safe concurrent reads.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "sahjony.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS investors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT,
    phone         TEXT,
    kind          TEXT NOT NULL DEFAULT 'lead',      -- lead | investor | client
    status        TEXT NOT NULL DEFAULT 'active',
    committed     REAL NOT NULL DEFAULT 0,
    contributed   REAL NOT NULL DEFAULT 0,
    units         REAL NOT NULL DEFAULT 0,
    notes         TEXT,
    share_token   TEXT,                              -- read-only investor link capability
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(email)
);
CREATE TABLE IF NOT EXISTS contributions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    investor_id   INTEGER NOT NULL REFERENCES investors(id),
    ts            TEXT NOT NULL,
    amount        REAL NOT NULL,                       -- +deposit / -withdrawal
    kind          TEXT NOT NULL DEFAULT 'deposit',
    nav_per_unit  REAL,
    units_delta   REAL,
    note          TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    cycle         INTEGER,
    symbol        TEXT NOT NULL,
    strategy      TEXT,
    kind          TEXT,                                -- equity | option
    side          TEXT,
    qty           REAL,
    price         REAL,
    premium       REAL,
    notional      REAL,
    purpose       TEXT,
    reason        TEXT,
    mode          TEXT,
    simulated     INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS equity_curve (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    cycle         INTEGER,
    equity        REAL,
    cash          REAL,
    deployed      REAL,
    realized_pnl  REAL,
    premium       REAL,
    mode          TEXT
);
CREATE TABLE IF NOT EXISTS position_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    cycle         INTEGER,
    symbol        TEXT,
    strategy      TEXT,
    state         TEXT,
    shares        REAL,
    cost_basis    REAL,
    price         REAL,
    market_value  REAL,
    unrealized    REAL
);
CREATE TABLE IF NOT EXISTS council_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    cycle         INTEGER,
    symbol        TEXT,
    conviction    REAL,
    direction     TEXT,
    composite     REAL,
    risk_mult     REAL,
    metrics       TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    kind          TEXT,
    detail        TEXT
);
CREATE TABLE IF NOT EXISTS ai_shadow_observations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL,
    provider          TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    base_conviction   REAL,
    adjustment        REAL,
    risk_multiplier   REAL,
    forward_return    REAL,
    turnover_cost_bps REAL,
    latency_ms        REAL,
    schema_valid      INTEGER,
    fallback_used     INTEGER,
    direction         TEXT
);
CREATE TABLE IF NOT EXISTS capital_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    amount        REAL NOT NULL,                       -- +deposit / -withdrawal (signed)
    kind          TEXT NOT NULL DEFAULT 'deposit',     -- deposit | withdrawal
    method        TEXT,                                -- ach | wire | alpaca | paper_reset | manual
    equity_after  REAL,                                -- account equity right after the flow
    note          TEXT
);
CREATE TABLE IF NOT EXISTS promotion_candidates (
    key           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'strategy',
    stage         TEXT NOT NULL DEFAULT 'research',
    evidence      TEXT NOT NULL DEFAULT '{}',
    approvals     TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS promotion_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    from_stage    TEXT NOT NULL,
    to_stage      TEXT NOT NULL,
    action        TEXT NOT NULL,
    actor         TEXT NOT NULL,
    allowed       INTEGER NOT NULL,
    reason        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS promotion_artifacts (
    artifact_id   TEXT PRIMARY KEY,
    candidate_key TEXT NOT NULL,
    stage         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    source        TEXT NOT NULL,
    payload       TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    signature     TEXT,
    signer        TEXT,
    verified      INTEGER NOT NULL,
    ingested_at   TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str = None):
        if path is None:
            from paths import db_path
            path = db_path()
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Backfill columns added after a DB was first created (additive only)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(investors)").fetchall()}
        if "share_token" not in cols:
            self.conn.execute("ALTER TABLE investors ADD COLUMN share_token TEXT")

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # ── writers (firm/trading desk) ──────────────────────────────────────────
    def log_trade(self, t: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO trades (ts,cycle,symbol,strategy,kind,side,qty,price,premium,
                                   notional,purpose,reason,mode,simulated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), t.get("cycle"), t.get("symbol"), t.get("strategy"), t.get("kind"),
             t.get("side"), t.get("qty"), t.get("price"), t.get("premium"), t.get("notional"),
             t.get("purpose"), t.get("reason"), t.get("mode"), 1 if t.get("simulated", True) else 0))
        self.conn.commit()

    def log_equity(self, cycle, equity, cash, deployed, realized, premium, mode) -> None:
        self.conn.execute(
            "INSERT INTO equity_curve (ts,cycle,equity,cash,deployed,realized_pnl,premium,mode)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (_now(), cycle, equity, cash, deployed, realized, premium, mode))
        self.conn.commit()

    def log_snapshot(self, cycle, symbol, strategy, state, shares, cost_basis, price,
                     market_value, unrealized) -> None:
        self.conn.execute(
            """INSERT INTO position_snapshots (ts,cycle,symbol,strategy,state,shares,cost_basis,
                                               price,market_value,unrealized)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (_now(), cycle, symbol, strategy, state, shares, cost_basis, price, market_value, unrealized))
        self.conn.commit()

    def log_council(self, cycle, symbol, conviction, direction, composite, risk_mult,
                    metrics: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO council_log (ts,cycle,symbol,conviction,direction,composite,risk_mult,metrics)
               VALUES (?,?,?,?,?,?,?,?)""",
            (_now(), cycle, symbol, conviction, direction, composite, risk_mult, json.dumps(metrics)))
        self.conn.commit()

    def log_event(self, kind: str, detail: Dict[str, Any]) -> None:
        self.conn.execute("INSERT INTO events (ts,kind,detail) VALUES (?,?,?)",
                          (_now(), kind, json.dumps(detail)))
        self.conn.commit()

    def log_ai_shadow_observations(self, rows: List[Dict[str, Any]]) -> None:
        self.conn.executemany(
            """INSERT INTO ai_shadow_observations
               (ts,provider,symbol,base_conviction,adjustment,risk_multiplier,
                forward_return,turnover_cost_bps,latency_ms,schema_valid,
                fallback_used,direction) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(row.get("ts"), row.get("provider"), row.get("symbol"),
              row.get("base_conviction"), row.get("adjustment"), row.get("risk_multiplier"),
              row.get("forward_return"), row.get("turnover_cost_bps"), row.get("latency_ms"),
              1 if row.get("schema_valid", True) else 0,
              1 if row.get("fallback_used", False) else 0, row.get("direction"))
             for row in rows],
        )
        self.conn.commit()

    # ── governed research / strategy promotion pipeline ─────────────────────
    @staticmethod
    def _promotion_row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        item = dict(row)
        item["evidence"] = json.loads(item.get("evidence") or "{}")
        item["approvals"] = json.loads(item.get("approvals") or "{}")
        return item

    def upsert_promotion_candidate(self, key: str, name: str,
                                   kind: str = "strategy") -> Dict[str, Any]:
        now = _now()
        self.conn.execute(
            """INSERT INTO promotion_candidates
               (key,name,kind,stage,evidence,approvals,created_at,updated_at)
               VALUES (?,?,?,'research','{}','{}',?,?)
               ON CONFLICT(key) DO UPDATE SET name=excluded.name, kind=excluded.kind,
                 updated_at=excluded.updated_at""",
            (key, name, kind, now, now),
        )
        self.conn.commit()
        return self.promotion_candidate(key)

    def update_promotion_candidate(self, key: str, *, stage: str = None,
                                   evidence: Dict[str, Any] = None,
                                   approvals: Dict[str, Any] = None) -> None:
        current = self.promotion_candidate(key)
        if current is None:
            raise KeyError(key)
        self.conn.execute(
            """UPDATE promotion_candidates SET stage=?, evidence=?, approvals=?, updated_at=?
               WHERE key=?""",
            (stage or current["stage"], json.dumps(evidence if evidence is not None else current["evidence"]),
             json.dumps(approvals if approvals is not None else current["approvals"]), _now(), key),
        )
        self.conn.commit()

    def promotion_candidate(self, key: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM promotion_candidates WHERE key=?", (key,)).fetchone()
        return self._promotion_row(row)

    def promotion_candidates(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM promotion_candidates ORDER BY name").fetchall()
        return [self._promotion_row(row) for row in rows]

    def log_promotion_event(self, candidate_key: str, from_stage: str, to_stage: str,
                            action: str, actor: str, allowed: bool, reason: str,
                            detail: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO promotion_events
               (ts,candidate_key,from_stage,to_stage,action,actor,allowed,reason,detail)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (_now(), candidate_key, from_stage, to_stage, action, actor,
             1 if allowed else 0, reason, json.dumps(detail)),
        )
        self.conn.commit()

    def promotion_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM promotion_events ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["allowed"] = bool(item["allowed"])
            item["detail"] = json.loads(item.get("detail") or "{}")
            result.append(item)
        return result

    def promotion_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM promotion_artifacts WHERE artifact_id=?", (artifact_id,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        item["verified"] = bool(item["verified"])
        return item

    def record_promotion_artifact(self, artifact: Dict[str, Any]) -> Dict[str, Any]:
        """Append an artifact once; an artifact id can never be mutated."""
        existing = self.promotion_artifact(artifact["artifact_id"])
        if existing:
            if existing["payload_hash"] != artifact["payload_hash"]:
                raise ValueError("artifact id already exists with different content")
            return existing
        self.conn.execute(
            """INSERT INTO promotion_artifacts
               (artifact_id,candidate_key,stage,created_at,source,payload,payload_hash,
                signature,signer,verified,ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (artifact["artifact_id"], artifact["candidate_key"], artifact["stage"],
             artifact["created_at"], artifact["source"], json.dumps(artifact["payload"],
             sort_keys=True, separators=(",", ":")), artifact["payload_hash"],
             artifact.get("signature"), artifact.get("signer"),
             1 if artifact.get("verified") else 0, _now()),
        )
        self.conn.commit()
        return self.promotion_artifact(artifact["artifact_id"])

    def promotion_artifacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT artifact_id FROM promotion_artifacts ORDER BY ingested_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [self.promotion_artifact(row["artifact_id"]) for row in rows]

    # ── CRM ledger ───────────────────────────────────────────────────────────
    def upsert_investor(self, name, email=None, phone=None, kind="lead", notes=None) -> int:
        row = self.conn.execute("SELECT id FROM investors WHERE email = ?", (email,)).fetchone() \
            if email else None
        if row:
            self.conn.execute(
                "UPDATE investors SET name=?, phone=COALESCE(?,phone), kind=?, notes=COALESCE(?,notes),"
                " updated_at=? WHERE id=?",
                (name, phone, kind, notes, _now(), row["id"]))
            self.conn.commit()
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO investors (name,email,phone,kind,notes,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?)", (name, email, phone, kind, notes, _now(), _now()))
        self.conn.commit()
        return int(cur.lastrowid)

    def record_contribution(self, investor_id: int, amount: float, nav_per_unit: float = 1.0,
                            kind: str = "deposit", note: str = None) -> None:
        units_delta = amount / nav_per_unit if nav_per_unit else 0.0
        self.conn.execute(
            "INSERT INTO contributions (investor_id,ts,amount,kind,nav_per_unit,units_delta,note)"
            " VALUES (?,?,?,?,?,?,?)",
            (investor_id, _now(), amount, kind, nav_per_unit, units_delta, note))
        self.conn.execute(
            "UPDATE investors SET contributed = contributed + ?, units = units + ?,"
            " kind = CASE WHEN ? > 0 THEN 'investor' ELSE kind END, updated_at=? WHERE id=?",
            (amount, units_delta, amount, _now(), investor_id))
        self.conn.commit()

    def list_investors(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM investors ORDER BY contributed DESC").fetchall()
        return [dict(r) for r in rows]

    # ── owner capital ledger (deposits / withdrawals on YOUR trading account) ──
    # This is the account-level cash ledger, separate from the investor CRM. Real
    # money moves through your broker (Alpaca ACH); recording it here keeps return
    # accounting honest — a deposit is capital, not a trading gain.
    def record_capital(self, amount: float, kind: str = "deposit", method: str = "manual",
                       equity_after: Optional[float] = None, note: str = None) -> float:
        kind = "withdrawal" if kind.lower().startswith("w") else "deposit"
        signed = -abs(amount) if kind == "withdrawal" else abs(amount)
        self.conn.execute(
            "INSERT INTO capital_ledger (ts,amount,kind,method,equity_after,note)"
            " VALUES (?,?,?,?,?,?)", (_now(), signed, kind, method, equity_after, note))
        self.conn.commit()
        return signed

    def capital_ledger(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM capital_ledger ORDER BY id DESC LIMIT ?",
                                 (limit,)).fetchall()
        return [dict(r) for r in rows]

    def capital_summary(self) -> Dict[str, Any]:
        r = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0) deposits,"
            " COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0) withdrawals,"
            " COALESCE(SUM(amount),0) net, COUNT(*) n FROM capital_ledger").fetchone()
        return {"deposits": float(r["deposits"]), "withdrawals": float(r["withdrawals"]),
                "net_capital": float(r["net"]), "flows": int(r["n"])}

    # ── investor read-only share links ───────────────────────────────────────
    def set_share_token(self, investor_id: int, token: str) -> None:
        self.conn.execute("UPDATE investors SET share_token=?, updated_at=? WHERE id=?",
                          (token, _now(), investor_id))
        self.conn.commit()

    def clear_share_token(self, investor_id: int) -> None:
        self.conn.execute("UPDATE investors SET share_token=NULL, updated_at=? WHERE id=?",
                          (_now(), investor_id))
        self.conn.commit()

    def get_investor_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        r = self.conn.execute("SELECT * FROM investors WHERE share_token=?", (token,)).fetchone()
        return dict(r) if r else None

    def shared_investors(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM investors WHERE share_token IS NOT NULL AND share_token != ''").fetchall()
        return [dict(r) for r in rows]

    def get_investor(self, investor_id: int) -> Optional[Dict[str, Any]]:
        r = self.conn.execute("SELECT * FROM investors WHERE id=?", (investor_id,)).fetchone()
        return dict(r) if r else None

    def fund_summary(self) -> Dict[str, Any]:
        r = self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(contributed),0) aum, COALESCE(SUM(units),0) units,"
            " COALESCE(SUM(committed),0) committed FROM investors").fetchone()
        invs = self.conn.execute("SELECT COUNT(*) c FROM investors WHERE kind='investor'").fetchone()
        return {"investors": int(invs["c"]), "contacts": int(r["n"]),
                "aum": float(r["aum"]), "units": float(r["units"]), "committed": float(r["committed"])}

    # ── readers (dashboard / reporting) ──────────────────────────────────────
    def recent_trades(self, limit: int = 25) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def equity_history(self, limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts,cycle,equity,cash,deployed,realized_pnl,premium FROM equity_curve"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def equity_history_regime(self, limit: int = 500,
                              jump_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Equity history trimmed to the CURRENT capital regime.

        A ``TRADING_CAPITAL`` change re-anchors the baseline (e.g. a $100k desk
        switched to a $50 crypto sleeve), leaving a synthetic >``jump_threshold``
        single-cycle step in the curve that is NOT trading P&L. Under the risk
        caps here a real cycle can't move total equity by 50% (per-position ≤15%),
        so such a step is unambiguously a re-anchor. Left in, those cliffs poison
        every downstream stat — Sharpe/Sortino/drawdown, vol-targeting (a −94%
        fake return read as 1400%+ annual vol → budgets halved), and the dashboard
        chart. Drop everything up to and including the last re-anchor so consumers
        see only the current regime; fall back to the full curve if there is none."""
        rows = self.equity_history(500)
        start = 0
        for i in range(1, len(rows)):
            try:
                prev = float(rows[i - 1].get("equity") or 0)
                cur = float(rows[i].get("equity") or 0)
            except (TypeError, ValueError):
                continue
            if prev > 0 and abs(cur - prev) / prev > jump_threshold:
                start = i
        regime = rows[start:]
        return regime[-limit:] if limit else regime

    def latest_council(self, cycle: Optional[int] = None) -> List[Dict[str, Any]]:
        if cycle is None:
            row = self.conn.execute("SELECT MAX(cycle) m FROM council_log").fetchone()
            cycle = row["m"] if row and row["m"] is not None else 0
        rows = self.conn.execute("SELECT * FROM council_log WHERE cycle=?", (cycle,)).fetchall()
        return [dict(r) for r in rows]
