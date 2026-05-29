// CIO Agent API — Layer 6 operations
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { cioAgent } from '@/lib/trading/cio-agent'

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const action = searchParams.get('action') || 'state'

    switch (action) {
      case 'state': {
        const state = cioAgent.getWorkforceState()
        return NextResponse.json({ workforce: state })
      }

      case 'pods': {
        const pods = cioAgent.getPods().map(p => ({
          podId: p.podId,
          name: p.name,
          allocatedCapital: p.allocatedCapital,
          conviction: p.conviction,
          performance: p.performance,
          riskLimits: p.riskLimits,
          totalValue: p.totalValue,
        }))
        return NextResponse.json({ pods })
      }

      case 'reflections': {
        const state = cioAgent.getWorkforceState()
        return NextResponse.json({ reflections: state.recentReflections })
      }

      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 })
    }
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
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
    const { action } = body

    switch (action) {
      case 'run-cycle': {
        const decision = await cioAgent.runCIOCycle()
        return NextResponse.json({ decision })
      }

      case 'veto': {
        const { podId, reason } = body
        if (!podId || !reason) {
          return NextResponse.json({ error: 'podId and reason are required' }, { status: 400 })
        }
        const success = cioAgent.overridePodDecision(podId, reason)
        return NextResponse.json({ success, message: success ? 'Pod vetoed' : 'Pod not found' })
      }

      case 'reflect': {
        const reflection = cioAgent.selfReflect()
        return NextResponse.json({ reflection })
      }

      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 })
    }
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
    )
  }
}
