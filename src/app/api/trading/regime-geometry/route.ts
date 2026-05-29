// GET /api/trading/regime-geometry — Fisher metric, geodesic path, regime detection
// POST /api/trading/regime-geometry — feed a new price observation
// DELETE /api/trading/regime-geometry — reset tracking for a symbol

import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { regimeGeometryDetector } from '@/lib/trading/regime-geometry-detector'
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

    const result = regimeGeometryDetector.getRegimeResult(symbol.toUpperCase(), assetType)
    if (!result) {
      return NextResponse.json({
        error: 'Insufficient data',
        message: `Not enough observations for ${symbol}. Feed price data via POST first.`,
      }, { status: 404 })
    }

    const context = regimeGeometryDetector.getRegimeContext(symbol.toUpperCase(), assetType)

    return NextResponse.json({ result, context })
  } catch (error) {
    console.error('Regime geometry error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Regime geometry analysis failed' },
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
    const { symbol, assetType, price, previousPrice } = body

    if (!symbol || !assetType || price === undefined) {
      return NextResponse.json({ error: 'symbol, assetType, and price are required' }, { status: 400 })
    }

    if (typeof price !== 'number' || price <= 0) {
      return NextResponse.json({ error: 'price must be a positive number' }, { status: 400 })
    }

    regimeGeometryDetector.updateSymbol(
      symbol.toUpperCase(),
      assetType as AssetType,
      price,
      previousPrice,
    )

    const result = regimeGeometryDetector.getRegimeResult(symbol.toUpperCase(), assetType as AssetType)

    return NextResponse.json({
      message: `Observation recorded for ${symbol}`,
      regime: result?.regime || 'calm',
      observationCount: result?.observationCount || 0,
      result,
    })
  } catch (error) {
    console.error('Regime geometry update error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Update failed' },
      { status: 500 }
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
    const symbol = searchParams.get('symbol')
    const assetType = searchParams.get('assetType') as AssetType

    if (!symbol || !assetType) {
      return NextResponse.json({ error: 'symbol and assetType are required' }, { status: 400 })
    }

    regimeGeometryDetector.resetSymbol(symbol.toUpperCase(), assetType)

    return NextResponse.json({ message: `Tracking reset for ${symbol}` })
  } catch (error) {
    console.error('Regime geometry reset error:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Reset failed' },
      { status: 500 }
    )
  }
}
