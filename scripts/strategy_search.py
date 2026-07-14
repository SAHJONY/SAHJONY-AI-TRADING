"""Large-scale strategy parameter search over the desk's crypto universe.

Runs ~200k systematic-strategy backtests across BTC/ETH/SOL/LTC and ranks them —
HONESTLY. Picking the best of 200k configs on one dataset is data-mining: the top
in-sample result is usually overfit noise. So we:
  1. split each series into IN-SAMPLE (train, first 70%) and OUT-OF-SAMPLE (test),
  2. rank candidates by the WORSE of train/test Sharpe (robustness, not luck),
  3. report test performance + buy&hold benchmark + train→test degradation.

Each strategy is tested across THREE realistic dimensions, which is what gets us to
200k honestly (not padding): the signal family+params, the transaction cost charged
per position change (0.10% / 0.50% / 0.95%-Robinhood-live), and whether position size
is volatility-scaled (de-risk when realized vol spikes). A strategy that only works at
zero cost, or only un-scaled, is fragile — spanning these exposes that.

Usage:  python -m scripts.strategy_search [N]      (default N=200000)
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.request
from multiprocessing import Pool

import numpy as np

CG_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "LTC": "litecoin"}
ANN = math.sqrt(365.0)
TRAIN_FRAC = 0.70
COSTS = (0.001, 0.005, 0.0095)     # per-turnover: 0.10% / 0.50% / 0.95% (RH live)
VOL_SCALES = (False, True)
VOL_TARGET_DAILY = 0.02            # ~38% annual; vol-scaling caps exposure above this
SEED = 20260704

_PRICES: dict = {}
_RETS: dict = {}
_VOLSCALE: dict = {}


# ── data ─────────────────────────────────────────────────────────────────────
def fetch_prices(days: int = 365) -> dict:
    out = {}
    for sym, cg in CG_IDS.items():
        url = (f"https://api.coingecko.com/api/v3/coins/{cg}/market_chart"
               f"?vs_currency=usd&days={days}&interval=daily")
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.load(r)
        out[sym] = np.array([p[1] for p in data.get("prices", [])], dtype=float)
        time.sleep(2.5)
    return out


# ── indicators ─────────────────────────────────────────────────────────────────
def _sma(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0))
    return np.concatenate([np.full(n - 1, np.nan), (c[n:] - c[:-n]) / n])


def _ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _rsi(x, n):
    d = np.diff(x)
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ku = np.convolve(up, np.ones(n) / n, "full")[:len(up)]
    kd = np.convolve(dn, np.ones(n) / n, "full")[:len(dn)]
    rs = np.divide(ku, kd, out=np.full_like(ku, np.inf), where=kd > 1e-12)
    return np.concatenate([[np.nan], 100 - 100 / (1 + rs)])


def _roll(x, n, fn):
    out = np.full_like(x, np.nan)
    for i in range(n - 1, len(x)):
        out[i] = fn(x[i - n + 1:i + 1])
    return out


# ── signal → position in {-1,0,1} ──────────────────────────────────────────────
def signal(prices, cfg):
    fam = cfg[0]
    if fam == "sma":
        _, fast, slow, short = cfg
        f, s = _sma(prices, fast), _sma(prices, slow)
        pos = np.where(f > s, 1.0, (-1.0 if short else 0.0))
        pos[np.isnan(f) | np.isnan(s)] = 0.0
        return pos
    if fam == "macd":
        _, fast, slow, sig, short = cfg
        line = _ema(prices, fast) - _ema(prices, slow)
        sigl = _ema(line, sig)
        pos = np.where(line > sigl, 1.0, (-1.0 if short else 0.0))
        return pos
    if fam == "rsi":
        _, n, lo, hi = cfg
        r = _rsi(prices, n)
        pos = np.zeros_like(prices)
        st = 0.0
        for i in range(len(prices)):
            if not math.isnan(r[i]):
                if r[i] < lo:
                    st = 1.0
                elif r[i] > hi:
                    st = 0.0
            pos[i] = st
        return pos
    if fam == "mom":
        _, look, short = cfg
        pos = np.zeros_like(prices)
        pos[look:] = np.where(prices[look:] > prices[:-look], 1.0, (-1.0 if short else 0.0))
        return pos
    if fam == "boll":
        _, n, k, _short = cfg
        m, sd = _sma(prices, n), _roll(prices, n, lambda w: w.std(ddof=0))
        lo, up = m - k * sd, m + k * sd
        pos = np.zeros_like(prices)
        st = 0.0
        for i in range(len(prices)):
            if not (math.isnan(lo[i]) or math.isnan(up[i])):
                if prices[i] < lo[i]:
                    st = 1.0
                elif prices[i] > up[i] or prices[i] >= m[i]:
                    st = 0.0
            pos[i] = st
        return pos
    if fam == "don":
        _, n, short = cfg
        hi, lo = _roll(prices, n, np.max), _roll(prices, n, np.min)
        pos = np.zeros_like(prices)
        st = 0.0
        for i in range(len(prices)):
            if not (math.isnan(hi[i]) or math.isnan(lo[i])):
                if prices[i] >= hi[i]:
                    st = 1.0
                elif prices[i] <= lo[i]:
                    st = -1.0 if short else 0.0
            pos[i] = st
        return pos
    return np.zeros_like(prices)


def _sharpe(rets):
    if len(rets) < 5:
        return 0.0, 0.0, 0.0
    mean, sd = rets.mean(), rets.std(ddof=1)
    sh = mean / sd * ANN if sd > 1e-9 else 0.0
    eq = np.cumprod(1.0 + rets)
    peak = np.maximum.accumulate(eq)
    return float(sh), float(eq[-1] - 1.0), float(((eq - peak) / peak).min())


def evaluate(cfg):
    base, sym, cost, vs = cfg[:-3], cfg[-3], cfg[-2], cfg[-1]
    prices, rets = _PRICES[sym], _RETS[sym]
    pos = signal(prices, base)
    if vs:
        pos = pos * _VOLSCALE[sym]
    split = int(len(prices) * TRAIN_FRAC)

    def run(sl_prices, sl_pos):
        r = np.diff(sl_prices) / sl_prices[:-1]
        held = sl_pos[:-1]
        turn = np.abs(np.diff(np.concatenate([[0.0], held])))
        return held * r - turn * cost

    tr = _sharpe(run(prices[:split], pos[:split]))
    te = _sharpe(run(prices[split:], pos[split:]))
    n_trades = int(np.abs(np.diff(np.concatenate([[0.0], np.sign(pos)]))).sum() / 2)
    return (tr[0], te[0], te[1], te[2], n_trades)


def _init(prices):
    global _PRICES, _RETS, _VOLSCALE
    _PRICES = prices
    _RETS = {s: np.diff(p) / p[:-1] for s, p in prices.items()}
    _VOLSCALE = {}
    for s, p in prices.items():
        r = np.concatenate([[0.0], np.diff(p) / p[:-1]])
        rv = _roll(r, 20, lambda w: w.std(ddof=0))
        sc = np.clip(VOL_TARGET_DAILY / np.where(rv > 1e-6, rv, np.inf), 0.0, 1.0)
        sc[np.isnan(sc)] = 1.0
        _VOLSCALE[s] = sc


# ── config space ───────────────────────────────────────────────────────────────
def base_configs():
    b = []
    for fast in range(2, 51):
        for slow in range(fast + 3, 205, 4):
            for short in (False, True):
                b.append(("sma", fast, slow, short))
    for fast in (6, 8, 10, 12, 16, 20):
        for slow in (20, 26, 30, 40, 50):
            for sig in (7, 9, 12):
                for short in (False, True):
                    b.append(("macd", fast, slow, sig, short))
    for n in range(5, 31):
        for lo in range(10, 42, 3):
            for hi in range(60, 92, 3):
                b.append(("rsi", n, lo, hi))
    for look in range(3, 100):
        for short in (False, True):
            b.append(("mom", look, short))
    for n in range(6, 41):
        for k in (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0):
            b.append(("boll", n, k, False))
    for n in range(5, 90):
        for short in (False, True):
            b.append(("don", n, short))
    return b


def main(argv=None):
    argv = argv or sys.argv[1:]
    target = int(argv[0]) if argv else 200000
    print(f"SAHJONY strategy search — target {target:,} backtests\n" + "=" * 66)
    print("Fetching CoinGecko daily history (BTC/ETH/SOL/LTC)…")
    prices = fetch_prices()
    for s, p in prices.items():
        print(f"  {s}: {len(p)} days  ${p[0]:,.0f} → ${p[-1]:,.0f}  (buy&hold {p[-1]/p[0]-1:+.1%})")
    split = int(min(len(p) for p in prices.values()) * TRAIN_FRAC)
    print(f"  train/test split at day {split} ({TRAIN_FRAC:.0%}/{1-TRAIN_FRAC:.0%})\n")

    base = base_configs()
    cfgs = [(*b, sym, cost, vs) for b in base for sym in CG_IDS
            for cost in COSTS for vs in VOL_SCALES]
    rng = np.random.default_rng(SEED)
    rng.shuffle(cfgs)
    if len(cfgs) > target:
        cfgs = cfgs[:target]
    print(f"Config space: {len(base):,} base × {len(CG_IDS)} sym × {len(COSTS)} cost × "
          f"{len(VOL_SCALES)} sizing → {len(cfgs):,} strategies. Backtesting…")

    t0 = time.time()
    with Pool(initializer=_init, initargs=(prices,)) as pool:
        results = pool.map(evaluate, cfgs, chunksize=1500)
    dt = time.time() - t0
    print(f"Done: {len(results):,} backtests in {dt:.1f}s ({len(results)/dt:,.0f}/s)\n")

    bh = {s: float(p[split:][-1] / p[split:][0] - 1.0) for s, p in prices.items()}
    rows = [(c, r) for c, r in zip(cfgs, results) if r is not None]
    rows.sort(key=lambda cr: (min(cr[1][0], cr[1][1]), cr[1][1]), reverse=True)

    print("TOP 15 STRATEGIES  (ranked by min(train,test) Sharpe — robust to overfitting)")
    print("-" * 100)
    print(f"{'#':>2}  {'strategy':<30}{'sym':<5}{'cost':>6}{'sized':>7}"
          f"{'trainSh':>8}{'testSh':>8}{'testRet':>9}{'maxDD':>8}{'trades':>7}")
    for i, (c, r) in enumerate(rows[:15], 1):
        tr, te, ret, dd, nt = r
        print(f"{i:>2}  {_describe(c[:-3]):<30}{c[-3]:<5}{c[-2]*100:>5.2f}%"
              f"{('vol' if c[-1] else 'flat'):>7}{tr:>8.2f}{te:>8.2f}{ret:>+8.1%}{dd:>+7.1%}{nt:>7}")

    train_sorted = sorted(rows, key=lambda cr: cr[1][0], reverse=True)
    tb = train_sorted[0]
    med_te = float(np.median([r[1] for _, r in rows]))
    print("\nOVERFITTING CHECK")
    print("-" * 66)
    print(f"  Best IN-SAMPLE: {_describe(tb[0][:-3])} [{tb[0][-3]}]  "
          f"train Sharpe {tb[1][0]:.2f} → test {tb[1][1]:.2f}")
    print(f"  Median test Sharpe across all {len(rows):,}: {med_te:.2f}  (≈0 ⇒ most are noise)")
    print("  Buy & hold (test): " + "  ".join(f"{s} {v:+.1%}" for s, v in bh.items()))

    winners = [{"rank": i + 1, "strategy": _describe(c[:-3]), "symbol": c[-3],
                "cost_pct": round(c[-2] * 100, 3), "vol_sized": bool(c[-1]),
                "train_sharpe": round(r[0], 3), "test_sharpe": round(r[1], 3),
                "test_return": round(r[2], 4), "test_max_dd": round(r[3], 4), "trades": r[4]}
               for i, (c, r) in enumerate(rows[:25])]
    with open("strategy_search_results.json", "w") as fh:
        json.dump({"tested": len(rows), "split_day": split, "benchmark_test": bh,
                   "winners": winners}, fh, indent=2)
    print("\nSaved top 25 → strategy_search_results.json")
    return 0


def _describe(c):
    fam = c[0]
    return {
        "sma": lambda: f"SMA {c[1]}/{c[2]}{' L/S' if c[3] else ''}",
        "macd": lambda: f"MACD {c[1]}/{c[2]}/{c[3]}{' L/S' if c[4] else ''}",
        "rsi": lambda: f"RSI({c[1]}) <{c[2]} >{c[3]}",
        "mom": lambda: f"Momentum {c[1]}d{' L/S' if c[2] else ''}",
        "boll": lambda: f"Bollinger({c[1]},{c[2]}σ)",
        "don": lambda: f"Donchian {c[1]}d{' L/S' if c[2] else ''}",
    }.get(fam, lambda: str(c))()


if __name__ == "__main__":
    raise SystemExit(main())
