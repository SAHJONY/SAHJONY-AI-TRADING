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
        # Telegram channel (text alerts) — needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        # WhatsApp via Meta WhatsApp Cloud API — needs WHATSAPP_TOKEN (permanent
        # access token) + WHATSAPP_PHONE_NUMBER_ID. Destination defaults to OWNER_PHONE.
        # Proactive (business-initiated) sends outside the 24h window require an
        # approved template: set WHATSAPP_TEMPLATE (name) + WHATSAPP_TEMPLATE_LANG.
        self.wa_token = os.getenv("WHATSAPP_TOKEN", "").strip()
        self.wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        self.wa_to = (os.getenv("WHATSAPP_TO", "") or self.owner_phone).strip()
        self.wa_template = os.getenv("WHATSAPP_TEMPLATE", "").strip()
        self.wa_template_lang = (os.getenv("WHATSAPP_TEMPLATE_LANG", "en_US") or "en_US").strip()
        self.wa_api = "https://graph.facebook.com/" + \
            (os.getenv("WHATSAPP_API_VERSION", "v21.0") or "v21.0").strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.tg_token and self.tg_chat)

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.wa_token and self.wa_phone_id and self.wa_to)

    @property
    def status(self) -> dict:
        return {"enabled": self.cfg.voice_alerts, "voice_configured": self.configured,
                "owner_phone_set": bool(self.owner_phone),
                "telegram_configured": self.telegram_configured,
                "whatsapp_configured": self.whatsapp_configured}

    def telegram_send(self, message: str) -> dict:
        """Send a Telegram message to the configured chat. Fault-isolated."""
        if not self.telegram_configured:
            return {"ok": False, "reason": "telegram_not_configured"}
        try:
            import requests
            r = requests.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                              timeout=15,
                              json={"chat_id": self.tg_chat, "text": message,
                                    "disable_web_page_preview": True})
            data = r.json() if r.content else {}
            if data.get("ok"):
                log.info("Telegram alert sent to chat %s", self.tg_chat)
                return {"ok": True}
            log.warning("Telegram send failed: %s", data.get("description"))
            return {"ok": False, "reason": data.get("description", "http_" + str(r.status_code))}
        except Exception as exc:
            log.error("telegram_send failed: %s", exc)
            return {"ok": False, "reason": str(exc)}

    def whatsapp_send(self, message: str) -> dict:
        """Send a WhatsApp message via Meta's WhatsApp Cloud API. Fault-isolated.

        Uses a free-form text message by default (works only inside the 24h
        customer-service window). If WHATSAPP_TEMPLATE is set, sends that approved
        template instead with `message` as its first body parameter — required for
        proactive, business-initiated alerts outside the 24h window."""
        if not self.whatsapp_configured:
            return {"ok": False, "reason": "whatsapp_not_configured"}
        to = self.wa_to.lstrip("+")   # Cloud API wants E.164 digits, no '+'
        if self.wa_template:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                       "template": {"name": self.wa_template,
                                    "language": {"code": self.wa_template_lang},
                                    "components": [{"type": "body", "parameters": [
                                        {"type": "text", "text": message[:1024]}]}]}}
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
                       "text": {"body": message[:4096]}}
        try:
            import requests
            r = requests.post(f"{self.wa_api}/{self.wa_phone_id}/messages", timeout=20,
                              headers={"Authorization": "Bearer " + self.wa_token,
                                       "Content-Type": "application/json"}, json=payload)
            data = r.json() if r.content else {}
            if r.ok and data.get("messages"):
                log.info("WhatsApp alert sent to %s", to)
                return {"ok": True, "id": data["messages"][0].get("id")}
            err = (data.get("error") or {}).get("message", "http_" + str(r.status_code))
            log.warning("WhatsApp send failed: %s", err)
            return {"ok": False, "reason": err}
        except Exception as exc:
            log.error("whatsapp_send failed: %s", exc)
            return {"ok": False, "reason": str(exc)}

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
        """Alert policy: fire when something notable happened — an executed action
        this cycle or an AI-brain risk-off posture.

        Channel gating:
          • Telegram = ALWAYS-ON (fires whenever configured, independent of any
            master switch) — the owner's designated primary channel.
          • Voice (Bland) + WhatsApp = "active outreach", gated by VOICE_ALERTS so
            they can be muted without touching Telegram."""
        push = bool(self.cfg.voice_alerts)   # gates voice + WhatsApp only
        if not (self.telegram_configured
                or (push and self.whatsapp_configured)
                or (push and self.configured and self.owner_phone)):
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
        results = {}
        tagged = "📊 " + self.cfg.firm_name + " — " + msg
        if self.telegram_configured:                       # always-on
            results["telegram"] = self.telegram_send(tagged)
        if push and self.whatsapp_configured:
            results["whatsapp"] = self.whatsapp_send(tagged)
        if push and self.configured and self.owner_phone:
            results["voice"] = self.voice_call(msg)
        return results or None

    def maybe_weekly_summary(self, status: dict, state: dict) -> Optional[dict]:
        """No-hype weekly performance digest to Telegram. Self-gating: fires at most
        once every 7 days via state['last_weekly_report'] (so it's safe to call every
        cycle). Telegram-only — independent of the voice/VOICE_ALERTS switch."""
        if not self.telegram_configured:
            return None
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        last = state.get("last_weekly_report")
        if last:
            try:
                if now - datetime.fromisoformat(last) < timedelta(days=7):
                    return None
            except Exception:
                pass
        acc = status.get("account", {}) or {}
        p = status.get("pnl", {}) or {}
        b = status.get("benchmark", {}) or {}
        curve = status.get("equity_curve", []) or []
        peak, maxdd = float("-inf"), 0.0
        for pt in curve:
            e = float(pt.get("equity", 0) or 0); peak = max(peak, e)
            if peak > 0:
                maxdd = min(maxdd, (e - peak) / peak * 100)
        rets = []
        for i in range(1, len(curve)):
            a = float(curve[i-1].get("equity", 0) or 0); c = float(curve[i].get("equity", 0) or 0)
            if a > 0:
                rets.append(c / a - 1)
        winrate = (sum(1 for r in rets if r > 0) / len(rets) * 100) if rets else 0.0
        lines = [f"📈 {status.get('firm', 'SAHJONY')} — Weekly Report",
                 f"Cycle {status.get('cycle')} · {status.get('mode')}",
                 f"Equity ${acc.get('equity', 0):,.0f} (start ${acc.get('equity_start', 0):,.0f})",
                 f"Return {p.get('total_return_pct', 0.0):+.2f}%"]
        if b.get("alpha_pct") is not None:
            lines.append(f"Alpha vs {b.get('symbol', 'SPY')} {b['alpha_pct']:+.2f}% "
                         f"(SPY {b.get('return_pct', 0.0):+.2f}%)")
        lines += [f"Max drawdown {maxdd:.2f}%",
                  f"Cycle win rate {winrate:.0f}% · {len(curve)} cycles · {len(status.get('recent_trades', []) or [])} recent trades"]
        if len(curve) < 30:
            lines.append("⚠ Small sample — treat as noise until ~30+ cycles.")
        lines.append("Dashboard: https://sahjony.github.io/SAHJONY-AI-TRADING/")
        res = self.telegram_send("\n".join(lines))
        state["last_weekly_report"] = now.isoformat()   # persisted by the caller
        return res


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="notify", description="Bland.ai voice comms")
    ap.add_argument("--test", action="store_true", help="place a test voice call")
    ap.add_argument("--telegram", action="store_true", help="send a test Telegram message")
    ap.add_argument("--whatsapp", action="store_true", help="send a test WhatsApp message")
    ap.add_argument("--phone", help="destination (defaults to OWNER_PHONE)")
    ap.add_argument("--message", default="This is a test from SAHJONY CAPITAL LLC. Comms are working.")
    args = ap.parse_args(argv)
    n = Notifier(load_config())
    print("status:", n.status)
    if args.telegram:
        print("telegram:", n.telegram_send("✅ " + args.message))
    if args.whatsapp:
        print("whatsapp:", n.whatsapp_send("✅ " + args.message))
    if args.test:
        print("voice:", n.voice_call(args.message, args.phone))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
