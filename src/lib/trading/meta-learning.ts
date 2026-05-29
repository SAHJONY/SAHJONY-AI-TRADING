// Meta-Learning System — performance tracking, agent evaluation, strategy optimization
import type {
  DebateRecord, AgentPerformance, PerformanceMetrics,
  AgentTradingRole, OptimizationSuggestion, FinalDecision,
} from '@/types/trading'
import type { DebateState } from '@/types/trading'
import { AGENT_ROLES } from '@/types/trading'

interface TrackerConfig {
  maxDebateRecords: number
  persistPath: string
}

const DEFAULT_CONFIG: TrackerConfig = {
  maxDebateRecords: 10000,
  persistPath: './data/meta-learning',
}

export class MetaLearningSystem {
  private debateRecords: DebateRecord[] = []
  private agentPerformances: Map<AgentTradingRole, AgentPerformance> = new Map()
  private config: TrackerConfig
  private recordCounter = 0

  constructor(config?: Partial<TrackerConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.initializeAgentPerformances()
  }

  private initializeAgentPerformances(): void {
    const roles = Object.keys(AGENT_ROLES) as AgentTradingRole[]
    for (const role of roles) {
      this.agentPerformances.set(role, {
        role,
        accuracy: 0.5,
        totalPredictions: 0,
        correctPredictions: 0,
        averageConfidence: 0,
        calibrationError: 0,
        attributedPnl: 0,
        lastUpdated: new Date().toISOString(),
      })
    }
  }

  recordDebate(
    symbol: string,
    assetType: string,
    finalDecision: FinalDecision,
    debateState: import('@/types/trading').DebateState,
  ): string {
    const id = `debate-${++this.recordCounter}-${Date.now()}`
    const record: DebateRecord = {
      id,
      symbol,
      assetType: assetType as any,
      timestamp: new Date().toISOString(),
      finalDecision,
      debateState,
      outcome: 'pending',
      pnl: null,
      pnlPct: null,
    }

    this.debateRecords.unshift(record)

    // Enforce max records
    if (this.debateRecords.length > this.config.maxDebateRecords) {
      this.debateRecords = this.debateRecords.slice(0, this.config.maxDebateRecords)
    }

    // Update agent performances from this debate
    this.updateAgentPerformances(record)

    return id
  }

  recordTradeOutcome(debateId: string, pnl: number, pnlPct: number): void {
    const record = this.debateRecords.find(r => r.id === debateId)
    if (!record) return

    record.outcome = pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven'
    record.pnl = pnl
    record.pnlPct = pnlPct

    // Update agent performances
    this.updateAgentPerformances(record)
  }

  private updateAgentPerformances(record: DebateRecord): void {
    const analyses = record.finalDecision.allAnalyses
    if (!analyses.length) return

    const isWin = record.outcome === 'win'
    const isLoss = record.outcome === 'loss'
    const isResolved = record.outcome !== 'pending'

    for (const analysis of analyses) {
      const perf = this.agentPerformances.get(analysis.role)
      if (!perf) continue

      // Only update accuracy if outcome is known
      if (isResolved) {
        const isCorrect = (isWin && (analysis.recommendation === 'BUY' || analysis.recommendation === 'STRONG_BUY')) ||
          (isLoss && (analysis.recommendation === 'SELL' || analysis.recommendation === 'STRONG_SELL'))

        perf.totalPredictions++
        if (isCorrect) perf.correctPredictions++
        perf.accuracy = perf.totalPredictions > 0
          ? perf.correctPredictions / perf.totalPredictions
          : 0.5

        // Update calibration
        const oldCalibration = perf.calibrationError
        const newCalibration = Math.abs(analysis.confidence - (isCorrect ? 1 : 0))
        perf.calibrationError = oldCalibration > 0
          ? (oldCalibration * 0.9 + newCalibration * 0.1)
          : newCalibration
      }

      // Update confidence rolling average
      perf.averageConfidence = perf.averageConfidence > 0
        ? perf.averageConfidence * 0.9 + analysis.confidence * 0.1
        : analysis.confidence

      if (record.pnl !== null) {
        perf.attributedPnl += record.pnl * (AGENT_ROLES[analysis.role].weight / 6)
      }

      perf.lastUpdated = new Date().toISOString()
    }
  }

  getPerformanceMetrics(): PerformanceMetrics {
    const resolvedRecords = this.debateRecords.filter(r => r.outcome !== 'pending')
    const totalTrades = resolvedRecords.length
    const winningTrades = resolvedRecords.filter(r => r.outcome === 'win').length
    const losingTrades = resolvedRecords.filter(r => r.outcome === 'loss').length
    const winRate = totalTrades > 0 ? winningTrades / totalTrades : 0

    const completedPnl = resolvedRecords
      .filter(r => r.pnl !== null)
      .map(r => r.pnl!)
    const cumulativePnl = completedPnl.reduce((sum, p) => sum + p, 0)
    const avgWin = winningTrades > 0
      ? completedPnl.filter(p => p > 0).reduce((sum, p) => sum + p, 0) / winningTrades
      : 0
    const avgLoss = losingTrades > 0
      ? Math.abs(completedPnl.filter(p => p < 0).reduce((sum, p) => sum + p, 0) / losingTrades)
      : 0
    const profitFactor = (avgWin * winningTrades) / (avgLoss * losingTrades) || 0

    // Sharpe ratio (annualized)
    const returns = completedPnl
    const avgReturn = returns.length > 0 ? returns.reduce((a, b) => a + b, 0) / returns.length : 0
    const stdReturn = returns.length > 1
      ? Math.sqrt(returns.reduce((a, b) => a + (b - avgReturn) ** 2, 0) / returns.length)
      : 0
    const sharpeRatio = stdReturn > 0 ? (avgReturn / stdReturn) * Math.sqrt(252) : 0

    // Max drawdown
    let peak = 0
    let maxDrawdown = 0
    let runningPnl = 0
    for (const pnl of completedPnl) {
      runningPnl += pnl
      if (runningPnl > peak) peak = runningPnl
      const drawdown = peak > 0 ? (peak - runningPnl) / peak : 0
      if (drawdown > maxDrawdown) maxDrawdown = drawdown
    }

    // Agent performances as record
    const agentPerformances: Record<string, AgentPerformance> = {}
    for (const [role, perf] of this.agentPerformances) {
      agentPerformances[role] = { ...perf }
    }

    return {
      winRate,
      sharpeRatio,
      maxDrawdown,
      profitFactor,
      totalTrades,
      winningTrades,
      losingTrades,
      avgWin,
      avgLoss,
      cumulativePnl,
      agentPerformances: agentPerformances as Record<AgentTradingRole, AgentPerformance>,
    }
  }

  getAgentPerformance(role: AgentTradingRole): AgentPerformance {
    return this.agentPerformances.get(role) || {
      role,
      accuracy: 0,
      totalPredictions: 0,
      correctPredictions: 0,
      averageConfidence: 0,
      calibrationError: 0,
      attributedPnl: 0,
      lastUpdated: new Date().toISOString(),
    }
  }

  generateOptimizations(): OptimizationSuggestion[] {
    const metrics = this.getPerformanceMetrics()
    const suggestions: OptimizationSuggestion[] = []

    // Weight optimization: boost high-accuracy agents, reduce low-accuracy
    for (const [role, perf] of this.agentPerformances) {
      const config = AGENT_ROLES[role]
      if (perf.totalPredictions >= 5) {
        if (perf.accuracy > 0.65 && config.weight < 1.0) {
          suggestions.push({
            type: 'weight',
            target: role,
            currentValue: config.weight,
            suggestedValue: Math.min(config.weight + 0.1, 1.0),
            confidence: perf.accuracy,
            reasoning: `${config.label} accuracy (${(perf.accuracy * 100).toFixed(0)}%) significantly above baseline. Increase voting weight.`,
          })
        } else if (perf.accuracy < 0.35 && config.weight > 0.3) {
          suggestions.push({
            type: 'weight',
            target: role,
            currentValue: config.weight,
            suggestedValue: Math.max(config.weight - 0.1, 0.3),
            confidence: 1 - perf.accuracy,
            reasoning: `${config.label} accuracy (${(perf.accuracy * 100).toFixed(0)}%) below threshold. Reduce voting weight.`,
          })
        }
      }
    }

    // Threshold optimization
    if (metrics.winRate > 0.6 && metrics.totalTrades >= 10) {
      suggestions.push({
        type: 'threshold',
        target: 'consensusThreshold',
        currentValue: 0.6,
        suggestedValue: 0.55,
        confidence: metrics.winRate,
        reasoning: `Win rate (${(metrics.winRate * 100).toFixed(0)}%) is strong. Lowering consensus threshold may capture more opportunities.`,
      })
    } else if (metrics.winRate < 0.4 && metrics.totalTrades >= 10) {
      suggestions.push({
        type: 'threshold',
        target: 'consensusThreshold',
        currentValue: 0.6,
        suggestedValue: 0.7,
        confidence: 1 - metrics.winRate,
        reasoning: `Win rate (${(metrics.winRate * 100).toFixed(0)}%) is below target. Raising consensus threshold will increase selectivity.`,
      })
    }

    // Risk optimization
    if (metrics.maxDrawdown > 0.2) {
      suggestions.push({
        type: 'risk',
        target: 'maxPositionSizePct',
        currentValue: 0.25,
        suggestedValue: 0.15,
        confidence: Math.min(metrics.maxDrawdown, 1),
        reasoning: `Max drawdown (${(metrics.maxDrawdown * 100).toFixed(1)}%) exceeds 20%. Reduce max position size to control risk.`,
      })
    }

    return suggestions
  }

  getRecentDebates(limit: number = 10): DebateRecord[] {
    return this.debateRecords.slice(0, limit)
  }

  getDebateById(id: string): DebateRecord | undefined {
    return this.debateRecords.find(r => r.id === id)
  }
}

export const metaLearning = new MetaLearningSystem()
