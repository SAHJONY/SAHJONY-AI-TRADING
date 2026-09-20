"""Shared keyless HTTP client for the intel engines.

One wrapper around ``requests`` that every keyless intel engine should use,
so rate limiting and retry behavior live in exactly one place:

  * per-host token-bucket rate limiting (conservative defaults; CoinGecko
    gets 1 request per 2s because the free tier 429s aggressively),
  * exponential backoff with jitter on HTTP 429 and 5xx, plus transient
    network errors — bounded by a max retry count AND a max total wait,
  * explicit (connect, read) timeouts on every call — never blocks forever,
  * no retry on 4xx other than 429,
  * structured errors returned to the caller (status code, host, attempts,
    total wait in ms) so engines can set their ``errors``/``stale`` flags
    honestly — ``request()`` never raises for HTTP-level failures,
  * thread-safe (engines may overlap), stdlib + ``requests`` only,
    zero credentials anywhere in this module.

This module is ADVISORY / MEASUREMENT infrastructure. It never emits orders,
never touches credentials, and never widens the risk envelope ($10/order,
12%/position, 70% deployed, 10% daily-drawdown halt — frozen).

How other engines should adopt it (ADOPTION NOTE)
-------------------------------------------------
Keep your module's ``_http_get_json(url, timeout, headers=None, params=None)``
helper (existing tests stub it), but re-implement it on top of a
module-level client::

    from intel.keyless_http import KeylessHttpClient

    _HTTP = KeylessHttpClient()   # one per module; hosts share the bucket map

    def _http_get_json(url: str, timeout: float, headers=None, params=None):
        res = _HTTP.get_json(url, timeout=timeout, headers=headers, params=params)
        if not res.ok:
            raise RuntimeError(res.error)   # keep the "raises on failure" contract
        return res.payload

    def _http_get_text(url: str, timeout: float) -> str:
        res = _HTTP.get_text(url, timeout=timeout)
        if not res.ok:
            raise RuntimeError(res.error)
        return res.text

Then DELETE any hand-rolled pacing (``time.sleep`` courtesy delays) — the
token bucket enforces per-host spacing for you. Keep each engine's
try/except in ``refresh()`` so failures still land in ``errors``/``stale``
and never raise; the ``res.error`` string already carries status, host,
attempt count, and total wait, which makes those flags honest.

Engines with special needs can tune per call or per client::

    _HTTP.get_json(url, timeout=20, max_retries=1)          # light-touch call
    KeylessHttpClient(rates={"api.coingecko.com": HostRate(0.2, 1)})  # slower CG

Threading: the client is safe to share across threads (the desk may call
engines in ways that overlap). ``requests.Session`` is thread-safe for
concurrent requests, and the token buckets are guarded by a lock.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

# Descriptive User-Agent (NOT a credential — several keyless endpoints,
# e.g. Yahoo, reject empty-UA requests).
USER_AGENT = "SAHJONY-Capital/1.0 (keyless research; intel/keyless_http.py)"

# Default timeouts: (connect, read). Every request carries an explicit
# timeout; nothing ever blocks indefinitely.
DEFAULT_CONNECT_TIMEOUT_S = 5.0
DEFAULT_READ_TIMEOUT_S = 15.0

# Retry policy defaults.
DEFAULT_MAX_RETRIES = 3          # retries after the first attempt (4 tries total)
DEFAULT_BASE_BACKOFF_S = 1.0    # wait = base * 2**n on retry n (n = 0,1,2,...)
DEFAULT_BACKOFF_CAP_S = 15.0    # per-wait ceiling, before jitter
DEFAULT_JITTER_S = 1.0          # uniform(0, jitter) added to each wait
DEFAULT_MAX_TOTAL_WAIT_S = 60.0 # hard ceiling on cumulative backoff per call


@dataclass(frozen=True)
class HostRate:
    """Token-bucket config for one host: steady-state requests/sec + burst."""
    rate_per_sec: float
    burst: int


# Conservative per-host defaults. CoinGecko's keyless tier is the known
# 429 source in this repo — 1 request per 2s with no burst.
DEFAULT_RATES: Dict[str, HostRate] = {
    "api.coingecko.com": HostRate(0.5, 1),
    "api.alternative.me": HostRate(1.0, 2),
    "api.gdelt.org": HostRate(0.5, 1),
    "mempool.space": HostRate(1.0, 2),
    "api.blockchain.info": HostRate(1.0, 2),
    "api.hyperliquid.xyz": HostRate(1.0, 2),
    "fapi.binance.com": HostRate(2.0, 3),
    "api.kraken.com": HostRate(1.0, 2),
    "api.coinbase.com": HostRate(2.0, 3),
    "www.deribit.com": HostRate(1.0, 2),
    "query1.finance.yahoo.com": HostRate(1.0, 2),
    "query2.finance.yahoo.com": HostRate(1.0, 2),
}
DEFAULT_HOST_RATE = HostRate(2.0, 3)

# Retried statuses: 429 (rate limited) and the 5xx range. Everything else
# 4xx is final — retrying a 400/401/403/404 only burns quota.
_RETRYABLE_STATUS = frozenset([429] + list(range(500, 600)))


@dataclass
class HttpResult:
    """Structured outcome of one logical request (all attempts included).

    ``ok`` is False for HTTP errors, invalid JSON (``get_json``), and
    exhausted retries — ``request()`` never raises for these. ``error`` is a
    one-line human summary carrying status, host, attempts, and total wait,
    suitable for an engine's ``errors`` list.
    """
    ok: bool
    method: str
    url: str
    host: str
    status: Optional[int]
    attempts: int
    total_wait_ms: float
    payload: Any = None            # parsed JSON for get_json(); None otherwise
    text: Optional[str] = None     # response body text
    error: Optional[str] = None
    retried: bool = False
    rate_limited: bool = False     # True if any attempt returned 429


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except Exception:
        return ""


def _norm_timeout(timeout: Any) -> Tuple[float, float]:
    """Accept a scalar (legacy engine signature) or a (connect, read) tuple."""
    if timeout is None:
        return DEFAULT_CONNECT_TIMEOUT_S, DEFAULT_READ_TIMEOUT_S
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        return float(timeout[0]), float(timeout[1])
    t = float(timeout)
    return DEFAULT_CONNECT_TIMEOUT_S, t


def _retry_after_s(headers: Dict[str, Any]) -> Optional[float]:
    """Parse Retry-After (delta-seconds form) when present and sane."""
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        v = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 300 else None  # ignore absurd values


class KeylessHttpClient:
    """Shared keyless HTTP client: token-bucket pacing + bounded retries.

    Args:
        rates: per-host overrides merged over ``DEFAULT_RATES``.
        default_rate: fallback for hosts not in the map.
        timeout: default (connect, read) or scalar seconds.
        max_retries / base_backoff_s / backoff_cap_s / jitter_s /
            max_total_wait_s: retry policy defaults (overridable per call).
        user_agent: descriptive UA string (not a credential).
        transport: object with ``request(method, url, ...)`` like
            ``requests.Session``. Defaults to a fresh ``requests.Session``.
            Test seam: pass a stub, or monkeypatch ``requests.Session``.
        time_fn / sleep_fn: test seams for deterministic timing.
    """

    def __init__(
        self,
        rates: Optional[Dict[str, HostRate]] = None,
        default_rate: Optional[HostRate] = None,
        timeout: Any = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_backoff_s: float = DEFAULT_BASE_BACKOFF_S,
        backoff_cap_s: float = DEFAULT_BACKOFF_CAP_S,
        jitter_s: float = DEFAULT_JITTER_S,
        max_total_wait_s: float = DEFAULT_MAX_TOTAL_WAIT_S,
        user_agent: str = USER_AGENT,
        transport: Any = None,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rates = dict(DEFAULT_RATES)
        if rates:
            self._rates.update(rates)
        self._default_rate = default_rate or DEFAULT_HOST_RATE
        self._timeout = _norm_timeout(timeout)
        self.max_retries = max_retries
        self.base_backoff_s = base_backoff_s
        self.backoff_cap_s = backoff_cap_s
        self.jitter_s = jitter_s
        self.max_total_wait_s = max_total_wait_s
        self.user_agent = user_agent
        self._transport = transport if transport is not None else requests.Session()
        self._time = time_fn
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        # host -> {"tokens": float, "updated": float}
        self._buckets: Dict[str, Dict[str, float]] = {}

    # ── rate limiting ────────────────────────────────────────────────────
    def _rate_for(self, host: str) -> HostRate:
        return self._rates.get(host, self._default_rate)

    def _pace(self, host: str) -> float:
        """Block until this host's token bucket has a token. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._time()
                cfg = self._rate_for(host)
                bucket = self._buckets.get(host)
                if bucket is None:
                    bucket = {"tokens": float(cfg.burst), "updated": now}
                    self._buckets[host] = bucket
                elapsed = max(0.0, now - bucket["updated"])
                bucket["tokens"] = min(float(cfg.burst),
                                       bucket["tokens"] + elapsed * cfg.rate_per_sec)
                bucket["updated"] = now
                if bucket["tokens"] >= 1.0:
                    bucket["tokens"] -= 1.0
                    return waited
                need = (1.0 - bucket["tokens"]) / cfg.rate_per_sec
            # Sleep outside the lock so other hosts' buckets keep refilling.
            self._sleep(need)
            waited += need

    # ── core request ─────────────────────────────────────────────────────
    def request(
        self,
        method: str,
        url: str,
        *,
        timeout: Any = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        max_retries: Optional[int] = None,
        max_total_wait_s: Optional[float] = None,
    ) -> HttpResult:
        """One logical request with pacing + bounded retries.

        Never raises for HTTP-level failures (4xx/5xx, timeouts, connection
        errors, exhausted retries) — those come back as ``HttpResult(ok=False)``.
        Unexpected non-requests exceptions (bugs, bad URL shape) may raise.
        """
        host = _host_of(url)
        connect_t, read_t = _norm_timeout(timeout) if timeout is not None else self._timeout
        hdrs = {"User-Agent": self.user_agent}
        if headers:
            hdrs.update(headers)

        retries_allowed = self.max_retries if max_retries is None else max_retries
        wait_budget = self.max_total_wait_s if max_total_wait_s is None else max_total_wait_s

        attempts = 0
        total_wait = 0.0
        saw_429 = False
        last_status: Optional[int] = None
        last_error: Optional[str] = None

        while True:
            attempts += 1
            self._pace(host)
            retried = attempts > 1
            try:
                resp = self._transport.request(
                    method, url,
                    timeout=(connect_t, read_t),
                    headers=hdrs,
                    params=params,
                    json=json_body,
                )
                status = int(getattr(resp, "status_code", 0) or 0)
                last_status = status
                resp_headers = dict(getattr(resp, "headers", {}) or {})
                body_text: Optional[str] = None
                try:
                    body_text = resp.text
                except Exception:
                    body_text = None

                if status in _RETRYABLE_STATUS:
                    if status == 429:
                        saw_429 = True
                    last_error = f"HTTP {status} (retryable)"
                    retry_hint = _retry_after_s(resp_headers) if status == 429 else None
                elif status < 400:
                    return HttpResult(
                        ok=True, method=method, url=url, host=host,
                        status=status, attempts=attempts,
                        total_wait_ms=round(total_wait * 1000.0, 1),
                        text=body_text, retried=retried, rate_limited=saw_429,
                    )
                else:
                    # Non-retryable 4xx: final answer, no backoff.
                    return HttpResult(
                        ok=False, method=method, url=url, host=host,
                        status=status, attempts=attempts,
                        total_wait_ms=round(total_wait * 1000.0, 1),
                        text=body_text, retried=retried, rate_limited=saw_429,
                        error=self._summarize(url, host, status,
                                              f"HTTP {status} (not retryable)",
                                              attempts, total_wait),
                    )
            except requests.RequestException as exc:
                # Timeouts / connection errors are transient → backoff.
                last_error = f"{type(exc).__name__}: {exc}"
                retry_hint = None
            except Exception:
                # Non-requests exceptions are bugs, not transport noise — surface them.
                raise

            # Decide whether another attempt is allowed.
            if attempts > retries_allowed:
                break
            wait = self._backoff_wait(attempts - 1, retry_hint)
            if total_wait + wait > wait_budget:
                last_error = f"{last_error}; wait budget exhausted ({wait_budget:.0f}s)"
                break
            self._sleep(wait)
            total_wait += wait

        return HttpResult(
            ok=False, method=method, url=url, host=host,
            status=last_status, attempts=attempts,
            total_wait_ms=round(total_wait * 1000.0, 1),
            retried=attempts > 1, rate_limited=saw_429,
            error=self._summarize(url, host, last_status, last_error,
                                  attempts, total_wait),
        )

    def _backoff_wait(self, retry_index: int, retry_hint: Optional[float]) -> float:
        """Exponential wait for retry ``retry_index`` (0-based), with jitter.

        A server ``Retry-After`` hint is honored but capped by the same
        per-wait ceiling so a bad header can't stall a cycle.
        """
        exp = min(self.backoff_cap_s, self.base_backoff_s * (2 ** retry_index))
        if retry_hint is not None:
            # Honor the server's ask, but never beyond the per-wait cap —
            # an absurd Retry-After must not stall a cycle.
            exp = min(self.backoff_cap_s, max(exp, retry_hint))
        jitter = random.uniform(0.0, self.jitter_s) if self.jitter_s > 0 else 0.0
        return exp + jitter

    @staticmethod
    def _summarize(url: str, host: str, status: Optional[int],
                   detail: Optional[str], attempts: int, total_wait: float) -> str:
        status_txt = f"HTTP {status}" if status else "no response"
        return (f"{status_txt} from {host or url} after {attempts} attempt(s), "
                f"waited {total_wait:.1f}s — {detail or 'unknown error'}")

    # ── convenience verbs ────────────────────────────────────────────────
    def get(self, url: str, **kwargs: Any) -> HttpResult:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResult:
        return self.request("POST", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> HttpResult:
        """GET + parse JSON. ``payload`` holds the parsed body on success;
        invalid JSON is a structured failure (ok=False), never a raise."""
        res = self.get(url, **kwargs)
        if not res.ok:
            return res
        try:
            import json as _json
            res.payload = _json.loads(res.text) if res.text else None
        except (ValueError, TypeError) as exc:
            res.ok = False
            res.error = self._summarize(url, res.host, res.status,
                                        f"invalid JSON: {exc}",
                                        res.attempts, res.total_wait_ms / 1000.0)
        return res

    def get_text(self, url: str, **kwargs: Any) -> HttpResult:
        """GET returning raw body text in ``res.text``."""
        return self.get(url, **kwargs)


# One shared default client for engines that don't need custom tuning.
_default_client: Optional[KeylessHttpClient] = None
_default_lock = threading.Lock()


def get_default_client() -> KeylessHttpClient:
    """Process-wide shared client (thread-safe). Prefer a module-level
    ``KeylessHttpClient()`` in your engine for explicit isolation instead."""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = KeylessHttpClient()
        return _default_client
