"""Is the LIVE dashboard actually serving what master says it should?

The desk commits public/status.json every cycle and CI reports a green deploy,
but neither of those proves the owner's dashboard changed. On 2026-08-07 the
repo was at cycle 899 while www.sahjonycapital.com served cycle 817 — 82 cycles
(~2 days) stale. Every push had built fine as a Vercel PREVIEW (target: null)
because the project's Production Branch was not `master`, so nothing was ever
promoted. Both signals people watch — "CI green" and "deployment READY" — were
true the entire time, which is exactly why it went unnoticed.

So compare the two numbers directly. Fetches the deployed status.json and diffs
its cycle against the committed one.

  python -m scripts.check_production_freshness
  python -m scripts.check_production_freshness --url https://www.sahjonycapital.com
  python -m scripts.check_production_freshness --max-lag 0   # exact match required

Exits 1 when production lags by more than --max-lag. Read-only: it fetches one
public JSON file and writes nothing. Never blocks on a network problem — an
unreachable site is reported and exits 0, because a flaky fetch is not evidence
that the deploy is broken.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://www.sahjonycapital.com"
DEFAULT_MAX_LAG = 5   # a cycle or two of lag is just deploy latency, not a freeze


def _local_cycle(path: str) -> int | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return int(json.load(fh).get("cycle"))
    except (OSError, ValueError, TypeError):
        return None


def _live_cycle(base_url: str, timeout: float) -> tuple[int | None, str]:
    url = base_url.rstrip("/") + "/status.json"
    req = urllib.request.Request(url, headers={
        "User-Agent": "sahjony-freshness-check",
        # The published status.json is served no-store, but proxies in between
        # are not bound by that. Ask for an unconditional fetch.
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from {url}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, f"unreachable: {getattr(exc, 'reason', exc)}"
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"invalid JSON at {url}: {type(exc).__name__}"
    try:
        return int(payload.get("cycle")), url
    except (TypeError, ValueError):
        return None, f"no usable 'cycle' field at {url}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.getenv("PUBLIC_BASE_URL") or DEFAULT_URL,
                    help="public base URL of the deployed dashboard")
    ap.add_argument("--status", default=os.path.join("public", "status.json"),
                    help="path to the committed status.json")
    ap.add_argument("--max-lag", type=int, default=DEFAULT_MAX_LAG,
                    help=f"cycles of lag tolerated before failing (default {DEFAULT_MAX_LAG})")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args(argv)

    local = _local_cycle(args.status)
    if local is None:
        print(f"  · no readable cycle in {args.status} — nothing to compare.")
        return 0

    live, detail = _live_cycle(args.url, args.timeout)
    if live is None:
        # A network failure is not evidence of a stale deploy. Say so and pass.
        print(f"  · could not read the live dashboard ({detail}) — skipping.")
        return 0

    lag = local - live
    print(f"  repo   cycle: {local}")
    print(f"  live   cycle: {live}   ({detail})")
    if lag > args.max_lag:
        print(f"\n  ✗ PRODUCTION IS {lag} CYCLE(S) BEHIND master.")
        print("    The build is green and the deployment is READY, but the site")
        print("    visitors load is not being updated. The usual cause is that the")
        print("    Vercel project's Production Branch is not 'master', so every")
        print("    push lands as a preview and only a manual promote goes live.")
        print("    Check: Vercel → Project → Settings → Git → Production Branch.")
        return 1
    if lag < 0:
        print(f"\n  · live is {abs(lag)} cycle(s) AHEAD of this checkout "
              "(stale local copy — pull master).")
        return 0
    print(f"\n  ✓ production is current (lag {lag}, tolerance {args.max_lag}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
