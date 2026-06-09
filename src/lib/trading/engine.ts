// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — TRADING ENGINE
// Autonomous AI trading execution via Alpaca (stocks/crypto)
// and CCXT (60+ crypto exchanges). Owner account has full
// unrestricted access with $100 minimum.
// ──────────────────────────────────────────────────────────────

import Alpaca from '@alpacahq/alpaca-trade-api'

// ── Owner Account Configuration ──
// Owner (sahjonycapitalllc@outlook.com) gets unrestricted access.
// API keys are set via environment variables on Vercel.

function getAlpacaClient(paper = true): Alpaca {
 const apiKey = paper
  ? process.env.ALPACA_PAPER_API_KEY!
  : process.env.ALPACA_LIVE_API_KEY!
 const secretKey = paper
  ? process.env.ALPACA_PAPER_SECRET_KEY!
  : process.env.ALPACA_LIVE_SECRET_KEY!

 if (!apiKey || !secretKey) {
  throw new Error('Alpaca API keys not configured. Set ALPACA_PAPER_API_KEY / ALPACA_LIVE_API_KEY env vars.')
 }

 return new Alpaca({
  keyId: apiKey,
  secretKey,
  paper,
 })
}

// ── Trading Types ──
export interface TradeOrder {
 symbol: string
 side: 'buy' | 'sell'
 qty?: number
 notional?: number // dollar amount (e.g., $100)
 type: 'market' | 'limit' | 'stop' | 'stop_limit'
 timeInForce: 'day' | 'gtc' | 'ioc'
 limitPrice?: number
 stopPrice?: number
 agentId?: string // which AI agent initiated this
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
}

// ── Account ──
export async function getAccount(paper = true): Promise<AccountSummary> {
 const alpaca = getAlpacaClient(paper)
 const account = await alpaca.getAccount()
 return {
  equity: Number(account.equity),
  cash: Number(account.cash),
  buyingPower: Number(account.buying_power),
  portfolioValue: Number(account.portfolio_value),
  unrealizedPL: Number(account.unrealized_pl),
  unrealizedPLPercent: Number(account.unrealized_plpc),
  daytradeCount: account.daytrade_count,
  patternDayTrader: account.pattern_day_trader,
  tradingBlocked: account.trading_blocked,
  transfersBlocked: account.transfers_blocked,
  accountBlocked: account.account_blocked,
  status: account.status,
 }
}

// ── Positions ──
export async function getPositions(paper = true): Promise<TradePosition[]> {
 const alpaca = getAlpacaClient(paper)
 const positions = await alpaca.getPositions()
 return positions.map((p: any) => ({
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

// ── Execute Order ──
export async function executeOrder(order: TradeOrder, paper = true): Promise<any> {
 const alpaca = getAlpacaClient(paper)

 const payload: any = {
  symbol: order.symbol.toUpperCase(),
  side: order.side,
  type: order.type,
  time_in_force: order.timeInForce,
 }

 // Use notional (dollar amount) for fractional shares — enables $100 trades
 if (order.notional) {
  payload.notional = order.notional
 } else if (order.qty) {
  payload.qty = order.qty
 } else {
  throw new Error('Must specify either qty or notional amount')
 }

 if (order.limitPrice) payload.limit_price = order.limitPrice
 if (order.stopPrice) payload.stop_price = order.stopPrice

 const result = await alpaca.createOrder(payload)
 return result
}

// ── Close Position ──
export async function closePosition(symbol: string, paper = true): Promise<any> {
 const alpaca = getAlpacaClient(paper)
 return alpaca.closePosition(symbol)
}

// ── Get Orders ──
export async function getOrders(paper = true, status = 'open'): Promise<any[]> {
 const alpaca = getAlpacaClient(paper)
 return alpaca.getOrders({ status, until: undefined, after: undefined, limit: 100, direction: 'desc', nested: undefined, symbols: undefined } as any)
}

// ── Autonomous Agent Execution ──
// This is the core engine — each AI agent can submit trades
// through this function. Owner account bypasses all limits.

export interface AgentTradeSignal {
 agentId: string
 agentName: string
 symbol: string
 action: 'buy' | 'sell' | 'close'
 confidence: number // 0-100
 reasoning: string
 notional?: number // dollar amount
 qty?: number
 type?: 'market' | 'limit'
 limitPrice?: number
}

export async function executeAgentSignal(
 signal: AgentTradeSignal,
 isOwner: boolean,
 paper = true
): Promise<{ success: boolean; orderId?: string; error?: string }> {
 try {
  // Owner: no confidence threshold, no restrictions
  if (!isOwner && signal.confidence < 60) {
   return { success: false, error: 'Confidence below 60% threshold for non-owner accounts' }
  }

  const order: TradeOrder = {
   symbol: signal.symbol,
   side: signal.action === 'close' ? 'sell' : signal.action,
   notional: signal.notional,
   qty: signal.qty,
   type: signal.type || 'market',
   timeInForce: 'gtc',
   limitPrice: signal.limitPrice,
   agentId: signal.agentId,
  }

  if (signal.action === 'close') {
   const result = await closePosition(signal.symbol, paper)
   return { success: true, orderId: result.id }
  }

  const result = await executeOrder(order, paper)
  return { success: true, orderId: result.id }
 } catch (error: any) {
  return { success: false, error: error.message || 'Trade execution failed' }
 }
}

// ── Market Data ──
export async function getQuotes(symbols: string[], paper = true): Promise<any> {
 const alpaca = getAlpacaClient(paper)
 // Get latest quotes
 const promises = symbols.map(s => alpaca.getLatestQuote(s))
 const quotes = await Promise.allSettled(promises)
 const result: Record<string, any> = {}
 symbols.forEach((s, i) => {
  if (quotes[i].status === 'fulfilled') {
   result[s] = quotes[i].value
  }
 })
 return result
}

// ── Portfolio History ──
export async function getPortfolioHistory(
 paper = true,
 period: '1D' | '1W' | '1M' | '3M' | '1A' = '1M'
): Promise<any> {
 const alpaca = getAlpacaClient(paper)
 return alpaca.getPortfolioHistory({ period, date_start: undefined, date_end: undefined, timeframe: '1D', extended_hours: undefined } as any)
}
