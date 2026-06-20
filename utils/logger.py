"""Centralized logging: rotating file + console. Import get_logger everywhere."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    os.makedirs(_LOG_DIR, exist_ok=True)
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("acb")
    root.setLevel(level)
    root.propagate = False

    # Rotating file: 2 MB x 5 files. Survives crashes; the loop logs here, never dies.
    fh = RotatingFileHandler(os.path.join(_LOG_DIR, "bot.log"), maxBytes=2_000_000, backupCount=5)
    fh.setFormatter(fmt)
    fh.setLevel(level)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(level)

    root.addHandler(fh)
    root.addHandler(ch)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the 'acb' tree."""
    _configure_root()
    return logging.getLogger("acb." + name)
