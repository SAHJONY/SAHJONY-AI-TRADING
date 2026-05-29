/**
 * Layer 5 — Strategy Genetic Algorithm
 *
 * Evolves trading strategy parameters using a genetic algorithm:
 * agent weights, debate thresholds, risk parameters, LLM temperatures.
 *
 * Chromosome design:
 *   genes = [macroWeight, sectorWeight, sentimentWeight, technicalWeight,
 *            riskWeight, executionWeight, consensusThreshold, maxRounds,
 *            maxPositionSize, minConfidenceForAuto, ...LLM temperatures...]
 *
 * Fitness function: weighted combination of Sharpe, win rate, total P&L,
 *   max drawdown penalty, profit factor, and decision speed.
 *
 * Operators: tournament selection, uniform crossover, gaussian mutation
 *   (for float genes), bit-flip (for boolean), uniform (for categorical).
 */

import { v4 as uuid } from 'uuid'
import * as path from 'path'
import * as fs from 'fs'
import {
  Gene,
  GenePool,
  GeneValue,
  StrategyChromosome,
  GAConfig,
  GARunResult,
  DebateRecord,
} from './types'
import { PerformanceTracker } from './performance-tracker'

// ═══════════════════════════════════════════════════════════════
// Default GA Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_GA_CONFIG: GAConfig = {
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
}

// ═══════════════════════════════════════════════════════════════
// Default Gene Pool
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_GENE_POOL: GenePool = {
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
    macro_strategist: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    sector_analyst: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    sentiment_agent: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    technical_analyst: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    risk_manager: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
    execution_optimizer: { temperature: { min: 0.0, max: 1.0, step: 0.1 }, provider: { options: ['openai', 'anthropic'] } },
  },
}

// ═══════════════════════════════════════════════════════════════
// Strategy GA Engine
// ═══════════════════════════════════════════════════════════════

export class StrategyGA {
  private config: GAConfig
  private genePool: GenePool
  private population: StrategyChromosome[] = []
  private generation = 0
  private tracker: PerformanceTracker

  constructor(
    config: Partial<GAConfig> = {},
    genePool?: Partial<GenePool>,
    tracker?: PerformanceTracker
  ) {
    this.config = { ...DEFAULT_GA_CONFIG, ...config }
    this.genePool = { ...DEFAULT_GENE_POOL, ...genePool }
    this.tracker = tracker ?? new PerformanceTracker()

    if (this.config.persist) {
      fs.mkdirSync(this.config.persistDir, { recursive: true })
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Initialization
  // ═══════════════════════════════════════════════════════════

  /**
   * Build the full gene list from the gene pool.
   */
  buildGenes(): Gene[] {
    const genes: Gene[] = []

    // Agent weights
    for (const [role, range] of Object.entries(this.genePool.agentWeights)) {
      genes.push({
        name: `${role}.performanceWeight`,
        value: this.randomFloat(range.min, range.max),
        type: 'float',
        constraints: { min: range.min, max: range.max, step: range.step },
        mutationRate: this.config.mutationRate,
      })
    }

    // Debate params
    genes.push({
      name: 'debate.maxRounds',
      value: this.randomInt(this.genePool.debate.maxRounds.min, this.genePool.debate.maxRounds.max),
      type: 'integer',
      constraints: {
        min: this.genePool.debate.maxRounds.min,
        max: this.genePool.debate.maxRounds.max,
        step: this.genePool.debate.maxRounds.step,
      },
      mutationRate: this.config.mutationRate * 0.5,
    })

    genes.push({
      name: 'debate.consensusThreshold',
      value: this.randomFloat(
        this.genePool.debate.consensusThreshold.min,
        this.genePool.debate.consensusThreshold.max
      ),
      type: 'float',
      constraints: {
        min: this.genePool.debate.consensusThreshold.min,
        max: this.genePool.debate.consensusThreshold.max,
        step: this.genePool.debate.consensusThreshold.step,
      },
      mutationRate: this.config.mutationRate,
    })

    genes.push({
      name: 'debate.timeoutMs',
      value: this.randomInt(this.genePool.debate.timeoutMs.min, this.genePool.debate.timeoutMs.max),
      type: 'integer',
      constraints: {
        min: this.genePool.debate.timeoutMs.min,
        max: this.genePool.debate.timeoutMs.max,
        step: this.genePool.debate.timeoutMs.step,
      },
      mutationRate: this.config.mutationRate * 0.3,
    })

    // Risk params
    genes.push({
      name: 'risk.maxPositionSizePct',
      value: this.randomFloat(
        this.genePool.risk.maxPositionSizePct.min,
        this.genePool.risk.maxPositionSizePct.max
      ),
      type: 'float',
      constraints: {
        min: this.genePool.risk.maxPositionSizePct.min,
        max: this.genePool.risk.maxPositionSizePct.max,
        step: this.genePool.risk.maxPositionSizePct.step,
      },
      mutationRate: this.config.mutationRate * 0.7,
    })

    genes.push({
      name: 'risk.minConfidenceForAuto',
      value: this.randomFloat(
        this.genePool.risk.minConfidenceForAuto.min,
        this.genePool.risk.minConfidenceForAuto.max
      ),
      type: 'float',
      constraints: {
        min: this.genePool.risk.minConfidenceForAuto.min,
        max: this.genePool.risk.minConfidenceForAuto.max,
        step: this.genePool.risk.minConfidenceForAuto.step,
      },
      mutationRate: this.config.mutationRate,
    })

    // LLM temperatures per role
    for (const [role, llmConfig] of Object.entries(this.genePool.llm)) {
      genes.push({
        name: `${role}.temperature`,
        value: this.randomFloat(llmConfig.temperature.min, llmConfig.temperature.max),
        type: 'float',
        constraints: {
          min: llmConfig.temperature.min,
          max: llmConfig.temperature.max,
          step: llmConfig.temperature.step,
        },
        mutationRate: this.config.mutationRate,
      })

      genes.push({
        name: `${role}.provider`,
        value: llmConfig.provider.options[
          Math.floor(Math.random() * llmConfig.provider.options.length)
        ],
        type: 'categorical',
        constraints: { options: llmConfig.provider.options },
        mutationRate: this.config.mutationRate * 0.5,
      })
    }

    return genes
  }

  /**
   * Create a random chromosome.
   */
  createRandomChromosome(): StrategyChromosome {
    return {
      id: uuid(),
      genes: this.buildGenes(),
      fitness: 0,
      generation: 0,
      parents: [],
      createdAt: new Date().toISOString(),
    }
  }

  /**
   * Initialize the population.
   */
  initializePopulation(): void {
    this.population = []
    for (let i = 0; i < this.config.populationSize; i++) {
      this.population.push(this.createRandomChromosome())
    }
    this.generation = 0
  }

  // ═══════════════════════════════════════════════════════════
  // Fitness Evaluation (the hard part — requires backtest data)
  // ═══════════════════════════════════════════════════════════

  /**
   * Evaluate fitness of a chromosome against historical outcomes.
   *
   * Each chromosome represents a strategy configuration. We estimate how
   * that strategy would have performed by:
   * 1. Re-weighting agent votes in historical debates using the chromosome's weights
   * 2. Computing a chromosome-specific theoretical win rate
   * 3. Combining with system-level metrics (Sharpe, drawdown) for stability
   *
   * This ensures different chromosomes get different fitness scores.
   */
  evaluateFitness(chromosome: StrategyChromosome): number {
    const trades = this.tracker.getTradeRecords()
    const debates = this.tracker.getDebateRecords()

    if (trades.length < this.config.minSamples) {
      return 0
    }

    // Extract chromosome parameters
    const weights = this.extractAgentWeights(chromosome)

    // Build debate → trade mapping for outcome lookups
    const tradeBySession = new Map(
      trades.filter(t => t.outcome !== 'PENDING').map(t => [t.debateSessionId, t])
    )

    // ── Chromosome-specific weighted accuracy ──
    // For each debate, compute what the consensus would have been
    // with this chromosome's agent weights, then check if it matched
    // the winning trade direction.
    let correctConsensus = 0
    let totalEvaluated = 0
    let weightedPnlSum = 0

    for (const debate of debates) {
      const trade = tradeBySession.get(debate.sessionId)
      if (!trade) continue

      const { consensusDirection, weightedConfidence } =
        this.simulateConsensus(debate, weights)

      // Was this chromosome's consensus correct?
      const isCorrect =
        (consensusDirection === trade.direction && trade.outcome === 'WIN') ||
        (consensusDirection !== trade.direction && trade.outcome === 'LOSS') ||
        consensusDirection === 'NEUTRAL'

      if (consensusDirection !== 'NEUTRAL') {
        if (isCorrect) correctConsensus++
        totalEvaluated++
        weightedPnlSum += isCorrect ? trade.pnl * weightedConfidence : trade.pnl * -0.5
      }
    }

    const chromosomeWinRate = totalEvaluated > 0 ? correctConsensus / totalEvaluated : 0.5
    const chromosomePnlScore = totalEvaluated > 0
      ? Math.tanh(weightedPnlSum / 50_000) * 0.5 + 0.5  // Normalize to 0–1
      : 0.5

    // ── System base metrics (same across chromosomes, provides stability) ──
    const metrics = this.tracker.getMetrics()
    const fw = this.config.fitnessWeights

    let fitness = 0

    // Sharpe from system metrics (stability anchor)
    fitness += fw.sharpe * 0.3 * Math.max(0, Math.min(1, (metrics?.sharpeRatio ?? 0 + 2) / 5))

    // Chromosome-specific win rate (primary differentiator)
    fitness += fw.winRate * chromosomeWinRate

    // Chromosome-specific P&L score
    fitness += fw.totalPnl * 0.5 * chromosomePnlScore

    // System P&L (stability)
    if (metrics) {
      fitness += fw.totalPnl * 0.5 * Math.max(0, Math.min(1, metrics.cumulativePnl / 100_000))
    }

    // Drawdown penalty from system (stability)
    const ddPenalty = metrics ? 1 - Math.min(1, metrics.maxDrawdownPct / 30) : 0.5
    fitness += fw.maxDrawdown * ddPenalty

    // Profit factor from system (stability)
    if (metrics) {
      const pfScore = Math.min(1, metrics.profitFactor / 3)
      fitness += fw.profitFactor * pfScore
    }

    // Decision speed (fewer rounds = higher score)
    const speedScore = metrics ? Math.max(0, 1 - metrics.avgRoundsPerDebate / 5) : 0.5
    fitness += fw.decisionSpeed * speedScore

    return Math.max(0, fitness)
  }

  /**
   * Simulate what the consensus would be with a given set of agent weights.
   */
  private simulateConsensus(
    debate: DebateRecord,
    weights: Record<string, number>
  ): { consensusDirection: 'LONG' | 'SHORT' | 'NEUTRAL'; weightedConfidence: number } {
    let longScore = 0
    let shortScore = 0
    let totalWeight = 0

    for (const analysis of debate.agentAnalyses) {
      const w = weights[analysis.role] ?? 0.5
      const rec = analysis.recommendation

      let directionMultiplier = 0
      if (rec === 'STRONG_BUY') directionMultiplier = 1.0
      else if (rec === 'BUY') directionMultiplier = 0.5
      else if (rec === 'SELL') directionMultiplier = -0.5
      else if (rec === 'STRONG_SELL') directionMultiplier = -1.0
      // HOLD → 0

      if (directionMultiplier > 0) {
        longScore += w * directionMultiplier * analysis.confidence
      } else if (directionMultiplier < 0) {
        shortScore += w * Math.abs(directionMultiplier) * analysis.confidence
      }
      totalWeight += w
    }

    // Normalize
    const normLong = totalWeight > 0 ? longScore / totalWeight : 0
    const normShort = totalWeight > 0 ? shortScore / totalWeight : 0
    const netSignal = normLong - normShort

    let consensusDirection: 'LONG' | 'SHORT' | 'NEUTRAL'
    if (netSignal > 0.15) consensusDirection = 'LONG'
    else if (netSignal < -0.15) consensusDirection = 'SHORT'
    else consensusDirection = 'NEUTRAL'

    return {
      consensusDirection,
      weightedConfidence: Math.abs(netSignal),
    }
  }

  /**
   * Evaluate fitness for all chromosomes in the population.
   */
  evaluatePopulation(): void {
    for (const chromosome of this.population) {
      chromosome.fitness = this.evaluateFitness(chromosome)
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Selection
  // ═══════════════════════════════════════════════════════════════

  /**
   * Tournament selection: pick N random chromosomes, return the fittest.
   */
  tournamentSelect(): StrategyChromosome {
    const tournament: StrategyChromosome[] = []
    const pool = [...this.population]

    for (let i = 0; i < this.config.tournamentSize; i++) {
      const idx = Math.floor(Math.random() * pool.length)
      tournament.push(pool[idx])
      pool.splice(idx, 1)
    }

    return tournament.reduce((best, cur) =>
      cur.fitness > best.fitness ? cur : best
    )
  }

  // ═══════════════════════════════════════════════════════════
  // Crossover
  // ═══════════════════════════════════════════════════════════════

  /**
   * Uniform crossover: each gene is randomly chosen from parent A or B.
   */
  crossover(parentA: StrategyChromosome, parentB: StrategyChromosome): [StrategyChromosome, StrategyChromosome] {
    if (Math.random() > this.config.crossoverRate) {
      return [this.cloneChromosome(parentA), this.cloneChromosome(parentB)]
    }

    const childAGenes: Gene[] = []
    const childBGenes: Gene[] = []

    for (let i = 0; i < parentA.genes.length; i++) {
      if (Math.random() < 0.5) {
        childAGenes.push({ ...parentA.genes[i] })
        childBGenes.push({ ...parentB.genes[i] })
      } else {
        childAGenes.push({ ...parentB.genes[i] })
        childBGenes.push({ ...parentA.genes[i] })
      }
    }

    return [
      {
        id: uuid(),
        genes: childAGenes,
        fitness: 0,
        generation: this.generation + 1,
        parents: [parentA.id, parentB.id],
        createdAt: new Date().toISOString(),
      },
      {
        id: uuid(),
        genes: childBGenes,
        fitness: 0,
        generation: this.generation + 1,
        parents: [parentA.id, parentB.id],
        createdAt: new Date().toISOString(),
      },
    ]
  }

  // ═══════════════════════════════════════════════════════════
  // Mutation
  // ═══════════════════════════════════════════════════════════════

  /**
   * Mutate a chromosome in-place.
   */
  mutate(chromosome: StrategyChromosome): void {
    for (const gene of chromosome.genes) {
      if (Math.random() > gene.mutationRate) continue

      switch (gene.type) {
        case 'float':
          gene.value = this.mutateFloat(gene.value as number, gene.constraints)
          break
        case 'integer':
          gene.value = this.mutateInt(gene.value as number, gene.constraints)
          break
        case 'boolean':
          gene.value = !gene.value
          break
        case 'categorical':
          gene.value = this.mutateCategorical(gene.value as string, gene.constraints)
          break
      }
    }
  }

  private mutateFloat(value: number, constraints: Gene['constraints']): number {
    const { min = 0, max = 1, step = 0.05 } = constraints
    // Gaussian mutation scaled by range
    const range = max - min
    const gaussian = this.randomGaussian() * range * 0.1
    let newValue = value + gaussian
    // Clamp
    newValue = Math.max(min, Math.min(max, newValue))
    // Snap to step
    if (step > 0) {
      newValue = Math.round(newValue / step) * step
    }
    return Math.max(min, Math.min(max, newValue))
  }

  private mutateInt(value: number, constraints: Gene['constraints']): number {
    const { min = 0, max = 100, step = 1 } = constraints
    const delta = Math.random() < 0.5 ? -step : step
    let newValue = value + delta
    return Math.max(min, Math.min(max, newValue))
  }

  private mutateCategorical(value: string, constraints: Gene['constraints']): string {
    const options = constraints.options || [value]
    const currentIdx = options.indexOf(value)
    const otherOptions = options.filter((_, i) => i !== currentIdx)
    if (otherOptions.length === 0) return value
    return otherOptions[Math.floor(Math.random() * otherOptions.length)]
  }

  // ═══════════════════════════════════════════════════════════
  // Evolution Loop
  // ═══════════════════════════════════════════════════════════════

  /**
   * Run the full genetic algorithm.
   */
  async evolve(initialPopulation?: StrategyChromosome[]): Promise<GARunResult> {
    const startTime = Date.now()

    // Check minimum samples
    const trades = this.tracker.getTradeSnapshots()
    if (trades.length < this.config.minSamples) {
      throw new Error(
        `Not enough trade samples for evolution: ${trades.length} < ${this.config.minSamples}`
      )
    }

    // Initialize or seed population
    if (initialPopulation && initialPopulation.length > 0) {
      this.population = initialPopulation
      this.generation = Math.max(...initialPopulation.map(c => c.generation))
    } else {
      this.initializePopulation()
    }

    const fitnessHistory: GARunResult['fitnessHistory'] = []
    let converged = false
    let stagnationCount = 0
    let previousBestFitness = -Infinity

    for (let gen = 0; gen < this.config.generations; gen++) {
      this.generation = gen

      // Evaluate
      this.evaluatePopulation()

      // Sort by fitness descending
      this.population.sort((a, b) => b.fitness - a.fitness)

      // Track fitness stats
      const best = this.population[0].fitness
      const worst = this.population[this.population.length - 1].fitness
      const avg = this.population.reduce((s, c) => s + c.fitness, 0) / this.population.length

      fitnessHistory.push({ generation: gen, best, average: avg, worst })

      // Convergence detection
      if (Math.abs(best - previousBestFitness) < 0.001) {
        stagnationCount++
        if (stagnationCount >= 5) {
          converged = true
          break
        }
      } else {
        stagnationCount = 0
      }
      previousBestFitness = best

      // Build next generation
      const nextPopulation: StrategyChromosome[] = []

      // Elitism: preserve top N
      for (let i = 0; i < this.config.eliteCount && i < this.population.length; i++) {
        nextPopulation.push(this.cloneChromosome(this.population[i]))
      }

      // Fill rest via crossover + mutation
      while (nextPopulation.length < this.config.populationSize) {
        const parentA = this.tournamentSelect()
        const parentB = this.tournamentSelect()
        const [childA, childB] = this.crossover(parentA, parentB)

        this.mutate(childA)
        this.mutate(childB)

        nextPopulation.push(childA)
        if (nextPopulation.length < this.config.populationSize) {
          nextPopulation.push(childB)
        }
      }

      this.population = nextPopulation
    }

    // Final evaluation
    this.evaluatePopulation()
    this.population.sort((a, b) => b.fitness - a.fitness)

    const bestChromosome = this.population[0]

    // Persist
    if (this.config.persist) {
      this.persistPopulation()
    }

    return {
      bestChromosome,
      fitnessHistory,
      generations: this.generation,
      durationMs: Date.now() - startTime,
      converged,
      finalPopulation: [...this.population],
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Helpers
  // ═══════════════════════════════════════════════════════════════

  /**
   * Convert a chromosome to a parameter map for easy access.
   */
  chromosomeToParams(chromosome: StrategyChromosome): Record<string, GeneValue> {
    const params: Record<string, GeneValue> = {}
    for (const gene of chromosome.genes) {
      params[gene.name] = gene.value
    }
    return params
  }

  /**
   * Extract just the agent weights from a chromosome.
   */
  extractAgentWeights(chromosome: StrategyChromosome): Record<string, number> {
    const weights: Record<string, number> = {}
    for (const gene of chromosome.genes) {
      if (gene.name.endsWith('.performanceWeight')) {
        const role = gene.name.replace('.performanceWeight', '')
        weights[role] = gene.value as number
      }
    }
    return weights
  }

  private cloneChromosome(c: StrategyChromosome): StrategyChromosome {
    return {
      ...c,
      id: uuid(),
      genes: c.genes.map(g => ({ ...g })),
      generation: this.generation + 1,
      parents: [c.id],
      createdAt: new Date().toISOString(),
    }
  }

  private randomFloat(min: number, max: number): number {
    return min + Math.random() * (max - min)
  }

  private randomInt(min: number, max: number): number {
    return Math.floor(Math.random() * (max - min + 1)) + min
  }

  /**
   * Generate a random number from a standard normal distribution
   * using the Box-Muller transform.
   */
  private randomGaussian(): number {
    let u = 0, v = 0
    while (u === 0) u = Math.random()
    while (v === 0) v = Math.random()
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v)
  }

  // ═══════════════════════════════════════════════════════════
  // Persistence
  // ═══════════════════════════════════════════════════════════════

  private persistPopulation(): void {
    try {
      const filePath = path.join(this.config.persistDir, 'population.json')
      const data = {
        generation: this.generation,
        population: this.population,
        savedAt: new Date().toISOString(),
      }
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2))
    } catch {
      // Non-critical
    }
  }

  /**
   * Load a previously persisted population.
   */
  loadPopulation(): StrategyChromosome[] | null {
    try {
      const filePath = path.join(this.config.persistDir, 'population.json')
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
        this.generation = data.generation
        return data.population as StrategyChromosome[]
      }
    } catch {
      // Fall through
    }
    return null
  }

  // ═══════════════════════════════════════════════════════════
  // Accessors
  // ═══════════════════════════════════════════════════════════

  getPopulation(): StrategyChromosome[] {
    return [...this.population]
  }

  getBestFitness(): number {
    if (this.population.length === 0) return 0
    return Math.max(...this.population.map(c => c.fitness))
  }

  getGeneration(): number {
    return this.generation
  }

  setTracker(tracker: PerformanceTracker): void {
    this.tracker = tracker
  }
}
