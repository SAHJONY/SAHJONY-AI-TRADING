"""Remote kill switch for a LOCAL desk.

A local `python main.py` desk only sees the local HALT file. This lets a remote
STOP (e.g. the dashboard writing desk.halt to Supabase) reach that local desk:
each cycle it reads a remote halt source and toggles the SAME local HALT file the
workforce already checks (workforce._halted) — so enforcement stays in one tested
place; this module is only the remote *source*.

Opt-in: set REMOTE_HALT_URL. It should return the desk's halt state as JSON —
any of these shapes work:
    true / false
    {"halt": true}
    [{"halt": true}]            # Supabase REST: /rest/v1/desks?id=eq.<id>&select=halt
Optional REMOTE_HALT_TOKEN is sent as both `apikey` and `Authorization: Bearer`
headers (Supabase anon/service key style).

SAFETY — fail closed. If the source can't be reached or parsed, the desk HALTS
(you asked to be able to stop it remotely; when "allowed to trade" can't be
confirmed, the safe default is to stop). Override with REMOTE_HALT_FAILSAFE=false.
Only halts it created (marker below) are auto-cleared, so a manual `scripts/live.sh
off` is never overridden by a remote "resume".
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from paths import halt_path
from utils.logger import get_logger

log = get_logger("remote_control")

_MARKER = "remote-halt"   # content written to HALT when THIS module halts the desk


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def fetch_remote_halt(cfg=None) -> Optional[bool]:
    """Return True (halt), False (trading allowed), or None (no source / error)."""
    url = os.getenv("REMOTE_HALT_URL", "").strip()
    if not url:
        return None
    try:
        req = urllib.request.Request(url, method="GET")
        token = os.getenv("REMOTE_HALT_TOKEN", "").strip()
        if token:
            req.add_header("apikey", token)
            req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8") or "null")
    except Exception as exc:
        log.error("remote halt fetch failed: %s", exc)
        return None
    if isinstance(data, bool):
        return data
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict):
        for k in ("halt", "halted", "trading_halt"):
            if k in data:
                return _truthy(data[k])
    return None


def apply_remote_halt(state: Optional[bool], failsafe: bool = True) -> str:
    """Toggle the local HALT file from a remote state. Returns a short status.

    state True  → ensure HALT (marker).
    state False → clear HALT only if WE set it (marker); never touch a manual halt.
    state None  → unknown: fail closed (halt) when failsafe, else leave as-is."""
    p = halt_path()
    if state is None:
        if failsafe:
            state = True  # can't confirm trading is allowed → stop
        else:
            return "unknown/left-as-is"
    if state is True:
        if not os.path.exists(p):
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(_MARKER)
            except Exception as exc:
                log.error("could not write HALT: %s", exc)
                return "error"
            log.warning("REMOTE STOP → desk HALTED (new risk suspended).")
        return "halted(remote)"
    # state is False → resume, but only clear a halt we created
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                content = fh.read().strip()
        except Exception:
            content = ""
        if content == _MARKER:
            try:
                os.remove(p)
                log.info("REMOTE RESUME → desk halt cleared.")
            except Exception as exc:
                log.error("could not clear HALT: %s", exc)
            return "resumed(remote)"
        return "left manual halt in place"
    return "trading"


def sync_remote_halt(cfg=None) -> str:
    """Fetch the remote halt state and apply it to the local HALT file. Safe to call
    every cycle; a no-op when REMOTE_HALT_URL is unset (fetch → None, failsafe off
    for the unset case so an un-configured desk is never halted)."""
    if not os.getenv("REMOTE_HALT_URL", "").strip():
        return "disabled"   # feature off → never touch the HALT file
    failsafe = os.getenv("REMOTE_HALT_FAILSAFE", "true").strip().lower() not in ("0", "false", "no", "off")
    return apply_remote_halt(fetch_remote_halt(cfg), failsafe=failsafe)
