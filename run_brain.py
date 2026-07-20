"""Analysis-only trading brain."""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("brain")


def main():
    log.info("SAHJONY Brain")
    log.info("Analysis mode only")
    log.info("Execution authority: DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
