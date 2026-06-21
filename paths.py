"""Filesystem layout — one place that resolves where a desk keeps its data.

By default everything lives under the repo root (single-desk, unchanged behavior).
Set SAHJONY_HOME to give a desk its own isolated home, so you can run multiple
accounts side by side without their state/db/status/kill-switch colliding:

    SAHJONY_HOME=~/desks/us-equities   python main.py --once
    SAHJONY_HOME=~/desks/crypto-247    python main.py --loop

Each home gets its own state.json, data/sahjony.db, public/status.json, and HALT.
"""
from __future__ import annotations

import os

_REPO = os.path.dirname(os.path.abspath(__file__))


def home() -> str:
    h = os.environ.get("SAHJONY_HOME", "").strip()
    base = os.path.abspath(os.path.expanduser(h)) if h else _REPO
    os.makedirs(base, exist_ok=True)
    return base


def state_path() -> str:
    return os.path.join(home(), "state.json")


def db_path() -> str:
    return os.path.join(home(), "data", "sahjony.db")


def status_path() -> str:
    return os.path.join(home(), "public", "status.json")


def investors_dir() -> str:
    return os.path.join(home(), "public", "investors")


def halt_path() -> str:
    return os.path.join(home(), "HALT")


def model_cache_path() -> str:
    """Where the autonomous model-updater caches each provider's resolved latest model."""
    return os.path.join(home(), "model_cache.json")
