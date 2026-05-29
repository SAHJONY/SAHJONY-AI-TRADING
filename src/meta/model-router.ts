/**
 * Layer 5 — Multi-Armed Bandit Model Router
 *
 * Selects the best LLM provider+model combination for each agent role
 * using multi-armed bandit algorithms. Maintains per-role bandit state
 * with UCB1, epsilon-greedy, and Thompson sampling strategies.
 *
 * Reward is computed from: directional accuracy, reasoning quality,
 * latency efficiency, and cost efficiency.
 */

import { v4 as uuid } from 'uuid'
import {
  ModelArm,
  RoleBanditState,
  BanditConfig,
  ModelReward,
  AgentTradingRole,
} from './types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_BANDIT_CONFIG: BanditConfig = {
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
}

// ═══════════════════════════════════════════════════════════════
// Default Arms (models to try)
// ═══════════════════════════════════════════════════════════════════

export interface ArmDefinition {
  provider: 'openai' | 'anthropic'
  model: string
}

export const DEFAULT_ARM_DEFINITIONS: ArmDefinition[] = [
  { provider: 'openai', model: 'gpt-4o' },
  { provider: 'openai', model: 'gpt-4o-mini' },
  { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
  { provider: 'anthropic', model: 'claude-3-5-haiku-latest' },
]

// ═══════════════════════════════════════════════════════════════
// Model Router
// ═══════════════════════════════════════════════════════════════

export class ModelRouter {
  private config: BanditConfig
  private bandits: Map<AgentTradingRole, RoleBanditState> = new Map()
  private armDefinitions: ArmDefinition[]

  constructor(
    config: Partial<BanditConfig> = {},
    armDefinitions?: ArmDefinition[]
  ) {
    this.config = { ...DEFAULT_BANDIT_CONFIG, ...config }
    this.armDefinitions = armDefinitions || DEFAULT_ARM_DEFINITIONS
  }

  // ═══════════════════════════════════════════════════════════
  // Initialization
  // ═══════════════════════════════════════════════════════════════

  /**
   * Initialize bandit state for all agent roles.
   */
  initialize(): void {
    const roles: AgentTradingRole[] = [
      'macro_strategist', 'sector_analyst', 'sentiment_agent',
      'technical_analyst', 'risk_manager', 'execution_optimizer',
    ]

    for (const role of roles) {
      this.initializeRole(role)
    }
  }

  /**
   * Initialize bandit state for a single role.
   */
  initializeRole(role: AgentTradingRole): void {
    const arms: ModelArm[] = this.armDefinitions.map(def => ({
      id: uuid(),
      provider: def.provider,
      model: def.model,
      role,
      stats: {
        pulls: 0,
        totalReward: 0,
        meanReward: 0,
        ucb: Infinity,
      },
    }))

    this.bandits.set(role, {
      role,
      arms,
      totalPulls: 0,
      strategy: this.config.strategy,
    })
  }

  // ═══════════════════════════════════════════════════════════════
  // Arm Selection
  // ═══════════════════════════════════════════════════════════════

  /**
   * Select the best arm for a given role using the configured strategy.
   */
  selectArm(role: AgentTradingRole): ModelArm {
    let bandit = this.bandits.get(role)
    if (!bandit) {
      this.initializeRole(role)
      bandit = this.bandits.get(role)!
    }

    // If any arm hasn't been pulled enough, explore it first (warmup)
    const unpulledArm = bandit.arms.find(
      a => a.stats.pulls < this.config.warmupPulls
    )
    if (unpulledArm) return unpulledArm

    switch (this.config.strategy) {
      case 'epsilon_greedy':
        return this.selectEpsilonGreedy(bandit)
      case 'ucb1':
        return this.selectUCB1(bandit)
      case 'thompson_sampling':
        return this.selectThompsonSampling(bandit)
      default:
        return this.selectUCB1(bandit)
    }
  }

  /**
   * Epsilon-greedy: explore with probability epsilon, exploit best otherwise.
   */
  private selectEpsilonGreedy(bandit: RoleBanditState): ModelArm {
    const epsilon = (this.config.epsilon ?? 0.1) *
      Math.pow(this.config.epsilonDecay ?? 1, bandit.totalPulls)

    if (Math.random() < epsilon) {
      // Explore: random arm
      return bandit.arms[Math.floor(Math.random() * bandit.arms.length)]
    }

    // Exploit: best mean reward
    return bandit.arms.reduce((best, cur) =>
      cur.stats.meanReward > best.stats.meanReward ? cur : best
    )
  }

  /**
   * UCB1: Upper Confidence Bound. Balances exploitation of high-reward arms
   * with exploration of uncertain arms.
   *
   * UCB = meanReward + C * sqrt(ln(totalPulls) / armPulls)
   */
  private selectUCB1(bandit: RoleBanditState): ModelArm {
    const totalPulls = bandit.totalPulls || 1
    const c = this.config.ucbC ?? 2.0

    // Compute UCB for each arm
    for (const arm of bandit.arms) {
      if (arm.stats.pulls === 0) {
        arm.stats.ucb = Infinity
      } else {
        const explorationBonus = c * Math.sqrt(Math.log(totalPulls) / arm.stats.pulls)
        arm.stats.ucb = arm.stats.meanReward + explorationBonus
      }
    }

    return bandit.arms.reduce((best, cur) =>
      cur.stats.ucb > best.stats.ucb ? cur : best
    )
  }

  /**
   * Thompson Sampling: sample from Beta distribution for each arm,
   * select arm with highest sample.
   *
   * Uses Beta(α, β) where α = successes, β = failures.
   * Success/failure is binarized from the composite reward.
   */
  private selectThompsonSampling(bandit: RoleBanditState): ModelArm {
    let bestArm = bandit.arms[0]
    let bestSample = -Infinity

    for (const arm of bandit.arms) {
      // Convert meanReward to success/failure counts
      const successes = arm.stats.meanReward * arm.stats.pulls
      const failures = arm.stats.pulls - successes

      // Sample Beta(α + 1, β + 1)
      const sample = this.sampleBeta(successes + 1, failures + 1)

      if (sample > bestSample) {
        bestSample = sample
        bestArm = arm
      }
    }

    return bestArm
  }

  // ═══════════════════════════════════════════════════════════════
  // Reward Update
  // ═══════════════════════════════════════════════════════════════

  /**
   * Update an arm's statistics with a new reward.
   */
  updateArm(
    role: AgentTradingRole,
    armId: string,
    reward: ModelReward
  ): void {
    const bandit = this.bandits.get(role)
    if (!bandit) return

    const arm = bandit.arms.find(a => a.id === armId)
    if (!arm) return

    // Weighted composite reward
    const rw = this.config.rewardWeights
    const composite =
      reward.directionalAccuracy * rw.directionalAccuracy +
      reward.reasoningQuality * rw.reasoningQuality +
      reward.latencyScore * rw.latencyScore +
      reward.costEfficiency * rw.costEfficiency

    // Update running statistics
    arm.stats.pulls++
    arm.stats.totalReward += composite
    arm.stats.meanReward = arm.stats.totalReward / arm.stats.pulls
    arm.stats.lastPulled = new Date().toISOString()

    bandit.totalPulls++
  }

  // ═══════════════════════════════════════════════════════════════
  // Analysis & Reporting
  // ═══════════════════════════════════════════════════════════════

  /**
   * Get the best arm for each role based on current statistics.
   */
  getBestArms(): Record<AgentTradingRole, { provider: string; model: string; meanReward: number; pulls: number }> {
    const result = {} as Record<AgentTradingRole, any>

    for (const [role, bandit] of this.bandits) {
      const best = bandit.arms.reduce((bestArm, cur) =>
        cur.stats.meanReward > bestArm.stats.meanReward ? cur : bestArm
      )
      result[role] = {
        provider: best.provider,
        model: best.model,
        meanReward: best.stats.meanReward,
        pulls: best.stats.pulls,
      }
    }

    return result
  }

  /**
   * Get full bandit state summary.
   */
  getBanditSummary(): {
    totalPulls: number
    dominantModels: Record<AgentTradingRole, string>
    perRole: Record<AgentTradingRole, Array<{
      provider: string
      model: string
      pulls: number
      meanReward: number
      ucb: number
    }>>
  } {
    const perRole = {} as any
    const dominantModels = {} as Record<AgentTradingRole, string>

    for (const [role, bandit] of this.bandits) {
      const sorted = [...bandit.arms].sort((a, b) => b.stats.meanReward - a.stats.meanReward)
      perRole[role] = sorted.map(a => ({
        provider: a.provider,
        model: a.model,
        pulls: a.stats.pulls,
        meanReward: a.stats.meanReward,
        ucb: a.stats.ucb,
      }))

      dominantModels[role] = sorted[0] ? `${sorted[0].provider}/${sorted[0].model}` : 'unknown'
    }

    return {
      totalPulls: Array.from(this.bandits.values()).reduce((s, b) => s + b.totalPulls, 0),
      dominantModels,
      perRole,
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Helpers
  // ═══════════════════════════════════════════════════════════════

  /**
   * Sample from Beta(α, β) distribution using gamma sampling.
   * Beta(α, β) = Gamma(α, 1) / (Gamma(α, 1) + Gamma(β, 1))
   */
  private sampleBeta(alpha: number, beta: number): number {
    const x = this.sampleGamma(alpha)
    const y = this.sampleGamma(beta)
    return x / (x + y)
  }

  /**
   * Sample from Gamma(shape, 1) using Marsaglia-Tsang method.
   */
  private sampleGamma(shape: number): number {
    if (shape < 1) {
      // Use Gamma(shape + 1, 1) * U^(1/shape) for shape < 1
      const u = Math.random()
      return this.sampleGamma(shape + 1) * Math.pow(u, 1 / shape)
    }

    const d = shape - 1 / 3
    const c = 1 / Math.sqrt(9 * d)

    while (true) {
      let x: number, v: number
      do {
        x = this.randomGaussian()
        v = 1 + c * x
      } while (v <= 0)

      v = v * v * v
      const u = Math.random()

      if (
        u < 1 - 0.0331 * (x * x) * (x * x) ||
        Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))
      ) {
        return d * v
      }
    }
  }

  private randomGaussian(): number {
    let u = 0, v = 0
    while (u === 0) u = Math.random()
    while (v === 0) v = Math.random()
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v)
  }

  /**
   * Reset bandit state for a role (for re-training).
   */
  resetRole(role: AgentTradingRole): void {
    this.initializeRole(role)
  }

  /**
   * Reset all bandit states.
   */
  resetAll(): void {
    this.bandits.clear()
    this.initialize()
  }

  // ═══════════════════════════════════════════════════════════════
  // Accessors
  // ═══════════════════════════════════════════════════════════════

  getBandit(role: AgentTradingRole): RoleBanditState | undefined {
    return this.bandits.get(role)
  }

  getConfig(): BanditConfig {
    return { ...this.config }
  }

  getArmDefinitions(): ArmDefinition[] {
    return [...this.armDefinitions]
  }
}
