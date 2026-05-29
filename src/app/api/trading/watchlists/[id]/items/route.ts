// Trading Watchlist Items — POST add, DELETE remove
import { NextResponse, NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { id } = await params
    const { symbol, assetType } = await request.json()
    if (!symbol) return NextResponse.json({ error: 'Symbol required' }, { status: 400 })

    const { data, error } = await supabase
      .from('trading_watchlist_items')
      .insert({ watchlist_id: id, user_id: user.id, symbol, asset_type: assetType || 'stock' })
      .select()
      .single()

    if (error) throw error
    return NextResponse.json({ item: data })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
