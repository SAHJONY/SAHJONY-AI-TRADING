"""AI Brain & Counsellors — the firm's LLM advisory layer.

Hierarchy (as directed by the owner):
  • PRIMARY ENGINE / BRAIN  — Claude (Anthropic, `claude-fable-5`) via the
    official `anthropic` SDK. Acts as Chief Investment Strategist: it reads the
    quant council's per-symbol verdicts AND the two counsellors' opinions, then
    issues the authoritative advisory overlay.
  • CO-STRATEGIST / FALLBACK — OpenAI's frontier GPT model through the Responses
    API with strict structured output. Its view advises Claude and it can produce
    the same bounded overlay if Claude is unavailable.
  • SECONDARY COUNSELLORS — Grok (xAI), Gemini (Google), and NVIDIA NIM.

This layer is an ADVISORY OVERLAY on the deterministic quant council — it nudges
conviction and a global risk posture; it never invents trades. It is fully
gated: with AI_BRAIN_ENABLED off (default) or a provider's key absent, that
engine is skipped and the system runs on pure quant signals. Every call is
wrapped so an API failure degrades to neutral, never crashing the trading loop.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


def _overlay_schema(symbols: List[str]) -> Dict:
    return {
        "type": "object",
        "properties": {
            "posture": {"type": "string", "enum": ["risk_on", "neutral", "risk_off"]},
            "global_risk_multiplier": {"type": "number"},
            "commentary": {"type": "string"},
            "per_symbol_adjust": {
                "type": "object", "properties": {s: {"type": "number"} for s in symbols},
                "required": symbols, "additionalProperties": False,
            },
        },
        "required": ["posture", "global_risk_multiplier", "commentary", "per_symbol_adjust"],
        "additionalProperties": False,
    }


def _estimated_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost from published per-million-token rates.

    Raw token counts are retained in telemetry so reports can be repriced later.
    Environment overrides allow rate updates without a code deployment.
    """
    model_lower = model.lower()
    defaults = (0.0, 0.0)
    if provider == "anthropic" and "fable-5" in model_lower:
        defaults = (10.0, 50.0)
    elif provider == "openai" and ("5.6-sol" in model_lower or model_lower == "gpt-5.6"):
        defaults = (5.0, 30.0)
    elif provider == "openai" and "5.6-terra" in model_lower:
        defaults = (2.5, 15.0)
    elif provider == "openai" and "5.6-luna" in model_lower:
        defaults = (1.0, 6.0)
    prefix = provider.upper()
    try:
        input_rate = float(os.getenv(f"{prefix}_INPUT_USD_PER_MTOK", defaults[0]))
        output_rate = float(os.getenv(f"{prefix}_OUTPUT_USD_PER_MTOK", defaults[1]))
    except (TypeError, ValueError):
        input_rate, output_rate = defaults
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)


@dataclass
class BrainVerdict:
    used: bool = False
    posture: str = "neutral"               # risk_on | neutral | risk_off
    global_risk_multiplier: float = 1.0    # 0.5 .. 1.2
    per_symbol_adjust: Dict[str, float] = field(default_factory=dict)
    commentary: str = ""
    brain_model: str = ""
    counsellors: Dict[str, str] = field(default_factory=dict)
    telemetry: Dict[str, Any] = field(default_factory=dict)

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
        self._last_openai_meta: Dict[str, Any] = {}
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
        return self.cfg.ai_brain_enabled and bool(
            self.anthropic_key or self.openai_key or self.nvidia_key
        )

    @property
    def status(self) -> Dict[str, object]:
        return {
            "enabled": self.cfg.ai_brain_enabled,
            "brain_claude": bool(self.anthropic_key),
            "counsellor_openai": bool(self.openai_key),
            "openai_fallback": bool(self.openai_key),
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
                if self.openai_key:
                    try:
                        log.warning("falling back to OpenAI Responses brain")
                        return _wrap(self._ask_openai_brain(
                            question, counsellors, symbols, fallback_used=True
                        ))
                    except Exception as exc2:
                        log.error("OpenAI fallback failed: %s", exc2)
                if self.nvidia_key:
                    try:
                        log.warning("falling back to NVIDIA NIM brain")
                        return _wrap(self._ask_nim_brain(question, counsellors, symbols))
                    except Exception as exc2:
                        log.error("NVIDIA NIM fallback failed: %s", exc2)
                        return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc2}"))
                return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc}"))
        if self.openai_key:
            try:
                return _wrap(self._ask_openai_brain(
                    question, counsellors, symbols, fallback_used=False
                ))
            except Exception as exc:
                log.error("OpenAI brain failed: %s", exc)
                if not self.nvidia_key:
                    return _wrap(BrainVerdict(used=False, commentary=f"brain error: {exc}"))
        # No working Claude/OpenAI → NVIDIA NIM is the last-resort brain.
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

    def shadow_advise(self, portfolio: List[Dict], selected: BrainVerdict) -> Dict[str, Dict]:
        """Produce comparable hypothetical overlays; never used for execution."""
        question = self._build_question(portfolio)
        symbols = [row["symbol"] for row in portfolio]
        outputs: Dict[str, BrainVerdict] = {}
        selected_provider = str(selected.telemetry.get("provider", ""))
        if selected_provider == "anthropic":
            selected_provider = "claude"
        if selected.used and selected_provider:
            outputs[selected_provider] = selected
        candidates = (
            ("claude", bool(self.anthropic_key),
             lambda: self._ask_claude(question, {}, symbols)),
            ("openai", bool(self.openai_key),
             lambda: self._ask_openai_brain(question, {}, symbols)),
            ("gemini", bool(self.gemini_key),
             lambda: self._shadow_compatible_brain(
                 "gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                 self.gemini_key, self.gemini_model, question, symbols)),
            ("grok", bool(self.xai_key),
             lambda: self._shadow_compatible_brain(
                 "grok", "https://api.x.ai/v1/chat/completions",
                 self.xai_key, self.grok_model, question, symbols)),
            ("nvidia", bool(self.nvidia_key),
             lambda: self._ask_nim_brain(question, {}, symbols)),
        )
        for provider, available, call in candidates:
            if not available or provider in outputs:
                continue
            try:
                outputs[provider] = call()
            except Exception as exc:
                log.warning("shadow provider %s failed: %s", provider, exc)
        return {
            provider: {
                "per_symbol_adjust": verdict.per_symbol_adjust,
                "risk_multiplier": verdict.global_risk_multiplier,
                "telemetry": verdict.telemetry,
            }
            for provider, verdict in outputs.items()
        }

    def _shadow_compatible_brain(self, provider: str, url: str, key: str, model: str,
                                 question: str, symbols: List[str]) -> BrainVerdict:
        started = time.perf_counter()
        verdict = self._oai_brain(url, key, model, question, {}, symbols, label=provider)
        verdict.telemetry = {
            "provider": provider, "requested_model": model, "resolved_model": model,
            "fallback_used": False, "schema_valid": True,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
            "conviction_adjustment": verdict.per_symbol_adjust,
            "risk_multiplier": verdict.global_risk_multiplier, "clamp_applied": False,
        }
        return verdict

    # ── PRIMARY: Claude (official anthropic SDK) ──────────────────────────────
    def _ask_claude(self, question: str, counsellors: Dict[str, str],
                    symbols: List[str]) -> BrainVerdict:
        import anthropic  # imported lazily so the package is optional offline
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        counsel_text = "\n".join(f"- {name.upper()} counsellor says: {op}"
                                 for name, op in counsellors.items() if op) or "(no counsellors)"
        schema = _overlay_schema(symbols)
        # Claude Fable 5 (the primary brain) keeps thinking always on — we pass
        # {type:"adaptive"} (any other explicit config 400s) and steer depth via
        # output_config.effort. Safety classifiers can decline a request with
        # stop_reason=="refusal"; we opt into the server-side fallback beta so a
        # decline is transparently re-served by Opus 4.8 inside the same call
        # (false positives on benign quant work do happen). This is forward-
        # compatible: Opus-tier models accept the same request shape.
        started = time.perf_counter()
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
        raw_adj = {s: data.get("per_symbol_adjust", {}).get(s, 0.0) for s in symbols}
        adj = {s: _clamp(raw_adj[s], -_MAX_ADJ, _MAX_ADJ) for s in symbols}
        raw_risk = data.get("global_risk_multiplier", 1.0)
        risk = _clamp(raw_risk, 0.5, 1.2)
        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return BrainVerdict(
            used=True,
            posture=data.get("posture", "neutral"),
            global_risk_multiplier=risk,
            per_symbol_adjust=adj,
            commentary=str(data.get("commentary", ""))[:600],
            brain_model=self.brain_model,
            telemetry={
                "provider": "anthropic", "requested_model": self.cfg.anthropic_model,
                "resolved_model": self.brain_model, "fallback_used": False,
                "schema_valid": True,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "estimated_cost_usd": _estimated_cost(
                    "anthropic", self.brain_model, input_tokens, output_tokens
                ),
                "conviction_adjustment": adj, "risk_multiplier": risk,
                "clamp_applied": risk != raw_risk or any(adj[s] != raw_adj[s] for s in symbols),
            },
        )

    # ── SECONDARY: OpenAI (GPT) counsellor ────────────────────────────────────
    def _ask_openai(self, question: str) -> Optional[str]:
        try:
            schema = {
                "type": "object",
                "properties": {
                    "risk_summary": {"type": "string"},
                    "fragilities": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["risk_summary", "fragilities", "confidence"],
                "additionalProperties": False,
            }
            data = self._openai_response_json(question, schema, "portfolio_risk_counsel")
            data["confidence"] = _clamp(data.get("confidence", 0.0), 0.0, 1.0)
            return json.dumps(data, separators=(",", ":"))
        except Exception as exc:
            log.warning("openai counsellor failed (model=%s): %s", self.openai_model, exc)
            return None

    def _openai_response_json(self, prompt: str, schema: Dict, schema_name: str) -> Dict:
        """Use the OpenAI Responses API with strict structured output."""
        import requests
        payload = {
            "model": self.openai_model,
            "instructions": _SYSTEM.format(firm=self.cfg.firm_name),
            "input": prompt,
            "max_output_tokens": 2000,
            "reasoning": {"effort": "high"},
            "text": {"format": {"type": "json_schema", "name": schema_name,
                                 "strict": True, "schema": schema}},
        }
        started = time.perf_counter()
        response = requests.post(
            "https://api.openai.com/v1/responses", timeout=60,
            headers={"Authorization": "Bearer " + self.openai_key,
                     "Content-Type": "application/json"}, json=payload,
        )
        if not response.ok:
            raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:200]}")
        body = response.json()
        usage = body.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        resolved_model = body.get("model") or self.openai_model
        self._last_openai_meta = {
            "provider": "openai", "requested_model": self.cfg.openai_model,
            "resolved_model": resolved_model,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "estimated_cost_usd": _estimated_cost(
                "openai", resolved_model, input_tokens, output_tokens
            ),
        }
        text = body.get("output_text") or ""
        if not text:
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")
        if not text:
            raise RuntimeError("OpenAI Responses returned no output_text")
        return self._extract_json(text)

    def _ask_openai_brain(self, question: str, counsellors: Dict[str, str],
                          symbols: List[str], fallback_used: bool = False) -> BrainVerdict:
        counsel_text = "\n".join(f"- {n.upper()}: {op}" for n, op in counsellors.items()
                                 if n != "openai" and op) or "(no other counsellors)"
        data = self._openai_response_json(
            question + "\n\nOther counsellor opinions:\n" + counsel_text,
            _overlay_schema(symbols), "portfolio_risk_overlay",
        )
        posture = str(data.get("posture", "neutral"))
        if posture not in {"risk_on", "neutral", "risk_off"}:
            posture = "neutral"
        raw_adj = {s: data.get("per_symbol_adjust", {}).get(s, 0.0) for s in symbols}
        adjusted = {s: _clamp(raw_adj[s], -_MAX_ADJ, _MAX_ADJ) for s in symbols}
        raw_risk = data.get("global_risk_multiplier", 1.0)
        risk = _clamp(raw_risk, 0.5, 1.2)
        telemetry = dict(self._last_openai_meta)
        telemetry.update({
            "fallback_used": fallback_used, "schema_valid": True,
            "conviction_adjustment": adjusted, "risk_multiplier": risk,
            "clamp_applied": risk != raw_risk or any(
                adjusted[s] != raw_adj[s] for s in symbols
            ),
        })
        return BrainVerdict(
            used=True, posture=posture,
            global_risk_multiplier=risk, per_symbol_adjust=adjusted,
            commentary=str(data.get("commentary", ""))[:600],
            brain_model=f"openai:{self.openai_model}",
            telemetry=telemetry,
        )

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
            headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
            payload = {"model": model, "max_tokens": 400, "temperature": 0.3,
                       "messages": [
                           {"role": "system", "content":
                            f"You are a counsellor to the Chief Strategist of "
                            f"{self.cfg.firm_name}. Give a concise (<120 words) risk-"
                            f"aware view on the portfolio. You advise; you do not decide."},
                           {"role": "user", "content": question}]}
            r = requests.post(url, timeout=45, headers=headers, json=payload)
            # GPT-5-family reasoning models reject the classic chat params: they want
            # 'max_completion_tokens' (not 'max_tokens') and only the default
            # temperature. The API reports these ONE AT A TIME, so a single-param
            # retry just trips the next complaint — apply BOTH known fixes together
            # when a 400 names either, then retry once.
            if r.status_code == 400 and ("max_tokens" in (r.text or "").lower()
                                         or "temperature" in (r.text or "").lower()):
                payload["max_completion_tokens"] = payload.pop("max_tokens", 400)
                payload.pop("temperature", None)
                r = requests.post(url, timeout=45, headers=headers, json=payload)
            if not r.ok:
                # Log the model tried AND the provider's error body: a 4xx body says
                # exactly why (model_not_found vs invalid_api_key vs quota), which the
                # bare status code hides — this is what makes the failure diagnosable.
                log.warning("%s counsellor HTTP %s (model=%s): %s",
                            label, r.status_code, model, (r.text or "")[:200].replace("\n", " "))
                return None
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.warning("%s counsellor failed (model=%s): %s", label, model, exc)
            return None
