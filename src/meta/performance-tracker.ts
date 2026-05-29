/**
 * Layer 5 — Performance Tracker
 *
 * Tracks agent accuracy, debate outcomes, P&L attribution, and computes
 * performance metrics per agent and system-wide. Feeds into the genetic
 * algorithm (fitness evaluation) and model router (reward calculation).
 */

import { EventEmitter } from 'events'
import {
  DebateRecord,
  TradeOutcomeRecord,
  AgentPerformanceMetrics,
  SystemPerformanceMetrics,
  TradeOutcome,
  ModelReward,
} from './types'
import type { AgentTradingRole, AgentAnalysis, FinalDecision } from './types'
import * as path from 'path'
import * as fs from 'fs'

// ═══════════════════════════════════════════════════════════════
// Default configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_TRACKER_CONFIG = {
  maxDebateRecords: 10_000,
  maxTradeRecords: 50_000,
  persistRecords: true,
  persistDir: path.resolve(process.cwd(), 'data', 'meta-learning'),
}

export type TrackerConfig = typeof DEFAULT_TRACKER_CONFIG

// ═══════════════════════════════════════════════════════════════
// Performance Tracker
// ═══════════════════════════════════════════════════════════════

export class PerformanceTracker extends EventEmitter {
  private config: TrackerConfig
  private debates: DebateRecord[] = []
  private trades: TradeOutcomeRecord[] = []
  private metrics: SystemPerformanceMetrics | null = null

  constructor(config: Partial<TrackerConfig> = {}) {
    super()
    this.config = { ...DEFAULT_TRACKER_CONFIG, ...config }
    this.ensurePersistDir()
    this.loadFromDisk()
  }

  // ═══════════════════════════════════════════════════════════
  // Record Ingestion
  // ═══════════════════════════════════════════════════════════

  /**
   * Record a completed debate session.
   */
  recordDebate(record: DebateRecord): void {
    this.debates.push(record)

    // Truncate if over limit (keep most recent)
    if (this.debates.length > this.config.maxDebateRecords) {
      this.debates = this.debates.slice(-this.config.maxDebateRecords)
    }

    this.emit('debateRecorded', { sessionId: record.sessionId })
    this.markDirty()
  }

  /**
   * Record a trade outcome (linked to debate session).
   */
  recordTradeOutcome(record: TradeOutcomeRecord): void {
    this.trades.push(record)

    if (this.trades.length > this.config.maxTradeRecords) {
      this.trades = this.trades.slice(-this.config.maxTradeRecords)
    }

    this.emit('tradeOutcomeRecorded', {
      sessionId: record.debateSessionId,
      pnl: record.pnl,
      outcome: record.outcome,
    })

    this.markDirty()
  }

  /**
   * Link a debate to its eventual trade outcome.
   * Called when a trade closes — updates the debate's ground truth.
   */
  linkOutcomeToDebate(sessionId: string, outcome: TradeOutcomeRecord): void {
    const debate = this.debates.find(d => d.sessionId === sessionId)
    if (debate) {
      // Debate record is already stored; we track outcomes separately
      // and cross-reference during metric computation
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Metric Computation
  // ═══════════════════════════════════════════════════════════

  /**
   * Compute full system performance metrics from all recorded data.
   */
  computeMetrics(): SystemPerformanceMetrics {
    const closedTrades = this.trades.filter(
      t => t.outcome !== 'PENDING'
    )

    // System-level stats
    const wins = closedTrades.filter(t => t.outcome === 'WIN')
    const losses = closedTrades.filter(t => t.outcome === 'LOSS')
    const winRate = closedTrades.length > 0
      ? wins.length / closedTrades.length
      : 0

    const allPnl = closedTrades.map(t => t.pnl)
    const cumulativePnl = allPnl.reduce((sum, p) => sum + p, 0)
    const avgPnl = closedTrades.length > 0 ? cumulativePnl / closedTrades.length : 0

    // Sharpe ratio (simplified: mean(pnl) / std(pnl), annualized estimate)
    const sharpeRatio = this.computeSharpe(closedTrades)

    // Max drawdown from cumulative P&L
    const maxDrawdownPct = this.computeMaxDrawdown(closedTrades)

    // Profit factor
    const grossProfit = wins.reduce((sum, t) => sum + t.pnl, 0)
    const grossLoss = Math.abs(losses.reduce((sum, t) => sum + t.pnl, 0))
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0

    // Agent-level metrics
    const agentMetrics = this.computeAgentMetrics()

    // Hold rate & veto rate
    const decisions = this.debates.map(d => d.decision)
    const holdCount = decisions.filter(d => d.action === 'HOLD').length
    const vetoCount = decisions.filter(d => d.vetoApplied).length

    const metrics: SystemPerformanceMetrics = {
      totalDebates: this.debates.length,
      totalTrades: closedTrades.length,
      winRate,
      avgPnl,
      cumulativePnl,
      sharpeRatio,
      maxDrawdownPct,
      avgRoundsPerDebate: this.computeAvgRounds(),
      vetoRate: this.debates.length > 0 ? vetoCount / this.debates.length : 0,
      holdRate: this.debates.length > 0 ? holdCount / this.debates.length : 0,
      profitFactor,
      agentMetrics,
      periodStart: this.debates[0]?.timestamp ?? new Date().toISOString(),
      periodEnd: this.debates[this.debates.length - 1]?.timestamp ?? new Date().toISOString(),
    }

    this.metrics = metrics
    return metrics
  }

  /**
   * Compute per-agent performance metrics.
   */
  private computeAgentMetrics(): Record<AgentTradingRole, AgentPerformanceMetrics> {
    const allRoles: AgentTradingRole[] = [
      'macro_strategist', 'sector_analyst', 'sentiment_agent',
      'technical_analyst', 'risk_manager', 'execution_optimizer',
    ]

    const result = {} as Record<AgentTradingRole, AgentPerformanceMetrics>

    for (const role of allRoles) {
      const metrics = this.computeSingleAgentMetrics(role)
      result[role] = metrics
    }

    return result
  }

  private computeSingleAgentMetrics(role: AgentTradingRole): AgentPerformanceMetrics {
    // Get all analyses from this role
    const analyses: AgentAnalysis[] = []
    for (const debate of this.debates) {
      const agentAnalysis = debate.agentAnalyses.find(a => a.role === role)
      if (agentAnalysis) {
        analyses.push(agentAnalysis)
      }
    }

    // Cross-reference with trade outcomes
    let correctPredictions = 0
    let totalWithOutcome = 0
    let sumConfidenceCorrect = 0
    let countConfidenceCorrect = 0
    let sumConfidenceWrong = 0
    let countConfidenceWrong = 0
    let calibrationSum = 0
    let attributedPnl = 0
    let onWinningSide = 0
    let totalDebates = 0
    const convergenceRounds: number[] = []

    for (const debate of this.debates) {
      const analysis = debate.agentAnalyses.find(a => a.role === role)
      if (!analysis) continue

      totalDebates++

      // Find trade outcome for this debate
      const trade = this.trades.find(t => t.debateSessionId === debate.sessionId)
      if (!trade || trade.outcome === 'PENDING') continue

      totalWithOutcome++

      // Was the recommendation correct?
      // HOLD (NEUTRAL) is correct when the trade outcome was a LOSS
      // (avoiding a bad trade = correct decision)
      const recDirection = this.recommendationToDirection(analysis.recommendation)
      const isCorrect: boolean =
        recDirection === 'NEUTRAL'
          ? trade.outcome === 'LOSS' // HOLD was correct if trade would have lost
          : (recDirection === trade.direction && trade.outcome === 'WIN')
            || (recDirection !== trade.direction && trade.outcome === 'LOSS')

      if (isCorrect) {
        correctPredictions++
        sumConfidenceCorrect += analysis.confidence
        countConfidenceCorrect++
      } else {
        sumConfidenceWrong += analysis.confidence
        countConfidenceWrong++
      }

      // Calibration: |confidence - 1| for correct, |confidence - 0| for wrong
      calibrationSum += isCorrect
        ? Math.abs(analysis.confidence - 1)
        : Math.abs(analysis.confidence - 0)

      // P&L attribution: if agent was on winning side of consensus
      const winningSide = this.directionToWinningSide(trade.direction, debate.decision.action)
      const agentSide = this.recommendationToDirection(analysis.recommendation)
      if (agentSide === winningSide) {
        onWinningSide++
        attributedPnl += trade.pnl
      }

      // Convergence round
      convergenceRounds.push(analysis.round)
    }

    const accuracy = totalWithOutcome > 0 ? correctPredictions / totalWithOutcome : 0.5
    const avgConvergence = convergenceRounds.length > 0
      ? convergenceRounds.reduce((s, r) => s + r, 0) / convergenceRounds.length
      : 0

    return {
      role,
      totalAnalyses: analyses.length,
      recommendationAccuracy: accuracy,
      avgConfidenceWhenCorrect: countConfidenceCorrect > 0
        ? sumConfidenceCorrect / countConfidenceCorrect : 0,
      avgConfidenceWhenWrong: countConfidenceWrong > 0
        ? sumConfidenceWrong / countConfidenceWrong : 0,
      calibrationError: totalWithOutcome > 0 ? calibrationSum / totalWithOutcome : 0.5,
      consensusAlignment: totalDebates > 0 ? onWinningSide / totalDebates : 0.5,
      avgWeightedContribution: 0, // Computed from voting breakdown
      attributedPnl,
      recommendationSharpe: 0, // Requires time-series
      avgConvergenceRound: avgConvergence,
      evolvedWeight: 0.5, // Will be updated by GA
      lastUpdated: new Date().toISOString(),
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Reward Computation (for MAB model router)
  // ═══════════════════════════════════════════════════════════════

  /**
   * Compute a ModelReward for a specific agent analysis run.
   * Used by the multi-armed bandit to evaluate LLM model performance.
   */
  computeModelReward(
    analysis: AgentAnalysis,
    debate: DebateRecord,
    latencyMs: number,
    tokensUsed: number
  ): ModelReward {
    // Find trade outcome
    const trade = this.trades.find(t => t.debateSessionId === debate.sessionId)
    const isDirectionallyCorrect = trade
      ? this.recommendationToDirection(analysis.recommendation) === trade.direction
        && trade.outcome === 'WIN'
      : false

    const directionalAccuracy = isDirectionallyCorrect ? 1 : 0

    // Reasoning quality: proxy via evidence count and specificity
    const reasoningQuality = Math.min(
      1,
      (analysis.evidenceRefs.length / 5) * 0.5 +
      (analysis.reasoning.length > 200 ? 0.5 : analysis.reasoning.length / 400)
    )

    // Latency: normalize to 0–1 (lower = better, 30s max)
    const latencyScore = Math.max(0, 1 - latencyMs / 30_000)

    // Cost efficiency: normalize (cheaper = better, 16k tokens max)
    const costEfficiency = Math.max(0, 1 - tokensUsed / 16_000)

    // Weighted composite
    const composite =
      directionalAccuracy * 0.5 +
      reasoningQuality * 0.2 +
      latencyScore * 0.15 +
      costEfficiency * 0.15

    return {
      directionalAccuracy,
      reasoningQuality,
      latencyScore,
      costEfficiency,
      composite,
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Statistical Helpers
  // ═══════════════════════════════════════════════════════════

  private computeSharpe(trades: TradeOutcomeRecord[]): number {
    if (trades.length < 2) return 0
    const pnls = trades.map(t => t.pnlPct)
    const mean = pnls.reduce((s, p) => s + p, 0) / pnls.length
    const variance = pnls.reduce((s, p) => s + (p - mean) ** 2, 0) / pnls.length
    const std = Math.sqrt(variance)
    return std > 0 ? mean / std : 0
  }

  private computeMaxDrawdown(trades: TradeOutcomeRecord[]): number {
    let peak = 0
    let maxDd = 0
    let cumulative = 0

    for (const trade of trades) {
      cumulative += trade.pnlPct
      if (cumulative > peak) peak = cumulative
      const dd = peak - cumulative
      if (dd > maxDd) maxDd = dd
    }

    return maxDd
  }

  private computeAvgRounds(): number {
    if (this.debates.length === 0) return 0
    return this.debates.reduce((s, d) => s + d.roundsRequired, 0) / this.debates.length
  }

  private recommendationToDirection(rec: string): 'LONG' | 'SHORT' | 'NEUTRAL' {
    if (rec === 'STRONG_BUY' || rec === 'BUY') return 'LONG'
    if (rec === 'STRONG_SELL' || rec === 'SELL') return 'SHORT'
    return 'NEUTRAL'
  }

  private directionToWinningSide(
    tradeDirection: 'LONG' | 'SHORT',
    decisionAction: 'BUY' | 'SELL' | 'HOLD'
  ): 'LONG' | 'SHORT' | 'NEUTRAL' {
    // The winning side is determined by the consensus decision:
    // If consensus was BUY, the winning side is LONG; if SELL, it's SHORT.
    // If consensus was HOLD, the winning side is NEUTRAL (no trade).
    if (decisionAction === 'BUY') return 'LONG'
    if (decisionAction === 'SELL') return 'SHORT'
    return 'NEUTRAL'
  }

  // ═══════════════════════════════════════════════════════════
  // Accessors
  // ═══════════════════════════════════════════════════════════

  getMetrics(): SystemPerformanceMetrics | null {
    return this.metrics ?? this.computeMetrics()
  }

  getDebateRecords(): DebateRecord[] {
    return [...this.debates]
  }

  getTradeRecords(): TradeOutcomeRecord[] {
    return [...this.trades]
  }

  getRecentTrades(count: number): TradeOutcomeRecord[] {
    return this.trades.slice(-count)
  }

  getRecordCounts(): { debates: number; trades: number } {
    return { debates: this.debates.length, trades: this.trades.length }
  }

  /**
   * Get trades with outcomes, used for fitness evaluation in the GA.
   */
  getTradeSnapshots(): Array<{ pnl: number; pnlPct: number; outcome: TradeOutcome }> {
    return this.trades
      .filter(t => t.outcome !== 'PENDING')
      .map(t => ({ pnl: t.pnl, pnlPct: t.pnlPct, outcome: t.outcome }))
  }

  // ═══════════════════════════════════════════════════════════
  // Persistence
  // ═══════════════════════════════════════════════════════════

  private ensurePersistDir(): void {
    if (this.config.persistRecords) {
      fs.mkdirSync(this.config.persistDir, { recursive: true })
    }
  }

  private dirty = false
  private saveTimeout: NodeJS.Timeout | null = null

  private markDirty(): void {
    if (!this.config.persistRecords) return
    this.dirty = true

    if (this.saveTimeout) clearTimeout(this.saveTimeout)
    this.saveTimeout = setTimeout(() => this.saveToDisk(), 5000)
  }

  private saveToDisk(): void {
    if (!this.dirty) return

    try {
      const debatesPath = path.join(this.config.persistDir, 'debate-records.json')
      const tradesPath = path.join(this.config.persistDir, 'trade-records.json')

      // Only persist recent records to avoid huge files
      const recentDebates = this.debates.slice(-5000)
      const recentTrades = this.trades.slice(-25000)

      fs.writeFileSync(debatesPath, JSON.stringify(recentDebates, null, 2))
      fs.writeFileSync(tradesPath, JSON.stringify(recentTrades, null, 2))
      this.dirty = false
    } catch (err) {
      // Non-critical — silently fail
    }
  }

  private loadFromDisk(): void {
    try {
      const debatesPath = path.join(this.config.persistDir, 'debate-records.json')
      const tradesPath = path.join(this.config.persistDir, 'trade-records.json')

      if (fs.existsSync(debatesPath)) {
        this.debates = JSON.parse(fs.readFileSync(debatesPath, 'utf-8'))
      }
      if (fs.existsSync(tradesPath)) {
        this.trades = JSON.parse(fs.readFileSync(tradesPath, 'utf-8'))
      }
    } catch {
      // Start fresh if load fails
    }
  }

  /**
   * Persist and shutdown.
   */
  async shutdown(): Promise<void> {
    if (this.saveTimeout) clearTimeout(this.saveTimeout)
    this.saveToDisk()
    this.emit('shutdown')
  }
}
