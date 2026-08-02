"""Remote kill switch (local desk) — no pytest, no network.

    python -m tests.test_remote_control

Verifies the remote STOP → local HALT-file plumbing and its safety properties:
fail-closed on unknown, and never overriding a manually-set halt.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("LOG_LEVEL", "WARNING")
# Isolate the desk home so we never touch the repo's real HALT file.
os.environ["SAHJONY_HOME"] = tempfile.mkdtemp(prefix="sahjony-rc-")

from paths import halt_path
from utils.remote_control import apply_remote_halt, sync_remote_halt


def _check(cond, msg):
    if not cond:
        print("✗ FAIL:", msg)
        sys.exit(1)
    print("✓", msg)


def _halted() -> bool:
    return os.path.exists(halt_path())


def _clear():
    try:
        os.remove(halt_path())
    except FileNotFoundError:
        pass


def main() -> int:
    _clear()

    # feature disabled when REMOTE_HALT_URL unset → never touches HALT
    os.environ.pop("REMOTE_HALT_URL", None)
    _check(sync_remote_halt() == "disabled", "no REMOTE_HALT_URL → disabled")
    _check(not _halted(), "disabled never creates a HALT")

    # remote says halt → HALT created
    _check(apply_remote_halt(True) == "halted(remote)", "remote halt → halted")
    _check(_halted(), "HALT file created by remote halt")

    # remote says resume → clears the halt WE created
    _check(apply_remote_halt(False) == "resumed(remote)", "remote resume → cleared")
    _check(not _halted(), "HALT removed on remote resume")

    # unknown + failsafe on → fail CLOSED (halt); failsafe off → left as-is
    _clear()
    _check(apply_remote_halt(None, failsafe=True) == "halted(remote)", "unknown + failsafe → halt")
    _check(_halted(), "fail-closed created a HALT")
    _clear()
    _check(apply_remote_halt(None, failsafe=False) == "unknown/left-as-is", "unknown + no failsafe → left as-is")
    _check(not _halted(), "no failsafe did not create a HALT")

    # a MANUAL halt (empty file, e.g. scripts/live.sh off) is never auto-resumed
    with open(halt_path(), "w") as fh:
        fh.write("")   # manual halt marker (empty, not 'remote-halt')
    _check(apply_remote_halt(False) == "left manual halt in place", "remote resume respects a manual halt")
    _check(_halted(), "manual HALT survives a remote resume")
    _clear()

    print("\nREMOTE CONTROL CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
