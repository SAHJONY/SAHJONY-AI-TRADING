'use client'

import React, { useState } from 'react'
import { Send, X, Loader2, ArrowUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { AssetType, OrderType, OrderSide } from '@/types/trading'
import { TRADING_ASSETS } from '@/types/trading'

interface OrderFormProps {
  portfolioId: string
  currentSymbol?: string
  currentAssetType?: AssetType
  currentPrice?: number
  balance?: number
  onSubmit: (data: {
    symbol: string
    assetType: AssetType
    orderType: OrderType
    side: OrderSide
    quantity: number
    price?: number
    stopPrice?: number
    limitPrice?: number
  }) => Promise<void>
  className?: string
}

export function OrderForm({
  portfolioId,
  currentSymbol = '',
  currentAssetType = 'stock',
  currentPrice = 0,
  balance = 0,
  onSubmit,
  className,
}: OrderFormProps) {
  const [symbol, setSymbol] = useState(currentSymbol)
  const [assetType, setAssetType] = useState<AssetType>(currentAssetType)
  const [orderType, setOrderType] = useState<OrderType>('market')
  const [side, setSide] = useState<OrderSide>('buy')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState(currentPrice > 0 ? currentPrice.toString() : '')
  const [stopPrice, setStopPrice] = useState('')
  const [limitPrice, setLimitPrice] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const estimatedTotal = parseFloat(quantity || '0') * parseFloat(price || (currentPrice > 0 ? currentPrice.toString() : '0') || '0')
  const canSubmit = symbol && parseFloat(quantity) > 0

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setError('')
    setLoading(true)

    try {
      await onSubmit({
        symbol: symbol.toUpperCase(),
        assetType,
        orderType,
        side,
        quantity: parseFloat(quantity),
        price: orderType !== 'market' ? parseFloat(price) : undefined,
        stopPrice: orderType === 'stop' || orderType === 'stop_limit' ? parseFloat(stopPrice) : undefined,
        limitPrice: orderType === 'limit' || orderType === 'stop_limit' ? parseFloat(limitPrice) : undefined,
      })
      setQuantity('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Order failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className={cn('card-elevated p-5', className)}>
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        <ArrowUpDown className="h-4 w-4 text-primary" />
        Place Order
      </h3>

      {/* Buy/Sell Toggle */}
      <div className="flex rounded-lg bg-zinc-800 p-1 mb-4">
        <button
          type="button"
          onClick={() => setSide('buy')}
          className={cn(
            'flex-1 py-2 rounded-md text-sm font-semibold transition-all',
            side === 'buy'
              ? 'bg-emerald-500/20 text-emerald-400 shadow'
              : 'text-zinc-500 hover:text-white'
          )}
        >
          Buy
        </button>
        <button
          type="button"
          onClick={() => setSide('sell')}
          className={cn(
            'flex-1 py-2 rounded-md text-sm font-semibold transition-all',
            side === 'sell'
              ? 'bg-red-500/20 text-red-400 shadow'
              : 'text-zinc-500 hover:text-white'
          )}
        >
          Sell
        </button>
      </div>

      {/* Asset Type */}
      <div className="flex gap-1 mb-4">
        {(Object.entries(TRADING_ASSETS) as [AssetType, typeof TRADING_ASSETS['stock']][]).map(([key, info]) => (
          <button
            key={key}
            type="button"
            onClick={() => setAssetType(key)}
            className={cn(
              'flex-1 py-1.5 rounded-md text-xs font-medium transition-all',
              assetType === key
                ? 'bg-primary/20 text-primary border border-primary/30'
                : 'text-zinc-500 hover:text-white border border-transparent'
            )}
          >
            {info.label}
          </button>
        ))}
      </div>

      {/* Symbol */}
      <div className="mb-3">
        <label className="text-xs text-zinc-500 mb-1 block">Symbol</label>
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="e.g. AAPL, BTC, EUR/USD"
          className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
        />
      </div>

      {/* Order Type */}
      <div className="mb-3">
        <label className="text-xs text-zinc-500 mb-1 block">Order Type</label>
        <select
          value={orderType}
          onChange={(e) => setOrderType(e.target.value as OrderType)}
          className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white focus:outline-none focus:border-primary transition-all"
        >
          <option value="market">Market</option>
          <option value="limit">Limit</option>
          <option value="stop">Stop</option>
          <option value="stop_limit">Stop Limit</option>
        </select>
      </div>

      {/* Quantity */}
      <div className="mb-3">
        <label className="text-xs text-zinc-500 mb-1 block">Quantity</label>
        <input
          type="number"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="0.00"
          className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
        />
        {balance > 0 && currentPrice > 0 && (
          <button
            type="button"
            onClick={() => setQuantity((balance / currentPrice).toFixed(4))}
            className="text-xs text-primary hover:text-primary-hover mt-1"
          >
            Max: {(balance / currentPrice).toFixed(4)}
          </button>
        )}
      </div>

      {/* Conditional Price Fields */}
      {orderType !== 'market' && (
        <div className="mb-3">
          <label className="text-xs text-zinc-500 mb-1 block">
            {orderType === 'limit' ? 'Limit Price' : 'Price'}
          </label>
          <input
            type="number"
            step="any"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="0.00"
            className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
          />
        </div>
      )}

      {orderType === 'stop' && (
        <div className="mb-3">
          <label className="text-xs text-zinc-500 mb-1 block">Stop Price</label>
          <input
            type="number"
            step="any"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            placeholder="0.00"
            className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
          />
        </div>
      )}

      {orderType === 'stop_limit' && (
        <>
          <div className="mb-3">
            <label className="text-xs text-zinc-500 mb-1 block">Stop Price</label>
            <input
              type="number"
              step="any"
              value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)}
              placeholder="0.00"
              className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
            />
          </div>
          <div className="mb-3">
            <label className="text-xs text-zinc-500 mb-1 block">Limit Price</label>
            <input
              type="number"
              step="any"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder="0.00"
              className="w-full px-3 py-2 bg-zinc-800 border border-border rounded-lg text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-all"
            />
          </div>
        </>
      )}

      {/* Estimated Total */}
      {estimatedTotal > 0 && (
        <div className="flex items-center justify-between py-3 border-t border-border mb-3">
          <span className="text-xs text-zinc-500">Estimated Total</span>
          <span className="text-sm font-semibold text-white">
            ${estimatedTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
      )}

      {error && (
        <div className="text-xs text-red-400 mb-3 p-2 bg-red-500/10 rounded-lg flex items-center gap-2">
          <X className="h-3 w-3 flex-shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={!canSubmit || loading}
        className={cn(
          'w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all',
          side === 'buy'
            ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30'
            : 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30',
          'disabled:opacity-30 disabled:cursor-not-allowed'
        )}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
        {side === 'buy' ? 'Buy' : 'Sell'} {symbol || 'Asset'}
      </button>
    </form>
  )
}
