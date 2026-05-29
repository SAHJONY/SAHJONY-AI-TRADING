'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Bot, Plus, Play, Trash2, ArrowUpRight, ArrowDownRight, Minus,
  BarChart3, Activity, ChevronRight, Zap, TrendingUp, Clock, CheckCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { StrategyBuilder } from '@/components/trading/strategy-builder'
import type { TradingStrategy, StrategyStatus, AssetType } from '@/types/trading'
import { TRADING_ASSETS } from '@/types/trading'
import { TopNav } from '@/components/layout/top-nav'

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<TradingStrategy[]>([])
  const [showBuilder, setShowBuilder] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<TradingStrategy | null>(null)
  const [testingSymbol, setTestingSymbol] = useState('AAPL')
  const [testingAssetType, setTestingAssetType] = useState<AssetType>('stock')
  const [signal, setSignal] = useState<{ signal: string; confidence: number; reason: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadStrategies()
  }, [])

  const loadStrategies = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/trading/strategies')
      const data = await res.json()
      if (data.strategies) setStrategies(data.strategies)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  const handleSave = async (data: {
    name: string; description: string; assetTypes: AssetType[];
    indicators: any[]; conditions: any
  }) => {
    const res = await fetch('/api/trading/strategies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (res.ok) {
      setShowBuilder(false)
      await loadStrategies()
    }
  }

  const handleDelete = async (id: string) => {
    await fetch(`/api/trading/strategies/${id}`, { method: 'DELETE' })
    await loadStrategies()
  }

  const handleTestSignal = async (strategyId: string) => {
    setTesting(true)
    setSignal(null)
    try {
      const res = await fetch(`/api/trading/strategies/${strategyId}/signal?symbol=${testingSymbol}&assetType=${testingAssetType}`)
      const data = await res.json()
      if (data.signal) setSignal(data.signal)
    } catch { /* ignore */ } finally {
      setTesting(false)
    }
  }

  const handleStatusChange = async (id: string, status: StrategyStatus) => {
    await fetch(`/api/trading/strategies/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    await loadStrategies()
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Bot className="h-8 w-8 text-primary" />
              Trading Strategies
            </h1>
            <p className="text-zinc-400 mt-1">Create and manage AI-powered trading strategies</p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/trading"
              className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 hover:text-white border border-border rounded-lg hover:border-zinc-600 transition-all"
            >
              <ChevronRight className="h-4 w-4 rotate-180" />
              Dashboard
            </Link>
            <button
              onClick={() => setShowBuilder(true)}
              className="flex items-center gap-2 px-5 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover hover:shadow-primary transition-all"
            >
              <Plus className="h-4 w-4" />
              New Strategy
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Strategy List */}
          <div className="lg:col-span-2 space-y-5">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
              </div>
            ) : strategies.length === 0 && !showBuilder ? (
              <div className="card-elevated p-12 text-center">
                <Bot className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
                <p className="text-white font-semibold mb-2">No strategies yet</p>
                <p className="text-zinc-500 text-sm mb-5">Create a strategy to automate your trading signals</p>
                <button
                  onClick={() => setShowBuilder(true)}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
                >
                  <Plus className="h-4 w-4" />
                  Create Your First Strategy
                </button>
              </div>
            ) : (
              strategies.map(s => (
                <div key={s.id} className={cn(
                  'card-elevated overflow-hidden',
                  selectedStrategy?.id === s.id && 'ring-1 ring-primary/50'
                )}>
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold text-white">{s.name}</h3>
                          <span className={cn(
                            'px-2 py-0.5 rounded-full text-xs font-medium',
                            s.status === 'active' ? 'bg-emerald-500/10 text-emerald-400' :
                            s.status === 'draft' ? 'bg-zinc-700 text-zinc-400' :
                            s.status === 'paused' ? 'bg-amber-500/10 text-amber-400' :
                            'bg-zinc-700 text-zinc-500'
                          )}>
                            {s.status}
                          </span>
                        </div>
                        {s.description && <p className="text-sm text-zinc-400">{s.description}</p>}
                      </div>
                      <div className="flex items-center gap-2">
                        <select
                          value={s.status}
                          onChange={(e) => handleStatusChange(s.id, e.target.value as StrategyStatus)}
                          className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white"
                        >
                          <option value="draft">Draft</option>
                          <option value="active">Active</option>
                          <option value="paused">Paused</option>
                          <option value="archived">Archived</option>
                        </select>
                        <button
                          onClick={() => handleDelete(s.id)}
                          className="p-1.5 text-zinc-500 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>

                    {/* Asset types */}
                    <div className="flex gap-1 mb-3">
                      {s.assetTypes.map(at => (
                        <span key={at} className="px-2 py-0.5 rounded text-xs" style={{ backgroundColor: TRADING_ASSETS[at].color + '20', color: TRADING_ASSETS[at].color }}>
                          {TRADING_ASSETS[at].label}
                        </span>
                      ))}
                    </div>

                    {/* Indicators */}
                    <div className="flex flex-wrap gap-2 mb-3">
                      {s.indicators.map(ind => (
                        <span key={ind.id} className="px-2 py-1 rounded-lg bg-zinc-800 text-xs text-zinc-300">
                          {ind.name || ind.type} ({ind.type.toUpperCase()})
                        </span>
                      ))}
                    </div>

                    {/* Conditions summary */}
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <div className="text-xs text-emerald-400 uppercase tracking-wider mb-1 font-semibold">
                          Entry ({s.conditions.entry.length})
                        </div>
                        {s.conditions.entry.map(c => (
                          <div key={c.id} className="text-zinc-400 text-xs">
                            {c.indicator || '---'} {c.operator} {c.value}
                          </div>
                        ))}
                      </div>
                      <div>
                        <div className="text-xs text-red-400 uppercase tracking-wider mb-1 font-semibold">
                          Exit ({s.conditions.exit.length})
                        </div>
                        {s.conditions.exit.map(c => (
                          <div key={c.id} className="text-zinc-400 text-xs">
                            {c.indicator || '---'} {c.operator} {c.value}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Metrics */}
                    {(s.performanceMetrics.totalTrades > 0) && (
                      <div className="grid grid-cols-4 gap-3 mt-4 pt-4 border-t border-border">
                        <div className="text-center">
                          <div className="text-xs text-zinc-500">Win Rate</div>
                          <div className="text-sm font-bold text-white">{s.performanceMetrics.winRate.toFixed(1)}%</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xs text-zinc-500">Trades</div>
                          <div className="text-sm font-bold text-white">{s.performanceMetrics.totalTrades}</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xs text-zinc-500">Sharpe</div>
                          <div className="text-sm font-bold text-white">{s.performanceMetrics.sharpeRatio.toFixed(2)}</div>
                        </div>
                        <div className="text-center">
                          <div className="text-xs text-zinc-500">Return</div>
                          <div className={cn(
                            'text-sm font-bold',
                            s.performanceMetrics.totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'
                          )}>
                            {s.performanceMetrics.totalReturn.toFixed(2)}%
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Test signal button */}
                    <button
                      onClick={() => {
                        setSelectedStrategy(s.id === selectedStrategy?.id ? null : s)
                        setSignal(null)
                      }}
                      className="flex items-center gap-2 mt-4 text-sm text-primary hover:text-primary-hover transition-colors"
                    >
                      <Play className="h-4 w-4" />
                      {selectedStrategy?.id === s.id ? 'Hide Test Panel' : 'Test Signal'}
                    </button>
                  </div>

                  {/* Signal Test Panel */}
                  {selectedStrategy?.id === s.id && (
                    <div className="border-t border-border p-5 bg-zinc-800/30">
                      <div className="flex items-center gap-3 mb-3">
                        <input
                          type="text"
                          value={testingSymbol}
                          onChange={(e) => setTestingSymbol(e.target.value)}
                          placeholder="Symbol"
                          className="w-32 px-3 py-1.5 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary"
                        />
                        <select
                          value={testingAssetType}
                          onChange={(e) => setTestingAssetType(e.target.value as AssetType)}
                          className="bg-zinc-800 border border-border rounded-lg px-2 py-1.5 text-sm text-white"
                        >
                          <option value="stock">Stock</option>
                          <option value="crypto">Crypto</option>
                          <option value="forex">Forex</option>
                        </select>
                        <button
                          onClick={() => handleTestSignal(s.id)}
                          disabled={testing}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-white text-sm rounded-lg hover:bg-primary-hover transition-all disabled:opacity-50"
                        >
                          <Zap className="h-4 w-4" />
                          {testing ? 'Testing...' : 'Generate Signal'}
                        </button>
                      </div>

                      {signal && (
                        <div className={cn(
                          'flex items-center gap-3 p-3 rounded-lg',
                          signal.signal === 'buy' ? 'bg-emerald-500/10 border border-emerald-500/20' :
                          signal.signal === 'sell' ? 'bg-red-500/10 border border-red-500/20' :
                          'bg-zinc-800 border border-border'
                        )}>
                          <div className={cn(
                            'p-2 rounded-lg',
                            signal.signal === 'buy' ? 'bg-emerald-500/20' :
                            signal.signal === 'sell' ? 'bg-red-500/20' : 'bg-zinc-700'
                          )}>
                            {signal.signal === 'buy' ? <ArrowUpRight className="h-5 w-5 text-emerald-400" /> :
                             signal.signal === 'sell' ? <ArrowDownRight className="h-5 w-5 text-red-400" /> :
                             <Minus className="h-5 w-5 text-zinc-400" />}
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-white uppercase">{signal.signal}</div>
                            <div className="text-xs text-zinc-400">
                              Confidence: {(signal.confidence * 100).toFixed(0)}% — {signal.reason}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}

            {/* Builder Panel */}
            {showBuilder && (
              <div className="card-elevated p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-white">Create New Strategy</h2>
                  <button
                    onClick={() => setShowBuilder(false)}
                    className="text-sm text-zinc-500 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                </div>
                <StrategyBuilder onSave={handleSave} />
              </div>
            )}
          </div>

          {/* Sidebar - Info */}
          <div className="space-y-5">
            <div className="card-elevated p-5">
              <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">How Strategies Work</h3>
              <div className="space-y-4">
                <div className="flex gap-3">
                  <div className="p-2 rounded-lg bg-primary/10 flex-shrink-0">
                    <BarChart3 className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">Indicators</div>
                    <div className="text-xs text-zinc-400">Define technical indicators like SMA, RSI, MACD, and Bollinger Bands</div>
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="p-2 rounded-lg bg-emerald-500/10 flex-shrink-0">
                    <TrendingUp className="h-5 w-5 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">Entry Conditions</div>
                    <div className="text-xs text-zinc-400">Set rules for when to enter a position based on indicators</div>
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="p-2 rounded-lg bg-red-500/10 flex-shrink-0">
                    <TrendingUp className="h-5 w-5 text-red-400 rotate-180" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">Exit Conditions</div>
                    <div className="text-xs text-zinc-400">Define when to exit positions to lock in profits or cut losses</div>
                  </div>
                </div>
                <div className="flex gap-3">
                  <div className="p-2 rounded-lg bg-accent/10 flex-shrink-0">
                    <Play className="h-5 w-5 text-accent" />
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">Backtesting</div>
                    <div className="text-xs text-zinc-400">Test your strategy against historical data to validate performance</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="card-elevated p-5">
              <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">Quick Links</h3>
              <Link
                href="/trading/backtesting"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-zinc-800/50 transition-colors group"
              >
                <div className="flex items-center gap-2">
                  <Play className="h-4 w-4 text-accent" />
                  <span className="text-sm text-zinc-300">Run Backtest</span>
                </div>
                <ChevronRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
              </Link>
              <Link
                href="/trading"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-zinc-800/50 transition-colors group"
              >
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary" />
                  <span className="text-sm text-zinc-300">Trading Dashboard</span>
                </div>
                <ChevronRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
