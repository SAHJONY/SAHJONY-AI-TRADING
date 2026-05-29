'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Play, BarChart3, TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight,
  Clock, CheckCircle, AlertTriangle, ChevronRight, Plus, Trash2, Zap,
  Target, Shield, Percent, Activity,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarketChart } from '@/components/trading/market-chart'
import type { TradingBacktest, TradingStrategy, AssetType, BacktestResults } from '@/types/trading'
import { TRADING_ASSETS, TIMEFRAMES } from '@/types/trading'
import { TopNav } from '@/components/layout/top-nav'

export default function BacktestingPage() {
  const [backtests, setBacktests] = useState<TradingBacktest[]>([])
  const [strategies, setStrategies] = useState<TradingStrategy[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)

  // Backtest form
  const [form, setForm] = useState({
    strategyId: '',
    name: '',
    symbol: 'AAPL',
    assetType: 'stock' as AssetType,
    timeframe: '1d',
    startDate: '',
    endDate: '',
    initialCapital: 10000,
  })

  // Expanded backtest
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [btRes, stRes] = await Promise.all([
          fetch('/api/trading/backtesting'),
          fetch('/api/trading/strategies'),
        ])

        const btData = await btRes.json()
        const stData = await stRes.json()

        if (btData.backtests) setBacktests(btData.backtests)
        if (stData.strategies) {
          setStrategies(stData.strategies)
          if (!form.strategyId && stData.strategies.length > 0) {
            setForm(f => ({ ...f, strategyId: stData.strategies[0].id }))
          }
        }

        // Default date range: last 6 months
        const end = new Date()
        const start = new Date()
        start.setMonth(start.getMonth() - 6)
        setForm(f => ({
          ...f,
          startDate: start.toISOString().slice(0, 10),
          endDate: end.toISOString().slice(0, 10),
        }))
      } catch { /* ignore */ } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleRunBacktest = async () => {
    if (!form.strategyId || !form.symbol) return
    setRunning(true)
    try {
      const res = await fetch('/api/trading/backtesting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (data.backtest) {
        setBacktests(prev => [data.backtest, ...prev])
        setExpanded(data.backtest.id)
      }
    } catch { /* ignore */ } finally {
      setRunning(false)
    }
  }

  const handleDelete = async (id: string) => {
    await fetch(`/api/trading/backtesting/${id}`, { method: 'DELETE' })
    setBacktests(prev => prev.filter(b => b.id !== id))
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <BarChart3 className="h-8 w-8 text-accent" />
              Backtesting
            </h1>
            <p className="text-zinc-400 mt-1">Test your trading strategies against historical data</p>
          </div>
          <Link
            href="/trading"
            className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 hover:text-white border border-border rounded-lg hover:border-zinc-600 transition-all"
          >
            <ChevronRight className="h-4 w-4 rotate-180" />
            Dashboard
          </Link>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Backtest Form */}
          <div className="lg:col-span-1">
            <div className="card-elevated p-5 sticky top-20">
              <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Play className="h-4 w-4 text-accent" />
                Run Backtest
              </h2>

              <div className="space-y-4">
                {/* Strategy */}
                <div>
                  <label className="text-xs text-zinc-500 mb-1 block">Strategy</label>
                  <select
                    value={form.strategyId}
                    onChange={(e) => setForm({ ...form, strategyId: e.target.value })}
                    className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary"
                  >
                    <option value="">Select strategy</option>
                    {strategies.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>

                {/* Symbol */}
                <div>
                  <label className="text-xs text-zinc-500 mb-1 block">Symbol</label>
                  <input
                    type="text"
                    value={form.symbol}
                    onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary"
                  />
                </div>

                {/* Asset Type */}
                <div>
                  <label className="text-xs text-zinc-500 mb-1 block">Asset Type</label>
                  <div className="flex gap-1">
                    {(Object.entries(TRADING_ASSETS) as [AssetType, typeof TRADING_ASSETS['stock']][]).map(([key, info]) => (
                      <button
                        key={key}
                        onClick={() => setForm({ ...form, assetType: key })}
                        className={cn(
                          'flex-1 py-1.5 rounded-md text-xs font-medium transition-all',
                          form.assetType === key
                            ? 'bg-primary/20 text-primary border border-primary/30'
                            : 'text-zinc-500 hover:text-white border border-transparent'
                        )}
                      >
                        {info.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Timeframe */}
                <div>
                  <label className="text-xs text-zinc-500 mb-1 block">Timeframe</label>
                  <select
                    value={form.timeframe}
                    onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
                    className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white"
                  >
                    {TIMEFRAMES.map(tf => (
                      <option key={tf.value} value={tf.value}>{tf.label}</option>
                    ))}
                  </select>
                </div>

                {/* Date Range */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-zinc-500 mb-1 block">Start Date</label>
                    <input
                      type="date"
                      value={form.startDate}
                      onChange={(e) => setForm({ ...form, startDate: e.target.value })}
                      className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 mb-1 block">End Date</label>
                    <input
                      type="date"
                      value={form.endDate}
                      onChange={(e) => setForm({ ...form, endDate: e.target.value })}
                      className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white"
                    />
                  </div>
                </div>

                {/* Initial Capital */}
                <div>
                  <label className="text-xs text-zinc-500 mb-1 block">Initial Capital ($)</label>
                  <input
                    type="number"
                    value={form.initialCapital}
                    onChange={(e) => setForm({ ...form, initialCapital: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white"
                  />
                </div>

                <button
                  onClick={handleRunBacktest}
                  disabled={!form.strategyId || running}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-accent/20 text-accent border border-accent/30 rounded-xl font-semibold hover:bg-accent/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  {running ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {running ? 'Running...' : 'Run Backtest'}
                </button>
              </div>
            </div>
          </div>

          {/* Results */}
          <div className="lg:col-span-2 space-y-5">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : backtests.length === 0 ? (
              <div className="card-elevated p-12 text-center">
                <BarChart3 className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
                <p className="text-white font-semibold mb-2">No backtests yet</p>
                <p className="text-zinc-500 text-sm">Select a strategy and symbol to run your first backtest</p>
              </div>
            ) : (
              backtests.map(bt => (
                <div key={bt.id} className="card-elevated overflow-hidden">
                  <div className="p-5">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                          {bt.name}
                          <span className={cn(
                            'px-2 py-0.5 rounded-full text-xs font-medium',
                            bt.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400' :
                            bt.status === 'running' ? 'bg-accent/10 text-accent' :
                            'bg-red-500/10 text-red-400'
                          )}>
                            {bt.status === 'running' && <Clock className="inline h-3 w-3 mr-1 animate-spin" />}
                            {bt.status}
                          </span>
                        </h3>
                        <div className="flex items-center gap-3 mt-1 text-xs text-zinc-500">
                          <span>{bt.symbol}</span>
                          <span>•</span>
                          <span>{bt.assetType}</span>
                          <span>•</span>
                          <span>{bt.timeframe}</span>
                          <span>•</span>
                          <span>{new Date(bt.startDate).toLocaleDateString()} — {new Date(bt.endDate).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <button onClick={() => handleDelete(bt.id)} className="text-zinc-500 hover:text-red-400 transition-colors">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                    {bt.status === 'completed' && bt.totalReturn !== null && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                        <div className="bg-zinc-800/50 p-3 rounded-lg text-center">
                          <div className="text-xs text-zinc-500 mb-1">Total Return</div>
                          <div className={cn(
                            'text-lg font-bold',
                            bt.totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'
                          )}>
                            {bt.totalReturn >= 0 ? '+' : ''}{bt.totalReturn.toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-zinc-800/50 p-3 rounded-lg text-center">
                          <div className="text-xs text-zinc-500 mb-1">Max Drawdown</div>
                          <div className="text-lg font-bold text-red-400">{bt.maxDrawdown?.toFixed(2)}%</div>
                        </div>
                        <div className="bg-zinc-800/50 p-3 rounded-lg text-center">
                          <div className="text-xs text-zinc-500 mb-1">Sharpe Ratio</div>
                          <div className="text-lg font-bold text-white">{bt.sharpeRatio?.toFixed(2)}</div>
                        </div>
                        <div className="bg-zinc-800/50 p-3 rounded-lg text-center">
                          <div className="text-xs text-zinc-500 mb-1">Win Rate</div>
                          <div className="text-lg font-bold text-white">{bt.winRate?.toFixed(1)}%</div>
                        </div>
                      </div>
                    )}

                    {/* Expand/Collapse */}
                    <button
                      onClick={() => setExpanded(expanded === bt.id ? null : bt.id)}
                      className="flex items-center gap-1 mt-3 text-sm text-primary hover:text-primary-hover transition-colors"
                    >
                      {expanded === bt.id ? 'Hide Details' : 'Show Details'}
                      <ChevronRight className={cn('h-4 w-4 transition-transform', expanded === bt.id && 'rotate-90')} />
                    </button>
                  </div>

                  {/* Expanded Details */}
                  {expanded === bt.id && bt.status === 'completed' && (
                    <div className="border-t border-border p-5 space-y-5">
                      {/* Trade metrics */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="flex items-center gap-2">
                          <Target className="h-5 w-5 text-primary" />
                          <div>
                            <div className="text-xs text-zinc-500">Total Trades</div>
                            <div className="text-sm font-bold text-white">{bt.totalTrades}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <ArrowUpRight className="h-5 w-5 text-emerald-400" />
                          <div>
                            <div className="text-xs text-zinc-500">Profitable</div>
                            <div className="text-sm font-bold text-emerald-400">{bt.profitableTrades}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <ArrowDownRight className="h-5 w-5 text-red-400" />
                          <div>
                            <div className="text-xs text-zinc-500">Losing</div>
                            <div className="text-sm font-bold text-red-400">{bt.losingTrades}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Shield className="h-5 w-5 text-accent" />
                          <div>
                            <div className="text-xs text-zinc-500">Avg Win / Loss</div>
                            <div className="text-sm font-bold text-white">
                              ${bt.avgWin?.toFixed(2)} / ${bt.avgLoss?.toFixed(2)}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Capital */}
                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-zinc-800/50 p-4 rounded-lg">
                          <div className="text-xs text-zinc-500 mb-1">Initial Capital</div>
                          <div className="text-xl font-bold text-white">
                            ${bt.initialCapital.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </div>
                        </div>
                        <div className="bg-zinc-800/50 p-4 rounded-lg">
                          <div className="text-xs text-zinc-500 mb-1">Final Capital</div>
                          <div className={cn(
                            'text-xl font-bold',
                            bt.finalCapital && bt.finalCapital >= bt.initialCapital ? 'text-emerald-400' : 'text-red-400'
                          )}>
                            ${bt.finalCapital?.toLocaleString('en-US', { minimumFractionDigits: 2 }) || '---'}
                          </div>
                        </div>
                      </div>

                      {/* Equity curve chart */}
                      {bt.resultsJson.equityCurve && bt.resultsJson.equityCurve.length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Equity Curve</h4>
                          <div className="bg-zinc-800/50 rounded-lg p-3">
                            <MarketChart
                              data={bt.resultsJson.equityCurve.map(e => ({
                                timestamp: e.timestamp,
                                open: e.value,
                                high: e.value,
                                low: e.value,
                                close: e.value,
                                volume: 0,
                              }))}
                              color="#22d3ee"
                              showVolume={false}
                              height={200}
                            />
                          </div>
                        </div>
                      )}

                      {/* Trade list */}
                      {bt.resultsJson.trades && bt.resultsJson.trades.length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                            Trades ({bt.resultsJson.trades.length})
                          </h4>
                          <div className="max-h-64 overflow-y-auto space-y-2">
                            {bt.resultsJson.trades.map((trade, i) => (
                              <div key={i} className="flex items-center justify-between p-3 bg-zinc-800/30 rounded-lg text-sm">
                                <div className="flex items-center gap-3">
                                  <span className={cn(
                                    'px-2 py-0.5 rounded text-xs font-bold',
                                    trade.pnl >= 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                                  )}>
                                    {trade.side.toUpperCase()}
                                  </span>
                                  <div className="text-xs text-zinc-500">
                                    {new Date(trade.entryDate).toLocaleDateString()} → {new Date(trade.exitDate).toLocaleDateString()}
                                  </div>
                                </div>
                                <div className="flex items-center gap-3 text-xs">
                                  <span className="text-zinc-400">Entry: ${trade.entryPrice.toFixed(2)}</span>
                                  <span className="text-zinc-400">Exit: ${trade.exitPrice.toFixed(2)}</span>
                                  <span className={cn(
                                    'font-semibold',
                                    trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                                  )}>
                                    {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)} ({trade.pnlPct >= 0 ? '+' : ''}{trade.pnlPct.toFixed(2)}%)
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
