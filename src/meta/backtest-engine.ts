/**
 * Layer 5 — Backtesting Engine
 *
 * Replays historical market data through the trading strategy to evaluate
 * performance before live deployment. Supports:
 * - Single-run backtests with configurable parameters
 * - Walk-forward optimization (train on in-sample, validate on out-of-sample)
 * - Sliding window analysis
 * - Commission and slippage modeling
 *
 * Note: This is a simplified vectorized backtest engine. In production,
 * you'd connect to a real market data provider and the full debate graph.
 * This engine works with pre-computed trade outcomes from the PerformanceTracker
 * to enable rapid parameter evaluation during GA evolution.
 */

import { v4 as uuid } from 'uuid'
import {
  BacktestConfig,
  BacktestTrade,
  BacktestResult,
  WalkForwardResult,
  HistoricalMarketPoint,
  TradeOutcome,
} from './types'
import { PerformanceTracker } from './performance-tracker'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_BACKTEST_CONFIG: BacktestConfig = {
  symbols: [],
  startDate: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
  endDate: new Date().toISOString(),
  timeframe: '1d',
  initialEquity: 100_000,
  commissionBps: 1,    // 0.01%
  slippageBps: 2,       // 0.02%
  walkForward: false,
  walkForwardWindowDays: 60,
  outOfSampleDays: 20,
}

// ═══════════════════════════════════════════════════════════════
// Backtest Engine
// ═══════════════════════════════════════════════════════════════

export class BacktestEngine {
  private config: BacktestConfig
  private dataCache: Map<string, HistoricalMarketPoint[]> = new Map()

  constructor(config: Partial<BacktestConfig> = {}) {
    this.config = { ...DEFAULT_BACKTEST_CONFIG, ...config }
  }

  // ═══════════════════════════════════════════════════════════
  // Data Loading
  // ═══════════════════════════════════════════════════════════════

  /**
   * Load historical market data for a symbol.
   * In production, this would fetch from a data provider API.
   * For now, generates synthetic data for testing.
   */
  loadHistoricalData(symbol: string): HistoricalMarketPoint[] {
    // Check cache
    if (this.dataCache.has(symbol)) {
      return this.dataCache.get(symbol)!
    }

    const data = this.generateSyntheticData(symbol)
    this.dataCache.set(symbol, data)
    return data
  }

  /**
   * Generate synthetic price data with realistic market characteristics.
   * Geometric Brownian Motion with mean reversion overlay.
   */
  private generateSyntheticData(symbol: string): HistoricalMarketPoint[] {
    const points: HistoricalMarketPoint[] = []
    const startDate = new Date(this.config.startDate)
    const endDate = new Date(this.config.endDate)
    const intervalMs = this.getIntervalMs()

    let price = 100 + Math.random() * 50
    let timestamp = startDate.getTime()
    const volatility = 0.015 + Math.random() * 0.01
    const drift = 0.0001 + Math.random() * 0.0001

    while (timestamp <= endDate.getTime()) {
      // Geometric Brownian Motion
      const gaussian = this.randomGaussian()
      const logReturn = drift + volatility * gaussian
      price = price * Math.exp(logReturn)

      // Add realistic OHLC structure
      const open = price
      const intradayVol = volatility * 0.3
      const close = open * Math.exp(intradayVol * this.randomGaussian())
      const high = Math.max(open, close) * (1 + Math.abs(this.randomGaussian()) * intradayVol * 0.5)
      const low = Math.min(open, close) * (1 - Math.abs(this.randomGaussian()) * intradayVol * 0.5)
      const volume = Math.floor(100_000 + Math.random() * 900_000)

      // Compute simple indicators
      const rsi14 = 30 + Math.random() * 40 // 30-70 range
      const sma50 = price * (0.95 + Math.random() * 0.1)

      points.push({
        symbol,
        timestamp: new Date(timestamp).toISOString(),
        open,
        high,
        low,
        close,
        volume,
        rsi14,
        sma50,
        sma200: price * (0.9 + Math.random() * 0.2),
        vwap: (open + high + low + close) / 4,
      })

      timestamp += intervalMs
    }

    return points
  }

  // ═══════════════════════════════════════════════════════════
  // Single-Run Backtest
  // ═══════════════════════════════════════════════════════════════

  /**
   * Run a backtest using the PerformanceTracker's trade records.
   *
   * This evaluates strategy performance by re-computing metrics from
   * existing trade outcomes (for rapid GA evaluation) or by simulating
   * trades from synthetic data.
   */
  async run(tracker?: PerformanceTracker): Promise<BacktestResult> {
    const startTime = Date.now()

    // If we have a tracker with real trade data, use it
    if (tracker) {
      return this.runFromTracker(tracker, startTime)
    }

    // Otherwise, simulate from synthetic data
    return this.runSynthetic(startTime)
  }

  /**
   * Run backtest from PerformanceTracker trade records.
   * This is the fast path for GA fitness evaluation.
   */
  private runFromTracker(tracker: PerformanceTracker, startTime: number): BacktestResult {
    const trades = tracker.getTradeRecords()
      .filter(t => t.outcome !== 'PENDING')
      .filter(t => this.isInDateRange(t.entryTimestamp))

    // Apply commission and slippage adjustments
    const adjustedTrades: BacktestTrade[] = trades.map(t => ({
      symbol: t.symbol,
      entryTimestamp: t.entryTimestamp,
      exitTimestamp: t.exitTimestamp,
      direction: t.direction,
      entryPrice: t.entryPrice,
      exitPrice: t.exitPrice,
      quantity: 100,
      pnl: t.pnl - this.calculateCommission(t.entryPrice) - this.calculateSlippage(t.entryPrice),
      pnlPct: t.pnlPct - this.config.commissionBps / 10000 - this.config.slippageBps / 10000,
      commission: this.calculateCommission(t.entryPrice),
      slippage: this.calculateSlippage(t.entryPrice),
      debateSessionId: t.debateSessionId,
      outcome: t.outcome,
    }))

    return this.computeResult(adjustedTrades, startTime)
  }

  /**
   * Run backtest from synthetic market data.
   * Simulates a simple strategy for demonstration.
   */
  private runSynthetic(startTime: number): BacktestResult {
    const trades: BacktestTrade[] = []

    for (const symbol of this.config.symbols) {
      const data = this.loadHistoricalData(symbol)
      if (data.length < 2) continue

      let position: 'LONG' | 'SHORT' | null = null
      let entryPrice = 0
      let entryTime = ''

      for (let i = 1; i < data.length; i++) {
        const prev = data[i - 1]
        const curr = data[i]

        // Simple momentum strategy: buy when RSI < 30, sell when RSI > 70
        if (!position && prev.rsi14 !== undefined && prev.rsi14 < 30) {
          position = 'LONG'
          entryPrice = curr.close
          entryTime = curr.timestamp
        } else if (position === 'LONG' && (prev.rsi14 !== undefined && prev.rsi14 > 70)) {
          const exitPrice = curr.close
          const pnl = (exitPrice - entryPrice) * 100
          const pnlPct = (exitPrice - entryPrice) / entryPrice * 100
          const outcome: TradeOutcome = pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN'

          trades.push({
            symbol,
            entryTimestamp: entryTime,
            exitTimestamp: curr.timestamp,
            direction: position,
            entryPrice,
            exitPrice,
            quantity: 100,
            pnl: pnl - this.calculateCommission(entryPrice) - this.calculateSlippage(entryPrice),
            pnlPct,
            commission: this.calculateCommission(entryPrice),
            slippage: this.calculateSlippage(entryPrice),
            debateSessionId: uuid(),
            outcome,
          })

          position = null
        }
      }
    }

    return this.computeResult(trades, startTime)
  }

  /**
   * Compute full backtest metrics from a list of trades.
   */
  private computeResult(trades: BacktestTrade[], startTime: number): BacktestResult {
    const wins = trades.filter(t => t.outcome === 'WIN')
    const losses = trades.filter(t => t.outcome === 'LOSS')

    const winRate = trades.length > 0 ? wins.length / trades.length : 0

    // P&L
    const cumulativePnl = trades.reduce((s, t) => s + t.pnl, 0)
    const avgTradePnl = trades.length > 0 ? cumulativePnl / trades.length : 0

    const grossProfit = wins.reduce((s, t) => s + t.pnl, 0)
    const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0))
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : Infinity

    // Return %
    const totalReturnPct = (cumulativePnl / this.config.initialEquity) * 100

    // Sharpe ratio
    const pnlPcts = trades.map(t => t.pnlPct)
    const sharpeRatio = this.computeSharpe(pnlPcts)

    // Sortino ratio (only downside deviation)
    const sortinoRatio = this.computeSortino(pnlPcts)

    // Drawdown
    const maxDrawdownPct = this.computeMaxDrawdownPct(trades)

    // Average win/loss
    const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0
    const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + t.pnl, 0) / losses.length) : 0
    const avgWinLossRatio = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 0

    // Consecutive win/loss streaks
    let currentStreak = 0
    let maxConsecutiveWins = 0
    let maxConsecutiveLosses = 0

    for (const trade of trades) {
      if (trade.outcome === 'WIN') {
        currentStreak = currentStreak > 0 ? currentStreak + 1 : 1
        maxConsecutiveWins = Math.max(maxConsecutiveWins, currentStreak)
      } else {
        currentStreak = currentStreak < 0 ? currentStreak - 1 : -1
        maxConsecutiveLosses = Math.max(maxConsecutiveLosses, Math.abs(currentStreak))
      }
    }

    // Calmar ratio
    const calmarRatio = maxDrawdownPct > 0 ? totalReturnPct / maxDrawdownPct : 0

    // Equity curve
    const equityCurve = this.buildEquityCurve(trades)

    // Symbol breakdown
    const symbolMap = new Map<string, { trades: BacktestTrade[] }>()
    for (const trade of trades) {
      if (!symbolMap.has(trade.symbol)) {
        symbolMap.set(trade.symbol, { trades: [] })
      }
      symbolMap.get(trade.symbol)!.trades.push(trade)
    }

    const symbolBreakdown = Array.from(symbolMap.entries()).map(([symbol, group]) => {
      const symWins = group.trades.filter(t => t.outcome === 'WIN')
      return {
        symbol,
        trades: group.trades.length,
        pnl: group.trades.reduce((s, t) => s + t.pnl, 0),
        winRate: group.trades.length > 0 ? symWins.length / group.trades.length : 0,
      }
    })

    return {
      config: this.config,
      totalTrades: trades.length,
      winRate,
      cumulativePnl,
      finalEquity: this.config.initialEquity + cumulativePnl,
      totalReturnPct,
      sharpeRatio,
      sortinoRatio,
      maxDrawdownPct,
      profitFactor: profitFactor === Infinity ? 999 : profitFactor,
      avgTradePnl,
      avgWinLossRatio: avgWinLossRatio === Infinity ? 999 : avgWinLossRatio,
      maxConsecutiveWins,
      maxConsecutiveLosses,
      calmarRatio,
      trades,
      equityCurve,
      symbolBreakdown,
      durationMs: Date.now() - startTime,
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Walk-Forward Optimization
  // ═══════════════════════════════════════════════════════════════

  /**
   * Run walk-forward optimization: sliding windows of in-sample training
   * and out-of-sample testing to measure strategy robustness.
   */
  async runWalkForward(tracker?: PerformanceTracker): Promise<WalkForwardResult> {
    const inSampleResults: BacktestResult[] = []
    const outOfSampleResults: BacktestResult[] = []

    const startDate = new Date(this.config.startDate)
    const endDate = new Date(this.config.endDate)
    const windowMs = this.config.walkForwardWindowDays * 24 * 60 * 60 * 1000
    const oosMs = this.config.outOfSampleDays * 24 * 60 * 60 * 1000

    let currentStart = startDate.getTime()

    while (currentStart + windowMs + oosMs <= endDate.getTime()) {
      // In-sample window
      const isConfig: BacktestConfig = {
        ...this.config,
        startDate: new Date(currentStart).toISOString(),
        endDate: new Date(currentStart + windowMs).toISOString(),
      }

      const isEngine = new BacktestEngine(isConfig)
      const isResult = await isEngine.run(tracker)
      inSampleResults.push(isResult)

      // Out-of-sample window
      const oosConfig: BacktestConfig = {
        ...this.config,
        startDate: new Date(currentStart + windowMs).toISOString(),
        endDate: new Date(currentStart + windowMs + oosMs).toISOString(),
      }

      const oosEngine = new BacktestEngine(oosConfig)
      const oosResult = await oosEngine.run(tracker)
      outOfSampleResults.push(oosResult)

      currentStart += oosMs
    }

    // Aggregate OOS
    const allOosTrades = outOfSampleResults.flatMap(r => r.trades)
    const oosWins = allOosTrades.filter(t => t.outcome === 'WIN')
    const oosWinRate = allOosTrades.length > 0 ? oosWins.length / allOosTrades.length : 0
    const oosCumulativePnl = allOosTrades.reduce((s, t) => s + t.pnl, 0)
    const oosSharpe = this.computeSharpe(allOosTrades.map(t => t.pnlPct))
    const oosMaxDd = this.computeMaxDrawdownPct(allOosTrades)

    // Robustness ratio: OOS Sharpe / IS Sharpe
    const isAvgSharpe = inSampleResults.length > 0
      ? inSampleResults.reduce((s, r) => s + r.sharpeRatio, 0) / inSampleResults.length
      : 0
    const robustnessRatio = isAvgSharpe > 0 ? oosSharpe / isAvgSharpe : 0

    return {
      inSample: inSampleResults,
      outOfSample: outOfSampleResults,
      aggregateOOS: {
        totalTrades: allOosTrades.length,
        winRate: oosWinRate,
        cumulativePnl: oosCumulativePnl,
        sharpeRatio: oosSharpe,
        maxDrawdownPct: oosMaxDd,
      },
      robustnessRatio,
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Statistical Helpers
  // ═══════════════════════════════════════════════════════════════

  private computeSharpe(pnlPcts: number[]): number {
    if (pnlPcts.length < 2) return 0
    const mean = pnlPcts.reduce((s, p) => s + p, 0) / pnlPcts.length
    const variance = pnlPcts.reduce((s, p) => s + (p - mean) ** 2, 0) / pnlPcts.length
    const std = Math.sqrt(variance)
    return std > 0 ? mean / std : 0
  }

  private computeSortino(pnlPcts: number[]): number {
    const negatives = pnlPcts.filter(p => p < 0)
    if (negatives.length < 2) return 0
    const mean = pnlPcts.reduce((s, p) => s + p, 0) / pnlPcts.length
    const downsideVariance = negatives.reduce((s, p) => s + p ** 2, 0) / negatives.length
    const downsideStd = Math.sqrt(downsideVariance)
    return downsideStd > 0 ? mean / downsideStd : 0
  }

  private computeMaxDrawdownPct(trades: BacktestTrade[]): number {
    let peak = 0
    let maxDd = 0
    let cumulative = this.config.initialEquity

    for (const trade of trades) {
      cumulative += trade.pnl
      if (cumulative > peak) peak = cumulative
      const dd = ((peak - cumulative) / peak) * 100
      if (dd > maxDd) maxDd = dd
    }

    return maxDd
  }

  private buildEquityCurve(trades: BacktestTrade[]): Array<{ timestamp: string; equity: number }> {
    const curve: Array<{ timestamp: string; equity: number }> = []
    let equity = this.config.initialEquity

    // Initial point
    curve.push({ timestamp: this.config.startDate, equity })

    for (const trade of trades) {
      equity += trade.pnl
      curve.push({ timestamp: trade.exitTimestamp || trade.entryTimestamp, equity })
    }

    return curve
  }

  // ═══════════════════════════════════════════════════════════════
  // Cost Helpers
  // ═══════════════════════════════════════════════════════════════

  private calculateCommission(price: number): number {
    // Commission = price * quantity * commissionBps / 10000
    // Assuming quantity = 100 for simplicity
    return price * 100 * this.config.commissionBps / 10000
  }

  private calculateSlippage(price: number): number {
    return price * 100 * this.config.slippageBps / 10000
  }

  private isInDateRange(timestamp: string): boolean {
    const ts = new Date(timestamp).getTime()
    const start = new Date(this.config.startDate).getTime()
    const end = new Date(this.config.endDate).getTime()
    return ts >= start && ts <= end
  }

  private getIntervalMs(): number {
    const map: Record<string, number> = {
      '1m': 60_000,
      '5m': 300_000,
      '15m': 900_000,
      '1h': 3_600_000,
      '4h': 14_400_000,
      '1d': 86_400_000,
    }
    return map[this.config.timeframe] || 86_400_000
  }

  private randomGaussian(): number {
    let u = 0, v = 0
    while (u === 0) u = Math.random()
    while (v === 0) v = Math.random()
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v)
  }

  // ═══════════════════════════════════════════════════════════════
  // Accessors
  // ═══════════════════════════════════════════════════════════════

  getConfig(): BacktestConfig {
    return { ...this.config }
  }

  setConfig(config: Partial<BacktestConfig>): void {
    this.config = { ...this.config, ...config }
  }

  clearCache(): void {
    this.dataCache.clear()
  }
}
