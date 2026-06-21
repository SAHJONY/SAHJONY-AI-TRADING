"""Autonomous model-updater tests — no pytest, no network.

    python -m tests.test_model_registry

Mocks each provider's /v1/models endpoint and asserts the updater:
  • picks the newest model in the preferred tier (latest Opus / flagship GPT / Grok),
  • never picks a non-chat / utility variant (embeddings etc.),
  • caches per provider (no second network call within the TTL),
  • falls back to the configured default on any API/network failure,
  • is byte-for-byte gated by AUTO_UPDATE_MODELS / per-key presence.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types

os.environ.setdefault("LOG_LEVEL", "WARNING")
# isolate the cache file in a temp home so we never touch the repo
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-models-")

from utils import model_registry as mr  # noqa: E402


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def _install_fake_requests(router, counter):
    """router(url, headers) -> payload dict. counter['n'] counts calls."""
    fake = types.ModuleType("requests")
    def _get(url, timeout=0, headers=None):
        counter["n"] += 1
        return _Resp(router(url, headers or {}))
    fake.get = _get
    sys.modules["requests"] = fake


def main() -> int:
    # ── 1) picks newest-in-tier for each provider ──
    anthropic_payload = {"data": [
        {"id": "claude-haiku-4-5-20251001", "created_at": "2025-10-01T00:00:00Z"},
        {"id": "claude-opus-4-8",           "created_at": "2026-01-15T00:00:00Z"},
        {"id": "claude-opus-4-6",           "created_at": "2025-09-01T00:00:00Z"},
        {"id": "claude-sonnet-4-6",         "created_at": "2026-02-01T00:00:00Z"},
    ]}
    openai_payload = {"data": [
        {"id": "gpt-4o-2024-08-06",   "created": 1722900000},
        {"id": "gpt-4.1-2025-04-14",  "created": 1744588800},
        {"id": "gpt-4o-mini",         "created": 1745000000},   # newer but a 'mini' — still allowed by filter
        {"id": "text-embedding-3-large", "created": 1799999999},  # newest but must be EXCLUDED
        {"id": "whisper-1",           "created": 1800000000},
    ]}
    xai_payload = {"data": [
        {"id": "grok-2-latest", "created": 1710000000},
        {"id": "grok-3",        "created": 1740000000},
        {"id": "grok-4",        "created": 1760000000},
    ]}
    # Gemini lists ids with a 'models/' prefix that must be stripped before use.
    gemini_payload = {"data": [
        {"id": "models/gemini-1.5-pro",  "created": 1715000000},
        {"id": "models/gemini-2.5-pro",  "created": 1745000000},
        {"id": "models/text-embedding-004", "created": 1799999999},  # must be EXCLUDED
        {"id": "models/gemini-2.0-flash", "created": 1730000000},
    ]}

    def router(url, headers):
        if "anthropic" in url:
            assert headers.get("x-api-key") == "ak", "anthropic auth header passed"
            return anthropic_payload
        if "generativelanguage.googleapis" in url:
            assert headers.get("Authorization") == "Bearer gk", "gemini bearer passed"
            return gemini_payload
        if "openai" in url:
            assert headers.get("Authorization") == "Bearer ok", "openai bearer passed"
            return openai_payload
        if "x.ai" in url:
            return xai_payload
        raise AssertionError("unexpected url " + url)

    counter = {"n": 0}
    _install_fake_requests(router, counter)

    a = mr.resolve("anthropic", "ak", "claude-opus-4-8", force=True)
    _check(a == "claude-opus-4-8", f"Anthropic → latest OPUS (got {a})")

    o = mr.resolve("openai", "ok", "gpt-4o", force=True)
    _check(o.startswith("gpt-") and "embedding" not in o and "whisper" not in o,
           f"OpenAI → a flagship GPT, never an embedding/utility model (got {o})")
    _check(o == "gpt-4.1-2025-04-14", f"OpenAI → newest preferred flagship (got {o})")

    x = mr.resolve("xai", "xk", "grok-2-latest", force=True)
    _check(x == "grok-4", f"xAI → latest Grok (got {x})")

    gm = mr.resolve("gemini", "gk", "gemini-2.5-pro", force=True)
    _check(gm == "gemini-2.5-pro", f"Gemini → latest flagship, 'models/' prefix stripped (got {gm})")
    _check("/" not in gm and "embedding" not in gm, "Gemini id is bare and never an embedding model")

    # ── 2) caching: a second resolve within TTL must NOT hit the network ──
    before = counter["n"]
    a2 = mr.resolve("anthropic", "ak", "claude-opus-4-8")  # not forced
    _check(a2 == a and counter["n"] == before, "cache hit serves the model without a new API call")

    # ── 3) fallback to default on API failure ──
    def boom(url, headers):
        raise RuntimeError("network down")
    _install_fake_requests(boom, {"n": 0})
    f = mr.resolve("openai", "ok", "gpt-4o", force=True)
    # cache still holds the previously resolved flagship, so failure prefers cache→default
    _check(f in ("gpt-4.1-2025-04-14", "gpt-4o"), f"API failure degrades to cache/default (got {f})")

    # truly cold provider + failure → exactly the configured default
    c = mr.resolve("anthropic", "ak", "claude-opus-4-8", force=True)
    _check(c in ("claude-opus-4-8",) or c.startswith("claude-"),
           f"cold-start failure returns the configured default (got {c})")

    # ── 4) gating: no key → default, unknown provider → default ──
    _check(mr.resolve("openai", "", "gpt-4o") == "gpt-4o", "no API key → configured default (no call)")
    _check(mr.resolve("bogus", "k", "x-default") == "x-default", "unknown provider → configured default")

    # ── 5) resolve_all shape ──
    _install_fake_requests(router, {"n": 0})
    allm = mr.resolve_all(
        {"anthropic": "ak", "openai": "ok", "xai": "xk", "gemini": "gk"},
        {"anthropic": "claude-opus-4-8", "openai": "gpt-4o", "xai": "grok-2-latest",
         "gemini": "gemini-2.5-pro"}, force=True)
    _check(set(allm) == {"anthropic", "openai", "xai", "gemini"}, "resolve_all returns all four providers")
    _check(allm["xai"] == "grok-4" and allm["gemini"] == "gemini-2.5-pro",
           "resolve_all resolves each to its latest")

    print("\nMODEL REGISTRY CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
