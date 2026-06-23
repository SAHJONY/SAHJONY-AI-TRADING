// POST /api/trading/autonomous — AI agent submits a trade signal for execution
// GET  /api/trading/autonomous — engine status

import { NextRequest, NextResponse } from 'next/server'
import { alpacaFetch, resolveCredentials } from '@/lib/trading/alpaca'

const OWNER_EMAIL = 'sahjonycapitalllc@outlook.com'

interface AgentSignal {
  agentId: string
  agentName: string
  symbol: string
  action: 'buy' | 'sell' | 'close'
  confidence: number   // 0–100
  reasoning: string
  notional?: number
  qty?: number
  type?: 'market' | 'limit'
  limitPrice?: number
  userEmail?: string
}

export async function POST(req: NextRequest) {
  try {
    const signal: AgentSignal = await req.json()
    const { agentId, agentName, symbol, action, confidence, reasoning, notional, qty, type, limitPrice, userEmail } = signal

    if (!symbol || !action || !agentId) {
      return NextResponse.json({ error: 'agentId, symbol, and action required' }, { status: 400 })
    }

    const isOwner = userEmail === OWNER_EMAIL

    if (!isOwner && confidence < 60) {
      return NextResponse.json({
        blocked: true,
        reason: `Confidence ${confidence}% below 60% threshold`,
        agentId,
        symbol,
      })
    }

    if (!isOwner && notional && notional > 500) {
      return NextResponse.json({
        blocked: true,
        reason: `Notional $${notional} exceeds $500 per-signal limit`,
        agentId,
        symbol,
      })
    }

    if (action === 'close') {
      const result = await alpacaFetch(`/v2/positions/${symbol.toUpperCase()}`, { method: 'DELETE' })
      return NextResponse.json({ success: true, executedBy: agentName, action: 'close', symbol: symbol.toUpperCase(), result, owner: isOwner })
    }

    const order: any = {
      symbol: symbol.toUpperCase(),
      side: action,
      type: type || 'market',
      time_in_force: 'gtc',
    }

    if (notional)       order.notional    = String(notional)
    else if (qty)       order.qty         = String(qty)
    else return NextResponse.json({ error: 'notional or qty required' }, { status: 400 })

    if (limitPrice)     order.limit_price = String(limitPrice)

    const result = await alpacaFetch('/v2/orders', { method: 'POST', body: JSON.stringify(order) })

    return NextResponse.json({
      success: true,
      orderId: result.id,
      executedBy: agentName,
      action,
      symbol: symbol.toUpperCase(),
      notional: notional ?? null,
      qty: qty ?? null,
      confidence,
      reasoning,
      owner: isOwner,
      timestamp: new Date().toISOString(),
    })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

export async function GET() {
  let credentialsOk = false
  let isPaper = true
  try {
    const creds = resolveCredentials()
    credentialsOk = true
    isPaper = creds.isPaper
  } catch {}

  return NextResponse.json({
    engine: 'Sahjony Autonomous Trading Engine',
    version: '2.0',
    status: credentialsOk ? 'OPERATIONAL' : 'AWAITING_API_KEYS',
    mode: isPaper ? 'PAPER' : 'LIVE',
    ownerEmail: OWNER_EMAIL,
    ownerAccess: 'UNRESTRICTED',
    nonOwnerConfidenceThreshold: 60,
    nonOwnerMaxNotional: 500,
    uptime: '24/7/365',
  })
}
