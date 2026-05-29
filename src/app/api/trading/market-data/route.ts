// GET /api/trading/market-data — Get quotes, historical bars, search
import { NextResponse, NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { marketDataService } from '@/lib/trading/market-data'
import type { AssetType } from '@/types/trading'

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { searchParams } = new URL(request.url)
    const action = searchParams.get('action') || 'quote'
    const symbol = searchParams.get('symbol')
    const assetType = (searchParams.get('assetType') || 'stock') as AssetType
    const symbols = searchParams.get('symbols')?.split(',')
    const timeframe = searchParams.get('timeframe') || '1d'
    const limit = parseInt(searchParams.get('limit') || '100')
    const query = searchParams.get('query') || ''

    switch (action) {
      case 'quote': {
        if (!symbol) return NextResponse.json({ error: 'Symbol required' }, { status: 400 })
        const quote = await marketDataService.getQuote(symbol, assetType)
        if (!quote) return NextResponse.json({ error: 'Symbol not found' }, { status: 404 })
        return NextResponse.json({ quote })
      }

      case 'quotes': {
        if (!symbols) return NextResponse.json({ error: 'Symbols required' }, { status: 400 })
        const quotes = await marketDataService.getQuotes(symbols, assetType)
        return NextResponse.json({ quotes })
      }

      case 'history': {
        if (!symbol) return NextResponse.json({ error: 'Symbol required' }, { status: 400 })
        const bars = await marketDataService.getHistoricalBars(symbol, assetType, timeframe, limit)
        return NextResponse.json({ bars })
      }

      case 'search': {
        if (!query) return NextResponse.json({ error: 'Query required' }, { status: 400 })
        const results = await marketDataService.searchSymbols(query, assetType !== 'stock' || searchParams.has('assetType') ? assetType : undefined)
        return NextResponse.json({ results })
      }

      default:
        return NextResponse.json({ error: 'Invalid action' }, { status: 400 })
    }
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
