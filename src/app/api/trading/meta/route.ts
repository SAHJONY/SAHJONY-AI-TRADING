// /api/trading/meta — meta-learning performance tracking and optimization
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { metaLearning } from '@/lib/trading/meta-learning'

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const metrics = metaLearning.getPerformanceMetrics()
    const optimizations = metaLearning.generateOptimizations()
    const recentDebates = metaLearning.getRecentDebates(20)
    const agentPerformances = Object.entries(metrics.agentPerformances).map(([role, perf]) => ({
      role,
      ...perf,
    }))

    return NextResponse.json({
      metrics,
      optimizations,
      agentPerformances,
      recentDebates,
      totalDebatesRecorded: metrics.totalTrades,
    })
  } catch (error) {
    console.error('Meta-learning error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Meta-learning query failed' },
      { status: 500 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    // Record debate
    if (body.action === 'recordDebate') {
      const { symbol, assetType, finalDecision, debateState } = body
      if (!symbol || !assetType || !finalDecision || !debateState) {
        return NextResponse.json({ error: 'symbol, assetType, finalDecision, and debateState are required' }, { status: 400 })
      }
      const id = metaLearning.recordDebate(symbol, assetType, finalDecision, debateState)
      return NextResponse.json({ id })
    }

    // Record trade outcome
    if (body.action === 'recordOutcome') {
      const { debateId, pnl, pnlPct } = body
      if (!debateId || pnl === undefined) {
        return NextResponse.json({ error: 'debateId and pnl are required' }, { status: 400 })
      }
      metaLearning.recordTradeOutcome(debateId, pnl, pnlPct || 0)
      return NextResponse.json({ success: true })
    }

    return NextResponse.json({ error: 'Invalid action. Use "recordDebate" or "recordOutcome".' }, { status: 400 })
  } catch (error) {
    console.error('Meta-learning record error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Meta-learning record failed' },
      { status: 500 }
    )
  }
}
