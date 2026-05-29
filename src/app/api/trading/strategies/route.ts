// Trading Strategies API — GET list, POST create
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { strategyEngine } from '@/lib/trading/strategy-engine'

export async function GET() {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const strategies = await strategyEngine.getStrategies(user.id)
    return NextResponse.json({ strategies })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const supabase = await createClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

    const { name, description, assetTypes, indicators, conditions, code } = await request.json()
    if (!name) return NextResponse.json({ error: 'Name is required' }, { status: 400 })

    const strategy = await strategyEngine.createStrategy(user.id, name, description || '', assetTypes || ['stock'], indicators || [], conditions || { entry: [], exit: [] }, code)
    return NextResponse.json({ strategy })
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
