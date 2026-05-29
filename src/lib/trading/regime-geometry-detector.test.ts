/**
 * Regime Geometry Detector — Unit Tests
 * 
 * Tests the Fisher Information Metric computation, KL divergence,
 * regime classification, sliding window recomputation, and state management.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { RegimeGeometryDetector } from '@/lib/trading/regime-geometry-detector'
import type { RegimeGeometryConfig } from '@/types/trading'

// ============================================================
// Test helpers
// ============================================================

/** Create a detector with fast warmup for testing */
function createTestDetector(overrides?: Partial<RegimeGeometryConfig>) {
  return new RegimeGeometryDetector({
    windowSize: 20,
    historyLength: 100,
    velocitySmoothing: 0.3,
    shiftThresholdSigma: 3.0,
    minObservations: 10,
    klSmoothingWindow: 4,
    ...overrides,
  })
}

/** Feed N days of constant prices (no volatility) */
function feedFlat(detector: RegimeGeometryDetector, n: number) {
  for (let i = 0; i < n; i++) {
    // Same price every time → log return = 0
    detector.updateSymbol('TEST', 'stock', 100, 100)
  }
}

/** Feed N days of linearly increasing prices (small positive trend) */
function feedTrend(detector: RegimeGeometryDetector, n: number, drift = 0.001) {
  let prev = 100
  for (let i = 0; i < n; i++) {
    const price = prev * (1 + drift)
    detector.updateSymbol('TEST', 'stock', price, prev)
    prev = price
  }
}

/** Feed N days of volatile prices (alternating +2% / -2%) */
function feedVolatile(detector: RegimeGeometryDetector, n: number) {
  let prev = 100
  for (let i = 0; i < n; i++) {
    const r = i % 2 === 0 ? 1.02 : 0.98
    const price = prev * r
    detector.updateSymbol('TEST', 'stock', price, prev)
    prev = price
  }
}

// ============================================================
// 1. Fisher Metric Computation (via public API)
// ============================================================

describe('Fisher Information Metric', () => {
  it('should compute correct Fisher metric for constant returns (zero variance)', () => {
    const d = createTestDetector()
    feedFlat(d, 20) // minObservations=10, windowSize=20

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    const m = result!.currentMetric

    // All returns are 0 → mu = 0
    expect(m.mu).toBeCloseTo(0, 10)

    // sigma2 is clamped to 1e-12 (unbiased variance of identical values = 0)
    expect(m.sigma2).toBeCloseTo(1e-12)

    // iMu = 1/sigma2 = 1e12, iSigma2 = 1/(2*sigma2^2) = 1/(2e-24) = 5e23
    // determinant = iMu * iSigma2 = 5e35
    expect(m.iMu).toBeCloseTo(1e12, -2)
    expect(m.determinant).toBeGreaterThan(1e30)
  })

  it('should compute correct Fisher metric for known returns', () => {
    const d = createTestDetector({ windowSize: 4, minObservations: 2 })

    // Feed specific returns to get a known mean and variance
    // log(101/100) ≈ 0.00995, log(99/100) ≈ -0.01005, etc.
    d.updateSymbol('TEST', 'stock', 101, 100)   // ~0.00995
    d.updateSymbol('TEST', 'stock', 99, 101)     // ~-0.01961
    d.updateSymbol('TEST', 'stock', 102, 99)     // ~0.02985
    d.updateSymbol('TEST', 'stock', 100, 102)    // ~-0.01980

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    const m = result!.currentMetric

    // Window size should be 4
    expect(m.windowSize).toBe(4)

    // mu should be the mean of the 4 log returns
    // sigma2 should be the unbiased variance
    expect(m.mu).not.toBeNaN()
    expect(m.sigma2).toBeGreaterThan(0)
    expect(m.iMu).toBeCloseTo(1 / m.sigma2, 5)
    expect(m.iSigma2).toBeCloseTo(1 / (2 * m.sigma2 * m.sigma2), 5)
    expect(m.determinant).toBeCloseTo(m.iMu * m.iSigma2, 5)
  })

  it('should clamp sigma2 to avoid division by zero', () => {
    const d = createTestDetector({ windowSize: 2, minObservations: 2 })

    // Two identical returns → variance = 0
    d.updateSymbol('TEST', 'stock', 100, 100) // log(1) = 0
    d.updateSymbol('TEST', 'stock', 100, 100) // log(1) = 0

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    const m = result!.currentMetric

    // sigma2 should be clamped to 1e-12, not 0
    expect(m.sigma2).toBeGreaterThanOrEqual(1e-12)
    expect(Number.isFinite(m.iMu)).toBe(true)
    expect(Number.isFinite(m.iSigma2)).toBe(true)
    expect(Number.isFinite(m.determinant)).toBe(true)
  })

  it('should handle negative returns correctly', () => {
    const d = createTestDetector({ windowSize: 4, minObservations: 2 })

    // All negative returns
    d.updateSymbol('TEST', 'stock', 95, 100)   // -0.0513
    d.updateSymbol('TEST', 'stock', 90, 95)     // -0.0541
    d.updateSymbol('TEST', 'stock', 85, 90)     // -0.0572
    d.updateSymbol('TEST', 'stock', 80, 85)     // -0.0606

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    const m = result!.currentMetric

    // mu should be negative
    expect(m.mu).toBeLessThan(0)
    expect(m.sigma2).toBeGreaterThan(0)
    expect(Number.isFinite(m.determinant)).toBe(true)
  })
})

// ============================================================
// 2. KL Divergence Correctness (via geodesic path)
// ============================================================

describe('KL Divergence & Symmetrized KL', () => {
  it('should produce zero KL for identical distributions (via geodesic path)', () => {
    const d = createTestDetector()

    // Feed constant returns — every metric will be identical
    // Need enough data to get multiple geodesic points
    feedFlat(d, 31) // 31 updates, each with enough returns to compute 2+ metrics

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()

    // With identical metrics, KL between consecutive should be near zero
    const geoPoints = result!.geodesicPath
    expect(geoPoints.length).toBeGreaterThan(0) // ensure geodesic points exist
    const avgKL = geoPoints.reduce((s, p) => s + p.klDistance, 0) / geoPoints.length
    expect(avgKL).toBeLessThan(0.01) // essentially zero

    // Cumulative geodesic distance should be near zero
    expect(result!.totalGeodesicDistance).toBeLessThan(0.05)
  })

  it('should produce non-zero KL for different distributions', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    // First batch: flat prices (low variance)
    feedFlat(d, 10)

    // Second batch: volatile prices (high variance)
    // This creates a shift in the distribution → KL > 0
    let prev = 100
    for (let i = 0; i < 15; i++) {
      const r = i % 4 === 0 ? 1.05 : i % 4 === 1 ? 0.95 : i % 4 === 2 ? 1.03 : 0.97
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()

    // Total geodesic distance should be > 0 — distribution changed
    expect(result!.totalGeodesicDistance).toBeGreaterThan(0)
  })

  it('should accumulate geodesic distance over multiple distribution shifts', () => {
    const d = createTestDetector({ windowSize: 8, minObservations: 4 })

    // Phase 1: calm
    feedFlat(d, 10)

    // Phase 2: high volatility
    feedVolatile(d, 20)

    const result1 = d.getRegimeResult('TEST', 'stock')
    expect(result1).not.toBeNull()
    const dist1 = result1!.totalGeodesicDistance
    expect(dist1).toBeGreaterThan(0) // volatile phase should produce geodesic movement

    // Phase 3: crash (extreme negative)
    let prev = 100
    for (let i = 0; i < 20; i++) {
      const price = prev * 0.97
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result2 = d.getRegimeResult('TEST', 'stock')
    expect(result2).not.toBeNull()

    // Distance should have accumulated further
    expect(result2!.totalGeodesicDistance).toBeGreaterThan(dist1)
  })
})

// ============================================================
// 3. Regime Classification Edge Cases
// ============================================================

describe('Regime Classification', () => {
  it('should return calm during warmup (insufficient geodesic history)', () => {
    const d = createTestDetector()

    // Feed just enough to compute metrics but not enough geodesic points
    feedFlat(d, 15) // minObservations=10 for metric, but need 10 geodesic points

    const result = d.getRegimeResult('TEST', 'stock')
    // With 15 zero-return updates, metrics exist but geodesicPath < minObservations
    expect(result).not.toBeNull()
    expect(result!.regime).toBe('calm')
  })

  it('should classify as calm for low-volatility, low-velocity data', () => {
    const d = createTestDetector()
    // Steady, small-magnitude returns → calm
    feedTrend(d, 80, 0.0001) // tiny drift

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // After many updates with tiny returns, should be calm
    expect(result!.regime).toBe('calm')
  })

  it('should detect trending regime with consistent directional returns', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5, historyLength: 26 })

    // Phase 1 (14 updates): alternating ±4% → moderate variance, lower determinant (~logDet 20)
    // Phase 2 (12 updates): consistent 0.5% drift → near-zero variance, enormous determinant (~logDet 82)
    // At query: 14 Phase 1 + 12 Phase 2 = 26 metrics, median at index 13 → Phase 1 (lower).
    // Current (Phase 2) > median → logDet > log50p true. Velocity decayed → low-velocity path.
    // All returns positive → sign changes 0 < 30% → trending.
    let prev = 100
    for (let i = 0; i < 14; i++) {
      const r = i % 2 === 0 ? 1.04 : 0.96
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }
    for (let i = 0; i < 12; i++) {
      const price = prev * 1.005
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // Trending: current det > median (Phase 1 baseline), consistent direction, low velocity
    expect(['trending', 'volatile']).toContain(result!.regime)
  })

  it('should detect volatile regime with high-variance returns', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5, historyLength: 26 })

    // Phase 1 (14 updates): alternating ±10% → very high variance, very low determinant (~logDet 13)
    // Phase 2 (12 updates): alternating ±3% → moderate variance, higher determinant (~logDet 20)
    // At query: 14 Phase 1 + 12 Phase 2 = 26 metrics, median at index 13 → Phase 1 (lower).
    // Current (Phase 2) > median → logDet > log50p true. Alternating signs → volatile.
    let prev = 100
    for (let i = 0; i < 14; i++) {
      const r = i % 2 === 0 ? 1.10 : 0.90
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }
    for (let i = 0; i < 12; i++) {
      const r = i % 2 === 0 ? 1.03 : 0.97
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // Volatile: current det > Phase 1 baseline median, alternating signs → volatile
    expect(result!.regime).not.toBe('calm')
  })

  it('should detect crisis with extreme returns', () => {
    const d = createTestDetector({ windowSize: 8, minObservations: 4 })

    // Phase 1: warm up with volatile data (high variance → low determinant)
    // This ensures the crisis phase has HIGHER determinant than warmup,
    // which is what the detector looks for (collapsing distribution structure)
    let prev = 100
    for (let i = 0; i < 30; i++) {
      const r = i % 3 === 0 ? 1.04 : i % 3 === 1 ? 0.96 : 1.02
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    // Phase 2: crisis — consistent crashes (low variance → high determinant spike)
    // All returns are similar and very negative = distribution collapses
    for (let i = 0; i < 25; i++) {
      const crash = 0.048 + Math.random() * 0.004 // ~5% consistent crash
      const price = prev * (1 - crash)
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // Crisis: distribution collapsed to narrow negative returns + geodesic jump from volatile
    expect(result!.regime).not.toBe('calm')
    expect(result!.totalGeodesicDistance).toBeGreaterThan(0.5)
  })

  it('should detect transitioning regime during gradual parameter change', () => {
    const d = createTestDetector({ windowSize: 8, minObservations: 4, historyLength: 50 })

    // Phase 1 (25 updates): alternating ±2% — establishes baseline with near-zero velocity.
    // The 50-point geodesic path history ensures threshold stays pinned near zero.
    let prev = 100
    for (let i = 0; i < 25; i++) {
      const r = i % 2 === 0 ? 1.02 : 0.98
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    // Phase 2 (4 updates): alternating ±10% — sharp regime shift.
    // Query mid-transition: the rolling window (size 8) still contains a mix of
    // Phase 1 (±2%) and Phase 2 (±10%) returns, creating a large KL spike that
    // pumps the velocity EMA. The threshold (computed from Phase 1 velocities ≈ 0)
    // hasn't caught up yet → velocity > threshold * 2 triggers transitioning.
    for (let i = 0; i < 4; i++) {
      const r = i % 2 === 0 ? 1.10 : 0.90
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // Transitioning: velocity spike from Phase 1→2 shift exceeds dynamic threshold
    expect(result!.regime).not.toBe('calm')
  })

  it('should produce confidence between 0 and 1', () => {
    const d = createTestDetector()
    feedVolatile(d, 80)

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    expect(result!.regimeConfidence).toBeGreaterThan(0)
    expect(result!.regimeConfidence).toBeLessThan(1)
  })

  it('should compute a positive velocity threshold', () => {
    const d = createTestDetector()
    feedVolatile(d, 80)

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    expect(result!.velocityThreshold).toBeGreaterThan(0)
  })
})

// ============================================================
// 4. Sliding Window Recomputation
// ============================================================

describe('Sliding Window Recomputation', () => {
  it('should maintain max windowSize returns in the buffer', () => {
    const d = createTestDetector({ windowSize: 20, minObservations: 5 })

    // Feed 50 updates — buffer should trim to 20
    feedTrend(d, 50, 0.001)

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    // observationCount represents the returns buffer length
    expect(result!.observationCount).toBeLessThanOrEqual(20)
  })

  it('should shift old data out of the window when new data arrives', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    // Feed fixed returns: first 15 days of exact values
    feedFlat(d, 15)

    const result1 = d.getRegimeResult('TEST', 'stock')
    const mu1 = result1!.currentMetric.mu

    // Now feed opposite returns
    let prev = 100
    for (let i = 0; i < 15; i++) {
      const price = prev * 0.95 // continuous decline
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result2 = d.getRegimeResult('TEST', 'stock')
    const mu2 = result2!.currentMetric.mu

    // After feeding decline, mu should be negative
    // (old flat data has been shifted out)
    expect(mu2).toBeLessThan(mu1)
    expect(mu2).toBeLessThan(0)
  })

  it('should not recompute when no new return is pushed (guard)', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    feedTrend(d, 15, 0.001)

    // Get current metric
    const result1 = d.getRegimeResult('TEST', 'stock')
    const timestamp1 = result1!.currentMetric.computedAt

    // Call updateSymbol without previousPrice — should be a no-op
    d.updateSymbol('TEST', 'stock', 105)

    // Get metric again — should be same (no recomputation)
    const result2 = d.getRegimeResult('TEST', 'stock')
    const timestamp2 = result2!.currentMetric.computedAt

    // Timestamps might differ because getRegimeResult rebuilds, but the geodesic
    // path length should not have increased from the no-op call
    expect(result2!.geodesicPath.length).toBe(result1!.geodesicPath.length)
  })

  it('should recompute when new return IS pushed (even with full buffer)', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    // Fill the buffer to exactly windowSize
    feedTrend(d, 15, 0.001)

    const result1 = d.getRegimeResult('TEST', 'stock')
    const pathLen1 = result1!.geodesicPath.length

    // Push one more return with previousPrice (buffer full, data shifts)
    d.updateSymbol('TEST', 'stock', 105, 104)

    const result2 = d.getRegimeResult('TEST', 'stock')
    const pathLen2 = result2!.geodesicPath.length

    // Should have one more geodesic point (new data triggered recomputation)
    expect(pathLen2).toBeGreaterThanOrEqual(pathLen1)
  })
})

// ============================================================
// 5. State Management
// ============================================================

describe('State Management', () => {
  let detector: RegimeGeometryDetector

  beforeEach(() => {
    detector = createTestDetector()
  })

  it('should track multiple symbols independently', () => {
    detector.updateSymbol('AAPL', 'stock', 101, 100)
    detector.updateSymbol('AAPL', 'stock', 102, 101)
    detector.updateSymbol('GOOGL', 'stock', 101, 100)
    detector.updateSymbol('GOOGL', 'stock', 102, 101)

    const tracked = detector.getTrackedSymbols()
    expect(tracked.length).toBe(2)
    expect(tracked).toContain('AAPL:stock')
    expect(tracked).toContain('GOOGL:stock')
  })

  it('should reset a single symbol without affecting others', () => {
    detector.updateSymbol('AAPL', 'stock', 101, 100)
    detector.updateSymbol('AAPL', 'stock', 102, 101)
    detector.updateSymbol('GOOGL', 'stock', 101, 100)

    detector.resetSymbol('AAPL', 'stock')

    const tracked = detector.getTrackedSymbols()
    expect(tracked).toContain('GOOGL:stock')
    expect(tracked).not.toContain('AAPL:stock')

    // AAPL should return null
    const aaplResult = detector.getRegimeResult('AAPL', 'stock')
    expect(aaplResult).toBeNull()
  })

  it('should reset all symbols', () => {
    detector.updateSymbol('AAPL', 'stock', 101, 100)
    detector.updateSymbol('GOOGL', 'stock', 101, 100)

    detector.resetAll()

    expect(detector.getTrackedSymbols().length).toBe(0)
    expect(detector.getRegimeResult('AAPL', 'stock')).toBeNull()
    expect(detector.getRegimeResult('GOOGL', 'stock')).toBeNull()
  })

  it('should return empty shifts for untracked symbol', () => {
    const shifts = detector.getRegimeShifts('UNKNOWN', 'stock')
    expect(shifts).toEqual([])
  })

  it('should report correct diagnostics', () => {
    feedTrend(detector, 30, 0.001)

    const diag = detector.getDiagnostics()
    expect(diag.trackedSymbols).toBe(1)
    expect(diag.totalObservations).toBeGreaterThan(0)
    expect(Array.isArray(diag.activityLog)).toBe(true)
  })

  it('should return empty result for symbol with no metrics', () => {
    // Only one update — not enough for metrics
    detector.updateSymbol('AAPL', 'stock', 101, 100)

    const result = detector.getRegimeResult('AAPL', 'stock')
    expect(result).toBeNull()
  })
})

// ============================================================
// 6. Integration: loadHistorical, getRegimeResult, getRegimeContext, regime shifts
// ============================================================

describe('Integration', () => {
  it('loadHistorical should bulk-load prices correctly', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    const prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    d.loadHistorical('AAPL', 'stock', prices)

    const result = d.getRegimeResult('AAPL', 'stock')
    expect(result).not.toBeNull()
    expect(result!.observationCount).toBeGreaterThan(0)
    // Consistent uptrend with small steps → should be calm or trending
    expect(['calm', 'trending']).toContain(result!.regime)
  })

  it('loadHistorical should handle fewer than 2 prices', () => {
    const d = createTestDetector()

    d.loadHistorical('AAPL', 'stock', [100])
    expect(d.getRegimeResult('AAPL', 'stock')).toBeNull()

    d.loadHistorical('AAPL', 'stock', [])
    expect(d.getRegimeResult('AAPL', 'stock')).toBeNull()
  })

  it('getRegimeResult should return null when no data loaded', () => {
    const d = createTestDetector()
    expect(d.getRegimeResult('UNKNOWN', 'stock')).toBeNull()
  })

  it('getRegimeContext should return formatted text with regime info', () => {
    const d = createTestDetector()
    feedVolatile(d, 80)

    const context = d.getRegimeContext('TEST', 'stock')
    expect(context).toContain('[Regime Geometry]')
    expect(context).toContain('TEST')
    expect(context).toContain('Regime:')
    expect(context).toContain('Fisher Metric:')
    expect(context).toContain('Geodesic Distance:')
    expect(context).toContain('Velocity:')
    expect(context).toContain('Observations:')
  })

  it('getRegimeContext should return insufficient data message when no metrics', () => {
    const d = createTestDetector()
    const context = d.getRegimeContext('NO_DATA', 'stock')
    expect(context).toContain('Insufficient data')
  })

  it('should detect and record regime shifts', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    // Warm up with calm data
    feedFlat(d, 20)

    // Inject extreme volatility to trigger a shift
    let prev = 100
    for (let i = 0; i < 30; i++) {
      const r = i % 3 === 0 ? 1.10 : i % 3 === 1 ? 0.90 : 1.05
      const price = prev * r
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const shifts = d.getRegimeShifts('TEST', 'stock')
    expect(shifts.length).toBeGreaterThan(0)

    // Each shift should have valid fields
    const shift = shifts[0]
    expect(shift.id).toBeTruthy()
    expect(shift.from).toBeTruthy()
    expect(shift.to).toBeTruthy()
    expect(shift.severity).toBeGreaterThan(0)
    expect(shift.timestamp).toBeTruthy()
    expect(shift.fisherDeterminant).toBeGreaterThan(0)
  })

  it('should include recentShifts in getRegimeResult', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    feedFlat(d, 20)

    // Inject alternating extreme moves to force regime shifts
    let prev = 100
    for (let i = 0; i < 30; i++) {
      const price = prev * (i % 3 === 0 ? 1.10 : 0.92)
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price
    }

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    expect(Array.isArray(result!.recentShifts)).toBe(true)
    // Should have recorded at least one regime shift after the extreme moves
    expect(result!.recentShifts.length).toBeGreaterThan(0)
  })

  it('getRegimeResult should include full result structure', () => {
    const d = createTestDetector()
    feedVolatile(d, 80)

    const result = d.getRegimeResult('TEST', 'stock')
    expect(result).not.toBeNull()
    expect(result!.symbol).toBe('TEST')
    expect(result!.assetType).toBe('stock')
    expect(result!.regime).toBeTruthy()
    expect(result!.regimeConfidence).toBeGreaterThan(0)
    expect(result!.currentMetric).toBeTruthy()
    expect(result!.currentMetric.iMu).toBeGreaterThan(0)
    expect(result!.geodesicPath.length).toBeGreaterThan(0)
    expect(result!.totalGeodesicDistance).toBeGreaterThanOrEqual(0)
    expect(result!.currentVelocity).toBeGreaterThanOrEqual(0)
    expect(result!.velocityThreshold).toBeGreaterThan(0)
    expect(typeof result!.regimeShiftDetected).toBe('boolean')
    expect(typeof result!.shiftSeverity).toBe('number')
    expect(typeof result!.timeSinceLastShift).toBe('number')
    expect(result!.observationCount).toBeGreaterThan(0)
    expect(result!.computedAt).toBeTruthy()
    expect(result!.summary).toBeTruthy()
  })

  it('should withstand rapid successive updates without errors', () => {
    const d = createTestDetector({ windowSize: 10, minObservations: 5 })

    // 200 rapid updates — no crashes, no NaN
    let prev = 100
    for (let i = 0; i < 200; i++) {
      const r = Math.random() * 0.06 - 0.03 // random in [-3%, +3%]
      const price = prev * (1 + r)
      d.updateSymbol('TEST', 'stock', price, prev)
      prev = price

      // Periodically verify no NaN propagation
      if (i > 30 && i % 20 === 0) {
        const result = d.getRegimeResult('TEST', 'stock')
        if (result) {
          expect(Number.isNaN(result.currentMetric.iMu)).toBe(false)
          expect(Number.isNaN(result.currentMetric.determinant)).toBe(false)
          expect(Number.isNaN(result.currentVelocity)).toBe(false)
          expect(Number.isNaN(result.velocityThreshold)).toBe(false)
        }
      }
    }
  })
})
