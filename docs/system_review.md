# Trading system review — findings and optimizations

Review of the live desk (~12.9k lines across `workforce/`, `strategies/`, `risk/`,
`intelligence/`, `utils/`, `database/`), not just the `backtest/` research package.

**Baseline:** all 20 test suites green (once `pynacl` is installed — see below).
**After:** 21 suites green, cycle time down 3.4×, no behaviour change.

---

## What was measured, not guessed

Every change below came from an instrumented measurement of a real cycle. Nothing
was optimized on suspicion.

| Metric | Before | After |
|---|---|---|
| Trading cycle (offline-sim, 3 tickers) | 182 ms | **53 ms** (3.4×) |
| Market-data calls per cycle | 33 | **20** |
| `annualized_vol` calls per cycle | 1,759 | **8** |
| `council_log WHERE cycle=?` @ 1.9M rows | 81 ms | **0.13 ms** (600×) |
| `MAX(cycle)` on `council_log` @ 1.9M rows | 99 ms | **0.01 ms** |

---

## 1. An O(n²) volatility loop was 45% of every cycle

`intelligence/agents.py`, the D.E. Shaw options agent:

```python
vols_hist = np.array([engines.annualized_vol(s.closes[:i])
                      for i in range(20, len(s.closes))])
```

Each iteration re-derived the entire log-return series over a growing slice —
O(n²) per agent, per symbol, per cycle. The profiler put it at **1,759 calls per
cycle and 45% of total cycle time**.

Replaced with `engines.expanding_vol()`, which gets every window's variance in
constant time from cumulative sums of *r* and *r²*. **The values are identical**
— verified element-for-element against the original loop on random-walk,
trending, high-volatility and boundary-length series, max absolute difference
`6.7e-16`. That equivalence is now a test, so the fast path cannot silently drift
from the definition it replaced.

## 2. The same price was fetched four times per cycle

The roles that make up a cycle each asked the broker independently: sleeve
valuation, gross-exposure check, strategy desks, execution trader. Measured on
one offline-sim cycle with three tickers: **33 market-data calls, the same symbol
priced 4×**. In paper/live mode each of those is a network round trip.

`utils/quote_cache.py` adds a per-cycle cache. It is worth being clear that this
is **a correctness fix as much as a speed one**: without it the desk can value
equity at one price, size the position at a second, and fill against a third,
all inside a single "instantaneous" decision. Pinning the quote for the duration
of a cycle removes that inconsistency.

Design notes:
- It wraps *any* adapter satisfying the `utils/broker.py` contract by delegation,
  so Alpaca, IBKR, CCXT, Robinhood and the simulator all benefit without knowing
  it exists.
- Wrapped at the `Firm` boundary rather than in `get_broker()`, so the factory
  keeps returning the bare adapter its contract promises (and
  `test_ibkr_adapter`'s isinstance check keeps meaning what it says).
- **A failed quote (`0.0`) is never cached.** Pinning one bad tick for a whole
  cycle would turn a single failure into a cycle-wide blackout and a zero-priced
  equity curve. This is tested.
- Invalidated at the top of `run_cycle` and on `advance_sim`.

## 3. The database had no indices at all

Eight tables, zero indices. `council_log` is the fastest-growing table on the
desk — agents × tickers × cycles — and a 24/7 desk at 15-minute cycles over 8
tickers writes **~1.9M rows in about seven months**. The reporter reads the
latest council *every cycle*, and both of its queries were full scans.

Benchmarked at 1.9M rows: `WHERE cycle=?` **81 ms → 0.13 ms**, `MAX(cycle)`
**99 ms → 0.01 ms**. Indices added for the growth tables and for the lookups that
were scans (`investors.share_token`, `contributions.investor_id`). All are
`CREATE INDEX IF NOT EXISTS` inside the schema script, so existing databases get
them on next start with no migration step.

A test asserts the council lookup **plans through its index** rather than merely
that the index exists — presence is not use.

## 4. `PRAGMA synchronous=NORMAL`

~17 commits per cycle, 0.62 s of a 3.6 s 20-cycle run, dominated by per-commit
fsync. WAL + NORMAL is the documented safe pairing: still durable across an
application crash. The residual exposure is the last transaction on OS crash or
power loss, which here means one cycle of telemetry — and per the reconciliation
logic the broker, not this file, is the source of truth for positions.

---

## Reviewed and found sound

Not everything needed changing, and it is worth recording what held up:

- **Risk ceilings.** `config.py` clamps every risk knob to a hard constant
  (`HARD_MAX_ALLOCATION_PCT`, `HARD_MAX_TOTAL_DEPLOYED_PCT`,
  `HARD_MAX_DAILY_DRAWDOWN_PCT`, `HARD_MIN_CONVICTION`). `.env` can only ever
  tighten them. The risk engine re-checks the absolute ceiling independently of
  the clamped config, so a config bug cannot widen it either.
- **Fault isolation.** Every external call (broker, LLM, voice, DB) degrades to a
  safe default. **There is not a single bare `except:` in the live code** — every
  handler names its exception and logs. A failing intent cannot sink a cycle.
- **Secret hygiene.** `public/status.json` — the only committed runtime artifact
  — was scanned for key-shaped tokens. The only hits were the substring `sk-o`
  inside the word "ri**sk-o**ff" in macro commentary. No secrets, no emails, no
  tokens.
- **Circuit breaker.** The daily-drawdown latch correctly distinguishes a capital
  flow from a loss: it only re-anchors when the desk is provably flat *and* has
  booked no realized P&L that day, so a deposit cannot un-trip a real halt.
- **Reconciliation.** The broker is treated as the source of truth for holdings,
  with orphan adoption under ladder risk management and ghost removal — the right
  default for a system whose state file is runtime-only.

## One environment note

`tests/test_robinhood_safety.py` fails on a fresh checkout with
`ModuleNotFoundError: nacl`. It is not a code defect — `pynacl` is declared in
`requirements.txt` but is an optional extra for the Robinhood venue. Installing
it makes the suite 21/21. Worth knowing before anyone reads that failure as a
safety regression.

## Verify

```bash
python -m py_compile $(git ls-files '*.py')   # syntax gate
python -m tests.test_optimizations            # 25 equivalence/invariant checks
python -m tests.test_dry_run                  # 8 offline cycles
python main.py --cycles 8                     # regenerates public/status.json
```
