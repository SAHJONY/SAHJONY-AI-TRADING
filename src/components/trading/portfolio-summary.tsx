'use client'

import React, { MouseEvent } from 'react'
import Link from 'next/link'
import { ArrowUpRight, ArrowDownRight, Minus, TrendingUp, BarChart3 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { PortfolioSummary, MarketQuote, AssetAllocation } from '@/types/trading'
import { TRADING_ASSETS } from '@/types/trading'

interface PortfolioSummaryCardProps {
  portfolio: PortfolioSummary
  className?: string
}

interface QuoteCardProps {
  quote: MarketQuote
  className?: string
  onClick?: () => void
}

export function PortfolioSummaryCard({ portfolio, className }: PortfolioSummaryCardProps) {
  const { portfolio: p, totalValue, totalPL, totalPLPct } = portfolio
  const isPositive = totalPL >= 0

  return (
    <div className={cn('grid grid-cols-2 md:grid-cols-4 gap-4', className)}>
      {/* Total Value */}
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
          <BarChart3 className="h-3.5 w-3.5" />
          TOTAL VALUE
        </div>
        <div className="text-2xl font-bold text-white">
          ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>

      {/* Cash Balance */}
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
          <Minus className="h-3.5 w-3.5" />
          CASH BALANCE
        </div>
        <div className="text-2xl font-bold text-white">
          ${p.currentBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="text-xs text-zinc-500 mt-1">
          {p.currency} {p.isPaper ? '• Paper' : '• Live'}
        </div>
      </div>

      {/* P&L */}
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
          <TrendingUp className="h-3.5 w-3.5" />
          TOTAL P&L
        </div>
        <div className={cn(
          'text-2xl font-bold',
          isPositive ? 'text-emerald-400' : 'text-red-400'
        )}>
          {isPositive ? '+' : ''}{totalPL.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className={cn(
          'flex items-center gap-1 text-sm mt-1',
          isPositive ? 'text-emerald-400/70' : 'text-red-400/70'
        )}>
          {isPositive ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
          {totalPLPct.toFixed(2)}%
        </div>
      </div>

      {/* Holdings */}
      <div className="card-elevated p-5">
        <div className="flex items-center gap-2 text-xs text-zinc-500 mb-2">
          <BarChart3 className="h-3.5 w-3.5" />
          HOLDINGS
        </div>
        <div className="text-2xl font-bold text-white">{portfolio.holdings.length}</div>
        <div className="text-xs text-zinc-500 mt-1">Positions</div>
      </div>
    </div>
  )
}

export function AllocationBar({ allocations }: { allocations: AssetAllocation[] }) {
  if (allocations.length === 0) return null

  return (
    <div>
      <div className="flex h-2 rounded-full overflow-hidden bg-zinc-800">
        {allocations.map((a) => (
          <div
            key={a.assetType}
            className="transition-all duration-300"
            style={{
              width: `${Math.max(a.percentage, 2)}%`,
              backgroundColor: TRADING_ASSETS[a.assetType].color,
            }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-3 mt-2">
        {allocations.map((a) => (
          <div key={a.assetType} className="flex items-center gap-1.5 text-xs text-zinc-400">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: TRADING_ASSETS[a.assetType].color }}
            />
            {TRADING_ASSETS[a.assetType].label} {a.percentage.toFixed(1)}%
          </div>
        ))}
      </div>
    </div>
  )
}

export function QuoteCard({ quote, className, onClick }: { quote: MarketQuote; className?: string; onClick?: () => void }) {
  const isPositive = quote.changePct24h >= 0

  const content = (
    <>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-white truncate">{quote.symbol}</span>
          <span className="text-xs text-zinc-500">{quote.exchange}</span>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5 truncate">{quote.name}</div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="font-semibold text-white font-mono text-sm">
          ${quote.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className={cn(
          'flex items-center justify-end gap-1 text-xs font-medium',
          isPositive ? 'text-emerald-400' : 'text-red-400'
        )}>
          {isPositive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
          {isPositive ? '+' : ''}{quote.changePct24h.toFixed(2)}%
        </div>
      </div>
    </>
  )

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className={cn(
          'card-elevated card-hover p-4 flex items-center justify-between group w-full text-left',
          className
        )}
      >
        {content}
      </button>
    )
  }

  return (
    <Link
      href={`/trading?symbol=${quote.symbol}&assetType=${quote.assetType}`}
      className={cn(
        'card-elevated card-hover p-4 flex items-center justify-between group',
        className
      )}
    >
      {content}
    </Link>
  )
}
