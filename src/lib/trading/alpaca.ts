// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — ALPACA BROKER API CLIENT
// Auth: HTTP Basic (base64 key:secret) — not header-based
// Sandbox:    https://broker-api.sandbox.alpaca.markets
// Production: https://broker-api.alpaca.markets
//
// Required env vars:
//   APCA_API_KEY_ID      — Broker API key  (or ALPACA_API_KEY)
//   APCA_API_SECRET_KEY  — Broker API secret (or ALPACA_SECRET_KEY)
//   APCA_API_BASE_URL    — Broker base URL (defaults to sandbox)
//   ALPACA_ACCOUNT_ID    — Account to trade on (auto-resolved if omitted)
// ──────────────────────────────────────────────────────────────

export const SANDBOX_BASE    = 'https://broker-api.sandbox.alpaca.markets'
export const PRODUCTION_BASE = 'https://broker-api.alpaca.markets'

export function resolveCredentials() {
  const key =
    process.env.APCA_API_KEY_ID ||
    process.env.ALPACA_API_KEY

  const secret =
    process.env.APCA_API_SECRET_KEY ||
    process.env.ALPACA_SECRET_KEY

  if (!key || !secret) {
    throw new Error(
      'Alpaca credentials missing. Set APCA_API_KEY_ID + APCA_API_SECRET_KEY in environment.'
    )
  }

  const baseUrl    = process.env.APCA_API_BASE_URL || SANDBOX_BASE
  const isSandbox  = baseUrl.includes('sandbox')
  const accountId  = process.env.ALPACA_ACCOUNT_ID || ''

  return { key, secret, baseUrl, isSandbox, accountId }
}

function basicAuth(): string {
  const { key, secret } = resolveCredentials()
  return 'Basic ' + Buffer.from(`${key}:${secret}`).toString('base64')
}

export async function brokerFetch(path: string, init?: RequestInit): Promise<any> {
  const { baseUrl } = resolveCredentials()
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: basicAuth(),
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (res.status === 204) return null
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Alpaca Broker ${res.status}: ${text}`)
  }
  return res.json()
}

// ── Resolve account ID ─────────────────────────────────────────
// Uses ALPACA_ACCOUNT_ID if set, otherwise fetches the first account.

let _cachedAccountId: string | null = null

export async function resolveAccountId(): Promise<string> {
  const { accountId } = resolveCredentials()
  if (accountId) return accountId
  if (_cachedAccountId) return _cachedAccountId

  const accounts = await brokerFetch('/v1/accounts?limit=1')
  if (!accounts?.length) throw new Error('No accounts found under this Broker API key')
  _cachedAccountId = accounts[0].id as string
  return _cachedAccountId!
}

// ── Types ──────────────────────────────────────────────────────

export interface AccountSummary {
  id: string
  equity: number
  cash: number
  buyingPower: number
  portfolioValue: number
  unrealizedPL: number
  unrealizedPLPercent: number
  daytradeCount: number
  patternDayTrader: boolean
  tradingBlocked: boolean
  status: string
  isSandbox: boolean
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

// ── Account ────────────────────────────────────────────────────

export async function getAccount(): Promise<AccountSummary> {
  const { isSandbox } = resolveCredentials()
  const id = await resolveAccountId()
  const a  = await brokerFetch(`/v1/trading/accounts/${id}/account`)
  return {
    id,
    equity:               Number(a.equity),
    cash:                 Number(a.cash),
    buyingPower:          Number(a.buying_power),
    portfolioValue:       Number(a.portfolio_value),
    unrealizedPL:         Number(a.unrealized_pl),
    unrealizedPLPercent:  Number(a.unrealized_plpc),
    daytradeCount:        a.daytrade_count,
    patternDayTrader:     a.pattern_day_trader,
    tradingBlocked:       a.trading_blocked,
    status:               a.status,
    isSandbox,
  }
}

// ── Positions ──────────────────────────────────────────────────

export async function getPositions(): Promise<TradePosition[]> {
  const id        = await resolveAccountId()
  const positions = await brokerFetch(`/v1/trading/accounts/${id}/positions`)
  return (positions || []).map((p: any) => ({
    symbol:               p.symbol,
    qty:                  Number(p.qty),
    side:                 p.side as 'long' | 'short',
    marketValue:          Number(p.market_value),
    avgEntryPrice:        Number(p.avg_entry_price),
    currentPrice:         Number(p.current_price),
    unrealizedPL:         Number(p.unrealized_pl),
    unrealizedPLPercent:  Number(p.unrealized_plpc),
    changeToday:          Number(p.change_today),
  }))
}

// ── Execute Order ──────────────────────────────────────────────

export async function executeOrder(order: TradeOrder): Promise<any> {
  const id      = await resolveAccountId()
  const payload: any = {
    symbol:        order.symbol.toUpperCase(),
    side:          order.side,
    type:          order.type,
    time_in_force: order.timeInForce,
  }

  if (order.notional)   payload.notional    = String(order.notional)
  else if (order.qty)   payload.qty         = String(order.qty)
  else throw new Error('Must specify either qty or notional amount')

  if (order.limitPrice) payload.limit_price = String(order.limitPrice)
  if (order.stopPrice)  payload.stop_price  = String(order.stopPrice)

  return brokerFetch(`/v1/trading/accounts/${id}/orders`, {
    method: 'POST',
    body:   JSON.stringify(payload),
  })
}

// ── Close Position ─────────────────────────────────────────────

export async function closePosition(symbol: string): Promise<any> {
  const id = await resolveAccountId()
  return brokerFetch(`/v1/trading/accounts/${id}/positions/${symbol.toUpperCase()}`, {
    method: 'DELETE',
  })
}
