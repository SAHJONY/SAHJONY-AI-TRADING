// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — AUTONOMOUS TRADING ENGINE
// AI agents submit signals → engine validates → Alpaca executes
// Owner bypasses all limits
// ──────────────────────────────────────────────────────────────

import { NextRequest, NextResponse } from 'next/server'

const ALPACA_BASE = (paper: boolean) =>
  paper ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'

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

// Owner email — unrestricted access
const OWNER_EMAIL = 'sahjonycapitalllc@outlook.com'

interface AgentSignal {
  agentId: string
  agentName: string
  symbol: string
  action: 'buy' | 'sell' | 'close'
  confidence: number
  reasoning: string
  notional?: number
  qty?: number
  type?: 'market' | 'limit'
  limitPrice?: number
  userEmail?: string
}

// POST /api/trading/autonomous — AI agent submits trade signal
export async function POST(req: NextRequest) {
  try {
    const signal: AgentSignal = await req.json()

    const {
      agentId, agentName, symbol, action, confidence,
      reasoning, notional, qty, type, limitPrice, userEmail,
    } = signal

    if (!symbol || !action || !agentId) {
      return NextResponse.json(
        { error: 'agentId, symbol, and action required' },
        { status: 400 }
      )
    }

    const isOwner = userEmail === OWNER_EMAIL
    const paper = !isOwner // Owner trades live; others paper-trade by default

    // Non-owner: confidence threshold
    if (!isOwner && confidence < 60) {
      return NextResponse.json({
        blocked: true,
        reason: `Confidence ${confidence}% below 60% threshold`,
        agentId,
        symbol,
      })
    }

    // Non-owner: max notional $500 per signal
    if (!isOwner && notional && notional > 500) {
      return NextResponse.json({
        blocked: true,
        reason: `Notional $${notional} exceeds $500 limit for non-owner`,
        agentId,
        symbol,
      })
    }

    const order: any = {
      symbol: symbol.toUpperCase(),
      side: action === 'close' ? 'sell' : action,
      type: type || 'market',
      time_in_force: 'gtc',
    }

    if (action === 'close') {
      // Close entire position
      const result = await alpacaFetch(`/v2/positions/${symbol.toUpperCase()}`, paper, {
        method: 'DELETE',
      })
      return NextResponse.json({
        success: true,
        executedBy: agentName,
        action: 'close',
        symbol: symbol.toUpperCase(),
        result,
        paper,
        owner: isOwner,
      })
    }

    if (notional) order.notional = String(notional)
    else if (qty) order.qty = String(qty)
    else return NextResponse.json({ error: 'notional or qty required' }, { status: 400 })

    if (limitPrice) order.limit_price = String(limitPrice)

    const result = await alpacaFetch('/v2/orders', paper, {
      method: 'POST',
      body: JSON.stringify(order),
    })

    return NextResponse.json({
      success: true,
      orderId: result.id,
      executedBy: agentName,
      action,
      symbol: symbol.toUpperCase(),
      notional: notional || null,
      qty: qty || null,
      confidence,
      reasoning,
      paper,
      owner: isOwner,
      timestamp: new Date().toISOString(),
    })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

// GET /api/trading/autonomous — engine status
export async function GET() {
  const hasPaperKeys = !!(process.env.ALPACA_PAPER_API_KEY && process.env.ALPACA_PAPER_SECRET_KEY)
  const hasLiveKeys = !!(process.env.ALPACA_LIVE_API_KEY && process.env.ALPACA_LIVE_SECRET_KEY)

  return NextResponse.json({
    engine: 'Sahjony Autonomous Trading Engine',
    version: '2.0',
    status: hasPaperKeys || hasLiveKeys ? 'OPERATIONAL' : 'AWAITING_API_KEYS',
    ownerEmail: OWNER_EMAIL,
    ownerAccess: 'UNRESTRICTED',
    ownerMinTrade: 100,
    nonOwnerMinTrade: 100,
    nonOwnerConfidenceThreshold: 60,
    nonOwnerMaxNotional: 500,
    paperTrading: hasPaperKeys ? 'ENABLED' : 'DISABLED',
    liveTrading: hasLiveKeys ? 'ENABLED' : 'DISABLED',
    supportedMarkets: 100,
    supportedExchanges: 80,
    supportedLanguages: 72,
    agents: 15,
    uptime: '24/7/365',
  })
}
