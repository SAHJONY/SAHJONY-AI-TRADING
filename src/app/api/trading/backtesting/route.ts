// Trading Backtesting API — GET list, POST run backtest
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { backtestEngine } from '@/lib/trading/backtest-engine'

export async function GET() {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const backtests = await backtestEngine.getBacktests(user.id)
    return NextResponse.json({ backtests })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { strategyId, name, symbol, assetType, timeframe, startDate, endDate, initialCapital } = await request.json()

    if (!strategyId || !symbol) {
      return NextResponse.json({ error: 'strategyId and symbol required' }, { status: 400 })
    }

    const backtest = await backtestEngine.runBacktest(
      user.id, strategyId, name || `Backtest ${symbol}`,
      symbol, assetType || 'stock', timeframe || '1d',
      startDate, endDate, initialCapital || 10000
    )
    return NextResponse.json({ backtest })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Internal server error'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
