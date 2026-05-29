// Trading News API — GET news feed
import { NextResponse, NextRequest } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { marketDataService } from '@/lib/trading/market-data'

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { searchParams } = new URL(request.url)
    const symbols = searchParams.get('symbols')?.split(',').filter(Boolean)
    const news = await marketDataService.getMarketNews(symbols)
    return NextResponse.json({ news })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
