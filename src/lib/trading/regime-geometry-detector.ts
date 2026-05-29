// Regime Geometry Detector (Layer 3) — Information Geometry for Market Regime Detection
//
// Implements Fisher Information Metric computation from sliding return windows,
// geodesic distance tracking via KL divergence, and market regime classification.
//
// Mathematical foundation:
//   - Fisher Information Metric for Gaussian N(μ,σ²): I = [[1/σ², 0], [0, 1/(2σ⁴)]]
//   - KL divergence between Gaussians: D_KL(N₁||N₂) = ½(σ₁²/σ₂² + (μ₂-μ₁)²/σ₂² - 1 + ln(σ₂²/σ₁²))
//   - Symmetrized KL (Jeffreys divergence): J = ½(D_KL(P||Q) + D_KL(Q||P))
//   - Geodesic distance approximated via cumulative Jeffreys divergences
//   - Regime shift detection: velocity > rolling_mean + shiftThresholdSigma * rolling_std
//
// Regime classifications:
//   - calm:      low Fisher determinant, low velocity
//   - trending:  moderate Fisher, moderate velocity (consistent direction)
//   - volatile:  high Fisher determinant, moderate velocity
//   - transitioning: increasing velocity, changing Fisher components
//   - crisis:    extreme velocity (geodesic jump), extreme Fisher values

import type {
  AssetType, MarketRegime, FisherMetric, GeodesicPathPoint,
  RegimeGeometryResult, RegimeGeometryConfig, RegimeShiftEvent,
} from '@/types/trading'
import { DEFAULT_REGIME_GEOMETRY_CONFIG } from '@/types/trading'

// ========== Internal State ==========

interface SymbolState {
  returns: number[]           // circular buffer of log returns
  metrics: FisherMetric[]     // Fisher metric history
  geodesicPath: GeodesicPathPoint[]  // geodesic trajectory
  smoothedVelocity: number    // EMA-smoothed geodesic velocity
  cumulativeDistance: number  // total geodesic distance traversed
  lastShiftTime: number       // timestamp of last regime shift
  lastRegime: MarketRegime    // previous regime classification
  regimeShifts: RegimeShiftEvent[]   // historical regime shifts
}

// ========== Regime Geometry Detector ==========

export class RegimeGeometryDetector {
  private config: RegimeGeometryConfig
  private states: Map<string, SymbolState> = new Map()
  private activityLog: string[] = []

  constructor(config?: Partial<RegimeGeometryConfig>) {
    this.config = { ...DEFAULT_REGIME_GEOMETRY_CONFIG, ...config }
  }

  // ========== Core: Feed a new return observation ==========

  /**
   * Feed a new price observation for a symbol.
   * Automatically computes the log return from the previous price.
   * Call this for each new price bar.
   * 
   * @param symbol - Trading symbol
   * @param assetType - Asset type
   * @param price - Current price close
   * @param previousPrice - Previous price close (optional; if omitted, uses last known)
   */
  updateSymbol(symbol: string, assetType: AssetType, price: number, previousPrice?: number): void {
    const key = this.symbolKey(symbol, assetType)
    const state = this.getOrCreateState(key)

    // Compute log return
    let newReturnPushed = false
    if (previousPrice !== undefined && previousPrice > 0 && price > 0) {
      const logReturn = Math.log(price / previousPrice)
      state.returns.push(logReturn)
      newReturnPushed = true
    } else {
      // If previousPrice omitted, track price but warn — can't compute return.
      // Subsequent calls with previousPrice will pick up correctly.
      if (state.returns.length === 0) {
        this.log(`No previousPrice for ${key} — cannot compute return; price not tracked`)
      }
    }

    // Trim returns buffer to window size
    if (state.returns.length > this.config.windowSize) {
      state.returns = state.returns.slice(-this.config.windowSize)
    }

    // Only compute metrics when we have enough data
    if (state.returns.length < this.config.minObservations) return

    // Skip recomputation if no new return data was pushed this call.
    // Track whether a new return actually landed (not just the buffer length,
    // since when the buffer is full, new data shifts old data out with no length change).
    if (!newReturnPushed) return

    // Compute Fisher metric from the current window
    const metric = this.computeFisherMetric(
      state.returns.slice(-this.config.windowSize),
      key,
    )
    state.metrics.push(metric)

    // Trim metric history
    if (state.metrics.length > this.config.historyLength) {
      state.metrics = state.metrics.slice(-this.config.historyLength)
    }      // Compute KL divergence from previous metric
      if (state.metrics.length >= 2) {
        const prevMetric = state.metrics[state.metrics.length - 2]
        const rawKL = this.symmetrizedKLDivergence(prevMetric, metric)

        // Smooth KL using a rolling window
      const recentKLs = state.geodesicPath.slice(-this.config.klSmoothingWindow)
        .map(p => p.klDistance)
      recentKLs.push(rawKL)
      const smoothedKL = recentKLs.reduce((s, k) => s + k, 0) / recentKLs.length

      // Update cumulative distance
      state.cumulativeDistance += rawKL

      // Update smoothed velocity (EMA)
      if (state.smoothedVelocity === 0 && state.geodesicPath.length === 0) {
        state.smoothedVelocity = smoothedKL
      } else {
        state.smoothedVelocity =
          this.config.velocitySmoothing * smoothedKL +
          (1 - this.config.velocitySmoothing) * state.smoothedVelocity
      }

      // Classify regime from current state
      const regime = this.classifyRegime(state, metric)

      // Check for regime shift
      const regimeShiftDetected = regime !== state.lastRegime && state.geodesicPath.length > 0
      if (regimeShiftDetected) {
        state.lastShiftTime = Date.now()
        const shiftEvent: RegimeShiftEvent = {
          id: `shift-${symbol}-${state.regimeShifts.length + 1}`,
          from: state.lastRegime,
          to: regime,
          severity: rawKL,
          timestamp: new Date().toISOString(),
          geodesicDistance: state.cumulativeDistance,
          fisherDeterminant: metric.determinant,
        }
        state.regimeShifts.push(shiftEvent)
        if (state.regimeShifts.length > 100) {
          state.regimeShifts = state.regimeShifts.slice(-100)
        }
        this.log(`Regime shift on ${symbol}: ${state.lastRegime} → ${regime} (severity: ${rawKL.toFixed(4)})`)
      }

      // Build geodesic path point
      const geoPoint: GeodesicPathPoint = {
        index: state.geodesicPath.length,
        metric,
        klDistance: rawKL,
        cumulativeDistance: state.cumulativeDistance,
        velocity: state.smoothedVelocity,
        regime,
        timestamp: new Date().toISOString(),
      }

      state.geodesicPath.push(geoPoint)
      if (state.geodesicPath.length > this.config.historyLength) {
        state.geodesicPath = state.geodesicPath.slice(-this.config.historyLength)
      }

      state.lastRegime = regime
    }
  }

  // ========== Query: Get regime analysis result ==========

  /**
   * Get the full regime geometry analysis for a symbol.
   * Returns null if not enough observations have been collected.
   */
  getRegimeResult(symbol: string, assetType: AssetType): RegimeGeometryResult | null {
    const key = this.symbolKey(symbol, assetType)
    const state = this.states.get(key)
    if (!state || state.metrics.length === 0) return null

    const currentMetric = state.metrics[state.metrics.length - 1]
    const regime = this.classifyRegime(state, currentMetric)

    // Compute regime confidence based on how far velocity exceeds thresholds
    const regimeConfidence = this.computeRegimeConfidence(state)

    // Compute dynamic velocity threshold from recent geodesic path
    const velocityThreshold = this.computeVelocityThreshold(state)

    // Detect regime shift severity
    const shiftSeverity = this.computeShiftSeverity(state)

    return {
      symbol,
      assetType,
      regime,
      regimeConfidence,
      currentMetric,
      geodesicPath: state.geodesicPath.slice(-50), // last 50 points
      totalGeodesicDistance: state.cumulativeDistance,
      currentVelocity: state.smoothedVelocity,
      velocityThreshold,
      regimeShiftDetected: state.lastShiftTime > Date.now() - 3600000, // within last hour
      shiftSeverity,
      timeSinceLastShift: Date.now() - state.lastShiftTime,
      recentShifts: state.regimeShifts.slice(-10),
      summary: this.buildSummary(symbol, regime, currentMetric, state),
      observationCount: state.returns.length,
      computedAt: new Date().toISOString(),
    }
  }

  /**
   * Get a concise text summary for inclusion in debate context.
   */
  getRegimeContext(symbol: string, assetType: AssetType): string {
    const result = this.getRegimeResult(symbol, assetType)
    if (!result) return `[Regime Geometry] ${symbol}: Insufficient data for regime detection.`

    return `[Regime Geometry] ${symbol}:
  Regime: ${result.regime.toUpperCase()} (confidence: ${(result.regimeConfidence * 100).toFixed(0)}%)
  Fisher Metric: μ=${(result.currentMetric.mu * 10000).toFixed(1)}bps, σ²=${(result.currentMetric.sigma2 * 1e6).toFixed(1)}e-6
  Geodesic Distance: ${result.totalGeodesicDistance.toFixed(4)}
  Velocity: ${(result.currentVelocity * 1000).toFixed(2)}e-3 | Threshold: ${(result.velocityThreshold * 1000).toFixed(2)}e-3
  Shift Detected: ${result.regimeShiftDetected ? 'YES (severity: ' + (result.shiftSeverity * 100).toFixed(0) + '%)' : 'No'}
  Observations: ${result.observationCount}`
  }

  // ========== Batch: Process a bar array (e.g., from HistoricalBar[]) ==========

  /**
   * Bulk-load historical data to initialize the detector.
   */
  loadHistorical(symbol: string, assetType: AssetType, prices: number[]): void {
    if (prices.length < 2) return

    for (let i = 1; i < prices.length; i++) {
      this.updateSymbol(symbol, assetType, prices[i], prices[i - 1])
    }
  }

  // ========== Fisher Information Metric Computation ==========

  /**
   * Compute the Fisher Information Metric for a univariate Gaussian N(μ, σ²).
   * 
   * Closed form:
   *   I(μ, σ²) = [[1/σ²,    0    ],
   *               [  0,   1/(2σ⁴)]]
   *
   * The determinant is 1/(2σ⁶), which serves as a "volume element"
   * — large σ² means low information (wide distribution = flat geometry).
   */
  private computeFisherMetric(returns: number[], key: string): FisherMetric {
    const n = returns.length
    if (n === 0) {
      return {
        iMu: 0, iSigma2: 0, determinant: 0,
        mu: 0, sigma2: 0, windowSize: 0,
        computedAt: new Date().toISOString(),
      }
    }

    // Estimate parameters
    const mu = returns.reduce((s, r) => s + r, 0) / n
    const sigma2 = n > 1
      ? returns.reduce((s, r) => s + (r - mu) ** 2, 0) / (n - 1) // unbiased
      : 0

    // Clamp sigma2 to avoid division by zero
    const safeSigma2 = Math.max(sigma2, 1e-12)

    // Fisher information components
    const iMu = 1 / safeSigma2
    const iSigma2 = 1 / (2 * safeSigma2 * safeSigma2)
    const determinant = iMu * iSigma2 // = 1/(2σ⁶)

    return {
      iMu,
      iSigma2,
      determinant,
      mu,
      sigma2: safeSigma2,
      windowSize: n,
      computedAt: new Date().toISOString(),
    }
  }

  // ========== KL Divergence (Local Geodesic Distance) ==========

  /**
   * KL divergence D_KL(P||Q) for two univariate Gaussians.
   * 
   * D_KL(N(μ₁,σ₁²) || N(μ₂,σ₂²)) =
   *   ½( σ₁²/σ₂² + (μ₂-μ₁)²/σ₂² - 1 + ln(σ₂²/σ₁²) )
   */
  private klDivergence(a: FisherMetric, b: FisherMetric): number {
    const { mu: mu1, sigma2: s1 } = a
    const { mu: mu2, sigma2: s2 } = b

    if (s1 <= 0 || s2 <= 0) return 0

    const meanDiffSq = (mu2 - mu1) ** 2
    const varianceRatio = s1 / s2
    const logRatio = Math.log(s2 / s1)

    return 0.5 * (varianceRatio + meanDiffSq / s2 - 1 + logRatio)
  }

  /**
   * Symmetrized KL (Jeffreys divergence):
   *   J(P||Q) = ½(D_KL(P||Q) + D_KL(Q||P))
   *
   * This is a true metric on the statistical manifold and provides
   * a better local approximation of the Fisher-Rao distance.
   */
  private symmetrizedKLDivergence(a: FisherMetric, b: FisherMetric): number {
    return 0.5 * (this.klDivergence(a, b) + this.klDivergence(b, a))
  }

  // ========== Regime Classification ==========

  /**
   * Classify the current market regime based on Fisher metric properties
   * and geodesic velocity.
   *
   * Requires a minimum number of geodesic path points before classifying
   * to avoid false positives during warmup.
   *
   * Decision tree:
   *   1. If insufficient data → CALM (warmup)
   *   2. If velocity > 5x threshold → CRISIS (geodesic jump)
   *   3. If Fisher determinant > 90th percentile AND velocity > threshold → CRISIS
   *   4. If velocity > 2x threshold → TRANSITIONING (rapid change)
   *   5. If velocity > threshold → check Fisher properties:
   *      - High determinant → VOLATILE (wide distribution)
   *      - Moderate determinant → TRANSITIONING
   *   6. If Fisher determinant > median:
   *      - Consistent mu direction → TRENDING
   *      - Otherwise → VOLATILE
   *   7. Otherwise → CALM (low Fisher, low velocity)
   */
  private classifyRegime(state: SymbolState, currentMetric: FisherMetric): MarketRegime {
    // Warmup gate: need enough geodesic history for stable classification
    if (state.geodesicPath.length < this.config.minObservations) {
      return 'calm'
    }

    const velocity = state.smoothedVelocity
    const threshold = this.computeVelocityThreshold(state)
    const logDet = Math.log(currentMetric.determinant)

    // Precompute percentiles once (avoids redundant O(n log n) sorts)
    const log90p = this.getLogDeterminantPercentile(state, 0.90)
    const log50p = this.getLogDeterminantPercentile(state, 0.50)

    // CRISIS: extreme velocity (geodesic "jump")
    if (velocity > threshold * 5) return 'crisis'

    // CRISIS: very high Fisher information + above threshold
    if (logDet > log90p && velocity > threshold) {
      return 'crisis'
    }

    // TRANSITIONING: rapid change
    if (velocity > threshold * 2) return 'transitioning'

    // Above threshold: check Fisher properties
    if (velocity > threshold) {
      // Compare against 2× median determinant in log space: log(2·d) = log(2) + log(d)
      if (logDet > log50p + Math.LN2) return 'volatile'
      return 'transitioning'
    }

    // High Fisher + low velocity → wide distribution that isn't changing
    // Still volatile — the distribution itself is wide, implying uncertainty
    if (logDet > log90p) return 'volatile'

    // Moderate Fisher + low velocity → check for trending
    if (logDet > log50p) {
      // Check if mu direction is consistent → trending, else volatile
      const recentReturns = state.returns.slice(-10)
      const signChanges = recentReturns.reduce((count, r, i) => {
        if (i === 0) return count
        return count + (Math.sign(r) !== Math.sign(recentReturns[i - 1]) ? 1 : 0)
      }, 0)
      if (signChanges < recentReturns.length * 0.3) return 'trending'
      return 'volatile'
    }

    return 'calm'
  }

  // ========== Threshold & Confidence Computation ==========

  /**
   * Compute the dynamic velocity threshold as:
   *   threshold = mean_velocity + shiftThresholdSigma * std_velocity
   *
   * Calculated from the recent geodesic path (last 50 points or all if fewer).
   */
  private computeVelocityThreshold(state: SymbolState): number {
    const velocities = state.geodesicPath.map(p => p.velocity)
    if (velocities.length < 5) return 0.01 // initial threshold

    const mean = velocities.reduce((s, v) => s + v, 0) / velocities.length
    const variance = velocities.reduce((s, v) => s + (v - mean) ** 2, 0) / velocities.length
    const std = Math.sqrt(variance)

    return mean + this.config.shiftThresholdSigma * std
  }

  /**
   * Compute confidence in the current regime classification.
   * Based on how far the current velocity exceeds (or falls below) the threshold.
   */
  private computeRegimeConfidence(state: SymbolState): number {
    const velocity = state.smoothedVelocity
    const threshold = this.computeVelocityThreshold(state)

    if (threshold <= 0) return 0.5

    // Logistic sigmoid: confidence grows with velocity/threshold ratio
    const ratio = velocity / threshold
    const confidence = 1 / (1 + Math.exp(-2 * (ratio - 1)))

    return Math.min(0.99, Math.max(0.01, confidence))
  }

  /**
   * Compute regime shift severity (0-1).
   * Based on the magnitude of the last KL divergence relative to recent history.
   */
  private computeShiftSeverity(state: SymbolState): number {
    const recentKLs = state.geodesicPath.slice(-20).map(p => p.klDistance)
    if (recentKLs.length < 5) return 0

    const meanKL = recentKLs.reduce((s, k) => s + k, 0) / recentKLs.length
    const maxKL = Math.max(...recentKLs)

    if (maxKL <= meanKL) return 0

    // Severity = how many multiples of mean the max is
    const severity = Math.min((maxKL - meanKL) / (meanKL || 0.001), 1)
    return Math.max(0, severity)
  }

  // ========== Helpers ==========

  /**
   * Get the nth percentile of log-transformed Fisher determinant values.
   * Using log-space because determinant ∝ 1/σ⁶ varies over many orders of magnitude.
   */
  private getLogDeterminantPercentile(state: SymbolState, percentile: number): number {
    const logs = state.metrics
      .map(m => Math.log(m.determinant))
      .sort((a, b) => a - b)
    if (logs.length === 0) return 0
    const index = Math.floor(logs.length * percentile)
    return logs[Math.min(index, logs.length - 1)]
  }

  /**
   * Build a human-readable summary of the current regime state.
   */
  private buildSummary(
    symbol: string,
    regime: MarketRegime,
    metric: FisherMetric,
    state: SymbolState,
  ): string {
    const volPct = (Math.sqrt(metric.sigma2) * Math.sqrt(252) * 100).toFixed(1) // annualized vol %
    const meanBps = (metric.mu * 10000).toFixed(1) // bps

    const regimeDescriptions: Record<MarketRegime, string> = {
      calm: `Calm: low volatility (${volPct}% ann.) with stable distribution parameters. Fisher determinant = ${metric.determinant.toExponential(2)}. Mean return = ${meanBps}bps.`,
      trending: `Trending: moderate volatility (${volPct}% ann.) with consistent directional bias. Fisher metric shows structured geometry. Geodesic distance: ${state.cumulativeDistance.toFixed(4)}.`,
      volatile: `Volatile: elevated distribution width (${volPct}% ann.). Fisher determinant = ${metric.determinant.toExponential(2)}. Wide parameter uncertainty.`,
      transitioning: `Transitioning: distribution parameters shifting. Geodesic velocity = ${(state.smoothedVelocity * 1000).toFixed(2)}e-3. Possible regime change in progress.`,
      crisis: `CRISIS: extreme parameter displacement detected. Geodesic velocity = ${(state.smoothedVelocity * 1000).toFixed(2)}e-3. Fisher determinant spike. Distribution structure collapsing — tail risk elevated.`,
    }

    return regimeDescriptions[regime]
  }

  private getOrCreateState(key: string): SymbolState {
    if (!this.states.has(key)) {
      this.states.set(key, {
        returns: [],
        metrics: [],
        geodesicPath: [],
        smoothedVelocity: 0,
        cumulativeDistance: 0,
        lastShiftTime: 0,
        lastRegime: 'calm',
        regimeShifts: [],
      })
    }
    return this.states.get(key)!
  }

  private symbolKey(symbol: string, assetType: AssetType): string {
    return `${symbol}:${assetType}`
  }

  private log(message: string): void {
    const entry = `[RegimeGeometry] ${message}`
    this.activityLog.push(entry)
    if (this.activityLog.length > 1000) {
      this.activityLog = this.activityLog.slice(-500)
    }
    console.log(entry)
  }

  // ========== State Management ==========

  /** Reset tracking for a symbol */
  resetSymbol(symbol: string, assetType: AssetType): void {
    this.states.delete(this.symbolKey(symbol, assetType))
  }

  /** Clear all tracking state */
  resetAll(): void {
    this.states.clear()
    this.activityLog = []
  }

  /** Get all tracked symbols */
  getTrackedSymbols(): string[] {
    return [...this.states.keys()]
  }

  /** Get regime shift history for a symbol */
  getRegimeShifts(symbol: string, assetType: AssetType): RegimeShiftEvent[] {
    const key = this.symbolKey(symbol, assetType)
    const state = this.states.get(key)
    if (!state) return []
    return [...state.regimeShifts]
  }

  /** Get diagnostic info */
  getDiagnostics(): { trackedSymbols: number; totalObservations: number; activityLog: string[] } {
    let totalObs = 0
    for (const state of this.states.values()) {
      totalObs += state.returns.length
    }
    return {
      trackedSymbols: this.states.size,
      totalObservations: totalObs,
      activityLog: [...this.activityLog.slice(-20)],
    }
  }
}

// Singleton instance
export const regimeGeometryDetector = new RegimeGeometryDetector()
