// GET /api/trading/knowledge — enriched market context with sentiment and technicals
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { knowledgePipeline } from '@/lib/trading/knowledge-pipeline'
import type { AssetType } from '@/types/trading'

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const symbol = searchParams.get('symbol')
    const assetType = searchParams.get('assetType') as AssetType

    if (!symbol || !assetType) {
      return NextResponse.json({ error: 'symbol and assetType are required' }, { status: 400 })
    }

    const context = await knowledgePipeline.enrichMarketContext(symbol.toUpperCase(), assetType)
    const textContext = await knowledgePipeline.getEnrichedContext(symbol.toUpperCase(), assetType)

    return NextResponse.json({ context, textContext })
  } catch (error) {
    console.error('Knowledge enrichment error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Knowledge enrichment failed' },
      { status: 500 }
    )
  }
}
