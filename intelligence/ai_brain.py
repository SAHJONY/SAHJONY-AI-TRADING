"""AI Brain & Counsellors — the firm's LLM advisory layer.

Hierarchy (as directed by the owner):
  • PRIMARY ENGINE / BRAIN  — Claude (Anthropic, `claude-opus-4-8`) via the
    official `anthropic` SDK. Acts as Chief Investment Strategist: it reads the
    quant council's per-symbol verdicts AND the two counsellors' opinions, then
    issues the authoritative advisory overlay.
  • SECONDARY ENGINES / COUNSELLORS — OpenAI (GPT) and Grok (xAI), each queried
    over its own REST API. Their views are inputs to the brain, not the final say.

This layer is an ADVISORY OVERLAY on the deterministic quant council — it nudges
conviction and a global risk posture; it never invents trades. It is fully
gated: with AI_BRAIN_ENABLED off (default) or a provider's key absent, that
engine is skipped and the system runs on pure quant signals. Every call is
wrapped so an API failure degrades to neutral, never crashing the trading loop.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import Config
from utils.logger import get_logger

log = get_logger("ai_brain")

_SYSTEM = (
    "You are the Chief Investment Strategist for {firm}, an automated, PAPER-trading "
    "quant fund. You receive a deterministic quant council's per-symbol verdicts and "
    "the opinions of two counsellor models. Your job is risk oversight and conviction "
    "calibration — NOT to invent trades. Be disciplined, skeptical, and capital-"
    "preservation-minded. Respond ONLY with JSON matching the requested schema."
)

# Per-symbol adjustment is clamped to a small range so the LLM can nudge, not hijack.
_MAX_ADJ = 0.15


@dataclass
class BrainVerdict:
    used: bool = False
    posture: str = "neutral"               # risk_on | neutral | risk_off
    global_risk_multiplier: float = 1.0    # 0.5 .. 1.2
    per_symbol_adjust: Dict[str, float] = field(default_factory=dict)
    commentary: str = ""
    brain_model: str = ""
    counsellors: Dict[str, str] = field(default_factory=dict)

    def adjust_for(self, symbol: str) -> float:
        return float(self.per_symbol_adjust.get(symbol, 0.0))


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return lo


class AIBrain:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.xai_key = os.getenv("XAI_API_KEY", "").strip()

    @property
    def enabled(self) -> bool:
        return self.cfg.ai_brain_enabled and bool(self.anthropic_key)

    @property
    def status(self) -> Dict[str, bool]:
        return {
            "enabled": self.cfg.ai_brain_enabled,
            "brain_claude": bool(self.anthropic_key),
            "counsellor_openai": bool(self.openai_key),
            "counsellor_grok": bool(self.xai_key),
        }

    # ── public entry point ────────────────────────────────────────────────────
    def advise(self, portfolio: List[Dict]) -> BrainVerdict:
        """portfolio: list of {symbol, price, conviction, direction, composite,
        alpha, beta, regime, vol}. Returns an advisory overlay (neutral if off)."""
        if not self.enabled or not portfolio:
            return BrainVerdict(used=False, commentary="AI brain disabled or no data")
        question = self._build_question(portfolio)
        counsellors = {}
        if self.openai_key:
            counsellors["openai"] = self._ask_openai(question)
        if self.xai_key:
            counsellors["grok"] = self._ask_grok(question)
        try:
            verdict = self._ask_claude(question, counsellors, [p["symbol"] for p in portfolio])
            verdict.counsellors = {k: (v or "")[:280] for k, v in counsellors.items()}
            return verdict
        except Exception as exc:  # brain failure → neutral overlay, never crash
            log.error("AI brain (Claude) failed: %s", exc)
            return BrainVerdict(used=False, commentary=f"brain error: {exc}",
                                counsellors={k: (v or "")[:280] for k, v in counsellors.items()})

    def _build_question(self, portfolio: List[Dict]) -> str:
        rows = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}
                for p in portfolio]
        return ("Quant council verdicts for the current cycle:\n"
                + json.dumps(rows, indent=2)
                + "\n\nAssess the overall risk posture and, per symbol, suggest a small "
                  "conviction adjustment in [-0.15, 0.15] (positive = more constructive). "
                  "Flag any symbol where the quant signal looks fragile.")

    # ── PRIMARY: Claude (official anthropic SDK) ──────────────────────────────
    def _ask_claude(self, question: str, counsellors: Dict[str, str],
                    symbols: List[str]) -> BrainVerdict:
        import anthropic  # imported lazily so the package is optional offline
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        counsel_text = "\n".join(f"- {name.upper()} counsellor says: {op}"
                                 for name, op in counsellors.items() if op) or "(no counsellors)"
        schema = {
            "type": "object",
            "properties": {
                "posture": {"type": "string", "enum": ["risk_on", "neutral", "risk_off"]},
                "global_risk_multiplier": {"type": "number"},
                "commentary": {"type": "string"},
                "per_symbol_adjust": {
                    "type": "object",
                    "properties": {s: {"type": "number"} for s in symbols},
                    "required": symbols,
                    "additionalProperties": False,
                },
            },
            "required": ["posture", "global_risk_multiplier", "commentary", "per_symbol_adjust"],
            "additionalProperties": False,
        }
        resp = client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            system=_SYSTEM.format(firm=self.cfg.firm_name),
            messages=[{"role": "user", "content": question + "\n\nCounsellor opinions:\n" + counsel_text}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
        adj = {s: _clamp(data.get("per_symbol_adjust", {}).get(s, 0.0), -_MAX_ADJ, _MAX_ADJ)
               for s in symbols}
        return BrainVerdict(
            used=True,
            posture=data.get("posture", "neutral"),
            global_risk_multiplier=_clamp(data.get("global_risk_multiplier", 1.0), 0.5, 1.2),
            per_symbol_adjust=adj,
            commentary=str(data.get("commentary", ""))[:600],
            brain_model=self.cfg.anthropic_model,
        )

    # ── SECONDARY: OpenAI (GPT) counsellor ────────────────────────────────────
    def _ask_openai(self, question: str) -> Optional[str]:
        return self._chat_completions(
            "https://api.openai.com/v1/chat/completions", self.openai_key,
            self.cfg.openai_model, question, label="openai")

    # ── SECONDARY: Grok (xAI) counsellor ──────────────────────────────────────
    def _ask_grok(self, question: str) -> Optional[str]:
        return self._chat_completions(
            "https://api.x.ai/v1/chat/completions", self.xai_key,
            self.cfg.xai_model, question, label="grok")

    def _chat_completions(self, url, key, model, question, label) -> Optional[str]:
        """OpenAI-compatible chat endpoint (both OpenAI and xAI speak it)."""
        try:
            import requests
            r = requests.post(url, timeout=30,
                              headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json"},
                              json={"model": model, "max_tokens": 400, "temperature": 0.3,
                                    "messages": [
                                        {"role": "system", "content":
                                         f"You are a counsellor to the Chief Strategist of "
                                         f"{self.cfg.firm_name}. Give a concise (<120 words) risk-"
                                         f"aware view on the portfolio. You advise; you do not decide."},
                                        {"role": "user", "content": question}]})
            if not r.ok:
                log.warning("%s counsellor HTTP %s", label, r.status_code)
                return None
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.warning("%s counsellor failed: %s", label, exc)
            return None
