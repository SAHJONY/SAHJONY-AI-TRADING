'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { TRADING_AGENTS } from '@/lib/agents/registry'
import { MARKETS } from '@/lib/global/markets-languages'
import {
  TrendingUp, TrendingDown, DollarSign, Activity,
  Zap, Shield, Eye, Play, Pause, Square,
  ArrowUpRight, ArrowDownRight, RefreshCw,
  Bot, BarChart3, Wallet, Globe, Lock, Unlock
} from 'lucide-react'

interface Position {
  symbol: string
  qty: number
  side: string
  marketValue: number
  avgEntryPrice: number
  currentPrice: number
  unrealizedPL: number
  unrealizedPLPercent: number
}

interface Account {
  equity: number
  cash: number
  buyingPower: number
  portfolioValue: number
  unrealizedPL: number
  unrealizedPLPercent: number
  status: string
  tradingBlocked: boolean
}

export default function TradingPage() {
  const { user, isOwner, unrestricted } = useAuth()
  const [account, setAccount] = useState<Account | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [autoMode, setAutoMode] = useState(false)
  const [activeAgents, setActiveAgents] = useState<string[]>([])
  const [tradeSymbol, setTradeSymbol] = useState('')
  const [tradeAmount, setTradeAmount] = useState('100')
  const [tradeSide, setTradeSide] = useState<'buy' | 'sell'>('buy')
  const [tradeStatus, setTradeStatus] = useState('')
  const [engineStatus, setEngineStatus] = useState<any>(null)

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/trading/account')
      if (res.ok) {
        const data = await res.json()
        setAccount(data.account)
        setPositions(data.positions || [])
      }
    } catch {}
    try {
      const res = await fetch('/api/trading/autonomous')
      if (res.ok) {
        const data = await res.json()
        setEngineStatus(data)
      }
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Owner defaults: all agents active
  useEffect(() => {
    if (isOwner && activeAgents.length === 0) {
      setActiveAgents(TRADING_AGENTS.filter(a => a.isDefault).map(a => a.id))
    }
  }, [isOwner, activeAgents.length])

  const executeTrade = async () => {
    if (!tradeSymbol || !tradeAmount) return
    setTradeStatus('Executing...')
    try {
      const res = await fetch('/api/trading/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: tradeSymbol.toUpperCase(),
          side: tradeSide,
          notional: Number(tradeAmount),
          type: 'market',
          timeInForce: 'gtc',
          paper: !isOwner, // Owner trades LIVE
        }),
      })
      const data = await res.json()
      if (data.success) {
        setTradeStatus(`✅ ${tradeSide.toUpperCase()} $${tradeAmount} ${tradeSymbol.toUpperCase()} — Order ${data.order?.id || 'placed'}`)
        setTimeout(fetchData, 2000)
      } else {
        setTradeStatus(`❌ ${data.error || 'Trade failed'}`)
      }
    } catch (err: any) {
      setTradeStatus(`❌ ${err.message}`)
    }
  }

  const closePosition = async (symbol: string) => {
    try {
      const res = await fetch(`/api/trading/account?symbol=${symbol}&live=${isOwner}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        setTradeStatus(`✅ Closed ${symbol}`)
        setTimeout(fetchData, 2000)
      }
    } catch {}
  }

  const toggleAgent = (id: string) => {
    setActiveAgents(prev =>
      prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
    )
  }

  const total247 = MARKETS.filter(m => m.is247).length
  const totalMarkets = MARKETS.length

  return (
    <div className="min-h-screen bg-[#020408] text-white">
      <TopNav />
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Owner Banner */}
        {isOwner && (
          <div className="mb-6 rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-amber-500/5 p-4 flex items-center gap-3">
            <Unlock className="w-6 h-6 text-amber-400" />
            <div>
              <p className="font-bold text-amber-400">OWNER ACCESS — UNRESTRICTED</p>
              <p className="text-sm text-amber-300/70">Live trading enabled. All 15 agents. All {totalMarkets} markets. $100 minimum. Zero limits.</p>
            </div>
          </div>
        )}

        {/* Engine Status */}
        {engineStatus && (
          <div className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Engine', value: engineStatus.status, color: engineStatus.status === 'OPERATIONAL' ? 'text-green-400' : 'text-yellow-400' },
              { label: 'Markets', value: engineStatus.supportedMarkets, color: 'text-sky-400' },
              { label: 'Agents', value: engineStatus.agents, color: 'text-purple-400' },
              { label: 'Min Trade', value: `$${isOwner ? 100 : 100}`, color: 'text-amber-400' },
            ].map((s, i) => (
              <div key={i} className="rounded-lg border border-slate-800 bg-[#060a12] p-3">
                <p className="text-xs text-slate-500 uppercase">{s.label}</p>
                <p className={`text-lg font-bold ${s.color}`}>{s.value}</p>
              </div>
            ))}
          </div>
        )}

        {/* Account Overview */}
        <div className="mb-6 grid grid-cols-2 md:grid-cols-4 gap-3">
          {account ? [
            { label: 'Portfolio Value', value: `$${account.portfolioValue?.toLocaleString() || '0'}`, icon: Wallet },
            { label: 'Cash', value: `$${account.cash?.toLocaleString() || '0'}`, icon: DollarSign },
            { label: 'Buying Power', value: `$${account.buyingPower?.toLocaleString() || '0'}`, icon: BarChart3 },
            { label: 'Unrealized P/L', value: `${account.unrealizedPL >= 0 ? '+' : ''}$${account.unrealizedPL?.toFixed(2) || '0'} (${(account.unrealizedPLPercent * 100)?.toFixed(2) || '0'}%)`, icon: account.unrealizedPL >= 0 ? TrendingUp : TrendingDown },
          ].map((s, i) => (
            <div key={i} className="rounded-xl border border-slate-800 bg-[#060a12] p-4">
              <div className="flex items-center gap-2 mb-1">
                <s.icon className="w-4 h-4 text-sky-400" />
                <p className="text-xs text-slate-500 uppercase">{s.label}</p>
              </div>
              <p className={`text-xl font-bold ${s.label === 'Unrealized P/L' ? (account.unrealizedPL >= 0 ? 'text-green-400' : 'text-red-400') : 'text-white'}`}>
                {s.value}
              </p>
            </div>
          )) : (
            <div className="col-span-4 rounded-xl border border-slate-800 bg-[#060a12] p-8 text-center">
              <p className="text-slate-400">
                {loading ? 'Loading account...' : 'Connect your Alpaca account to start trading'}
              </p>
              {!loading && (
                <a href="/funding" className="mt-3 inline-block rounded-lg bg-sky-500 px-6 py-2 text-sm font-semibold text-white hover:bg-sky-600 transition">
                  Fund Account — $100 Minimum
                </a>
              )}
            </div>
          )}
        </div>

        {/* Autonomous Mode Toggle */}
        <div className="mb-6 rounded-xl border border-sky-500/20 bg-[#0a1020] p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Bot className="w-6 h-6 text-sky-400" />
              <div>
                <h3 className="font-bold text-white">Autonomous AI Trading</h3>
                <p className="text-sm text-slate-400">
                  {isOwner ? 'All 15 agents active. Owner: unlimited notional, live execution.' : 'Active agents trade on your behalf within plan limits.'}
                </p>
              </div>
            </div>
            <button
              onClick={() => setAutoMode(!autoMode)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 font-semibold transition ${
                autoMode
                  ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                  : 'bg-slate-800 text-slate-300 border border-slate-700'
              }`}
            >
              {autoMode ? <><Pause className="w-4 h-4" /> Running</> : <><Play className="w-4 h-4" /> Start</>}
            </button>
          </div>

          {/* Agent Selector */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {TRADING_AGENTS.map(agent => {
              const active = activeAgents.includes(agent.id)
              return (
                <button
                  key={agent.id}
                  onClick={() => toggleAgent(agent.id)}
                  className={`flex items-center gap-2 rounded-lg p-2 text-left text-sm transition border ${
                    active
                      ? 'bg-sky-500/10 border-sky-500/30 text-sky-300'
                      : 'bg-slate-900/50 border-slate-800 text-slate-500'
                  }`}
                >
                  <span className="text-lg">{agent.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold truncate">{agent.name}</p>
                    <p className="text-xs opacity-70 truncate">{agent.specialty}</p>
                  </div>
                  {isOwner && <Unlock className="w-3 h-3 text-amber-400 shrink-0" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* Manual Trade */}
        <div className="mb-6 rounded-xl border border-amber-500/20 bg-[#0a1020] p-4">
          <h3 className="font-bold text-amber-400 mb-3 flex items-center gap-2">
            <Zap className="w-5 h-5" /> Quick Trade {isOwner && <span className="text-xs bg-amber-500/20 px-2 py-0.5 rounded text-amber-300">LIVE</span>}
          </h3>
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              placeholder="Symbol (e.g. AAPL, BTC/USD)"
              value={tradeSymbol}
              onChange={e => setTradeSymbol(e.target.value)}
              className="rounded-lg border border-slate-700 bg-[#060a12] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-sky-500 focus:outline-none w-48"
            />
            <input
              type="number"
              placeholder="$ Amount"
              value={tradeAmount}
              onChange={e => setTradeAmount(e.target.value)}
              min={isOwner ? 1 : 100}
              className="rounded-lg border border-slate-700 bg-[#060a12] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-sky-500 focus:outline-none w-32"
            />
            <div className="flex rounded-lg overflow-hidden border border-slate-700">
              <button
                onClick={() => setTradeSide('buy')}
                className={`px-4 py-2 text-sm font-semibold transition ${tradeSide === 'buy' ? 'bg-green-500 text-white' : 'bg-slate-900 text-slate-400'}`}
              >
                BUY
              </button>
              <button
                onClick={() => setTradeSide('sell')}
                className={`px-4 py-2 text-sm font-semibold transition ${tradeSide === 'sell' ? 'bg-red-500 text-white' : 'bg-slate-900 text-slate-400'}`}
              >
                SELL
              </button>
            </div>
            <button
              onClick={executeTrade}
              className="rounded-lg bg-sky-500 px-6 py-2 text-sm font-semibold text-white hover:bg-sky-600 transition flex items-center gap-2"
            >
              <ArrowUpRight className="w-4 h-4" /> Execute
            </button>
          </div>
          {tradeStatus && (
            <p className="mt-2 text-sm text-slate-300">{tradeStatus}</p>
          )}
        </div>

        {/* Positions */}
        <div className="rounded-xl border border-slate-800 bg-[#060a12] p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-sky-400" /> Open Positions
            </h3>
            <button onClick={fetchData} className="text-slate-400 hover:text-white transition">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
          {positions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-xs uppercase">
                    <th className="text-left py-2">Symbol</th>
                    <th className="text-right py-2">Qty</th>
                    <th className="text-right py-2">Avg Entry</th>
                    <th className="text-right py-2">Current</th>
                    <th className="text-right py-2">Value</th>
                    <th className="text-right py-2">P/L</th>
                    <th className="text-right py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={i} className="border-t border-slate-800/50">
                      <td className="py-2 font-semibold text-white">{p.symbol}</td>
                      <td className="text-right py-2 text-slate-300">{p.qty}</td>
                      <td className="text-right py-2 text-slate-400">${p.avgEntryPrice.toFixed(2)}</td>
                      <td className="text-right py-2 text-slate-300">${p.currentPrice.toFixed(2)}</td>
                      <td className="text-right py-2 text-white">${p.marketValue.toFixed(2)}</td>
                      <td className={`text-right py-2 font-semibold ${p.unrealizedPL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {p.unrealizedPL >= 0 ? '+' : ''}${p.unrealizedPL.toFixed(2)} ({(p.unrealizedPLPercent * 100).toFixed(2)}%)
                      </td>
                      <td className="text-right py-2">
                        <button
                          onClick={() => closePosition(p.symbol)}
                          className="rounded px-2 py-1 text-xs bg-red-500/20 text-red-400 hover:bg-red-500/30 transition"
                        >
                          Close
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-center text-slate-500 py-8">
              {loading ? 'Loading positions...' : 'No open positions. Start trading from $100.'}
            </p>
          )}
        </div>

        {/* Global Markets Summary */}
        <div className="mt-6 rounded-xl border border-slate-800 bg-[#060a12] p-4">
          <h3 className="font-bold flex items-center gap-2 mb-3">
            <Globe className="w-5 h-5 text-sky-400" /> Global Markets — {totalMarkets} Exchanges, {total247} Open 24/7
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
            {['North America', 'South America', 'Europe', 'Asia-Pacific', 'Middle East', 'Africa', 'Caribbean', 'Global'].map(region => {
              const count = MARKETS.filter(m => m.region === region).length
              const open247 = MARKETS.filter(m => m.region === region && m.is247).length
              return (
                <div key={region} className="rounded-lg border border-slate-800 bg-[#0a1020] p-2">
                  <p className="text-slate-500 uppercase text-[10px]">{region}</p>
                  <p className="text-white font-bold">{count}</p>
                  {open247 > 0 && <p className="text-green-400 text-[10px]">{open247} 24/7</p>}
                </div>
              )
            })}
          </div>
        </div>
      </main>
    </div>
  )
}
