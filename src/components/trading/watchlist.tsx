'use client'

import React, { useState, useEffect } from 'react'
import { Star, Plus, Trash2, MoreVertical, TrendingUp, TrendingDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Watchlist, WatchlistItem, MarketQuote, AssetType } from '@/types/trading'
import { TRADING_ASSETS } from '@/types/trading'

interface WatchlistPanelProps {
  watchlists: Watchlist[]
  onCreateWatchlist: (name: string) => Promise<void>
  onAddItem: (watchlistId: string, symbol: string, assetType: AssetType) => Promise<void>
  onRemoveItem: (watchlistId: string, itemId: string) => Promise<void>
  onDeleteWatchlist: (id: string) => Promise<void>
  className?: string
}

export function WatchlistPanel({
  watchlists,
  onCreateWatchlist,
  onAddItem,
  onRemoveItem,
  onDeleteWatchlist,
  className,
}: WatchlistPanelProps) {
  const [activeWatchlist, setActiveWatchlist] = useState<string | null>(null)
  const [newSymbol, setNewSymbol] = useState('')
  const [newListName, setNewListName] = useState('')
  const [showNewList, setShowNewList] = useState(false)
  const [quotes, setQuotes] = useState<Record<string, MarketQuote>>({})

  useEffect(() => {
    if (watchlists.length > 0 && !activeWatchlist) {
      setActiveWatchlist(watchlists[0].id)
    }
  }, [watchlists, activeWatchlist])

  const current = watchlists.find(w => w.id === activeWatchlist)

  const handleAddSymbol = async () => {
    if (!activeWatchlist || !newSymbol) return
    // Detect asset type from symbol
    let assetType: AssetType = 'stock'
    if (newSymbol.includes('/')) assetType = 'forex'
    else if (['BTC', 'ETH', 'SOL', 'DOGE', 'ADA', 'AVAX'].includes(newSymbol.toUpperCase())) assetType = 'crypto'

    await onAddItem(activeWatchlist, newSymbol.toUpperCase(), assetType)
    setNewSymbol('')
  }

  return (
    <div className={cn('card-elevated', className)}>
      {/* Watchlist tabs */}
      <div className="flex items-center gap-1 p-2 border-b border-border overflow-x-auto">
        {watchlists.map(w => (
          <button
            key={w.id}
            onClick={() => setActiveWatchlist(w.id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-all',
              activeWatchlist === w.id
                ? 'bg-primary/20 text-primary'
                : 'text-zinc-500 hover:text-white hover:bg-zinc-800'
            )}
          >
            {w.isDefault && <Star className="h-3 w-3" />}
            {w.name}
          </button>
        ))}
        <button
          onClick={() => setShowNewList(!showNewList)}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-zinc-800 transition-all"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* New list form */}
      {showNewList && (
        <div className="flex items-center gap-2 p-3 border-b border-border">
          <input
            type="text"
            value={newListName}
            onChange={(e) => setNewListName(e.target.value)}
            placeholder="List name"
            className="flex-1 bg-zinc-800 border border-border rounded-lg px-3 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary"
          />
          <button
            onClick={async () => {
              if (newListName) {
                await onCreateWatchlist(newListName)
                setNewListName('')
                setShowNewList(false)
              }
            }}
            className="px-3 py-1.5 bg-primary text-white text-sm rounded-lg hover:bg-primary-hover transition-all"
          >
            Create
          </button>
        </div>
      )}

      {/* Add symbol */}
      <div className="flex items-center gap-2 p-3">
        <input
          type="text"
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddSymbol()}
          placeholder="Add symbol..."
          className="flex-1 bg-zinc-800 border border-border rounded-lg px-3 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary"
        />
        <button
          onClick={handleAddSymbol}
          disabled={!newSymbol}
          className="p-1.5 bg-primary/20 text-primary rounded-lg hover:bg-primary/30 transition-all disabled:opacity-30"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Items */}
      <div className="divide-y divide-border">
        {(!current || !current.items || current.items.length === 0) ? (
          <div className="p-6 text-center text-sm text-zinc-500">No symbols in watchlist</div>
        ) : (
          current.items.map((item) => {
            const quote = quotes[item.symbol]
            const assetInfo = TRADING_ASSETS[item.assetType]

            return (
              <div key={item.id} className="flex items-center justify-between px-4 py-3 hover:bg-zinc-800/30 transition-colors group">
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold"
                    style={{ backgroundColor: assetInfo.color + '20', color: assetInfo.color }}
                  >
                    {item.symbol.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{item.symbol}</div>
                    <div className="text-xs text-zinc-500">{assetInfo.label}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {quote && (
                    <div className="text-right">
                      <div className="text-sm font-semibold text-white font-mono">
                        ${quote.price.toFixed(2)}
                      </div>
                      <div className={cn(
                        'text-xs flex items-center gap-1',
                        quote.changePct24h >= 0 ? 'text-emerald-400' : 'text-red-400'
                      )}>
                        {quote.changePct24h >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                        {quote.changePct24h >= 0 ? '+' : ''}{quote.changePct24h.toFixed(2)}%
                      </div>
                    </div>
                  )}
                  <button
                    onClick={() => onRemoveItem(current.id, item.id)}
                    className="text-zinc-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
