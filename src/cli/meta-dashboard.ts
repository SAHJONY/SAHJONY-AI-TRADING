/**
 * Meta-Learning Dashboard — CLI Rendering
 *
 * Renders a comprehensive ASCII dashboard for the self-evolving
 * meta-learning pipeline. Called from the CLI via `/meta` command.
 *
 * Panels:
 *   1. System Overview — debates, trades, win rate, Sharpe, P&L, drawdown
 *   2. Agent Performance — per-agent accuracy, calibration, alignment, attributed P&L
 *   3. GA Fitness History — generation-by-generation ASCII chart
 *   4. Bandit Model Dominance — dominant LLM model per agent role
 *   5. Optimization Suggestions — recent suggestions from the pipeline
 */

import type {
  MetaLearningPipeline,
  MetaLearningStatus,
  SystemPerformanceMetrics,
  OptimizationSuggestion,
  GARunResult,
} from '../meta'
import type { AgentTradingRole } from '../trading/types'

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

const BAR_WIDTH = 30
const AGENT_LABELS: Record<AgentTradingRole, string> = {
  macro_strategist: 'Macro',
  sector_analyst: 'Sector',
  sentiment_agent: 'Sentiment',
  technical_analyst: 'Technical',
  risk_manager: 'Risk',
  execution_optimizer: 'Exec',
}

function bar(value: number, max: number, width = BAR_WIDTH): string {
  const clamped = Math.max(0, Math.min(1, max > 0 ? value / max : 0))
  const filled = Math.round(clamped * width)
  const empty = width - filled
  const color = clamped > 0.7 ? '█' : clamped > 0.4 ? '▓' : '▒'
  return color.repeat(filled) + '░'.repeat(empty)
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

function usd(v: number): string {
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : v >= 0 ? '+' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
  return `${sign}$${abs.toFixed(2)}`
}

function fixed(v: number | undefined, decimals = 2): string {
  return v !== undefined ? v.toFixed(decimals) : 'N/A'
}

function pad(s: string, len: number): string {
  return s.padEnd(len)
}

function header(title: string): string {
  const line = '═'.repeat(64)
  return `\n${line}\n  ${title}\n${line}`
}

function subHeader(title: string): string {
  return `\n  ┌─ ${title}\n  │`
}

function timestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

// ═══════════════════════════════════════════════════════════════
// ASCII Sparkline Chart
// ═══════════════════════════════════════════════════════════════

const SPARK_CHARS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']

function miniChart(values: number[], width = 40, height = 6): string {
  if (values.length < 2) return '(not enough data)'
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const rows: string[] = []
  for (let row = height - 1; row >= 0; row--) {
    const threshold = min + (range * row) / (height - 1)
    let line = '  │'
    const step = Math.max(1, Math.floor(values.length / width))
    for (let i = 0; i < values.length; i += step) {
      if (values[i] >= threshold) {
        // Find the best character for this bar height
        const barHeight = (values[i] - min) / range
        const charIdx = Math.min(SPARK_CHARS.length - 1, Math.floor(barHeight * SPARK_CHARS.length))
        line += SPARK_CHARS[charIdx]
      } else {
        line += ' '
      }
    }
    rows.push(line)
  }
  rows.push(`  └${'─'.repeat(Math.min(width, Math.ceil(values.length / Math.max(1, Math.floor(values.length / width)))))}`)

  return rows.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 1: System Overview
// ═══════════════════════════════════════════════════════════════

function renderOverview(status: MetaLearningStatus, metrics?: SystemPerformanceMetrics, tradeCount?: number, debateCount?: number): string {
  const lines: string[] = [header('📊 META-LEARNING DASHBOARD')]

  // Status row
  const statusIcon = status.running ? '🟢 RUNNING' : '🔴 STOPPED'
  lines.push(`\n  Status: ${statusIcon}    Generation: ${status.generationCount}    Prompt Versions: ${status.promptVersionCount}`)

  // Last evolution
  if (status.lastEvolution) {
    const evo = status.lastEvolution
    lines.push(`  Last Evolution: ${timestamp(evo.timestamp)}  |  Trigger: ${evo.trigger}  |  Best Fitness: ${evo.bestFitness.toFixed(4)}  |  Δ: ${evo.fitnessDelta >= 0 ? '+' : ''}${evo.fitnessDelta.toFixed(4)}`)
  }

  // Last prompt opt
  if (status.lastPromptOptimization) {
    const po = status.lastPromptOptimization
    lines.push(`  Last Prompt Opt: ${timestamp(po.timestamp)}  |  Roles: ${po.rolesOptimized.length}  |  Avg ΔAccuracy: ${(po.avgAccuracyImprovement * 100).toFixed(1)}%`)
  }

  if (!metrics) {
    lines.push(`\n  No performance data available yet. Run some debates to populate metrics.`)
    return lines.join('\n')
  }

  // ── Performance KPIs ──

  lines.push(subHeader('PERFORMANCE OVERVIEW'))

  // Row 1: Debates, Trades, Win Rate
  lines.push(`  │  Debates: ${metrics.totalDebates.toString().padStart(6)}   Trades: ${metrics.totalTrades.toString().padStart(6)}   Win Rate: ${pct(metrics.winRate).padStart(7)}   ${bar(metrics.winRate, 1)}`)

  // Row 2: P&L
  lines.push(`  │  Cumul. P&L: ${usd(metrics.cumulativePnl).padStart(10)}   Avg P&L: ${usd(metrics.avgPnl).padStart(10)}   Profit Factor: ${fixed(metrics.profitFactor).padStart(6)}`)

  // Row 3: Sharpe, Drawdown, Rounds
  lines.push(`  │  Sharpe:    ${fixed(metrics.sharpeRatio).padStart(6)}   Max DD:    ${fixed(metrics.maxDrawdownPct, 1)}%`.padEnd(45) + `   Avg Rounds: ${fixed(metrics.avgRoundsPerDebate, 1)}`)

  // Row 4: Veto & Hold rates
  lines.push(`  │  Veto Rate:  ${pct(metrics.vetoRate).padStart(6)}   Hold Rate:  ${pct(metrics.holdRate).padStart(6)}`)

  // Period
  lines.push(`  │  Period: ${timestamp(metrics.periodStart)} → ${timestamp(metrics.periodEnd)}`)

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 2: Agent Performance Trends
// ═══════════════════════════════════════════════════════════════

function renderAgentPerformance(metrics?: SystemPerformanceMetrics): string {
  const lines: string[] = [header('🤖 AGENT PERFORMANCE')]

  if (!metrics || Object.keys(metrics.agentMetrics).length === 0) {
    lines.push(`\n  No agent metrics available.`)
    return lines.join('\n')
  }

  // Find best agent for each metric to highlight
  const roles = Object.keys(metrics.agentMetrics) as AgentTradingRole[]
  const maxAccuracy = Math.max(...roles.map(r => metrics.agentMetrics[r].recommendationAccuracy))
  const maxAlignment = Math.max(...roles.map(r => metrics.agentMetrics[r].consensusAlignment))
  const maxPnl = Math.max(...roles.map(r => metrics.agentMetrics[r].attributedPnl))

  lines.push(`\n  Role          Accuracy       Calib.Err  Alignment    Attr.P&L      Weight`)
  lines.push(`  ${'─'.repeat(72)}`)

  for (const role of roles) {
    const a = metrics.agentMetrics[role]
    const isBestAcc = a.recommendationAccuracy >= maxAccuracy
    const isBestAlign = a.consensusAlignment >= maxAlignment
    const isBestPnl = a.attributedPnl >= maxPnl && maxPnl > 0

    const accMarker = isBestAcc ? '★' : ' '
    const alignMarker = isBestAlign ? '★' : ' '
    const pnlMarker = isBestPnl ? '★' : ' '

    lines.push(
      `  ${pad(AGENT_LABELS[role], 12)}  ` +
      `${accMarker}${pct(a.recommendationAccuracy).padStart(7)}    ` +
      `${fixed(a.calibrationError).padStart(6)}     ` +
      `${alignMarker}${pct(a.consensusAlignment).padStart(7)}    ` +
      `${pnlMarker}${usd(a.attributedPnl).padStart(10)}    ` +
      `${fixed(a.evolvedWeight).padStart(5)}`
    )
  }

  lines.push(`  ${'─'.repeat(72)}`)
  lines.push(`  ★ = best in category`)

  // ── Accuracy bar chart ──
  lines.push(`\n  Accuracy (${BAR_WIDTH} char bar):`)
  for (const role of roles) {
    const a = metrics.agentMetrics[role]
    lines.push(`  ${pad(AGENT_LABELS[role], 12)} ${bar(a.recommendationAccuracy, 1)} ${pct(a.recommendationAccuracy)}`)
  }

  // ── Confidence calibration note ──
  lines.push(`\n  Confidence Calibration:`)
  for (const role of roles) {
    const a = metrics.agentMetrics[role]
    const correctPct = pct(a.avgConfidenceWhenCorrect)
    const wrongPct = pct(a.avgConfidenceWhenWrong)
    lines.push(`  ${pad(AGENT_LABELS[role], 12)} Correct: ${correctPct.padStart(7)}   Wrong: ${wrongPct.padStart(7)}   Error: ${fixed(a.calibrationError).padStart(5)}`)
  }

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 3: GA Fitness History
// ═══════════════════════════════════════════════════════════════

function renderGAFitness(gaResult?: GARunResult | null, population?: Array<{ fitness: number }>): string {
  const lines: string[] = [header('🧬 GENETIC ALGORITHM — FITNESS HISTORY')]

  // Try to get data from GA if available
  if (!gaResult || gaResult.fitnessHistory.length === 0) {
    if (population && population.length > 0) {
      lines.push(`\n  Population: ${population.length} chromosomes`)
      const bestFitness = Math.max(...population.map(c => c.fitness))
      const avgFitness = population.reduce((s, c) => s + c.fitness, 0) / population.length
      lines.push(`  Best Fitness: ${bestFitness.toFixed(4)}   Avg Fitness: ${avgFitness.toFixed(4)}`)
      return lines.join('\n')
    }
    lines.push(`\n  No GA evolution data yet. Run an evolution cycle to populate.`)
    return lines.join('\n')
  }

  const history = gaResult.fitnessHistory

  // Summary row
  const firstBest = history[0].best
  const lastBest = history[history.length - 1].best
  const improvement = lastBest - firstBest

  lines.push(`\n  Generations: ${history.length}   Converged: ${gaResult.converged ? '✅ Yes' : '❌ No'}   Duration: ${(gaResult.durationMs / 1000).toFixed(1)}s`)
  lines.push(`  Best Fitness: ${lastBest.toFixed(4)}   Improvement: ${improvement >= 0 ? '+' : ''}${improvement.toFixed(4)}`)

  // Mini chart for best fitness
  const bestValues = history.map(h => h.best)
  lines.push(`\n  Best Fitness Trend:`)
  lines.push(miniChart(bestValues, 50, 6))

  // Generation table
  lines.push(`\n  Gen   Best        Avg         Worst       Δ Best`)
  lines.push(`  ${'─'.repeat(55)}`)

  const maxGens = Math.min(20, history.length)
  const step = Math.max(1, Math.floor(history.length / maxGens))
  let prevBest = history[0].best

  for (let i = 0; i < history.length; i += step) {
    const h = history[i]
    const delta = h.best - prevBest
    const deltaStr = delta >= 0 ? `+${delta.toFixed(4)}` : delta.toFixed(4)
    lines.push(
      `  ${h.generation.toString().padStart(3)}   ${h.best.toFixed(4).padStart(8)}   ${h.average.toFixed(4).padStart(8)}   ${h.worst.toFixed(4).padStart(8)}   ${deltaStr}`
    )
    prevBest = h.best
  }

  // Also show the last generation if it was skipped
  if (history.length > 0 && (history.length - 1) % step !== 0) {
    const h = history[history.length - 1]
    const delta = h.best - (history[Math.max(0, history.length - 2)]?.best ?? h.best)
    const deltaStr = delta >= 0 ? `+${delta.toFixed(4)}` : delta.toFixed(4)
    lines.push(
      `  ${h.generation.toString().padStart(3)}   ${h.best.toFixed(4).padStart(8)}   ${h.average.toFixed(4).padStart(8)}   ${h.worst.toFixed(4).padStart(8)}   ${deltaStr}`
    )
  }

  // Final population overview
  if (gaResult.finalPopulation.length > 0) {
    lines.push(`\n  Final Population: ${gaResult.finalPopulation.length} chromosomes`)
    const fitnesses = gaResult.finalPopulation.map(c => c.fitness).sort((a, b) => b - a)
    lines.push(`  Top 5: ${fitnesses.slice(0, 5).map(f => f.toFixed(4)).join('  ')}`)
    lines.push(`  Spread: ${fitnesses[0].toFixed(4)} → ${fitnesses[fitnesses.length - 1].toFixed(4)}`)
  }

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 4: Bandit Model Dominance
// ═══════════════════════════════════════════════════════════════

function renderBanditDominance(banditSummary?: {
  totalPulls: number
  dominantModels: Record<AgentTradingRole, string>
  perRole: Record<AgentTradingRole, Array<{
    provider: string
    model: string
    pulls: number
    meanReward: number
    ucb: number
  }>>
} | null): string {
  const lines: string[] = [header('🎰 MULTI-ARMED BANDIT — MODEL DOMINANCE')]

  if (!banditSummary || banditSummary.totalPulls === 0) {
    lines.push(`\n  No bandit data yet. Run some debates to populate model statistics.`)
    return lines.join('\n')
  }

  lines.push(`\n  Total Pulls: ${banditSummary.totalPulls}`)

  // Per-role breakdown
  const roles = Object.keys(banditSummary.dominantModels) as AgentTradingRole[]

  for (const role of roles) {
    const dominant = banditSummary.dominantModels[role]
    const arms = banditSummary.perRole[role] || []

    lines.push(`\n  ┌─ ${AGENT_LABELS[role]}`)
    lines.push(`  │  Dominant: ${dominant}`)

    if (arms.length === 0) continue

    const maxPulls = Math.max(...arms.map(a => a.pulls))
    const maxReward = Math.max(...arms.map(a => a.meanReward))

    for (const arm of arms.slice(0, 4)) {
      const pullBar = bar(arm.pulls, maxPulls, 15)
      const rewardBar = bar(arm.meanReward, maxReward, 10)
      const modelName = `${arm.provider}/${arm.model}`.substring(0, 28)
      lines.push(
        `  │  ${pad(modelName, 30)} pulls:${arm.pulls.toString().padStart(4)} ${pullBar}  reward:${arm.meanReward.toFixed(3)} ${rewardBar}`
      )
    }
  }

  // ── Overall dominance summary ──
  lines.push(`\n  ┌─ MODEL MARKET SHARE`)
  const modelCounts = new Map<string, number>()
  for (const role of roles) {
    const dominant = banditSummary.dominantModels[role]
    modelCounts.set(dominant, (modelCounts.get(dominant) || 0) + 1)
  }
  const sortedModels = [...modelCounts.entries()].sort((a, b) => b[1] - a[1])
  for (const [model, count] of sortedModels) {
    const pctVal = (count / roles.length) * 100
    lines.push(`  │  ${pad(model, 30)} ${count}/${roles.length} roles  ${bar(pctVal / 100, 1, 20)} ${pctVal.toFixed(0)}%`)
  }

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 5: Optimization Suggestions
// ═══════════════════════════════════════════════════════════════

function renderSuggestions(suggestions: OptimizationSuggestion[]): string {
  const lines: string[] = [header('💡 OPTIMIZATION SUGGESTIONS')]

  if (suggestions.length === 0) {
    lines.push(`\n  No suggestions yet. Run an evolution cycle to generate optimization suggestions.`)
    return lines.join('\n')
  }

  for (let i = 0; i < suggestions.length; i++) {
    const s = suggestions[i]
    const typeLabel = s.type.replace(/_/g, ' ').toUpperCase()
    const autoLabel = s.autoApplied ? '[AUTO-APPLIED]' : '[REVIEW]'

    lines.push(`\n  ┌─ Suggestion #${i + 1}  ${autoLabel}  ${typeLabel}`)
    lines.push(`  │  ${s.description}`)
    lines.push(`  │  Parameter: ${s.parameter}`)
    lines.push(`  │  Current:  ${String(s.currentValue)}  →  Suggested: ${String(s.suggestedValue)}`)
    lines.push(`  │  Expected: ${s.expectedImprovement.metric} ${s.expectedImprovement.current.toFixed(2)} → ${s.expectedImprovement.projected.toFixed(2)} (Δ${s.expectedImprovement.delta >= 0 ? '+' : ''}${s.expectedImprovement.delta.toFixed(4)})`)
    lines.push(`  │  Confidence: ${pct(s.confidence).padStart(7)}   ${bar(s.confidence, 1)}`)
    lines.push(`  │  ${timestamp(s.timestamp)}`)
  }

  // Top-level summary
  const autoApplied = suggestions.filter(s => s.autoApplied).length
  const needsReview = suggestions.filter(s => !s.autoApplied).length
  lines.push(`\n  Summary: ${autoApplied} auto-applied, ${needsReview} need review`)
  lines.push(`  Run '/meta apply' to apply all pending suggestions`)

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Panel 6: Recent Trade Log (compact)
// ═══════════════════════════════════════════════════════════════

function renderRecentTrades(trades: Array<{
  symbol: string
  direction: string
  outcome: string
  pnl: number
  pnlPct: number
  entryTimestamp: string
}>, count = 10): string {
  const lines: string[] = [header('📈 RECENT TRADES')]

  if (trades.length === 0) {
    lines.push(`\n  No trades recorded yet.`)
    return lines.join('\n')
  }

  const recent = trades.slice(-count).reverse()

  lines.push(`\n  #    Symbol   Dir     Outcome     P&L          P&L%      Entry`)
  lines.push(`  ${'─'.repeat(72)}`)

  for (let i = 0; i < recent.length; i++) {
    const t = recent[i]
    const outcomeIcon = t.outcome === 'WIN' ? '🟢 WIN ' : t.outcome === 'LOSS' ? '🔴 LOSS' : '⚪ EVEN'
    const pnlColor = t.pnl >= 0 ? '+' : ''
    lines.push(
      `  ${(i + 1).toString().padStart(3)}  ${pad(t.symbol, 6)}  ${pad(t.direction, 6)}  ${outcomeIcon}   ${pnlColor}${usd(t.pnl).padStart(10)}  ${fixed(t.pnlPct, 2)}%`.padEnd(54) + `  ${timestamp(t.entryTimestamp)}`
    )
  }

  // Summary of shown
  const shown = recent
  const shownWins = shown.filter(t => t.outcome === 'WIN').length
  const shownPnl = shown.reduce((s, t) => s + t.pnl, 0)
  lines.push(`  ${'─'.repeat(72)}`)
  lines.push(`  Last ${shown.length} trades: ${shownWins}W/${shown.length - shownWins}L   P&L: ${usd(shownPnl)}`)

  return lines.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Main Dashboard Renderer
// ═══════════════════════════════════════════════════════════════

export interface DashboardOptions {
  /** Which panels to show (default: all) */
  panels?: ('overview' | 'agents' | 'ga' | 'bandit' | 'suggestions' | 'trades')[]
  /** Show extended details */
  verbose?: boolean
  /** Number of recent trades to show */
  tradeCount?: number
}

export function renderMetaDashboard(
  pipeline: MetaLearningPipeline,
  options: DashboardOptions = {}
): string {
  const panels = options.panels || ['overview', 'agents', 'ga', 'bandit', 'suggestions']
  const tradeCount = options.tradeCount ?? 10

  const status = pipeline.getStatus()
  const metrics = status.currentMetrics
  const tracker = pipeline.getTracker()
  const ga = pipeline.getGA()
  const modelRouter = pipeline.getModelRouter()

  // Gather data
  const recordCounts = tracker.getRecordCounts()
  const population = ga.getPopulation()
  const banditSummary = modelRouter.getBanditSummary()
  const tradeRecords = tracker.getTradeRecords()

  // Build suggestions from status (last evolution suggestions aren't stored, show placeholder)
  const suggestions: OptimizationSuggestion[] = []

  // If there are evolved weights, show them as suggestions
  const evolvedWeights = pipeline.getEvolvedWeights()
  if (evolvedWeights && metrics) {
    for (const [role, weight] of Object.entries(evolvedWeights)) {
      const currentWeight = metrics.agentMetrics[role as AgentTradingRole]?.evolvedWeight ?? 0.5
      if (Math.abs(weight - currentWeight) > 0.02) {
        suggestions.push({
          id: `sug-${role}-weight`,
          type: 'weight_update',
          description: `Adjust ${AGENT_LABELS[role as AgentTradingRole] || role} voting weight from ${currentWeight.toFixed(2)} to ${weight.toFixed(2)}`,
          parameter: `${role}.performanceWeight`,
          currentValue: currentWeight,
          suggestedValue: weight,
          expectedImprovement: {
            metric: 'sharpeRatio',
            current: metrics.sharpeRatio,
            projected: metrics.sharpeRatio * 1.01,
            delta: metrics.sharpeRatio * 0.01,
          },
          confidence: 0.6,
          autoApplied: false,
          timestamp: new Date().toISOString(),
        })
      }
    }
  }

  const recommendedModels = pipeline.getRecommendedModels()
  for (const [role, rec] of Object.entries(recommendedModels)) {
    const dominant = banditSummary.dominantModels[role as AgentTradingRole]
    if (dominant && dominant !== 'unknown') {
      suggestions.push({
        id: `sug-${role}-model`,
        type: 'model_switch',
        description: `Route ${AGENT_LABELS[role as AgentTradingRole] || role} to ${rec.provider}/${rec.model} (bandit recommends, current dominant: ${dominant})`,
        parameter: `${role}.llmModel`,
        currentValue: dominant,
        suggestedValue: `${rec.provider}/${rec.model}`,
        expectedImprovement: {
          metric: 'latency',
          current: 0,
          projected: 0,
          delta: 0,
        },
        confidence: 0.55,
        autoApplied: false,
        timestamp: new Date().toISOString(),
      })
    }
  }

  // Render
  const output: string[] = []

  if (panels.includes('overview')) {
    output.push(renderOverview(status, metrics, recordCounts.trades, recordCounts.debates))
  }

  if (panels.includes('agents')) {
    output.push(renderAgentPerformance(metrics))
  }

  if (panels.includes('ga')) {
    // GA doesn't store active result - we show population state
    output.push(renderGAFitness(null, population.length > 0 ? population : undefined))
  }

  if (panels.includes('bandit')) {
    output.push(renderBanditDominance(banditSummary))
  }

  if (panels.includes('suggestions')) {
    output.push(renderSuggestions(suggestions))
  }

  if (panels.includes('trades')) {
    const formattedTrades = tradeRecords.map(t => ({
      symbol: t.symbol,
      direction: t.direction,
      outcome: t.outcome,
      pnl: t.pnl,
      pnlPct: t.pnlPct,
      entryTimestamp: t.entryTimestamp,
    }))
    output.push(renderRecentTrades(formattedTrades, tradeCount))
  }

  // Footer
  output.push(`\n${'═'.repeat(64)}`)
  output.push(`  Meta-Learning Pipeline ${status.running ? '🟢 Active' : '🔴 Inactive'}  |  Type '/meta help' for commands`)
  output.push(`${'═'.repeat(64)}\n`)

  return output.join('\n')
}

// ═══════════════════════════════════════════════════════════════
// Compact One-Line Status (for quick CLI glance)
// ═══════════════════════════════════════════════════════════════

export function renderMetaStatusLine(pipeline: MetaLearningPipeline): string {
  const status = pipeline.getStatus()
  const metrics = status.currentMetrics
  const tracker = pipeline.getTracker()
  const counts = tracker.getRecordCounts()

  const parts: string[] = []
  parts.push(status.running ? '🟢' : '🔴')
  parts.push(`Gen:${status.generationCount}`)
  parts.push(`Debates:${counts.debates}`)
  parts.push(`Trades:${counts.trades}`)

  if (metrics) {
    parts.push(`WR:${pct(metrics.winRate)}`)
    parts.push(`Sharpe:${fixed(metrics.sharpeRatio)}`)
    parts.push(`P&L:${usd(metrics.cumulativePnl)}`)
    parts.push(`DD:${fixed(metrics.maxDrawdownPct, 1)}%`)
  }

  if (status.lastEvolution) {
    parts.push(`LastEvo:${timestamp(status.lastEvolution.timestamp)}`)
  }

  return `[Meta] ${parts.join(' | ')}`
}
