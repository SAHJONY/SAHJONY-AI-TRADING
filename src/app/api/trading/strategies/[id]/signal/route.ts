// Trading Strategy signal endpoint
import { NextResponse, NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { strategyEngine } from '@/lib/trading/strategy-engine'
import type { AssetType } from '@/types/trading'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { id } = await params
    const { searchParams } = new URL(request.url)
    const symbol = searchParams.get('symbol')
    const assetType = (searchParams.get('assetType') || 'stock') as AssetType

    if (!symbol) return NextResponse.json({ error: 'Symbol required' }, { status: 400 })

    const strategy = await strategyEngine.getStrategy(id, user.id)
    if (!strategy) return NextResponse.json({ error: 'Strategy not found' }, { status: 404 })

    const signal = await strategyEngine.generateSignal(strategy, symbol, assetType)
    return NextResponse.json({ signal })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
