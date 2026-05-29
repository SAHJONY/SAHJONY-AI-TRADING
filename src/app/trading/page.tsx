'use client'

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import {
  TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Activity,
  BarChart3, Briefcase, Newspaper, Plus, Zap, Play, Bot, Wallet, LineChart, Brain,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarketChart } from '@/components/trading/market-chart'
import { PortfolioSummaryCard, AllocationBar, QuoteCard } from '@/components/trading/portfolio-summary'
import { OrderForm } from '@/components/trading/order-form'
import { WatchlistPanel } from '@/components/trading/watchlist'
import { AgentDebatePanel } from '@/components/trading/agent-debate-panel'
import type {
  MarketQuote, HistoricalBar, PortfolioSummary, Watchlist, WatchlistItem,
  AssetType, OrderType, OrderSide, TradingOrder, MarketNewsItem,
} from '@/types/trading'
import { TRADING_ASSETS, TIMEFRAMES } from '@/types/trading'
import { TopNav } from '@/components/layout/top-nav'

export default function TradingDashboard() {
  // Market data
  const [activeSymbol, setActiveSymbol] = useState('AAPL')
  const [activeAssetType, setActiveAssetType] = useState<AssetType>('stock')
  const [activeTimeframe, setActiveTimeframe] = useState('1d')
  const [quote, setQuote] = useState<MarketQuote | null>(null)
  const [bars, setBars] = useState<HistoricalBar[]>([])
  const [marketQuotes, setMarketQuotes] = useState<MarketQuote[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Portfolio
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null)
  const [orders, setOrders] = useState<TradingOrder[]>([])

  // News
  const [news, setNews] = useState<MarketNewsItem[]>([])

  // Watchlists
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])

  // UI state
  const [activeTab, setActiveTab] = useState<'overview' | 'portfolio' | 'news' | 'debate'>('overview')

  // Fetch market data for active symbol
  const fetchMarketData = useCallback(async () => {
    try {
      const [quoteRes, barsRes] = await Promise.all([
        fetch(`/api/trading/market-data?action=quote&symbol=${activeSymbol}&assetType=${activeAssetType}`),
        fetch(`/api/trading/market-data?action=history&symbol=${activeSymbol}&assetType=${activeAssetType}&timeframe=${activeTimeframe}&limit=200`),
      ])

      const quoteData = await quoteRes.json()
      const barsData = await barsRes.json()

      if (quoteData.quote) setQuote(quoteData.quote)
      if (barsData.bars) setBars(barsData.bars)
    } catch (err) {
      console.error('Failed to fetch market data:', err)
    }
  }, [activeSymbol, activeAssetType, activeTimeframe])

  // Load initial data
  useEffect(() => {
    const loadAll = async () => {
      setIsLoading(true)
      try {
        // Load market overview quotes
        const stocks = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA']
        const crypto = ['BTC', 'ETH', 'SOL']
        const quotesRes = await fetch(`/api/trading/market-data?action=quotes&symbols=${[...stocks, ...crypto].join(',')}&assetType=stock`)
        const quotesData = await quotesRes.json()
        if (quotesData.quotes) {
          // Also get crypto quotes
          const cryptoRes = await fetch(`/api/trading/market-data?action=quotes&symbols=${crypto.join(',')}&assetType=crypto`)
          const cryptoData = await cryptoRes.json()
          setMarketQuotes([...(quotesData.quotes || []), ...(cryptoData.quotes || [])])
        }

        // Load portfolio
        const portfoliosRes = await fetch('/api/trading/portfolio')
        const portfoliosData = await portfoliosRes.json()
        if (portfoliosData.portfolios?.length > 0) {
          const pfRes = await fetch(`/api/trading/portfolio/${portfoliosData.portfolios[0].id}`)
          const pfData = await pfRes.json()
          if (pfData.portfolio) setPortfolio(pfData.portfolio)

          // Load orders
          const ordersRes = await fetch(`/api/trading/orders?portfolioId=${portfoliosData.portfolios[0].id}`)
          const ordersData = await ordersRes.json()
          if (ordersData.orders) setOrders(ordersData.orders)
        }

        // Load news
        const newsRes = await fetch('/api/trading/news')
        const newsData = await newsRes.json()
        if (newsData.news) setNews(newsData.news)

        // Load watchlist
        await loadWatchlists()
      } catch (err) {
        console.error('Failed to load data:', err)
      } finally {
        setIsLoading(false)
      }
    }

    loadAll()
  }, [])

  // Fetch market data when symbol changes
  useEffect(() => {
    fetchMarketData()
  }, [fetchMarketData])

  // Watchlist operations
  const loadWatchlists = async () => {
    try {
      const res = await fetch('/api/trading/watchlists')
      if (res.ok) {
        const data = await res.json()
        setWatchlists(data.watchlists || [])
      }
    } catch { /* ignore */ }
  }

  const handleCreateWatchlist = async (name: string) => {
    try {
      const res = await fetch('/api/trading/watchlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (res.ok) await loadWatchlists()
    } catch { /* ignore */ }
  }

  const handleAddToWatchlist = async (watchlistId: string, symbol: string, assetType: AssetType) => {
    try {
      const res = await fetch(`/api/trading/watchlists/${watchlistId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, assetType }),
      })
      if (res.ok) await loadWatchlists()
    } catch { /* ignore */ }
  }

  const handleRemoveFromWatchlist = async (watchlistId: string, itemId: string) => {
    try {
      await fetch(`/api/trading/watchlists/${watchlistId}/items/${itemId}`, { method: 'DELETE' })
      await loadWatchlists()
    } catch { /* ignore */ }
  }

  const handleDeleteWatchlist = async (id: string) => {
    try {
      await fetch(`/api/trading/watchlists/${id}`, { method: 'DELETE' })
      await loadWatchlists()
    } catch { /* ignore */ }
  }

  // Order submission
  const handlePlaceOrder = async (data: {
    symbol: string; assetType: AssetType; orderType: OrderType; side: OrderSide;
    quantity: number; price?: number; stopPrice?: number; limitPrice?: number
  }) => {
    if (!portfolio) throw new Error('No portfolio')

    const res = await fetch('/api/trading/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        portfolioId: portfolio.portfolio.id,
        ...data,
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || 'Order failed')
    }
    // Refresh portfolio
    const pfRes = await fetch(`/api/trading/portfolio/${portfolio.portfolio.id}`)
    const pfData = await pfRes.json()
    if (pfData.portfolio) setPortfolio(pfData.portfolio)
  }

  // Calculate asset type distribution
  const stocksCount = marketQuotes.filter(q => q.assetType === 'stock').length
  const cryptoCount = marketQuotes.filter(q => q.assetType === 'crypto').length

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Activity className="h-8 w-8 text-primary" />
              Trading
            </h1>
            <p className="text-zinc-400 mt-1">Multi-asset trading dashboard with AI-powered insights</p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/trading/strategies"
              className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 hover:text-white border border-border rounded-lg hover:border-zinc-600 transition-all"
            >
              <Bot className="h-4 w-4" />
              Strategies
            </Link>
            <Link
              href="/trading/backtesting"
              className="flex items-center gap-2 px-4 py-2 text-sm text-zinc-400 hover:text-white border border-border rounded-lg hover:border-zinc-600 transition-all"
            >
              <Play className="h-4 w-4" />
              Backtesting
            </Link>
            <Link
              href="/trading/portfolio"
              className="flex items-center gap-2 px-5 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover hover:shadow-primary transition-all"
            >
              <Wallet className="h-4 w-4" />
              Portfolio
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          {/* Sidebar - Watchlist + Order Form */}
          <div className="space-y-5">
            <WatchlistPanel
              watchlists={watchlists}
              onCreateWatchlist={handleCreateWatchlist}
              onAddItem={handleAddToWatchlist}
              onRemoveItem={handleRemoveFromWatchlist}
              onDeleteWatchlist={handleDeleteWatchlist}
            />

            {portfolio && (
              <OrderForm
                portfolioId={portfolio.portfolio.id}
                currentSymbol={activeSymbol}
                currentAssetType={activeAssetType}
                currentPrice={quote?.price || 0}
                balance={portfolio.portfolio.currentBalance}
                onSubmit={handlePlaceOrder}
              />
            )}
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 space-y-5">
            {/* Asset type tabs */}
            <div className="flex items-center gap-1">
              {(Object.entries(TRADING_ASSETS) as [AssetType, typeof TRADING_ASSETS['stock']][]).map(([key, info]) => (
                <button
                  key={key}
                  onClick={() => { setActiveAssetType(key); setActiveSymbol(info.exampleSymbols[0]) }}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                    activeAssetType === key
                      ? 'bg-primary/20 text-primary border border-primary/30'
                      : 'text-zinc-500 hover:text-white border border-transparent'
                  )}
                >
                  {info.label}
                </button>
              ))}
            </div>

            {/* Chart Area */}
            <div className="card-elevated p-5">
              {/* Symbol selector + quote header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-4">
                  <select
                    value={activeSymbol}
                    onChange={(e) => setActiveSymbol(e.target.value)}
                    className="bg-zinc-800 border border-border rounded-lg px-3 py-1.5 text-lg font-semibold text-white focus:outline-none focus:border-primary"
                  >
                    {TRADING_ASSETS[activeAssetType].exampleSymbols.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  {quote && (
                    <div className="flex items-center gap-3">
                      <span className="text-2xl font-bold text-white font-mono">
                        ${quote.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                      <span className={cn(
                        'flex items-center gap-1 text-sm font-semibold',
                        quote.changePct24h >= 0 ? 'text-emerald-400' : 'text-red-400'
                      )}>
                        {quote.changePct24h >= 0 ? <ArrowUpRight className="h-4 w-4" /> : <ArrowDownRight className="h-4 w-4" />}
                        {quote.changePct24h.toFixed(2)}% ({quote.change24h > 0 ? '+' : ''}{quote.change24h.toFixed(2)})
                      </span>
                    </div>
                  )}
                </div>

                {/* Timeframe selector */}
                <div className="flex items-center gap-1">
                  {TIMEFRAMES.slice(2).map(tf => (
                    <button
                      key={tf.value}
                      onClick={() => setActiveTimeframe(tf.value)}
                      className={cn(
                        'px-3 py-1 rounded-md text-xs font-medium transition-all',
                        activeTimeframe === tf.value
                          ? 'bg-primary/20 text-primary'
                          : 'text-zinc-500 hover:text-white hover:bg-zinc-800'
                      )}
                    >
                      {tf.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Quote stats */}
              {quote && (
                <div className="grid grid-cols-4 gap-4 mb-4">
                  {[
                    { label: 'Open', value: `$${quote.price.toFixed(2)}` },
                    { label: 'High', value: `$${quote.high24h.toFixed(2)}` },
                    { label: 'Low', value: `$${quote.low24h.toFixed(2)}` },
                    { label: 'Volume', value: quote.volume24h.toLocaleString('en-US', { maximumFractionDigits: 0 }) },
                  ].map(stat => (
                    <div key={stat.label} className="text-center p-2 bg-zinc-800/50 rounded-lg">
                      <div className="text-xs text-zinc-500 mb-0.5">{stat.label}</div>
                      <div className="text-sm font-semibold text-white">{stat.value}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Chart */}
              {bars.length > 0 && (
                <MarketChart data={bars} color={TRADING_ASSETS[activeAssetType].color} className="w-full" />
              )}

              {isLoading && (
                <div className="h-[300px] flex items-center justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              )}
            </div>

            {/* Content Tabs: Overview / Portfolio / News */}
            <div className="flex items-center gap-2 border-b border-border">
              {[
                { id: 'overview' as const, label: 'Market Overview', icon: BarChart3 },
                { id: 'debate' as const, label: 'AI Debate', icon: Brain },
                { id: 'portfolio' as const, label: 'Portfolio', icon: Briefcase },
                { id: 'news' as const, label: 'News Feed', icon: Newspaper },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all -mb-px',
                    activeTab === tab.id
                      ? 'border-primary text-primary'
                      : 'border-transparent text-zinc-500 hover:text-white'
                  )}
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <div className="space-y-5">
                {/* Quick Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="card-elevated p-4">
                    <div className="text-xs text-zinc-500 mb-1">Assets Tracked</div>
                    <div className="text-2xl font-bold text-white">{marketQuotes.length}</div>
                  </div>
                  <div className="card-elevated p-4">
                    <div className="text-xs text-zinc-500 mb-1">Stocks</div>
                    <div className="text-2xl font-bold text-white">{stocksCount}</div>
                  </div>
                  <div className="card-elevated p-4">
                    <div className="text-xs text-zinc-500 mb-1">Crypto</div>
                    <div className="text-2xl font-bold text-white">{cryptoCount}</div>
                  </div>
                  <div className="card-elevated p-4">
                    <div className="text-xs text-zinc-500 mb-1">Market Sentiment</div>
                    <div className="text-2xl font-bold text-emerald-400">Bullish</div>
                  </div>
                </div>

                {/* Market Quotes */}
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Markets</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {marketQuotes.slice(0, 8).map(q => (
                      <QuoteCard
                        key={`${q.symbol}-${q.assetType}`}
                        quote={q}
                        onClick={() => { setActiveSymbol(q.symbol); setActiveAssetType(q.assetType) }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* AI Debate Tab */}
            {activeTab === 'debate' && (
              <div className="space-y-5">
                <AgentDebatePanel
                  onDebateComplete={(debate) => {
                    if (debate.finalDecision?.action !== 'HOLD') {
                      setActiveSymbol(debate.symbol)
                      setActiveAssetType(debate.assetType)
                    }
                  }}
                />

                {/* Knowledge context preview */}
                <div className="card-elevated p-5">
                  <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                    <Brain className="h-4 w-4 inline mr-2" />
                    Agent Intelligence
                  </h3>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    {[
                      { label: 'Multi-Agent Debate', desc: '6 specialized agents debate market conditions using consensus voting' },
                      { label: 'Risk Veto', desc: 'Risk Manager can veto trades at ≥80% confidence to protect capital' },
                      { label: 'Knowledge Enrichment', desc: 'Real-time news, sentiment analysis, and technical indicators' },
                      { label: 'Meta-Learning', desc: 'Continuous improvement from trade outcomes and agent performance tracking' },
                    ].map(item => (
                      <div key={item.label} className="p-3 rounded-lg bg-zinc-800/50">
                        <div className="text-white font-medium mb-1">{item.label}</div>
                        <div className="text-xs text-zinc-400">{item.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Portfolio Tab */}
            {activeTab === 'portfolio' && portfolio && (
              <div className="space-y-5">
                <PortfolioSummaryCard portfolio={portfolio} />

                {/* Allocation */}
                {portfolio.assetAllocation.length > 0 && (
                  <div className="card-elevated p-5">
                    <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-4">Asset Allocation</h3>
                    <AllocationBar allocations={portfolio.assetAllocation} />
                  </div>
                )}

                {/* Holdings */}
                <div className="card-elevated">
                  <div className="p-5 border-b border-border">
                    <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Holdings</h3>
                  </div>
                  {portfolio.holdings.length === 0 ? (
                    <div className="p-8 text-center text-sm text-zinc-500">No open positions</div>
                  ) : (
                    <div className="divide-y divide-border">
                      {portfolio.holdings.map(h => {
                        const pl = h.currentPrice ? (h.currentPrice - h.averagePrice) * h.quantity : 0
                        const plPct = h.currentPrice && h.averagePrice ? ((h.currentPrice - h.averagePrice) / h.averagePrice) * 100 : 0
                        return (
                          <div key={h.id} className="flex items-center justify-between px-5 py-4 hover:bg-zinc-800/20 transition-colors">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                                <span className="text-sm font-bold text-primary">{h.symbol.slice(0, 2)}</span>
                              </div>
                              <div>
                                <div className="text-sm font-semibold text-white">{h.symbol}</div>
                                <div className="text-xs text-zinc-500">
                                  {h.quantity.toFixed(4)} shares @ ${h.averagePrice.toFixed(2)}
                                </div>
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="text-sm font-semibold text-white">
                                ${h.currentPrice ? (h.quantity * h.currentPrice).toFixed(2) : '---'}
                              </div>
                              <div className={cn(
                                'text-xs font-medium',
                                pl >= 0 ? 'text-emerald-400' : 'text-red-400'
                              )}>
                                {pl >= 0 ? '+' : ''}{pl.toFixed(2)} ({plPct.toFixed(2)}%)
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Recent Orders */}
                {orders.length > 0 && (
                  <div className="card-elevated">
                    <div className="p-5 border-b border-border">
                      <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Recent Orders</h3>
                    </div>
                    <div className="divide-y divide-border">
                      {orders.slice(0, 10).map(order => (
                        <div key={order.id} className="flex items-center justify-between px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span className={cn(
                              'px-2 py-0.5 rounded text-xs font-bold',
                              order.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                            )}>
                              {order.side.toUpperCase()}
                            </span>
                            <span className="text-sm text-white">{order.symbol}</span>
                            <span className="text-xs text-zinc-500">{order.assetType}</span>
                          </div>
                          <div className="flex items-center gap-4 text-sm">
                            <span className="text-zinc-400">{order.filledQuantity}/{order.quantity}</span>
                            <span className="text-white">${order.filledPrice?.toFixed(2) || '---'}</span>
                            <span className={cn(
                              'px-2 py-0.5 rounded text-xs',
                              order.status === 'filled' ? 'bg-emerald-500/10 text-emerald-400' :
                              order.status === 'cancelled' ? 'bg-red-500/10 text-red-400' :
                              'bg-zinc-700 text-zinc-400'
                            )}>
                              {order.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'portfolio' && !portfolio && (
              <div className="card-elevated p-12 text-center">
                <Briefcase className="h-12 w-12 text-zinc-600 mx-auto mb-4" />
                <p className="text-white font-semibold mb-2">No portfolio yet</p>
                <p className="text-zinc-500 text-sm mb-5">Create a paper trading portfolio to get started</p>
                <button
                  onClick={async () => {
                    try {
                      const res = await fetch('/api/trading/portfolio', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: 'My Portfolio', initialBalance: 10000, isPaper: true }),
                      })
                      if (res.ok) {
                        const data = await res.json()
                        const pfRes = await fetch(`/api/trading/portfolio/${data.portfolio.id}`)
                        const pfData = await pfRes.json()
                        if (pfData.portfolio) setPortfolio(pfData.portfolio)
                      }
                    } catch { /* ignore */ }
                  }}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
                >
                  <Plus className="h-4 w-4" />
                  Create Paper Portfolio
                </button>
              </div>
            )}

            {/* News Tab */}
            {activeTab === 'news' && (
              <div className="space-y-3">
                {news.map((item) => (
                  <div key={item.id} className="card-elevated p-4 hover:bg-zinc-800/20 transition-colors group">
                    <div className="flex items-start gap-4">
                      <div className={cn(
                        'w-2 h-2 rounded-full mt-1.5 flex-shrink-0',
                        item.sentiment === 'positive' ? 'bg-emerald-400' :
                        item.sentiment === 'negative' ? 'bg-red-400' : 'bg-zinc-500'
                      )} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs text-zinc-500">{item.source}</span>
                          <span className="text-xs text-zinc-600">•</span>
                          <span className="text-xs text-zinc-500">
                            {new Date(item.publishedAt).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          {item.symbols.length > 0 && (
                            <>
                              <span className="text-xs text-zinc-600">•</span>
                              <span className="text-xs text-primary">{item.symbols.join(', ')}</span>
                            </>
                          )}
                        </div>
                        <h4 className="text-sm font-medium text-white group-hover:text-primary transition-colors">
                          {item.title}
                        </h4>
                        <p className="text-xs text-zinc-400 mt-1 line-clamp-2">{item.summary}</p>
                        <div className="flex items-center gap-3 mt-2">
                          <span className={cn(
                            'text-xs px-2 py-0.5 rounded-full',
                            item.sentiment === 'positive' ? 'bg-emerald-500/10 text-emerald-400' :
                            item.sentiment === 'negative' ? 'bg-red-500/10 text-red-400' :
                            'bg-zinc-700 text-zinc-400'
                          )}>
                            {item.sentiment} ({(item.sentimentScore * 100).toFixed(0)}%)
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
