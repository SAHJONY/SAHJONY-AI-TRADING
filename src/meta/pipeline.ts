/**
 * Layer 5 — Meta-Learning Pipeline Orchestrator
 *
 * Ties together all Layer 5 components into a self-evolving system:
 * - Performance tracking (continuous)
 * - Model routing via multi-armed bandit (per-analysis)
 * - Genetic algorithm evolution (periodic/weekly)
 * - Prompt optimization (periodic/biweekly)
 * - Backtesting (on trigger: evolution, manual, degradation)
 *
 * Integration with Layer 4:
 *   The workforce emits events (debateStarted, debateComplete, orderExecuted).
 *   The MetaLearningPipeline listens to these to record performance data and
 *   update bandit rewards. Periodically (or on trigger), it runs evolution
 *   and pushes updated weights/thresholds/prompts back to the workforce.
 */

import { EventEmitter } from 'events'
import { createHash } from 'crypto'
import * as path from 'path'
import * as fs from 'fs'
import {
  MetaLearningConfig,
  MetaLearningStatus,
  EvolutionTrigger,
  OptimizationSuggestion,
  AgentTradingRole,
  DebateRecord,
  TradeOutcomeRecord,
  ModelReward,
  SystemPerformanceMetrics,
} from './types'
import { PerformanceTracker } from './performance-tracker'
import { StrategyGA } from './strategy-ga'
import { PromptOptimizer } from './prompt-optimizer'
import { ModelRouter } from './model-router'
import { BacktestEngine } from './backtest-engine'
import { AgentAnalysis, FinalDecision } from '../trading/types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_META_CONFIG: MetaLearningConfig = {
  ga: {
    populationSize: 50,
    generations: 20,
    eliteCount: 5,
    crossoverRate: 0.8,
    mutationRate: 0.1,
    tournamentSize: 3,
    fitnessWeights: {
      sharpe: 0.30,
      winRate: 0.20,
      totalPnl: 0.15,
      maxDrawdown: 0.15,
      profitFactor: 0.10,
      decisionSpeed: 0.10,
    },
    minSamples: 50,
    persist: true,
    persistDir: path.resolve(process.cwd(), 'data', 'meta-learning', 'ga'),
  },
  genePool: {
    agentWeights: {
      macro_strategist: { min: 0.1, max: 1.0, step: 0.05 },
      sector_analyst: { min: 0.1, max: 1.0, step: 0.05 },
      sentiment_agent: { min: 0.1, max: 1.0, step: 0.05 },
      technical_analyst: { min: 0.1, max: 1.0, step: 0.05 },
      risk_manager: { min: 0.1, max: 1.0, step: 0.05 },
      execution_optimizer: { min: 0.1, max: 1.0, step: 0.05 },
    },
    debate: {
      maxRounds: { min: 2, max: 5, step: 1 },
      consensusThreshold: { min: 0.4, max: 0.85, step: 0.05 },
      timeoutMs: { min: 30_000, max: 300_000, step: 10_000 },
    },
    risk: {
      maxPositionSizePct: { min: 0.05, max: 0.50, step: 0.05 },
      minConfidenceForAuto: { min: 0.5, max: 0.9, step: 0.05 },
    },
    llm: {
      macro_strategist: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
      sector_analyst: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
      sentiment_agent: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
      technical_analyst: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
      risk_manager: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
      execution_optimizer: { temperature: { min: 0, max: 1, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    },
  },
  bandit: {
    strategy: 'ucb1',
    epsilon: 0.1,
    epsilonDecay: 0.995,
    ucbC: 2.0,
    warmupPulls: 5,
    rewardWeights: {
      directionalAccuracy: 0.50,
      reasoningQuality: 0.20,
      latencyScore: 0.15,
      costEfficiency: 0.15,
    },
  },
  backtest: {
    symbols: [],
    startDate: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    endDate: new Date().toISOString(),
    timeframe: '1d',
    initialEquity: 100_000,
    commissionBps: 1,
    slippageBps: 2,
    walkForward: false,
    walkForwardWindowDays: 60,
    outOfSampleDays: 20,
  },
  promptOptimization: {
    minEvaluations: 20,
    maxFewShotExamples: 4,
    positiveExamplesOnly: true,
    mutationIterations: 5,
  },
  schedule: {
    evolutionCron: '0 0 * * 0', // Weekly on Sunday midnight
    evolutionSampleThreshold: 100,
    sharpeDegradationThreshold: -0.5,
    drawdownTriggerPct: 15,
  },
  retention: {
    maxDebateRecords: 10_000,
    maxTradeRecords: 50_000,
    persistRecords: true,
    persistDir: path.resolve(process.cwd(), 'data', 'meta-learning'),
  },
}

// ═══════════════════════════════════════════════════════════════
// Meta-Learning Pipeline
// ═══════════════════════════════════════════════════════════════

export class MetaLearningPipeline extends EventEmitter {
  private config: MetaLearningConfig

  // Sub-components
  private tracker: PerformanceTracker
  private ga: StrategyGA
  private promptOptimizer: PromptOptimizer
  private modelRouter: ModelRouter
  private backtestEngine: BacktestEngine

  // State
  private status: MetaLearningStatus
  private running = false
  private cronInterval: NodeJS.Timeout | null = null

  // Cache for prompt text hashing
  private promptTexts: Map<AgentTradingRole, string> = new Map()

  constructor(config: Partial<MetaLearningConfig> = {}) {
    super()
    this.config = { ...DEFAULT_META_CONFIG, ...config }

    // Initialize sub-components
    this.tracker = new PerformanceTracker({
      maxDebateRecords: this.config.retention.maxDebateRecords,
      maxTradeRecords: this.config.retention.maxTradeRecords,
      persistRecords: this.config.retention.persistRecords,
      persistDir: this.config.retention.persistDir,
    })

    this.ga = new StrategyGA(this.config.ga, this.config.genePool, this.tracker)
    this.promptOptimizer = new PromptOptimizer(this.config.promptOptimization, this.tracker)
    this.modelRouter = new ModelRouter(this.config.bandit)
    this.backtestEngine = new BacktestEngine(this.config.backtest)

    // Load persisted state
    this.modelRouter.initialize()
    this.promptOptimizer.loadVariants()

    this.status = {
      running: false,
      banditState: {
        totalPulls: 0,
        dominantModels: {} as Record<AgentTradingRole, string>,
      },
      generationCount: 0,
      promptVersionCount: 0,
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Lifecycle
  // ═══════════════════════════════════════════════════════════════

  /**
   * Start the meta-learning pipeline.
   */
  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    this.status.running = true

    console.log('[MetaLearning] Starting pipeline...')

    // Schedule periodic evolution
    try {
      const cron = require('node-cron')
      this.cronInterval = cron.schedule(this.config.schedule.evolutionCron, async () => {
        console.log('[MetaLearning] Cron-triggered evolution')
        await this.triggerEvolution('schedule')
      })
    } catch {
      // Fallback: weekly interval
      this.cronInterval = setInterval(
        () => this.triggerEvolution('schedule'),
        7 * 24 * 60 * 60 * 1000
      )
    }

    this.emit('started')
    console.log('[MetaLearning] Pipeline started')
  }

  /**
   * Stop the pipeline gracefully.
   */
  async stop(): Promise<void> {
    this.running = false
    this.status.running = false

    if (this.cronInterval) {
      clearInterval(this.cronInterval)
      this.cronInterval = null
    }

    await this.tracker.shutdown()
    this.emit('stopped')
    console.log('[MetaLearning] Pipeline stopped')
  }

  // ═══════════════════════════════════════════════════════════════
  // Event Handlers (integrate with Layer 4 Workforce)
  // ═══════════════════════════════════════════════════════════════

  /**
   * Called by the TradingWorkforce after each debate completes.
   * Records the debate for performance tracking and triggers
   * sample-threshold-based evolution if enough new data is available.
   */
  onDebateComplete(record: DebateRecord): void {
    this.tracker.recordDebate(record)

    // Check if we should trigger evolution based on sample count
    const tradeCount = this.tracker.getRecordCounts().trades
    if (
      tradeCount >= this.config.schedule.evolutionSampleThreshold &&
      tradeCount % this.config.schedule.evolutionSampleThreshold === 0
    ) {
      this.triggerEvolution('sample_count').catch(err =>
        console.error('[MetaLearning] Evolution trigger failed:', err)
      )
    }
  }

  /**
   * Called by the TradingWorkforce when a trade is executed.
   * Records the outcome for performance tracking.
   */
  onTradeExecuted(outcome: TradeOutcomeRecord): void {
    this.tracker.recordTradeOutcome(outcome)
  }

  /**
   * Called after each agent produces its analysis in a debate.
   * Updates the multi-armed bandit with reward data for model selection.
   *
   * @param debateId - The session ID of the debate this analysis belongs to,
   *   required to look up the correct debate for reward computation.
   */
  onAgentAnalysis(
    debateId: string,
    role: AgentTradingRole,
    analysis: AgentAnalysis,
    modelProvider: 'openai' | 'anthropic',
    modelName: string,
    latencyMs: number,
    tokensUsed: number
  ): void {
    // Look up the specific debate by session ID (avoids race condition
    // when multiple debates run concurrently)
    const debates = this.tracker.getDebateRecords()
    const debate = debates.find(d => d.sessionId === debateId)
    if (!debate) return

    const reward = this.tracker.computeModelReward(analysis, debate, latencyMs, tokensUsed)

    // Find the arm for this provider/model/role
    const bandit = this.modelRouter.getBandit(role)
    if (!bandit) return

    const arm = bandit.arms.find(
      a => a.provider === modelProvider && a.model === modelName
    )
    if (arm) {
      this.modelRouter.updateArm(role, arm.id, reward)
    }

    // Update prompt performance
    const promptHash = this.promptTexts.get(role)
    if (promptHash) {
      const variant = this.promptOptimizer.getVariantByHash(role, promptHash)
      if (variant) {
        const isCorrect = reward.directionalAccuracy > 0.5
        this.promptOptimizer.evaluateVariant(variant, analysis, isCorrect)
      }
    }
  }

  /**
   * Register the current prompt text for an agent role (for version tracking).
   */
  registerPrompt(role: AgentTradingRole, text: string): void {
    this.promptTexts.set(role, text)
    this.promptOptimizer.registerVariant(role, text, 'manual')
    this.status.promptVersionCount = this.promptOptimizer.getVariantCount()
  }

  // ═══════════════════════════════════════════════════════════════
  // Evolution Pipeline
  // ═══════════════════════════════════════════════════════════════

  /**
   * Trigger the full evolution pipeline:
   * 1. Compute latest performance metrics
   * 2. Run backtest for fitness evaluation
   * 3. Run genetic algorithm
   * 4. Generate optimization suggestions
   * 5. Optionally auto-apply changes
   */
  async triggerEvolution(trigger: EvolutionTrigger): Promise<{
    suggestions: OptimizationSuggestion[]
    gaResult: Awaited<ReturnType<StrategyGA['evolve']>>
    backtestResult: Awaited<ReturnType<BacktestEngine['run']>>
  }> {
    console.log(`[MetaLearning] Triggering evolution (${trigger})...`)
    const startTime = Date.now()

    // 1. Compute latest metrics
    const metrics = this.tracker.computeMetrics()

    // 2. Run backtest
    const backtestResult = await this.backtestEngine.run(this.tracker)

    // 3. Run genetic algorithm
    let gaResult
    try {
      const existingPopulation = this.ga.loadPopulation()
      gaResult = await this.ga.evolve(existingPopulation ?? undefined)
    } catch (err) {
      console.error('[MetaLearning] GA evolution failed:', err)
      gaResult = null
    }

    // 4. Generate suggestions
    const suggestions = gaResult
      ? this.generateSuggestions(gaResult, metrics, trigger)
      : []

    // 5. Update status
    this.status.lastEvolution = {
      timestamp: new Date().toISOString(),
      trigger,
      generationsCompleted: gaResult?.generations ?? 0,
      bestFitness: gaResult?.bestChromosome?.fitness ?? 0,
      fitnessDelta: gaResult?.fitnessHistory?.length
        ? gaResult.fitnessHistory[gaResult.fitnessHistory.length - 1].best -
          gaResult.fitnessHistory[0].best
        : 0,
    }
    this.status.generationCount = this.ga.getGeneration()

    const duration = Date.now() - startTime
    console.log(`[MetaLearning] Evolution complete in ${duration}ms. Best fitness: ${gaResult?.bestChromosome?.fitness?.toFixed(4) ?? 'N/A'}`)

    this.emit('evolutionComplete', {
      trigger,
      suggestions: suggestions.length,
      bestFitness: gaResult?.bestChromosome?.fitness,
      durationMs: duration,
    })

    return {
      suggestions,
      gaResult: gaResult!,
      backtestResult,
    }
  }

  /**
   * Run prompt optimization for all agent roles.
   */
  async optimizePrompts(
    basePrompts: Record<AgentTradingRole, string>
  ): Promise<Map<AgentTradingRole, any>> {
    console.log('[MetaLearning] Starting prompt optimization...')
    const results = await this.promptOptimizer.optimizeAll(basePrompts)

    this.status.lastPromptOptimization = {
      timestamp: new Date().toISOString(),
      rolesOptimized: Array.from(results.keys()),
      avgAccuracyImprovement: Array.from(results.values()).reduce(
        (sum, r) => sum + r.improvement.accuracyDelta, 0
      ) / results.size,
    }

    this.status.promptVersionCount = this.promptOptimizer.getVariantCount()

    this.emit('promptOptimizationComplete', {
      rolesOptimized: results.size,
    })

    return results
  }

  // ═══════════════════════════════════════════════════════════════
  // Suggestions & Auto-Apply
  // ═══════════════════════════════════════════════════════════════

  /**
   * Generate optimization suggestions from GA results.
   */
  private generateSuggestions(
    gaResult: Awaited<ReturnType<StrategyGA['evolve']>>,
    metrics: SystemPerformanceMetrics,
    trigger: EvolutionTrigger
  ): OptimizationSuggestion[] {
    const suggestions: OptimizationSuggestion[] = []
    const bestChromosome = gaResult.bestChromosome
    const params = this.ga.chromosomeToParams(bestChromosome)
    const weights = this.ga.extractAgentWeights(bestChromosome)

    // Agent weight suggestions
    for (const [role, weight] of Object.entries(weights)) {
      const currentWeight = metrics.agentMetrics[role as AgentTradingRole]?.evolvedWeight ?? 0.5
      const delta = Math.abs((weight as number) - currentWeight)

      if (delta > 0.05) {
        suggestions.push({
          id: `sug-${role}-weight`,
          type: 'weight_update',
          description: `Adjust ${role} voting weight from ${currentWeight.toFixed(2)} to ${(weight as number).toFixed(2)} based on evolved performance`,
          parameter: `${role}.performanceWeight`,
          currentValue: currentWeight,
          suggestedValue: weight as number,
          expectedImprovement: {
            metric: 'sharpeRatio',
            current: metrics.sharpeRatio,
            projected: metrics.sharpeRatio * (1 + delta * 0.1),
            delta: metrics.sharpeRatio * delta * 0.1,
          },
          confidence: Math.min(0.95, 0.5 + gaResult.bestChromosome.fitness),
          autoApplied: trigger === 'schedule' && gaResult.bestChromosome.fitness > 0.7,
          timestamp: new Date().toISOString(),
        })
      }
    }

    // Debate threshold suggestions
    const consensusThreshold = params['debate.consensusThreshold'] as number
    if (consensusThreshold !== undefined) {
      suggestions.push({
        id: 'sug-consensus-threshold',
        type: 'threshold_update',
        description: `Adjust consensus threshold to ${consensusThreshold.toFixed(2)}`,
        parameter: 'debate.consensusThreshold',
        currentValue: 0.6,
        suggestedValue: consensusThreshold,
        expectedImprovement: {
          metric: 'winRate',
          current: metrics.winRate,
          projected: Math.min(1, metrics.winRate + 0.02),
          delta: 0.02,
        },
        confidence: 0.6,
        autoApplied: false,
        timestamp: new Date().toISOString(),
      })
    }

    // Risk threshold suggestions
    const maxPosition = params['risk.maxPositionSizePct'] as number
    if (maxPosition !== undefined) {
      suggestions.push({
        id: 'sug-max-position',
        type: 'threshold_update',
        description: `Adjust max position size to ${((maxPosition as number) * 100).toFixed(0)}%`,
        parameter: 'risk.maxPositionSizePct',
        currentValue: 0.25,
        suggestedValue: maxPosition,
        expectedImprovement: {
          metric: 'maxDrawdown',
          current: metrics.maxDrawdownPct,
          projected: metrics.maxDrawdownPct * 0.9,
          delta: -metrics.maxDrawdownPct * 0.1,
        },
        confidence: 0.65,
        autoApplied: trigger === 'drawdown',
        timestamp: new Date().toISOString(),
      })
    }

    return suggestions
  }

  /**
   * Get the evolved agent weights from the best chromosome.
   */
  getEvolvedWeights(): Record<string, number> | null {
    const population = this.ga.getPopulation()
    if (population.length === 0) return null

    const best = population.reduce((a, b) => a.fitness > b.fitness ? a : b)
    return this.ga.extractAgentWeights(best)
  }

  /**
   * Get the recommended model for each agent role from the bandit.
   */
  getRecommendedModels(): Record<AgentTradingRole, { provider: string; model: string }> {
    return this.modelRouter.getBestArms()
  }

  /**
   * Select the best model for a given agent role (bandit-driven).
   */
  selectModel(role: AgentTradingRole): { provider: string; model: string } {
    const arm = this.modelRouter.selectArm(role)
    return { provider: arm.provider, model: arm.model }
  }

  // ═══════════════════════════════════════════════════════════════
  // Manual Triggers & Status
  // ═══════════════════════════════════════════════════════════════

  /**
   * Manually trigger evolution.
   */
  async evolve(): Promise<Awaited<ReturnType<typeof this.triggerEvolution>>> {
    return this.triggerEvolution('manual')
  }

  /**
   * Trigger evolution due to drawdown breach.
   */
  async evolveOnDrawdown(): Promise<Awaited<ReturnType<typeof this.triggerEvolution>>> {
    return this.triggerEvolution('drawdown')
  }

  /**
   * Trigger evolution due to performance degradation.
   */
  async evolveOnDegradation(): Promise<Awaited<ReturnType<typeof this.triggerEvolution>>> {
    return this.triggerEvolution('performance_degradation')
  }

  /**
   * Run a backtest with current parameters.
   */
  async backtest(): Promise<Awaited<ReturnType<BacktestEngine['run']>>> {
    return this.backtestEngine.run(this.tracker)
  }

  /**
   * Run walk-forward backtest.
   */
  async walkForwardBacktest(): Promise<Awaited<ReturnType<BacktestEngine['runWalkForward']>>> {
    return this.backtestEngine.runWalkForward(this.tracker)
  }

  // ═══════════════════════════════════════════════════════════════
  // Accessors
  // ═══════════════════════════════════════════════════════════════

  getStatus(): MetaLearningStatus {
    // Update live stats
    this.status.currentMetrics = this.tracker.getMetrics() ?? undefined
    this.status.banditState = {
      totalPulls: this.modelRouter.getBanditSummary().totalPulls,
      dominantModels: this.modelRouter.getBanditSummary().dominantModels,
    }
    this.status.generationCount = this.ga.getGeneration()
    this.status.promptVersionCount = this.promptOptimizer.getVariantCount()
    return { ...this.status }
  }

  getTracker(): PerformanceTracker {
    return this.tracker
  }

  getGA(): StrategyGA {
    return this.ga
  }

  getModelRouter(): ModelRouter {
    return this.modelRouter
  }

  getPromptOptimizer(): PromptOptimizer {
    return this.promptOptimizer
  }

  getBacktestEngine(): BacktestEngine {
    return this.backtestEngine
  }

  isRunning(): boolean {
    return this.running
  }

  getConfig(): MetaLearningConfig {
    return { ...this.config }
  }
}
