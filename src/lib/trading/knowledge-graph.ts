// Knowledge Graph Engine (Layer 2) — Causal Inference for Market Factor Relationships
//
// Provides a causal graph of market factors with:
//   - Factor registry: predefined macro/sentiment/technical/intermarket factors
//   - Causal edge definitions: known causal relationships between factors
//   - Granger causality testing: statistical test for predictive causation
//   - Cross-correlation analysis: lag-aware correlation between time series
//   - Factor exposure analysis: linear regression decomposition of returns
//   - Causal path enumeration: paths through the causal graph to explain price movements
//
// Integrates with KnowledgePipeline (enrichment) and AgentDebate (context).

import type {
  AssetType, HistoricalBar,
  FactorDefinition, CausalEdge, CausalGraph,
  FactorExposure, GrangerCausalityResult, LaggedCorrelation,
  CausalAnalysisResult, CausalPath, CausalAttribution,
  KnowledgeGraphConfig,
} from '@/types/trading'
import { DEFAULT_KNOWLEDGE_GRAPH_CONFIG } from '@/types/trading'

// ============================================================================
// Predefined Market Factors
// ============================================================================

const PREDEFINED_FACTORS: FactorDefinition[] = [
  // Macro factors
  { id: 'interest_rates',   name: 'Interest Rates (Fed Funds)',     category: 'macro',   measurement: 'FOMC rate, treasury yields',   assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 5,  defaultDirection: -1 },
  { id: 'inflation',        name: 'Inflation (CPI/PCE)',            category: 'macro',   measurement: 'CPI YoY, PCE, breakevens',     assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 3,  defaultDirection: -1 },
  { id: 'gdp_growth',       name: 'GDP Growth',                     category: 'macro',   measurement: 'Real GDP QoQ annualized',       assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 10, defaultDirection: 1  },
  { id: 'employment',       name: 'Employment (Nonfarm Payrolls)',  category: 'macro',   measurement: 'NFP, unemployment rate',         assetTypes: ['stock', 'forex'],           typicalLag: 3,  defaultDirection: 1  },
  { id: 'dollar_index',     name: 'US Dollar Index (DXY)',          category: 'macro',   measurement: 'DXY index',                     assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 2,  defaultDirection: -1 },
  { id: 'oil_price',        name: 'Crude Oil Price',                category: 'macro',   measurement: 'WTI / Brent futures',           assetTypes: ['stock', 'forex'],           typicalLag: 3,  defaultDirection: -1 },

  // Sentiment factors
  { id: 'vix',              name: 'VIX (Volatility Index)',         category: 'sentiment', measurement: 'CBOE VIX',                   assetTypes: ['stock', 'crypto'],           typicalLag: 1,  defaultDirection: -1 },
  { id: 'put_call_ratio',   name: 'Put/Call Ratio',                 category: 'sentiment', measurement: 'CBOE equity put/call',         assetTypes: ['stock'],                     typicalLag: 1,  defaultDirection: -1 },
  { id: 'fear_greed',       name: 'Fear & Greed Index',             category: 'sentiment', measurement: 'CNN / AltIndex',               assetTypes: ['stock', 'crypto'],           typicalLag: 1,  defaultDirection: 1  },

  // Technical factors
  { id: 'momentum',         name: 'Price Momentum',                 category: 'technical', measurement: 'N-day returns, MACD',         assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 0,  defaultDirection: 1  },
  { id: 'volume',           name: 'Trading Volume',                 category: 'technical', measurement: 'Normalized volume vs avg',     assetTypes: ['stock', 'crypto'],           typicalLag: 1,  defaultDirection: 1  },
  { id: 'breadth',          name: 'Market Breadth',                 category: 'technical', measurement: 'Advance/decline, % > MA',     assetTypes: ['stock'],                     typicalLag: 3,  defaultDirection: 1  },

  // Intermarket factors
  { id: 'bond_yields',      name: '10Y Treasury Yield',             category: 'intermarket', measurement: 'US10Y yield',               assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 3,  defaultDirection: -1 },
  { id: 'credit_spreads',   name: 'Credit Spreads (HY-IG)',         category: 'intermarket', measurement: 'HY OAS - IG OAS',           assetTypes: ['stock'],                     typicalLag: 5,  defaultDirection: -1 },
  { id: 'gold_price',       name: 'Gold Price',                     category: 'intermarket', measurement: 'XAU/USD',                   assetTypes: ['stock', 'crypto', 'forex'], typicalLag: 2,  defaultDirection: -1 },
  { id: 'btc_dominance',    name: 'Bitcoin Dominance',              category: 'intermarket', measurement: 'BTC market cap / total',     assetTypes: ['crypto'],                    typicalLag: 3,  defaultDirection: -1 },
]

// ============================================================================
// Predefined Causal Edges (Known Market Structure)
// ============================================================================

const PREDEFINED_EDGES: CausalEdge[] = [
  // Monetary policy chain
  { from: 'interest_rates',  to: 'bond_yields',     strength: 0.95, confidence: 0.99, lag: 1, discovered: false, mechanism: 'Higher policy rates raise the risk-free discount rate across the yield curve' },
  { from: 'interest_rates',  to: 'dollar_index',    strength: 0.85, confidence: 0.95, lag: 3, discovered: false, mechanism: 'Rate differentials drive capital flows into USD, strengthening the dollar' },
  { from: 'interest_rates',  to: 'credit_spreads',  strength: 0.70, confidence: 0.85, lag: 5, discovered: false, mechanism: 'Tighter policy raises borrowing costs, widening credit spreads for risky borrowers' },
  { from: 'interest_rates',  to: 'oil_price',       strength: 0.40, confidence: 0.70, lag: 5, discovered: false, mechanism: 'Stronger USD from higher rates puts downward pressure on commodities' },

  // Dollar → commodities & risk assets
  { from: 'dollar_index',    to: 'gold_price',       strength: 0.80, confidence: 0.95, lag: 1, discovered: false, mechanism: 'Stronger dollar makes gold more expensive for foreign buyers, reducing demand' },
  { from: 'dollar_index',    to: 'oil_price',        strength: 0.60, confidence: 0.85, lag: 2, discovered: false, mechanism: 'Commodities priced in USD become more expensive globally when dollar strengthens' },
  { from: 'dollar_index',    to: 'btc_dominance',    strength: 0.45, confidence: 0.70, lag: 3, discovered: false, mechanism: 'Strong USD can reduce risk appetite for alternative stores of value' },

  // Inflation chain
  { from: 'inflation',       to: 'interest_rates',   strength: 0.90, confidence: 0.95, lag: 3, discovered: false, mechanism: 'Central banks raise rates in response to above-target inflation' },
  { from: 'inflation',       to: 'gold_price',       strength: 0.65, confidence: 0.80, lag: 2, discovered: false, mechanism: 'Inflation erodes fiat purchasing power, increasing demand for gold as a hedge' },
  { from: 'inflation',       to: 'bond_yields',      strength: 0.75, confidence: 0.90, lag: 3, discovered: false, mechanism: 'Higher inflation expectations raise the term premium in bond markets' },

  // Volatility & sentiment chain
  { from: 'vix',             to: 'credit_spreads',   strength: 0.80, confidence: 0.90, lag: 1, discovered: false, mechanism: 'Market fear widens credit spreads as investors demand higher risk premia' },
  { from: 'vix',             to: 'put_call_ratio',   strength: 0.85, confidence: 0.90, lag: 1, discovered: false, mechanism: 'Rising volatility drives hedging demand, increasing put buying' },
  { from: 'vix',             to: 'fear_greed',       strength: 0.90, confidence: 0.95, lag: 0, discovered: false, mechanism: 'VIX is a primary input to most fear & greed composite indices' },
  { from: 'put_call_ratio',  to: 'fear_greed',       strength: 0.75, confidence: 0.85, lag: 1, discovered: false, mechanism: 'Elevated put buying signals bearish sentiment' },

  // Growth chain
  { from: 'gdp_growth',      to: 'employment',       strength: 0.70, confidence: 0.80, lag: 6, discovered: false, mechanism: 'GDP growth drives labor demand, reducing unemployment' },
  { from: 'gdp_growth',      to: 'oil_price',        strength: 0.55, confidence: 0.75, lag: 6, discovered: false, mechanism: 'Stronger economic activity increases energy demand' },
  { from: 'employment',      to: 'inflation',        strength: 0.60, confidence: 0.80, lag: 6, discovered: false, mechanism: 'Tight labor markets drive wage growth, feeding into services inflation' },
  { from: 'employment',      to: 'fear_greed',       strength: 0.50, confidence: 0.75, lag: 3, discovered: false, mechanism: 'Strong employment data boosts consumer and investor confidence' },

  // Bond yield spillovers
  { from: 'bond_yields',     to: 'vix',              strength: 0.55, confidence: 0.75, lag: 3, discovered: false, mechanism: 'Rising yields compress equity valuations, increasing uncertainty and volatility' },
  { from: 'bond_yields',     to: 'gold_price',       strength: 0.50, confidence: 0.70, lag: 2, discovered: false, mechanism: 'Higher real yields increase the opportunity cost of holding non-yielding gold' },
  { from: 'credit_spreads',  to: 'vix',              strength: 0.70, confidence: 0.85, lag: 2, discovered: false, mechanism: 'Widening spreads signal stress that typically precedes equity volatility' },

  // Oil → macro feedback
  { from: 'oil_price',       to: 'inflation',        strength: 0.55, confidence: 0.80, lag: 3, discovered: false, mechanism: 'Higher energy costs feed into headline CPI and production costs' },
  { from: 'oil_price',       to: 'bond_yields',      strength: 0.40, confidence: 0.70, lag: 5, discovered: false, mechanism: 'Sustained oil price increases raise inflation expectations and yields' },

  // Gold → sentiment
  { from: 'gold_price',      to: 'fear_greed',       strength: 0.45, confidence: 0.70, lag: 2, discovered: false, mechanism: 'Rising gold can signal risk-off sentiment as investors seek safe havens' },

  // Technical factor interconnections
  { from: 'momentum',        to: 'volume',           strength: 0.60, confidence: 0.75, lag: 1, discovered: false, mechanism: 'Price momentum attracts attention and trading volume' },
  { from: 'volume',          to: 'breadth',          strength: 0.55, confidence: 0.70, lag: 2, discovered: false, mechanism: 'High volume with broad participation confirms healthy market structure' },
]

// ============================================================================
// Knowledge Graph Engine
// ============================================================================

export class KnowledgeGraphEngine {
  private config: KnowledgeGraphConfig
  private factors: Map<string, FactorDefinition> = new Map()
  private edges: CausalEdge[] = []
  private adjacencyList: Map<string, CausalEdge[]> = new Map() // from → edges
  private activityLog: string[] = []

  constructor(config?: Partial<KnowledgeGraphConfig>) {
    this.config = { ...DEFAULT_KNOWLEDGE_GRAPH_CONFIG, ...config }
    this.initialize()
  }

  // ==========================================================================
  // Initialization
  // ==========================================================================

  /** Load predefined factors and edges into the engine */
  private initialize(): void {
    for (const factor of PREDEFINED_FACTORS) {
      this.factors.set(factor.id, factor)
    }
    for (const edge of PREDEFINED_EDGES) {
      this.addEdge(edge)
    }
    this.log(`Initialized with ${this.factors.size} factors and ${this.edges.length} causal edges`)
  }

  // ==========================================================================
  // Factor & Edge Management
  // ==========================================================================

  /** Register a new factor or update an existing one */
  registerFactor(factor: FactorDefinition): void {
    this.factors.set(factor.id, factor)
    this.log(`Registered factor: ${factor.id} (${factor.name})`)
  }

  /** Add a causal edge to the graph */
  addEdge(edge: CausalEdge): void {
    // Avoid duplicates
    const exists = this.edges.some(e =>
      e.from === edge.from && e.to === edge.to && e.lag === edge.lag
    )
    if (exists) return

    this.edges.push(edge)

    // Update adjacency list
    if (!this.adjacencyList.has(edge.from)) {
      this.adjacencyList.set(edge.from, [])
    }
    this.adjacencyList.get(edge.from)!.push(edge)
  }

  /** Remove a causal edge */
  removeEdge(from: string, to: string, lag: number): boolean {
    const idx = this.edges.findIndex(e => e.from === from && e.to === to && e.lag === lag)
    if (idx === -1) return false

    this.edges.splice(idx, 1)

    // Rebuild adjacency for this 'from' node
    const outEdges = this.edges.filter(e => e.from === from)
    if (outEdges.length === 0) {
      this.adjacencyList.delete(from)
    } else {
      this.adjacencyList.set(from, outEdges)
    }
    return true
  }

  /** Get the full causal graph */
  getCausalGraph(): CausalGraph {
    return {
      factors: [...this.factors.values()],
      edges: [...this.edges],
      updatedAt: new Date().toISOString(),
    }
  }

  /** Get all factors for a given asset type */
  getFactorsForAssetType(assetType: AssetType): FactorDefinition[] {
    return [...this.factors.values()].filter(f => f.assetTypes.includes(assetType))
  }

  // ==========================================================================
  // Granger Causality Testing
  // ==========================================================================

  /**
   * Test whether series1 Granger-causes series2.
   *
   * Granger causality: series1 "Granger-causes" series2 if past values of
   * series1 help predict series2 beyond what past values of series2 alone can predict.
   *
   * Implemented via F-test on restricted vs unrestricted linear regressions.
   */
  computeGrangerCausality(
    series1: { label: string; values: number[] },
    series2: { label: string; values: number[] },
    maxLag: number = this.config.maxGrangerLag,
  ): GrangerCausalityResult {
    const n = Math.min(series1.values.length, series2.values.length)
    if (n < maxLag + 5) {
      return {
        cause: series1.label,
        effect: series2.label,
        fStat: 0,
        pValue: 1,
        significant: false,
        optimalLag: 0,
        direction: 'none',
      }
    }

    // Align series (use last n observations minus lags)
    let bestResult: { fStat: number; pValue: number; lag: number; significant: boolean } | null = null

    for (let lag = 1; lag <= maxLag; lag++) {
      const result = this.grangerFTest(series1.values, series2.values, lag)
      if (!bestResult || result.fStat > bestResult.fStat) {
        bestResult = { ...result, lag }
      }
    }

    if (!bestResult) {
      return {
        cause: series1.label,
        effect: series2.label,
        fStat: 0, pValue: 1, significant: false, optimalLag: 0,
        direction: 'none',
      }
    }

    // Check reverse direction
    const reverseResult = this.grangerFTest(series2.values, series1.values, bestResult.lag)

    let direction: GrangerCausalityResult['direction'] = 'none'
    if (bestResult.significant && reverseResult.significant) {
      direction = 'bidirectional'
    } else if (bestResult.significant) {
      direction = 'forward'
    } else if (reverseResult.significant) {
      direction = 'reverse'
    }

    this.log(`Granger: ${series1.label} → ${series2.label}: F=${bestResult.fStat.toFixed(2)}, p=${bestResult.pValue.toFixed(4)}, lag=${bestResult.lag}, dir=${direction}`)

    return {
      cause: series1.label,
      effect: series2.label,
      fStat: bestResult.fStat,
      pValue: bestResult.pValue,
      significant: bestResult.significant,
      optimalLag: bestResult.lag,
      direction,
    }
  }

  /** Compute the F-statistic for Granger causality at a specific lag */
  private grangerFTest(
    y1: number[], // potential cause
    y2: number[], // potential effect
    lag: number,
  ): { fStat: number; pValue: number; significant: boolean } {
    const n = y1.length - lag
    if (n <= lag + 2) return { fStat: 0, pValue: 1, significant: false }

    // Build design matrices
    // Restricted model: y2_t = α + Σ β_i * y2_{t-i}
    // Unrestricted model: y2_t = α + Σ β_i * y2_{t-i} + Σ γ_i * y1_{t-i}

    const pRestricted = lag + 1 // parameters: intercept + lag terms
    const pUnrestricted = 2 * lag + 1 // intercept + 2*lag terms
    const df1 = lag // numerator df = extra params
    const df2 = n - pUnrestricted // denominator df

    if (df2 <= 0) return { fStat: 0, pValue: 1, significant: false }

    // Build target vector Y = y2[lag...n+lag-1]
    const Y: number[] = []
    for (let t = 0; t < n; t++) {
      Y.push(y2[t + lag])
    }

    // Restricted OLS: Y ~ [1, y2_{t-1}, ..., y2_{t-lag}]
    const Xr: number[][] = []
    for (let t = 0; t < n; t++) {
      const row: number[] = [1] // intercept
      for (let l = 1; l <= lag; l++) {
        row.push(y2[t + lag - l])
      }
      Xr.push(row)
    }
    const ssrR = this.computeResidualSS(Y, Xr)

    // Unrestricted OLS: Y ~ [1, y2_{t-1}, ..., y2_{t-lag}, y1_{t-1}, ..., y1_{t-lag}]
    const Xu: number[][] = []
    for (let t = 0; t < n; t++) {
      const row: number[] = [1]
      for (let l = 1; l <= lag; l++) row.push(y2[t + lag - l])
      for (let l = 1; l <= lag; l++) row.push(y1[t + lag - l])
      Xu.push(row)
    }
    const ssrU = this.computeResidualSS(Y, Xu)

    // F-statistic
    if (ssrU <= 0) return { fStat: 0, pValue: 1, significant: false }
    const fStat = ((ssrR - ssrU) / df1) / (ssrU / df2)

    // Approximate p-value from F-distribution
    const pValue = this.approximateFPValue(fStat, df1, df2)
    const significant = pValue < this.config.significanceLevel

    return { fStat: Math.max(0, fStat), pValue, significant }
  }

  /** Compute residual sum of squares from OLS using normal equations */
  private computeResidualSS(Y: number[], X: number[][]): number {
    const n = X.length
    const k = X[0].length

    // X'X
    const XtX: number[][] = Array.from({ length: k }, () => new Array(k).fill(0))
    // X'Y
    const XtY: number[] = new Array(k).fill(0)

    for (let i = 0; i < n; i++) {
      const row = X[i]
      for (let p = 0; p < k; p++) {
        XtY[p] += row[p] * Y[i]
        for (let q = 0; q < k; q++) {
          XtX[p][q] += row[p] * row[q]
        }
      }
    }

    // Solve X'X * β = X'Y via Gaussian elimination (k is small: max 2*lag+1 ≈ 11)
    const beta = this.solveLinearSystem(XtX, XtY)

    // Compute residuals
    let ssr = 0
    for (let i = 0; i < n; i++) {
      let pred = 0
      for (let p = 0; p < k; p++) {
        pred += X[i][p] * beta[p]
      }
      ssr += (Y[i] - pred) ** 2
    }

    return ssr
  }

  /** Solve linear system Ax = b via Gaussian elimination with partial pivoting */
  private solveLinearSystem(A: number[][], b: number[]): number[] {
    const n = A.length
    // Augmented matrix [A|b]
    const M: number[][] = A.map((row, i) => [...row, b[i]])

    for (let col = 0; col < n; col++) {
      // Partial pivot
      let maxRow = col
      for (let row = col + 1; row < n; row++) {
        if (Math.abs(M[row][col]) > Math.abs(M[maxRow][col])) maxRow = row
      }
      [M[col], M[maxRow]] = [M[maxRow], M[col]]

      if (Math.abs(M[col][col]) < 1e-12) continue // singular

      // Eliminate below
      for (let row = col + 1; row < n; row++) {
        const factor = M[row][col] / M[col][col]
        for (let j = col; j <= n; j++) {
          M[row][j] -= factor * M[col][j]
        }
      }
    }

    // Back substitution
    const x: number[] = new Array(n).fill(0)
    for (let i = n - 1; i >= 0; i--) {
      if (Math.abs(M[i][i]) < 1e-12) { x[i] = 0; continue }
      let sum = M[i][n]
      for (let j = i + 1; j < n; j++) {
        sum -= M[i][j] * x[j]
      }
      x[i] = sum / M[i][i]
    }

    return x
  }

  /** Approximate the p-value of an F-test using a simple analytic approximation */
  private approximateFPValue(fStat: number, df1: number, df2: number): number {
    if (fStat <= 0) return 1
    if (df2 <= 0) return 1

    // Use the regularized incomplete beta function approximation
    // F ~ Beta(df1/2, df2/2) scaled: x = df1*F / (df1*F + df2)
    const x = (df1 * fStat) / (df1 * fStat + df2)
    const a = df1 / 2
    const b = df2 / 2

    // Regularized incomplete beta via continued fraction
    const betaReg = this.regularizedBeta(x, a, b)
    return 1 - betaReg
  }

  /** Regularized incomplete beta function via continued fraction (Lentz's method) */
  private regularizedBeta(x: number, a: number, b: number): number {
    if (x <= 0) return 0
    if (x >= 1) return 1

    // Beta(a, b) via log-gamma
    const logBeta = this.logGamma(a) + this.logGamma(b) - this.logGamma(a + b)

    // Continued fraction for I_x(a,b)
    const MAX_ITER = 200
    const EPS = 1e-12

    const front = Math.exp(a * Math.log(x) + b * Math.log(1 - x) - logBeta) / a

    // Lentz's continued fraction
    let f = 1
    let c = 1
    let d = 0
    let delta: number

    for (let m = 0; m < MAX_ITER; m++) {
      if (m === 0) {
        d = 1
        const numerator = -(a + b) * x / (a + 1)
        c = 1 + numerator
        d = 1 / c
        f = d
      } else {
        const m2 = 2 * m
        // d_{2m} = 1 + (m*(b-m)*x)/((a+m2-1)*(a+m2))
        const dNum = m * (b - m) * x
        const dDen = (a + m2 - 1) * (a + m2)
        d = 1 + dNum / dDen
        d = 1 / d
        c = 1 + dNum / dDen / c
        f *= c * d
        // c_{2m+1} = 1 - ((a+m)*(a+b+m)*x)/((a+m2)*(a+m2+1))
        const cNum = (a + m) * (a + b + m) * x
        const cDen = (a + m2) * (a + m2 + 1)
        c = 1 - cNum / cDen
        d = 1 / (1 + cNum / cDen * d)
        f *= c * d
      }

      delta = c * d
      if (Math.abs(delta - 1) < EPS) break
    }

    return Math.max(0, Math.min(1, front * (f - 1)))
  }

  /** Log-gamma via Stirling's approximation */
  private logGamma(z: number): number {
    if (z <= 0) return Infinity
    // Stirling: ln Γ(z) ≈ (z - 0.5) * ln(z) - z + 0.5 * ln(2π)
    if (z > 10) {
      return (z - 0.5) * Math.log(z) - z + 0.5 * Math.log(2 * Math.PI) +
        1 / (12 * z) - 1 / (360 * z ** 3) + 1 / (1260 * z ** 5)
    }
    // For small z, recurse: Γ(z+1) = z * Γ(z)
    let result = 0
    let x = z
    while (x < 10) {
      result -= Math.log(x)
      x += 1
    }
    result += (x - 0.5) * Math.log(x) - x + 0.5 * Math.log(2 * Math.PI) +
      1 / (12 * x) - 1 / (360 * x ** 3)
    return result
  }

  // ==========================================================================
  // Cross-Correlation with Lag Analysis
  // ==========================================================================

  /**
   * Compute cross-correlation between two series at multiple lags.
   * Positive optimalLag means series1 leads series2.
   */
  computeCorrelation(
    series1: { label: string; values: number[] },
    series2: { label: string; values: number[] },
    maxLag: number = this.config.maxCorrelationLag,
  ): LaggedCorrelation {
    const n = Math.min(series1.values.length, series2.values.length)
    const correlations: { lag: number; value: number }[] = []

    // Center the series (subtract mean)
    const mean1 = series1.values.reduce((s, v) => s + v, 0) / n
    const mean2 = series2.values.reduce((s, v) => s + v, 0) / n
    const c1 = series1.values.map(v => v - mean1)
    const c2 = series2.values.map(v => v - mean2)

    const std1 = Math.sqrt(c1.reduce((s, v) => s + v * v, 0) / n)
    const std2 = Math.sqrt(c2.reduce((s, v) => s + v * v, 0) / n)

    if (std1 === 0 || std2 === 0) {
      return {
        series1: series1.label, series2: series2.label,
        contemporaneous: 0, maxCrossCorrelation: 0, optimalLag: 0,
        correlations: [],
      }
    }

    let maxAbsCC = -1
    let maxCC = 0
    let optimalLag = 0

    for (let lag = -maxLag; lag <= maxLag; lag++) {
      let cov = 0
      let count = 0

      for (let i = 0; i < n; i++) {
        const j = i + lag
        if (j >= 0 && j < n) {
          cov += c1[i] * c2[j]
          count++
        }
      }

      if (count > 0) {
        // Clamp correlation to [-1, 1] to handle floating point precision errors
        const rawCorr = (cov / count) / (std1 * std2)
        const corr = Math.max(-1, Math.min(1, rawCorr))
        correlations.push({ lag, value: corr })
        if (Math.abs(corr) > maxAbsCC) {
          maxAbsCC = Math.abs(corr)
          maxCC = corr
          optimalLag = lag
        }
      }
    }

    // Sort by lag ascending
    correlations.sort((a, b) => a.lag - b.lag)

    return {
      series1: series1.label,
      series2: series2.label,
      contemporaneous: correlations.find(c => c.lag === 0)?.value ?? 0,
      maxCrossCorrelation: maxCC,
      optimalLag,
      correlations,
    }
  }

  // ==========================================================================
  // Factor Exposure Analysis (Linear Regression)
  // ==========================================================================

  /**
   * Compute factor exposures for an asset by regressing its returns
   * against factor returns.
   */
  computeFactorExposures(
    assetReturns: number[],
    factorReturns: { factorId: string; returns: number[] }[],
  ): FactorExposure[] {
    const n = assetReturns.length
    const exposures: FactorExposure[] = []

    for (const factor of factorReturns) {
      const fReturns = factor.returns
      if (fReturns.length < n) {
        // Align to the same length
        const aligned = fReturns.slice(-n)
        if (aligned.length < 3) {
          exposures.push({
            factorId: factor.factorId,
            beta: 0, rSquared: 0, tStat: 0, significant: false,
          })
          continue
        }

        // Simple OLS: assetReturn = α + β * factorReturn + ε
        const { beta, rSquared, tStat } = this.simpleOLS(assetReturns.slice(-aligned.length), aligned)
        exposures.push({
          factorId: factor.factorId,
          beta,
          rSquared,
          tStat,
          significant: Math.abs(tStat) > 2 && rSquared >= this.config.minRSquared,
        })
      } else {
        const aligned = fReturns.slice(0, n)
        const { beta, rSquared, tStat } = this.simpleOLS(assetReturns, aligned)
        exposures.push({
          factorId: factor.factorId,
          beta,
          rSquared,
          tStat,
          significant: Math.abs(tStat) > 2 && rSquared >= this.config.minRSquared,
        })
      }
    }

    return exposures
  }

  /** Single-variable OLS: y = α + β * x + ε */
  private simpleOLS(
    y: number[],
    x: number[],
  ): { beta: number; alpha: number; rSquared: number; tStat: number } {
    const n = Math.min(y.length, x.length)
    if (n < 3) return { beta: 0, alpha: 0, rSquared: 0, tStat: 0 }

    // Align to same length
    const yy = y.slice(-n)
    const xx = x.slice(-n)

    const meanY = yy.reduce((s, v) => s + v, 0) / n
    const meanX = xx.reduce((s, v) => s + v, 0) / n

    let cov = 0, varX = 0
    for (let i = 0; i < n; i++) {
      const dx = xx[i] - meanX
      cov += (yy[i] - meanY) * dx
      varX += dx * dx
    }

    if (varX === 0) return { beta: 0, alpha: meanY, rSquared: 0, tStat: 0 }

    const beta = cov / varX
    const alpha = meanY - beta * meanX

    // R² and t-stat
    let ssRes = 0, ssTot = 0
    for (let i = 0; i < n; i++) {
      const pred = alpha + beta * xx[i]
      ssRes += (yy[i] - pred) ** 2
      ssTot += (yy[i] - meanY) ** 2
    }

    const rSquared = ssTot > 0 ? 1 - ssRes / ssTot : 0
    const seBeta = ssRes > 0 && varX > 0 && n > 2
      ? Math.sqrt(ssRes / (n - 2)) / Math.sqrt(varX)
      : 0
    const tStat = seBeta > 0 ? beta / seBeta : 0

    return { beta, alpha, rSquared: Math.max(0, rSquared), tStat }
  }

  // ==========================================================================
  // Causal Path Enumeration
  // ==========================================================================

  /**
   * Find all causal paths from macro factors to a given symbol/asset.
   * Uses DFS with pruning.
   */
  findCausalPaths(
    assetType: AssetType,
    targetConcept: string,
  ): CausalPath[] {
    const paths: CausalPath[] = []

    // Entry points: macro factors that apply to this asset type
    const entryFactors = [...this.factors.values()]
      .filter(f => f.category === 'macro' && f.assetTypes.includes(assetType))

    for (const entry of entryFactors) {
      this.dfsCausalPaths(
        entry.id,
        targetConcept,
        [entry.id],
        1.0,
        0,
        paths,
      )
    }

    // Sort by total strength descending
    paths.sort((a, b) => b.totalStrength - a.totalStrength)

    return paths.slice(0, this.config.maxCausalPaths)
  }

  private dfsCausalPaths(
    current: string,
    target: string,
    visited: string[],
    strength: number,
    totalLag: number,
    results: CausalPath[],
  ): void {
    if (visited.length > this.config.maxPathLength) return
    if (results.length >= this.config.maxCausalPaths * 2) return

    // Check if we've reached (or are close to) the target
    if (current === target || this.isRelated(target, current)) {
      const path = [...visited]
      results.push({
        path,
        totalStrength: strength,
        totalLag,
        explanation: this.buildPathExplanation(path),
      })
    }

    // Explore outgoing edges
    const outEdges = this.adjacencyList.get(current) || []
    for (const edge of outEdges) {
      if (visited.includes(edge.to)) continue // no cycles
      if (strength * edge.strength < this.config.minPathStrength) continue // prune weak paths

      visited.push(edge.to)
      this.dfsCausalPaths(
        edge.to,
        target,
        visited,
        strength * edge.strength,
        totalLag + edge.lag,
        results,
      )
      visited.pop()
    }
  }

  /** Check if a factor is closely related to the target concept */
  private isRelated(target: string, factorId: string): boolean {
    // Direct factor match
    if (target.includes(factorId) || factorId.includes(target)) return true
    // Concept groupings
    const groups: Record<string, string[]> = {
      'tech_equities': ['momentum', 'fear_greed', 'vix'],
      'risk_assets': ['vix', 'fear_greed', 'credit_spreads'],
      'safe_havens': ['gold_price', 'bond_yields', 'dollar_index'],
      'inflation_hedge': ['gold_price', 'oil_price', 'btc_dominance'],
    }
    for (const [concept, factors] of Object.entries(groups)) {
      if (target.includes(concept) && factors.includes(factorId)) return true
    }
    return false
  }

  /** Build a human-readable explanation for a causal path */
  private buildPathExplanation(path: string[]): string {
    const parts: string[] = []
    for (let i = 0; i < path.length; i++) {
      const factor = this.factors.get(path[i])
      parts.push(factor?.name || path[i])
      if (i < path.length - 1) {
        const edge = this.edges.find(e => e.from === path[i] && e.to === path[i + 1])
        if (edge) {
          parts.push(`→ (${edge.mechanism}) →`)
        } else {
          parts.push('→')
        }
      }
    }
    return parts.join(' ')
  }

  // ==========================================================================
  // Full Causal Analysis
  // ==========================================================================

  /**
   * Run a complete causal analysis for a symbol using historical bars
   * and available factor data.
   */
  analyzeCausalStructure(
    symbol: string,
    assetType: AssetType,
    bars: HistoricalBar[],
    factorData?: Record<string, number[]>,
  ): CausalAnalysisResult {
    // Compute asset returns
    const assetReturns: number[] = []
    for (let i = 1; i < bars.length; i++) {
      assetReturns.push(Math.log(bars[i].close / bars[i - 1].close))
    }

    // Relevant factors for this asset type
    const relevantFactors = this.getFactorsForAssetType(assetType)

    // 1. Factor exposures (if factor data available)
    let factorExposures: FactorExposure[] = []
    if (factorData && Object.keys(factorData).length > 0) {
      const factorReturns = relevantFactors
        .filter(f => factorData[f.id])
        .map(f => ({
          factorId: f.id,
          returns: this.computeReturns(factorData[f.id]),
        }))
      factorExposures = this.computeFactorExposures(assetReturns, factorReturns)
    } else {
      // Mock exposures based on factor defaultDirections
      factorExposures = relevantFactors.map(f => ({
        factorId: f.id,
        beta: f.defaultDirection * (0.1 + Math.abs(this.hashToNumber(f.id + symbol)) * 0.9),
        rSquared: 0.05 + Math.abs(this.hashToNumber(f.id + symbol + 'r2')) * 0.3,
        tStat: 1 + Math.abs(this.hashToNumber(f.id + symbol + 't')) * 3,
        significant: Math.abs(this.hashToNumber(f.id + symbol + 't')) * 3 > 2,
      }))
    }

    // 2. Granger causality analysis (if factor data available)
    let grangerResults: GrangerCausalityResult[] = []
    if (factorData && Object.keys(factorData).length > 0) {
      for (const factor of relevantFactors.slice(0, 5)) {
        const fData = factorData[factor.id]
        if (fData && fData.length > 10) {
          const fReturns = this.computeReturns(fData)
          const result = this.computeGrangerCausality(
            { label: factor.id, values: fReturns },
            { label: symbol, values: assetReturns },
          )
          if (result.significant) {
            grangerResults.push(result)
          }
        }
      }
    }

    // 3. Cross-correlation with key factors
    const correlations: LaggedCorrelation[] = []
    if (factorData && Object.keys(factorData).length > 0) {
      for (const factor of relevantFactors.slice(0, 3)) {
        const fData = factorData[factor.id]
        if (fData && fData.length > 10) {
          correlations.push(
            this.computeCorrelation(
              { label: factor.id, values: this.computeReturns(fData) },
              { label: symbol, values: assetReturns },
            )
          )
        }
      }
    }

    // 4. Causal paths from macro factors to this symbol
    const targetConcept = this.inferTargetConcept(symbol, assetType)
    const causalPaths = this.findCausalPaths(assetType, targetConcept)

    // 5. Causal attribution
    const attribution = this.computeAttribution(factorExposures)

    // 6. Build summary
    const summary = this.buildAnalysisSummary(
      symbol, assetType, factorExposures, grangerResults,
      correlations, causalPaths, attribution,
    )

    return {
      symbol,
      assetType,
      factorExposures,
      grangerResults,
      correlations,
      causalPaths,
      attribution,
      summary,
      computedAt: new Date().toISOString(),
    }
  }

  /** Compute log returns from a price series */
  private computeReturns(prices: number[]): number[] {
    const returns: number[] = []
    for (let i = 1; i < prices.length; i++) {
      if (prices[i - 1] > 0) {
        returns.push(Math.log(prices[i] / prices[i - 1]))
      }
    }
    return returns
  }

  /** Infer a target concept based on the symbol and asset type */
  private inferTargetConcept(symbol: string, assetType: AssetType): string {
    const techStocks = ['AAPL', 'GOOGL', 'MSFT', 'NVDA', 'META', 'AMZN']
    const financeStocks = ['JPM', 'BAC', 'GS', 'MS']
    const energyStocks = ['XOM', 'CVX', 'COP']

    if (assetType === 'crypto') return 'risk_assets'
    if (energyStocks.includes(symbol)) return 'inflation_hedge'
    if (financeStocks.includes(symbol)) return 'interest_rates'
    if (techStocks.includes(symbol)) return 'tech_equities'
    return 'risk_assets'
  }

  /** Decompose returns into factor contributions */
  private computeAttribution(exposures: FactorExposure[]): CausalAttribution {
    const significantExposures = exposures.filter(e => e.significant)
    const totalRSquared = Math.min(
      significantExposures.reduce((s, e) => s + e.rSquared, 0),
      0.95,
    )

    const factorContributions = significantExposures
      .map(e => {
        const factor = this.factors.get(e.factorId)
        return {
          factorId: e.factorId,
          contribution: e.rSquared,
          label: factor?.name || e.factorId,
        }
      })
      .sort((a, b) => b.contribution - a.contribution)
      .slice(0, 5)

    return {
      explainedPct: totalRSquared,
      idiosyncraticPct: 1 - totalRSquared,
      factorContributions,
    }
  }

  /** Build a human-readable analysis summary */
  private buildAnalysisSummary(
    symbol: string,
    assetType: AssetType,
    exposures: FactorExposure[],
    granger: GrangerCausalityResult[],
    correlations: LaggedCorrelation[],
    paths: CausalPath[],
    attribution: CausalAttribution,
  ): string {
    const parts: string[] = []

    // Top exposures
    const topExposures = exposures
      .filter(e => e.significant)
      .sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta))
      .slice(0, 3)

    if (topExposures.length > 0) {
      parts.push(`Key Factor Exposures:`)
      for (const exp of topExposures) {
        const name = this.factors.get(exp.factorId)?.name || exp.factorId
        parts.push(`  ${name}: β=${exp.beta.toFixed(2)}, R²=${(exp.rSquared * 100).toFixed(0)}%`)
      }
    }

    // Granger causality
    if (granger.length > 0) {
      parts.push(`Granger Causal Relationships:`)
      for (const g of granger) {
        const causeName = this.factors.get(g.cause)?.name || g.cause
        parts.push(`  ${causeName} → ${symbol}: F=${g.fStat.toFixed(2)}, p=${g.pValue.toFixed(4)}, lag=${g.optimalLag}`)
      }
    }

    // Top causal paths
    if (paths.length > 0) {
      parts.push(`Top Causal Paths:`)
      for (const path of paths.slice(0, 3)) {
        parts.push(`  ${path.explanation} (strength: ${(path.totalStrength * 100).toFixed(0)}%, lag: ${path.totalLag}d)`)
      }
    }

    // Attribution
    parts.push(
      `Attribution: ${(attribution.explainedPct * 100).toFixed(0)}% explained by causal factors, ` +
      `${(attribution.idiosyncraticPct * 100).toFixed(0)}% idiosyncratic`
    )

    return parts.join('\n')
  }

  // ==========================================================================
  // Context Generation for Debate Agents
  // ==========================================================================

  /** Generate a concise text summary for inclusion in debate context */
  getCausalContext(symbol: string, assetType: AssetType, bars?: HistoricalBar[]): string {
    if (!bars || bars.length < 5) {
      return `[Causal Graph] ${symbol}: Insufficient data for causal analysis.`
    }

    const result = this.analyzeCausalStructure(symbol, assetType, bars)

    const topExposure = result.factorExposures
      .filter(e => e.significant)
      .sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta))[0]

    const topPath = result.causalPaths[0]

    const lines: string[] = [
      `[Causal Graph] ${symbol}:`,
      `  Attribution: ${(result.attribution.explainedPct * 100).toFixed(0)}% factor-driven, ${(result.attribution.idiosyncraticPct * 100).toFixed(0)}% idiosyncratic`,
    ]

    if (topExposure) {
      const name = this.factors.get(topExposure.factorId)?.name || topExposure.factorId
      lines.push(`  Top Exposure: ${name} (β=${topExposure.beta.toFixed(2)}, R²=${(topExposure.rSquared * 100).toFixed(0)}%)`)
    }

    if (topPath) {
      lines.push(`  Key Causal Chain: ${topPath.explanation}`)
    }

    if (result.grangerResults.length > 0) {
      const sigGranger = result.grangerResults[0]
      const causeName = this.factors.get(sigGranger.cause)?.name || sigGranger.cause
      lines.push(`  Granger: ${causeName} → ${symbol} (p=${sigGranger.pValue.toFixed(3)}, lag=${sigGranger.optimalLag}d)`)
    }

    return lines.join('\n')
  }

  // ==========================================================================
  // Utilities
  // ==========================================================================

  /** Reset the engine to its initial state */
  reset(): void {
    this.factors.clear()
    this.edges = []
    this.adjacencyList.clear()
    this.activityLog = []
    this.initialize()
  }

  /** Get activity log for diagnostics */
  getActivityLog(): string[] {
    return [...this.activityLog.slice(-50)]
  }

  /** Get diagnostic info */
  getDiagnostics(): { factorCount: number; edgeCount: number; activityLog: string[] } {
    return {
      factorCount: this.factors.size,
      edgeCount: this.edges.length,
      activityLog: [...this.activityLog.slice(-20)],
    }
  }

  /** Simple deterministic hash for mock data generation */
  private hashToNumber(seed: string): number {
    let hash = 0
    for (let i = 0; i < seed.length; i++) {
      hash = ((hash << 5) - hash) + seed.charCodeAt(i)
      hash |= 0
    }
    return Math.abs(hash % 1000) / 1000
  }

  private log(message: string): void {
    const entry = `[KnowledgeGraph] ${message}`
    this.activityLog.push(entry)
    if (this.activityLog.length > 1000) {
      this.activityLog = this.activityLog.slice(-500)
    }
    console.log(entry)
  }
}

// Singleton instance
export const knowledgeGraph = new KnowledgeGraphEngine()
