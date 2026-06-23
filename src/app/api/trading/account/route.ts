// GET    /api/trading/account          — portfolio snapshot (account + positions + open orders)
// POST   /api/trading/account          — execute a trade
// DELETE /api/trading/account?symbol=X — close a position

import { NextRequest, NextResponse } from 'next/server'
import { brokerFetch, getAccount, getPositions, resolveAccountId } from '@/lib/trading/alpaca'

export async function GET() {
  try {
    const id = await resolveAccountId()
    const [account, positions, orders] = await Promise.all([
      getAccount(),
      getPositions(),
      brokerFetch(`/v1/trading/accounts/${id}/orders?status=open`),
    ])
    return NextResponse.json({ account, positions, openOrders: orders || [] })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const { symbol, side, qty, notional, type, timeInForce, limitPrice, stopPrice } = await req.json()

    if (!symbol || !side) {
      return NextResponse.json({ error: 'symbol and side required' }, { status: 400 })
    }

    const id      = await resolveAccountId()
    const payload: any = {
      symbol:        symbol.toUpperCase(),
      side,
      type:          type || 'market',
      time_in_force: timeInForce || 'gtc',
    }

    if (notional)   payload.notional    = String(notional)
    else if (qty)   payload.qty         = String(qty)
    else return NextResponse.json({ error: 'qty or notional required' }, { status: 400 })

    if (limitPrice) payload.limit_price = String(limitPrice)
    if (stopPrice)  payload.stop_price  = String(stopPrice)

    const order = await brokerFetch(`/v1/trading/accounts/${id}/orders`, {
      method: 'POST',
      body:   JSON.stringify(payload),
    })
    return NextResponse.json({ success: true, order })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const symbol = req.nextUrl.searchParams.get('symbol')
    if (!symbol) return NextResponse.json({ error: 'symbol required' }, { status: 400 })

    const id     = await resolveAccountId()
    const result = await brokerFetch(
      `/v1/trading/accounts/${id}/positions/${symbol.toUpperCase()}`,
      { method: 'DELETE' }
    )
    return NextResponse.json({ success: true, result })
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
}
