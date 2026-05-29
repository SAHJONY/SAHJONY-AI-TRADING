// Trading Portfolio API — GET list, POST create
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { portfolioService } from '@/lib/trading/portfolio'

export async function GET() {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const portfolios = await portfolioService.getPortfolios(user.id)
    return NextResponse.json({ portfolios })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { name, initialBalance, isPaper } = await request.json()
    if (!name) return NextResponse.json({ error: 'Name is required' }, { status: 400 })

    const portfolio = await portfolioService.createPortfolio(user.id, name, initialBalance || 10000, isPaper ?? true)
    return NextResponse.json({ portfolio })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
