'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Wallet, Plus, ArrowUpRight, ArrowDownRight, TrendingUp,
  BarChart3, Trash2, ChevronRight, Activity, Briefcase, PieChart,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { PortfolioSummaryCard, AllocationBar } from '@/components/trading/portfolio-summary'
import type { PortfolioSummary, TradingOrder, TradingPortfolio } from '@/types/trading'
import { TRADING_ASSETS } from '@/types/trading'
import { TopNav } from '@/components/layout/top-nav'

interface RawPortfolioRow {
  id: string
  user_id: string
  name: string
  currency: string
  initial_balance: number
  current_balance: number
  is_paper: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export default function PortfolioPage() {
  const [portfolios, setPortfolios] = useState<RawPortfolioRow[]>([])
  const [selectedPortfolio, setSelectedPortfolio] = useState<PortfolioSummary | null>(null)
  const [orders, setOrders] = useState<TradingOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    name: '',
    initialBalance: 10000,
    isPaper: true,
    currency: 'USD',
  })

  useEffect(() => {
    loadPortfolios()
  }, [])

  const loadPortfolios = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/trading/portfolio')
      const data = await res.json()
      if (data.portfolios) {
        setPortfolios(data.portfolios)
        if (data.portfolios.length > 0 && !selectedPortfolio) {
          await loadPortfolioDetail(data.portfolios[0].id)
        }
      }
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  const loadPortfolioDetail = async (id: string) => {
    try {
      const [pfRes, ordersRes] = await Promise.all([
        fetch(`/api/trading/portfolio/${id}`),
        fetch(`/api/trading/orders?portfolioId=${id}`),
      ])
      const pfData = await pfRes.json()
      const ordersData = await ordersRes.json()
      if (pfData.portfolio) setSelectedPortfolio(pfData.portfolio)
      if (ordersData.orders) setOrders(ordersData.orders)
    } catch { /* ignore */ }
  }

  const handleCreate = async () => {
    try {
      const res = await fetch('/api/trading/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createForm.name || 'My Portfolio',
          initialBalance: createForm.initialBalance,
          isPaper: createForm.isPaper,
          currency: createForm.currency,
        }),
      })
      if (res.ok) {
        setShowCreate(false)
        await loadPortfolios()
      }
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: string) => {
    try {
      const res = await fetch(`/api/trading/portfolio/${id}`, { method: 'DELETE' })
      if (res.ok) {
        if (selectedPortfolio?.portfolio.id === id) setSelectedPortfolio(null)
        await loadPortfolios()
      }
    } catch { /* ignore */ }
  }

  const handleCancelOrder = async (orderId: string) => {
    await fetch(`/api/trading/orders/${orderId}/cancel`, { method: 'POST' })
    if (selectedPortfolio) await loadPortfolioDetail(selectedPortfolio.portfolio.id)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <TopNav />
        <main className="container-custom flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </main>
      </div>
    )
  }

  const p = selectedPortfolio
  const livePortfolios = portfolios.filter(pf => !pf.is_paper)
  const paperPortfolios = portfolios.filter(pf => pf.is_paper)

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Wallet className="h-8 w-8 text-primary" />
              Portfolio
            </h1>
            <p className="text-zinc-400 mt-1">Track your holdings, orders, and performance</p>
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
              onClick={() => setShowCreate(!showCreate)}
              className="flex items-center gap-2 px-5 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover hover:shadow-primary transition-all"
            >
              <Plus className="h-4 w-4" />
              New Portfolio
            </button>
          </div>
        </div>

        {/* Create portfolio modal */}
        {showCreate && (
          <div className="card-elevated p-6 mb-6">
            <h3 className="text-lg font-semibold text-white mb-4">Create New Portfolio</h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="text-xs text-zinc-500 mb-1 block">Name</label>
                <input
                  type="text"
                  value={createForm.name}
                  onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="My Portfolio"
                  className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 mb-1 block">Initial Balance ($)</label>
                <input
                  type="number"
                  value={createForm.initialBalance}
                  onChange={e => setCreateForm({ ...createForm, initialBalance: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 mb-1 block">Type</label>
                <select
                  value={createForm.isPaper ? 'paper' : 'live'}
                  onChange={e => setCreateForm({ ...createForm, isPaper: e.target.value === 'paper' })}
                  className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white"
                >
                  <option value="paper">Paper Trading</option>
                  <option value="live">Live Trading</option>
                </select>
              </div>
              <div className="flex items-end">
                <button
                  onClick={handleCreate}
                  disabled={createForm.initialBalance <= 0}
                  className="w-full px-4 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover transition-all disabled:opacity-50"
                >
                  Create Portfolio
                </button>
              </div>
            </div>
          </div>
        )}

        {portfolios.length === 0 ? (
          <div className="card-elevated p-12 text-center">
            <Wallet className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
            <p className="text-white font-semibold mb-2">No portfolios yet</p>
            <p className="text-zinc-500 text-sm mb-5">Create a portfolio to start tracking your trades</p>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
            >
              <Plus className="h-4 w-4" />
              Create Your First Portfolio
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
            {/* Portfolio sidebar */}
            <div className="space-y-3">
              {livePortfolios.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Live</h3>
                  {livePortfolios.map(pf => (
                    <button
                      key={pf.id}
                      onClick={() => loadPortfolioDetail(pf.id)}
                      className={cn(
                        'w-full flex items-center justify-between p-3 rounded-lg text-left transition-all mb-1',
                        selectedPortfolio?.portfolio.id === pf.id
                          ? 'bg-primary/10 border border-primary/30'
                          : 'hover:bg-zinc-800/50 border border-transparent'
                      )}
                    >
                      <div>
                        <div className="text-sm font-medium text-white">{pf.name}</div>
                        <div className="text-xs text-zinc-500">{pf.currency}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">LIVE</span>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(pf.id) }}
                          className="text-zinc-600 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {paperPortfolios.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Paper Trading</h3>
                  {paperPortfolios.map(pf => (
                    <button
                      key={pf.id}
                      onClick={() => loadPortfolioDetail(pf.id)}
                      className={cn(
                        'w-full flex items-center justify-between p-3 rounded-lg text-left transition-all mb-1',
                        selectedPortfolio?.portfolio.id === pf.id
                          ? 'bg-primary/10 border border-primary/30'
                          : 'hover:bg-zinc-800/50 border border-transparent'
                      )}
                    >
                      <div>
                        <div className="text-sm font-medium text-white">{pf.name}</div>
                        <div className="text-xs text-zinc-500">{pf.currency}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-accent bg-accent/10 px-1.5 py-0.5 rounded">Paper</span>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(pf.id) }}
                          className="text-zinc-600 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              <Link
                href="/trading/strategies"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-zinc-800/50 transition-colors group text-sm text-zinc-400"
              >
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-accent" />
                  <span>Strategies</span>
                </div>
                <ChevronRight className="h-4 w-4 text-zinc-600" />
              </Link>
            </div>

            {/* Portfolio Detail */}
            <div className="lg:col-span-3 space-y-5">
              {!p ? (
                <div className="card-elevated p-12 text-center">
                  <Briefcase className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
                  <p className="text-white font-semibold mb-2">Select a portfolio</p>
                  <p className="text-zinc-500 text-sm">Choose a portfolio from the sidebar to view details</p>
                </div>
              ) : (
                <>
                  {/* Portfolio header */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-xl font-bold text-white">{p.portfolio.name}</h2>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={cn(
                          'text-xs px-2 py-0.5 rounded-full font-medium',
                          p.portfolio.isPaper
                            ? 'bg-accent/10 text-accent'
                            : 'bg-emerald-500/10 text-emerald-400'
                        )}>
                          {p.portfolio.isPaper ? 'Paper Trading' : 'Live'}
                        </span>
                        <span className="text-xs text-zinc-500">{p.portfolio.currency}</span>
                      </div>
                    </div>
                    <Link
                      href="/trading"
                      className="flex items-center gap-2 px-4 py-2 text-sm text-primary hover:text-primary-hover border border-primary/30 rounded-lg hover:border-primary/50 transition-all"
                    >
                      <Activity className="h-4 w-4" />
                      Trade Now
                    </Link>
                  </div>

                  {/* Summary cards */}
                  <PortfolioSummaryCard portfolio={p} />

                  {/* Asset allocation */}
                  {p.assetAllocation.length > 0 && (
                    <div className="card-elevated p-5">
                      <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">
                        <PieChart className="h-4 w-4 inline mr-2" />
                        Asset Allocation
                      </h3>
                      <AllocationBar allocations={p.assetAllocation} />
                    </div>
                  )}

                  {/* Holdings */}
                  <div className="card-elevated">
                    <div className="p-5 border-b border-border flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
                        Holdings ({p.holdings.length})
                      </h3>
                      <span className="text-xs text-zinc-500">
                        Cash: ${p.portfolio.currentBalance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    {p.holdings.length === 0 ? (
                      <div className="p-8 text-center text-sm text-zinc-500">
                        No open positions. Go to the{' '}
                        <Link href="/trading" className="text-primary hover:text-primary-hover">dashboard</Link>
                        {' '}to place a trade.
                      </div>
                    ) : (
                      <div className="divide-y divide-border">
                        {p.holdings.map(h => {
                          const pl = h.currentPrice ? (h.currentPrice - h.averagePrice) * h.quantity : 0
                          const plPct = h.currentPrice && h.averagePrice ? ((h.currentPrice - h.averagePrice) / h.averagePrice) * 100 : 0
                          const assetInfo = TRADING_ASSETS[h.assetType]
                          return (
                            <div key={h.id} className="flex items-center justify-between px-5 py-4 hover:bg-zinc-800/20 transition-colors">
                              <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold"
                                  style={{ backgroundColor: assetInfo.color + '20', color: assetInfo.color }}>
                                  {h.symbol.slice(0, 2)}
                                </div>
                                <div>
                                  <div className="text-sm font-semibold text-white">
                                    {h.symbol}
                                    <span className="ml-2 text-xs text-zinc-500">{assetInfo.label}</span>
                                  </div>
                                  <div className="text-xs text-zinc-500">
                                    {h.quantity.toFixed(h.assetType === 'crypto' ? 6 : 2)} units @ ${h.averagePrice.toFixed(2)}
                                  </div>
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-sm font-semibold text-white">
                                  ${h.currentPrice ? (h.quantity * h.currentPrice).toFixed(2) : '---'}
                                </div>
                                <div className={cn(
                                  'flex items-center justify-end gap-1 text-xs font-medium',
                                  pl >= 0 ? 'text-emerald-400' : 'text-red-400'
                                )}>
                                  {pl >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                                  {pl >= 0 ? '+' : ''}{pl.toFixed(2)} ({plPct >= 0 ? '+' : ''}{plPct.toFixed(2)}%)
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* Orders */}
                  <div className="card-elevated">
                    <div className="p-5 border-b border-border">
                      <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
                        Orders ({orders.length})
                      </h3>
                    </div>
                    {orders.length === 0 ? (
                      <div className="p-8 text-center text-sm text-zinc-500">No orders yet</div>
                    ) : (
                      <div className="divide-y divide-border">
                        {orders.map(order => (
                          <div key={order.id} className="flex items-center justify-between px-5 py-3 hover:bg-zinc-800/20 transition-colors">
                            <div className="flex items-center gap-3">
                              <span className={cn(
                                'px-2 py-0.5 rounded text-xs font-bold',
                                order.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                              )}>
                                {order.side.toUpperCase()}
                              </span>
                              <span className="text-sm text-white">{order.symbol}</span>
                              <span className="text-xs text-zinc-500">{order.orderType}</span>
                            </div>
                            <div className="flex items-center gap-4 text-sm">
                              <span className="text-zinc-400">
                                {order.filledQuantity}/{order.quantity}
                              </span>
                              <span className="text-white font-mono">
                                ${order.filledPrice?.toFixed(2) || order.limitPrice?.toFixed(2) || '---'}
                              </span>
                              <span className={cn(
                                'px-2 py-0.5 rounded text-xs font-medium',
                                order.status === 'filled' ? 'bg-emerald-500/10 text-emerald-400' :
                                order.status === 'cancelled' ? 'bg-red-500/10 text-red-400' :
                                order.status === 'rejected' ? 'bg-red-500/10 text-red-400' :
                                'bg-amber-500/10 text-amber-400'
                              )}>
                                {order.status}
                              </span>
                              {(order.status === 'pending' || order.status === 'open') && (
                                <button
                                  onClick={() => handleCancelOrder(order.id)}
                                  className="text-xs text-red-400 hover:text-red-300 transition-colors"
                                >
                                  Cancel
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
