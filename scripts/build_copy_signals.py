"""Curated copy-trading signal feed — SEC Form 4 insider open-market purchases.

Highest-standard, keyless, authoritative source: the SEC EDGAR full-text search
API (efts.sec.gov) for recent Form 4 filings, then each filing's official XML.
We keep only **open-market purchases** (transaction code "P") — insider buying is
a well-studied alpha signal and far cleaner than insider *sales* (which are often
just comp/diversification). Output is the exact JSON the CopyTrader expects:

    [{"symbol","side":"buy","weight","source"}, ...]

Ranked by aggregate purchase notional, deduped per ticker, capped to TOP_N. The
SAHJONY Risk Officer still gates every mirrored order (alloc caps, conviction).

Run:  python -m scripts.build_copy_signals          # writes public/copy_signals.json
Safety: on any failure OR an empty result it leaves the previous feed untouched,
so a bad fetch never blanks the desk's signals.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

import requests

UA = {"User-Agent": os.getenv("SEC_USER_AGENT",
                              "SAHJONY Capital research contact@sahjonycapital.com")}
EFTS = "https://efts.sec.gov/LATEST/search-index?forms=4"
OUT = os.getenv("COPY_SIGNALS_OUT", "public/copy_signals.json")
TOP_N = int(os.getenv("COPY_SIGNALS_TOP_N", "15"))
MAX_SCAN = int(os.getenv("COPY_SIGNALS_MAX_SCAN", "80"))   # filings to fetch/parse

_TX = re.compile(r"<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>", re.S)
_SYM = re.compile(r"<issuerTradingSymbol>\s*(.*?)\s*</issuerTradingSymbol>", re.S)
_CODE = re.compile(r"<transactionCode>\s*(.*?)\s*</transactionCode>", re.S)
_SH = re.compile(r"<transactionShares>\s*<value>\s*(.*?)\s*</value>", re.S)
_PX = re.compile(r"<transactionPricePerShare>\s*<value>\s*(.*?)\s*</value>", re.S)


def _recent_form4_ids(limit: int) -> list:
    """Return [(accession, filename, [ciks]), ...] for the most recent Form 4s."""
    r = requests.get(EFTS, headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", {}).get("hits", [])[:limit]:
        acc, _, fn = h.get("_id", "").partition(":")
        ciks = h.get("_source", {}).get("ciks", [])
        if acc and fn and ciks:
            out.append((acc, fn, ciks))
    return out


def _fetch_xml(acc: str, fn: str, ciks: list) -> str:
    accn = acc.replace("-", "")
    for cik in ciks:
        try:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{fn}"
            x = requests.get(url, headers=UA, timeout=20)
            if x.ok and "<" in x.text:
                return x.text
        except Exception:
            continue
    return ""


def _purchases(xml: str):
    """Yield (ticker, shares, price) for open-market purchases (code 'P')."""
    sym_m = _SYM.search(xml)
    if not sym_m:
        return
    ticker = sym_m.group(1).upper().strip()
    if not ticker or "/" in ticker or len(ticker) > 6:
        return
    for block in _TX.findall(xml):
        code = _CODE.search(block)
        if not code or code.group(1).strip().upper() != "P":   # P = open-market purchase
            continue
        try:
            shares = float((_SH.search(block) or [None, "0"]).group(1))
            price = float((_PX.search(block) or [None, "0"]).group(1))
        except Exception:
            continue
        if shares > 0 and price > 0:
            yield ticker, shares, price


def build() -> list:
    notional = defaultdict(float)
    who = {}
    scanned = kept = 0
    for acc, fn, ciks in _recent_form4_ids(MAX_SCAN):
        xml = _fetch_xml(acc, fn, ciks)
        scanned += 1
        if not xml:
            continue
        owner = re.search(r"<rptOwnerName>\s*(.*?)\s*</rptOwnerName>", xml, re.S)
        owner = (owner.group(1).strip() if owner else "insider")[:48]
        for ticker, shares, price in _purchases(xml):
            notional[ticker] += shares * price
            who.setdefault(ticker, owner)
            kept += 1
        time.sleep(0.12)   # be polite to SEC (<10 req/s)
    if not notional:
        return []
    ranked = sorted(notional.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    top = ranked[0][1] if ranked else 1.0
    signals = []
    for ticker, val in ranked:
        signals.append({"symbol": ticker, "side": "buy",
                        "weight": round(max(0.25, min(1.0, val / top)), 3),
                        "source": f"SEC Form 4: {who.get(ticker, 'insider')}"})
    print(f"scanned={scanned} purchases={kept} tickers={len(notional)} → {len(signals)} signals")
    return signals


def main() -> int:
    try:
        signals = build()
    except Exception as exc:
        print(f"build failed ({exc}) — leaving existing feed untouched")
        return 1
    if not signals:
        print("no insider purchases found — leaving existing feed untouched")
        return 1
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(signals, f, indent=2)
    print(f"wrote {OUT} with {len(signals)} signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
