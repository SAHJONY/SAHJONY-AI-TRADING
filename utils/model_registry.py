"""Autonomous model updater — always run on each provider's LATEST model.

The owner's standing directive: keep the AI brain and its counsellors on the
newest model each provider offers, without hand-editing model IDs. This module
queries each provider's public *models* endpoint, picks the newest model in the
preferred tier, and caches the answer so we don't re-query every cycle.

Hierarchy preserved (CLAUDE.md): Claude is the PRIMARY brain (we prefer the
latest **Opus**), OpenAI (GPT) and Grok (xAI) are counsellors (latest flagship).

Fault isolation: every lookup is wrapped. No key, no network, a slow/odd API —
any failure falls back to the configured default model. The trading loop never
depends on this succeeding; it only ever *upgrades* the model when it safely can.

How "latest" is chosen: among a provider's chat models we keep those matching the
preferred family (e.g. "opus"), drop non-chat/utility variants, and take the one
with the newest creation date the API reports. Newest-in-tier, not "most hyped".
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from paths import model_cache_path
from utils.logger import get_logger

log = get_logger("model_registry")

_DEFAULT_TTL_HOURS = 24.0
# substrings that mark a NON-chat / non-flagship variant we never want to pick
_EXCLUDE = ("embed", "whisper", "tts", "audio", "realtime", "moderation",
            "dall-e", "image", "vision-only", "search", "transcribe", "instruct")


def _refresh_hours() -> float:
    try:
        return max(0.0, float(os.getenv("MODEL_REFRESH_HOURS", _DEFAULT_TTL_HOURS)))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_HOURS


def _ok_id(model_id: str) -> bool:
    mid = model_id.lower()
    return not any(x in mid for x in _EXCLUDE)


def _pick_latest(models: List[Dict], prefer: Tuple[str, ...]) -> Optional[str]:
    """models: [{'id','created'}] with created as a sortable number (epoch).
    Prefer the newest id whose name contains any 'prefer' keyword; if none match,
    the newest acceptable chat id overall."""
    usable = [m for m in models if m.get("id") and _ok_id(m["id"])]
    if not usable:
        return None
    usable.sort(key=lambda m: m.get("created", 0), reverse=True)
    for kw in prefer:
        for m in usable:
            if kw in m["id"].lower():
                return m["id"]
    return usable[0]["id"]


# ── provider model listers (return [{'id','created'}], newest-sortable) ──────────
def _anthropic_models(key: str) -> List[Dict]:
    import requests
    r = requests.get("https://api.anthropic.com/v1/models", timeout=15,
                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        # Anthropic returns ISO 'created_at'; turn it into a sortable epoch.
        created = m.get("created_at") or ""
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = 0
        out.append({"id": m.get("id", ""), "created": ts})
    return out


def _openai_compatible_models(key: str, url: str) -> List[Dict]:
    """OpenAI, xAI and Google(Gemini) all expose GET /v1/models → {data:[{id, created}]}.
    Gemini returns ids like 'models/gemini-2.5-pro'; strip the prefix so the id can
    be passed straight back to the chat endpoint."""
    import requests
    r = requests.get(url, timeout=15, headers={"Authorization": "Bearer " + key})
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        mid = (m.get("id", "") or "").split("/")[-1]
        out.append({"id": mid, "created": m.get("created", 0)})
    return out


# provider -> (lister, preferred-family keywords, ordered best→worst)
# Google/Gemini exposes an OpenAI-compatible surface, so it reuses the same lister.
_GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/openai/models"
_PROVIDERS: Dict[str, Tuple[Callable[[str], List[Dict]], Tuple[str, ...]]] = {
    "anthropic": (lambda k: _anthropic_models(k), ("opus", "sonnet", "haiku")),
    "openai":    (lambda k: _openai_compatible_models(k, "https://api.openai.com/v1/models"),
                  ("gpt-5", "gpt-4.1", "gpt-4o", "gpt-4", "gpt")),
    "xai":       (lambda k: _openai_compatible_models(k, "https://api.x.ai/v1/models"),
                  ("grok-4", "grok-3", "grok-2", "grok")),
    "gemini":    (lambda k: _openai_compatible_models(k, _GEMINI_MODELS_URL),
                  ("gemini-3", "gemini-2.5-pro", "gemini-2.5", "gemini-2", "gemini-1.5", "gemini")),
}


def _load_cache() -> Dict:
    try:
        with open(model_cache_path(), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: Dict) -> None:
    try:
        with open(model_cache_path(), "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
    except OSError as exc:
        log.warning("could not write model cache: %s", exc)


def resolve(provider: str, key: str, default: str, *, force: bool = False) -> str:
    """Return the provider's latest preferred model, or `default` on any problem.

    Caches per provider for MODEL_REFRESH_HOURS so we query at most once a day.
    Mini variants etc. are filtered out; Claude prefers Opus (owner directive)."""
    if provider not in _PROVIDERS or not key:
        return default
    cache = _load_cache()
    entry = cache.get(provider) or {}
    fresh = (not force and entry.get("model")
             and (time.time() - entry.get("ts", 0)) < _refresh_hours() * 3600)
    if fresh:
        return entry["model"]

    lister, prefer = _PROVIDERS[provider]
    try:
        latest = _pick_latest(lister(key), prefer)
    except Exception as exc:  # network/API/parse — never break the brain
        log.warning("%s model lookup failed (%s) → using %s", provider, exc, default)
        return entry.get("model") or default
    if not latest:
        return entry.get("model") or default

    if latest != entry.get("model"):
        log.info("%s latest model: %s%s", provider, latest,
                 f" (was {entry['model']})" if entry.get("model") else "")
    cache[provider] = {"model": latest, "ts": time.time(), "default": default}
    _save_cache(cache)
    return latest


def resolve_all(keys: Dict[str, str], defaults: Dict[str, str], *, force: bool = False) -> Dict[str, str]:
    """keys/defaults keyed by 'anthropic'|'openai'|'xai'|'gemini'. Returns resolved ids."""
    return {p: resolve(p, keys.get(p, ""), defaults.get(p, ""), force=force)
            for p in ("anthropic", "openai", "xai", "gemini")}
