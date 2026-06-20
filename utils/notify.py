"""Voice comms via Bland.ai — phone alerts to the owner / investors.

The firm can place an outbound call (e.g. on executed trades, a risk-off posture,
or a daily summary). Fully gated: needs VOICE_API_KEY + a destination phone
(OWNER_PHONE) and VOICE_ALERTS=true. Every call is wrapped so a comms failure
never affects trading. Also exposes a CLI for a test call:

    python -m utils.notify --test --phone +1XXXXXXXXXX
"""
from __future__ import annotations

import argparse
import os
from typing import Optional

from config import Config, load_config
from utils.logger import get_logger

log = get_logger("notify")

BLAND_URL = "https://api.bland.ai/v1/calls"
_MAX_TASK_CHARS = 1500


class Notifier:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api_key = os.getenv("VOICE_API_KEY", "").strip()
        self.from_number = os.getenv("VOICE_FROM_NUMBER", "").strip()
        self.owner_phone = os.getenv("OWNER_PHONE", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> dict:
        return {"enabled": self.cfg.voice_alerts, "voice_configured": self.configured,
                "owner_phone_set": bool(self.owner_phone)}

    def voice_call(self, message: str, phone: Optional[str] = None) -> dict:
        """Place a Bland.ai voice call delivering `message`. Returns a result dict."""
        phone = (phone or self.owner_phone).strip()
        if not self.api_key:
            return {"ok": False, "reason": "voice_not_configured"}
        if not phone:
            return {"ok": False, "reason": "no_destination_phone"}
        task = ("You are the automated voice line for " + self.cfg.firm_name +
                ", a paper-trading quant fund. Deliver this update clearly and briefly, "
                "then end the call: " + message)[:_MAX_TASK_CHARS]
        payload = {"phone_number": phone, "task": task,
                   "voice": self.cfg.voice_name, "language": self.cfg.voice_language,
                   "max_duration": 2}
        if self.from_number:
            payload["from"] = self.from_number
        try:
            import requests
            r = requests.post(BLAND_URL, timeout=25,
                              headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                              json=payload)
            ok = r.ok
            data = r.json() if r.content else {}
            if ok:
                log.info("Voice call queued to %s (id=%s)", phone, data.get("call_id"))
                return {"ok": True, "call_id": data.get("call_id")}
            log.warning("Bland.ai HTTP %s: %s", r.status_code, data)
            return {"ok": False, "reason": "http_" + str(r.status_code), "detail": data}
        except Exception as exc:
            log.error("voice_call failed: %s", exc)
            return {"ok": False, "reason": str(exc)}

    def maybe_alert(self, status: dict) -> Optional[dict]:
        """Alert policy: only call when enabled AND something notable happened —
        an executed action this cycle or an AI-brain risk-off posture."""
        if not (self.cfg.voice_alerts and self.configured and self.owner_phone):
            return None
        executed = status.get("executed_this_cycle", [])
        posture = (status.get("brain", {}) or {}).get("posture", "neutral")
        if not executed and posture != "risk_off":
            return None
        a, p = status["account"], status["pnl"]
        acts = ", ".join(f"{e['symbol']} {e['purpose']}" for e in executed[:4]) or "no new trades"
        msg = (f"Cycle {status.get('cycle')} update. Equity {a['equity']:,.0f} dollars, "
               f"return {p['total_return_pct']:+.2f} percent. Posture {posture}. "
               f"Actions: {acts}.")
        return self.voice_call(msg)


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="notify", description="Bland.ai voice comms")
    ap.add_argument("--test", action="store_true", help="place a test call")
    ap.add_argument("--phone", help="destination (defaults to OWNER_PHONE)")
    ap.add_argument("--message", default="This is a test call from SAHJONY CAPITAL LLC. Voice comms are working.")
    args = ap.parse_args(argv)
    n = Notifier(load_config())
    print("status:", n.status)
    if args.test:
        print(n.voice_call(args.message, args.phone))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
