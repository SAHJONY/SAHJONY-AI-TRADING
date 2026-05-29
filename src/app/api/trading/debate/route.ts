// POST /api/trading/debate — run a multi-agent trading debate
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { agentDebateOrchestrator } from '@/lib/trading/agent-debate'
import type { AssetType } from '@/types/trading'

export async function POST(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()
    const { symbol, assetType } = body

    if (!symbol || !assetType) {
      return NextResponse.json({ error: 'symbol and assetType are required' }, { status: 400 })
    }

    const validAssetTypes: AssetType[] = ['stock', 'crypto', 'forex']
    if (!validAssetTypes.includes(assetType as AssetType)) {
      return NextResponse.json({ error: `Invalid assetType. Must be one of: ${validAssetTypes.join(', ')}` }, { status: 400 })
    }

    const debateState = await agentDebateOrchestrator.runDebate(
      symbol.toUpperCase(),
      assetType as AssetType
    )

    return NextResponse.json({ debate: debateState })
  } catch (error) {
    console.error('Debate error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Debate failed' },
      { status: 500 }
    )
  }
}
