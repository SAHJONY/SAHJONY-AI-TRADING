"""Backtest harness for docs/btc_futures_5m_playbook.md (OHLCV-only strategies).

Offline by design: no broker, no DB, no LLM. Feed it 5m bars, get trade-by-trade
results with fees, slippage, fixed-fractional sizing and a leverage cap applied.
"""
