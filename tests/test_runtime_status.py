import importlib.util
import io
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("runtime_status", Path("api/runtime-status.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def payload():
    return {
        "updated": "2026-07-15T00:00:00Z", "read_only": True,
        "execution_authority": False, "total_value": 1, "cash": -5,
        "buying_power": -5, "positions": [],
        "agentic": {"identity_verified": True, "account_number_last4": "1131",
                    "connected": True, "ok": True, "equity": 1, "cash": -5,
                    "buying_power": -5, "status": "active"},
    }


def test_runtime_payload_is_masked_and_read_only():
    result = MODULE.sanitize(payload())
    assert result["account_mask"].endswith("1131")
    assert result["execution_authority"] is False
    assert result["orders"] == []


def test_runtime_payload_rejects_execution_authority():
    raw = payload(); raw["execution_authority"] = True
    with pytest.raises(ValueError):
        MODULE.sanitize(raw)


def test_runtime_payload_requires_verified_identity():
    raw = payload(); raw["agentic"]["identity_verified"] = False
    with pytest.raises(ValueError):
        MODULE.sanitize(raw)


def test_redis_normalizes_upstash_pipeline_results(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps([{"result": "OK"}, {"result": None}]).encode()

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "secret")
    monkeypatch.setattr(MODULE.request, "urlopen", lambda *_args, **_kwargs: Response())

    assert MODULE.redis([["SET", "key", "value"], ["GET", "missing"]]) == ["OK", None]


def test_redis_rejects_non_pipeline_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return io.BytesIO(b'{"result":"OK"}').read()

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "secret")
    monkeypatch.setattr(MODULE.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(ValueError, match="pipeline"):
        MODULE.redis([["GET", "key"]])
