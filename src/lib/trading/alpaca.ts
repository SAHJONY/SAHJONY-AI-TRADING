// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — ALPACA CLIENT
// Credential resolution order:
//   1. APCA_API_KEY_ID / APCA_API_SECRET_KEY  (Alpaca SDK standard)
//   2. ALPACA_API_KEY / ALPACA_SECRET_KEY      (legacy GitHub secret names)
// Base URL comes from APCA_API_BASE_URL; defaults to paper trading.
// ──────────────────────────────────────────────────────────────

export const PAPER_BASE = 'https://paper-api.alpaca.markets'
export const LIVE_BASE  = 'https://api.alpaca.markets'

export function resolveCredentials(): { key: string; secret: string; baseUrl: string; isPaper: boolean } {
  const key =
    process.env.APCA_API_KEY_ID ||
    process.env.ALPACA_API_KEY

  const secret =
    process.env.APCA_API_SECRET_KEY ||
    process.env.ALPACA_SECRET_KEY

  if (!key || !secret) {
    throw new Error(
      'Alpaca credentials missing. Set APCA_API_KEY_ID + APCA_API_SECRET_KEY ' +
      '(or legacy ALPACA_API_KEY + ALPACA_SECRET_KEY) in environment.'
    )
  }

  const baseUrl = process.env.APCA_API_BASE_URL || PAPER_BASE
  const isPaper = baseUrl.includes('paper')

  return { key, secret, baseUrl, isPaper }
}

export function alpacaHeaders(): Record<string, string> {
  const { key, secret } = resolveCredentials()
  return {
    'APCA-API-KEY-ID': key,
    'APCA-API-SECRET-KEY': secret,
    'Content-Type': 'application/json',
  }
}

export async function alpacaFetch(path: string, init?: RequestInit): Promise<any> {
  const { baseUrl } = resolveCredentials()
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...alpacaHeaders(), ...(init?.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Alpaca ${res.status}: ${text}`)
  }
  return res.json()
}

// ── Types ──────────────────────────────────────────────────────

export interface TradeOrder {
  symbol: string
  side: 'buy' | 'sell'
  qty?: number
  notional?: number
  type: 'market' | 'limit' | 'stop' | 'stop_limit'
  timeInForce: 'day' | 'gtc' | 'ioc'
  limitPrice?: number
  stopPrice?: number
}

export interface TradePosition {
  symbol: string
  qty: number
  side: 'long' | 'short'
  marketValue: number
  avgEntryPrice: number
  currentPrice: number
  unrealizedPL: number
  unrealizedPLPercent: number
  changeToday: number
}

export interface AccountSummary {
  equity: number
  cash: number
  buyingPower: number
  portfolioValue: number
  unrealizedPL: number
  unrealizedPLPercent: number
  daytradeCount: number
  patternDayTrader: boolean
  tradingBlocked: boolean
  transfersBlocked: boolean
  accountBlocked: boolean
  status: string
  isPaper: boolean
}

// ── Account ────────────────────────────────────────────────────

export async function getAccount(): Promise<AccountSummary> {
  const { isPaper } = resolveCredentials()
  const a = await alpacaFetch('/v2/account')
  return {
    equity: Number(a.equity),
    cash: Number(a.cash),
    buyingPower: Number(a.buying_power),
    portfolioValue: Number(a.portfolio_value),
    unrealizedPL: Number(a.unrealized_pl),
    unrealizedPLPercent: Number(a.unrealized_plpc),
    daytradeCount: a.daytrade_count,
    patternDayTrader: a.pattern_day_trader,
    tradingBlocked: a.trading_blocked,
    transfersBlocked: a.transfers_blocked,
    accountBlocked: a.account_blocked,
    status: a.status,
    isPaper,
  }
}

// ── Positions ──────────────────────────────────────────────────

export async function getPositions(): Promise<TradePosition[]> {
  const positions = await alpacaFetch('/v2/positions')
  return (positions || []).map((p: any) => ({
    symbol: p.symbol,
    qty: Number(p.qty),
    side: p.side as 'long' | 'short',
    marketValue: Number(p.market_value),
    avgEntryPrice: Number(p.avg_entry_price),
    currentPrice: Number(p.current_price),
    unrealizedPL: Number(p.unrealized_pl),
    unrealizedPLPercent: Number(p.unrealized_plpc),
    changeToday: Number(p.change_today),
  }))
}

// ── Execute Order ──────────────────────────────────────────────

export async function executeOrder(order: TradeOrder): Promise<any> {
  const payload: any = {
    symbol: order.symbol.toUpperCase(),
    side: order.side,
    type: order.type,
    time_in_force: order.timeInForce,
  }

  if (order.notional) payload.notional = String(order.notional)
  else if (order.qty) payload.qty = String(order.qty)
  else throw new Error('Must specify either qty or notional amount')

  if (order.limitPrice) payload.limit_price = String(order.limitPrice)
  if (order.stopPrice)  payload.stop_price  = String(order.stopPrice)

  return alpacaFetch('/v2/orders', { method: 'POST', body: JSON.stringify(payload) })
}

// ── Close Position ─────────────────────────────────────────────

export async function closePosition(symbol: string): Promise<any> {
  return alpacaFetch(`/v2/positions/${symbol.toUpperCase()}`, { method: 'DELETE' })
}
