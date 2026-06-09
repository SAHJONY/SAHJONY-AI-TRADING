// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — TRADING API (ALPACA)
// Owner account: unrestricted, $100 minimum, autonomous
// ──────────────────────────────────────────────────────────────

import { NextRequest, NextResponse } from 'next/server'

const ALPACA_BASE = (paper: boolean) =>
  paper
    ? 'https://paper-api.alpaca.markets'
    : 'https://api.alpaca.markets'

function getHeaders(paper: boolean) {
  const key = paper
    ? process.env.ALPACA_PAPER_API_KEY
    : process.env.ALPACA_LIVE_API_KEY
  const secret = paper
    ? process.env.ALPACA_PAPER_SECRET_KEY
    : process.env.ALPACA_LIVE_SECRET_KEY
  if (!key || !secret) throw new Error('Alpaca API keys not configured')
  return {
    'APCA-API-KEY-ID': key,
    'APCA-API-SECRET-KEY': secret,
    'Content-Type': 'application/json',
  }
}

async function alpacaFetch(path: string, paper: boolean, init?: RequestInit) {
  const res = await fetch(`${ALPACA_BASE(paper)}${path}`, {
    ...init,
    headers: { ...getHeaders(paper), ...(init?.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Alpaca ${res.status}: ${text}`)
  }
  return res.json()
}

// GET /api/trading/account — portfolio summary
export async function GET(req: NextRequest) {
  try {
    const paper = req.nextUrl.searchParams.get('live') !== 'true'
    const account = await alpacaFetch('/v2/account', paper)
    const positions = await alpacaFetch('/v2/positions', paper)
    const orders = await alpacaFetch('/v2/orders?status=open', paper)

    return NextResponse.json({
      account: {
        equity: Number(account.equity),
        cash: Number(account.cash),
        buyingPower: Number(account.buying_power),
        portfolioValue: Number(account.portfolio_value),
        unrealizedPL: Number(account.unrealized_pl),
        unrealizedPLPercent: Number(account.unrealized_plpc),
        status: account.status,
        patternDayTrader: account.pattern_day_trader,
        tradingBlocked: account.trading_blocked,
      },
      positions: (positions || []).map((p: any) => ({
        symbol: p.symbol,
        qty: Number(p.qty),
        side: p.side,
        marketValue: Number(p.market_value),
        avgEntryPrice: Number(p.avg_entry_price),
        currentPrice: Number(p.current_price),
        unrealizedPL: Number(p.unrealized_pl),
        unrealizedPLPercent: Number(p.unrealized_plpc),
        changeToday: Number(p.change_today),
      })),
      openOrders: orders || [],
      paper,
    })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

// POST /api/trading/account — execute trade
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { symbol, side, qty, notional, type, timeInForce, limitPrice, stopPrice, paper: usePaper } = body

    if (!symbol || !side) {
      return NextResponse.json({ error: 'symbol and side required' }, { status: 400 })
    }

    const paper = usePaper !== false
    const order: any = {
      symbol: symbol.toUpperCase(),
      side,
      type: type || 'market',
      time_in_force: timeInForce || 'gtc',
    }

    if (notional) order.notional = String(notional)
    else if (qty) order.qty = String(qty)
    else return NextResponse.json({ error: 'qty or notional required' }, { status: 400 })

    if (limitPrice) order.limit_price = String(limitPrice)
    if (stopPrice) order.stop_price = String(stopPrice)

    const result = await alpacaFetch('/v2/orders', paper, {
      method: 'POST',
      body: JSON.stringify(order),
    })

    return NextResponse.json({ success: true, order: result, paper })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

// DELETE /api/trading/account — close position
export async function DELETE(req: NextRequest) {
  try {
    const symbol = req.nextUrl.searchParams.get('symbol')
    const paper = req.nextUrl.searchParams.get('live') !== 'true'
    if (!symbol) return NextResponse.json({ error: 'symbol required' }, { status: 400 })

    const result = await alpacaFetch(`/v2/positions/${symbol.toUpperCase()}`, paper, {
      method: 'DELETE',
    })

    return NextResponse.json({ success: true, result, paper })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
