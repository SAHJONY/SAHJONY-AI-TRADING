// Pod Manager API — Layer 5 operations
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { PodManager, createPod } from '@/lib/trading/pod-manager'
import { cioAgent } from '@/lib/trading/cio-agent'
import type { PodConfig, PodRiskLimits, AssetType } from '@/types/trading'

// In-memory pod registry for the workforce
const podRegistry = new Map<string, PodManager>()

export async function GET(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const pods = Array.from(podRegistry.values()).map(p => ({
      podId: p.podId,
      name: p.name,
      allocatedCapital: p.allocatedCapital,
      conviction: p.conviction,
      performance: p.performance,
      riskLimits: p.riskLimits,
      totalValue: p.totalValue,
    }))

    return NextResponse.json({ pods })
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
    const { name, description, assets, strategyIds, allocatedCapital, riskLimits } = body

    if (!name || !assets || !Array.isArray(assets) || assets.length === 0) {
      return NextResponse.json({ error: 'Name and assets array are required' }, { status: 400 })
    }

    const podId = `pod-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

    const config: PodConfig = createPod(
      podId,
      name,
      description || '',
      assets.map((a: { symbol: string; assetType: AssetType; targetAllocationPct?: number }) => ({
        symbol: a.symbol,
        assetType: a.assetType,
        targetAllocationPct: a.targetAllocationPct || 1 / assets.length,
      })),
      strategyIds || [],
      allocatedCapital || 25000,
      riskLimits as Partial<PodRiskLimits> | undefined,
    )

    const pod = new PodManager(config)
    podRegistry.set(podId, pod)
    cioAgent.registerPod(pod)

    return NextResponse.json({
      podId: pod.podId,
      name: pod.name,
      allocatedCapital: pod.allocatedCapital,
      message: 'Pod created and registered with CIO',
    })
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
    )
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const supabase = await createClient()
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const podId = searchParams.get('podId')
    if (!podId) {
      return NextResponse.json({ error: 'podId is required' }, { status: 400 })
    }

    const pod = podRegistry.get(podId)
    if (!pod) {
      return NextResponse.json({ error: 'Pod not found' }, { status: 404 })
    }

    cioAgent.removePod(podId)
    podRegistry.delete(podId)

    return NextResponse.json({ message: `Pod "${pod.name}" removed` })
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 },
    )
  }
}
