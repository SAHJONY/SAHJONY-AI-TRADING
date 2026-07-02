"""AI Brain & Counsellors — the firm's LLM advisory layer.

Hierarchy (as directed by the owner):
  • PRIMARY ENGINE / BRAIN  — Claude (Anthropic, `claude-fable-5`) via the
    official `anthropic` SDK. Acts as Chief Investment Strategist: it reads the
    quant council's per-symbol verdicts AND the two counsellors' opinions, then
    issues the authoritative advisory overlay.
  • SECONDARY ENGINES / COUNSELLORS — OpenAI (GPT), Grok (xAI) and Gemini
    (Google), each queried over its (OpenAI-compatible) REST API. Their views are
    inputs to the brain, not the final say.

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
        # Gemini accepts either GEMINI_API_KEY or Google's GOOGLE_API_KEY.
        self.gemini_key = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
        # NVIDIA NIM — free, OpenAI-compatible. Doubles as a counsellor AND the
        # last-resort fallback brain when Claude is absent or fails.
        self.nvidia_key = (os.getenv("NVIDIA_API_KEY", "") or os.getenv("NVIDIA_NIM_API_KEY", "")).strip()
        self.nvidia_base = (os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
                            or "https://integrate.api.nvidia.com/v1").strip().rstrip("/")
        self.nvidia_model = (os.getenv("NVIDIA_MODEL", "openai/gpt-oss-120b")
                             or "openai/gpt-oss-120b").strip()
        # Autonomously resolve each provider's latest model (cached ~daily). Falls
        # back to the configured defaults whenever the lookup can't run.
        self.brain_model = cfg.anthropic_model
        self.openai_model = cfg.openai_model
        self.grok_model = cfg.xai_model
        self.gemini_model = cfg.gemini_model
        if cfg.auto_update_models:
            try:
                from utils.model_registry import resolve_all
                latest = resolve_all(
                    {"anthropic": self.anthropic_key, "openai": self.openai_key,
                     "xai": self.xai_key, "gemini": self.gemini_key},
                    {"anthropic": cfg.anthropic_model, "openai": cfg.openai_model,
                     "xai": cfg.xai_model, "gemini": cfg.gemini_model},
                )
                self.brain_model = latest["anthropic"] or self.brain_model
                self.openai_model = latest["openai"] or self.openai_model
                self.grok_model = latest["xai"] or self.grok_model
                self.gemini_model = latest["gemini"] or self.gemini_model
            except Exception as exc:  # never let model discovery break the brain
                log.warning("auto model update skipped: %s", exc)

    @property
    def enabled(self) -> bool:
        # NVIDIA NIM can serve as the brain on its own (free testing / fallback),
        # so the overlay is live with either a Claude key or an NVIDIA key.
        return self.cfg.ai_brain_enabled and (bool(self.anthropic_key) or bool(self.nvidia_key))

    @property
    def status(self) -> Dict[str, object]:
        return {
            "enabled": self.cfg.ai_brain_enabled,
            "brain_claude": bool(self.anthropic_key),
            "counsellor_openai": bool(self.openai_key),
            "counsellor_grok": bool(self.xai_key),
            "counsellor_gemini": bool(self.gemini_key),
            "counsellor_nvidia": bool(self.nvidia_key),
            "nvidia_fallback": bool(self.nvidia_key),
            "auto_update_models": self.cfg.auto_update_models,
            "models": {"brain": self.brain_model, "openai": self.openai_model,
                       "grok": self.grok_model, "gemini": self.gemini_model,
                       "nvidia": (self.nvidia_model if self.nvidia_key else "")},
        }

    # ── public entry point ────────────────────────────────────────────────────
    def advise(self, portfolio: List[Dict]) -> BrainVerdict:
        """portfolio: list of {symbol, price, conviction, direction, composite,
        alpha, beta, regime, vol}. Returns an advisory overlay (neutral if off)."""
        if not self.enabled or not portfolio:
            return BrainVerdict(used=False, commentary="AI brain disabled or no data")
        question = self._build_question(portfolio)
        symbols = [p["symbol"] for p in portfolio]
        counsellors = {}
        if self.openai_key:
            counsellors["openai"] = self._ask_openai(question)
        if self.xai_key:
            counsellors["grok"] = self._ask_grok(question)
        if self.gemini_key:
            counsellors["gemini"] = self._ask_gemini(question)
        if self.nvidia_key:
            counsellors["nvidia"] = self._ask_nvidia(question)

        def _wrap(v: BrainVerdict) -> BrainVerdict:
            v.counsellors = {k: (val or "")[:280] for k, val in counsellors.items()}
            return v

        # PRIMARY brain: Claude. LAST-RESORT FALLBACK: NVIDIA NIM (free, OpenAI-
        # compatible). Either failure degrades to neutral — never crashes the loop.
        if self.anthropic_key:
            try:
                return _wrap(self._ask_claude(question, counsellors, symbols))
            except Exception as exc:
                log.error("AI brain (Claude) failed: %s", exc)
                if self.nvidia_key:
                    try:
                        log.warning("falling back to NVIDIA NIM brain")
                        return _wrap(self._ask_nim_brain(question, counsellors, symbols))
                    except Exception as exc2:
                        log.error("NVIDIA NIM fallback failed: %s", exc2)
                        return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc2}"))
                return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc}"))
        # No Claude key → NVIDIA NIM is the brain (free testing / last resort).
        if self.nvidia_key:
            try:
                return _wrap(self._ask_nim_brain(question, counsellors, symbols))
            except Exception as exc:
                log.error("NVIDIA NIM brain failed: %s", exc)
                return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc}"))
        return _wrap(BrainVerdict(used=False, commentary="no brain provider configured"))

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
        # Claude Fable 5 (the primary brain) keeps thinking always on — we pass
        # {type:"adaptive"} (any other explicit config 400s) and steer depth via
        # output_config.effort. Safety classifiers can decline a request with
        # stop_reason=="refusal"; we opt into the server-side fallback beta so a
        # decline is transparently re-served by Opus 4.8 inside the same call
        # (false positives on benign quant work do happen). This is forward-
        # compatible: Opus-tier models accept the same request shape.
        resp = client.beta.messages.create(
            model=self.brain_model,
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": "claude-opus-4-8"}],
            # headroom for adaptive thinking: thinking tokens count toward max_tokens,
            # so a tight cap can truncate the JSON overlay and degrade the brain to neutral.
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            system=_SYSTEM.format(firm=self.cfg.firm_name),
            messages=[{"role": "user", "content": question + "\n\nCounsellor opinions:\n" + counsel_text}],
        )
        # Always inspect stop_reason before reading content: a refusal carries an
        # empty content array, so parsing it blind would look like a broken brain.
        if getattr(resp, "stop_reason", None) == "refusal":
            raise RuntimeError("Claude declined the request (stop_reason=refusal)")
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "{}")
        data = json.loads(text)
        adj = {s: _clamp(data.get("per_symbol_adjust", {}).get(s, 0.0), -_MAX_ADJ, _MAX_ADJ)
               for s in symbols}
        return BrainVerdict(
            used=True,
            posture=data.get("posture", "neutral"),
            global_risk_multiplier=_clamp(data.get("global_risk_multiplier", 1.0), 0.5, 1.2),
            per_symbol_adjust=adj,
            commentary=str(data.get("commentary", ""))[:600],
            brain_model=self.brain_model,
        )

    # ── SECONDARY: OpenAI (GPT) counsellor ────────────────────────────────────
    def _ask_openai(self, question: str) -> Optional[str]:
        return self._chat_completions(
            "https://api.openai.com/v1/chat/completions", self.openai_key,
            self.openai_model, question, label="openai")

    # ── SECONDARY: Grok (xAI) counsellor ──────────────────────────────────────
    def _ask_grok(self, question: str) -> Optional[str]:
        return self._chat_completions(
            "https://api.x.ai/v1/chat/completions", self.xai_key,
            self.grok_model, question, label="grok")

    # ── SECONDARY: Gemini (Google) counsellor ─────────────────────────────────
    # Google exposes an OpenAI-compatible endpoint, so it speaks the same protocol.
    def _ask_gemini(self, question: str) -> Optional[str]:
        return self._chat_completions(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            self.gemini_key, self.gemini_model, question, label="gemini")

    # ── SECONDARY: NVIDIA NIM counsellor (free, OpenAI-compatible) ─────────────
    def _ask_nvidia(self, question: str) -> Optional[str]:
        return self._chat_completions(
            self.nvidia_base + "/chat/completions", self.nvidia_key,
            self.nvidia_model, question, label="nvidia")

    # ── FALLBACK BRAIN: NVIDIA NIM produces the structured overlay itself ──────
    # Used when Claude is absent or fails. OpenAI-compatible JSON-mode request.
    def _ask_nim_brain(self, question: str, counsellors: Dict[str, str],
                       symbols: List[str]) -> BrainVerdict:
        return self._oai_brain(self.nvidia_base + "/chat/completions", self.nvidia_key,
                               self.nvidia_model, question, counsellors, symbols, label="nvidia")

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = (text or "").strip()
        try:
            return json.loads(text)
        except Exception:
            i, j = text.find("{"), text.rfind("}")
            if i != -1 and j != -1 and j > i:
                return json.loads(text[i:j + 1])
            raise ValueError("no JSON object in response")

    def _oai_brain(self, url, key, model, question, counsellors, symbols, label) -> BrainVerdict:
        """Brain verdict via any OpenAI-compatible chat endpoint (e.g. NVIDIA NIM)."""
        import requests
        counsel_text = "\n".join(f"- {n.upper()} counsellor says: {op}"
                                 for n, op in counsellors.items() if op) or "(no counsellors)"
        instr = (question + "\n\nCounsellor opinions:\n" + counsel_text +
                 "\n\nRespond ONLY with a JSON object with keys: "
                 '"posture" (one of "risk_on","neutral","risk_off"), '
                 '"global_risk_multiplier" (number 0.5-1.2), "commentary" (string), '
                 '"per_symbol_adjust" (object mapping each symbol to a number in [-0.15,0.15]). '
                 "Symbols: " + ", ".join(symbols) + ".")
        payload = {"model": model, "max_tokens": 1500, "temperature": 0.2,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": _SYSTEM.format(firm=self.cfg.firm_name)},
                                {"role": "user", "content": instr}]}
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        r = requests.post(url, timeout=45, headers=headers, json=payload)
        if not r.ok and r.status_code in (400, 404, 415, 422):
            # some NIM models reject json_object response_format → retry plain
            payload.pop("response_format", None)
            r = requests.post(url, timeout=45, headers=headers, json=payload)
        if not r.ok:
            raise RuntimeError(f"{label} HTTP {r.status_code}: {r.text[:200]}")
        text = r.json()["choices"][0]["message"]["content"]
        data = self._extract_json(text)
        adj = {s: _clamp(data.get("per_symbol_adjust", {}).get(s, 0.0), -_MAX_ADJ, _MAX_ADJ)
               for s in symbols}
        return BrainVerdict(
            used=True,
            posture=str(data.get("posture", "neutral")),
            global_risk_multiplier=_clamp(data.get("global_risk_multiplier", 1.0), 0.5, 1.2),
            per_symbol_adjust=adj,
            commentary=str(data.get("commentary", ""))[:600],
            brain_model=f"{label}:{model}",
        )

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
