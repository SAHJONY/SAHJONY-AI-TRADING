/**
 * Layer 5 — Self-Evolving Meta-Learning Types
 *
 * Defines schemas for performance tracking, strategy evolution (genetic algorithm),
 * prompt optimization (DSPy-lite), multi-armed bandit model routing, and backtesting.
 */

import type { AgentTradingRole, AgentAnalysis, FinalDecision, MarketDataInput } from '../trading/types'

// Re-export types imported from trading layer so other meta modules can import from ./types
export type { AgentTradingRole, AgentAnalysis, FinalDecision, MarketDataInput }

// ═══════════════════════════════════════════════════════════════
// Performance Tracking
// ═══════════════════════════════════════════════════════════════

/** Outcome of a trade (determined ex-post) */
export type TradeOutcome = 'WIN' | 'LOSS' | 'BREAKEVEN' | 'PENDING'

/** How a specific debate session resolved */
export interface DebateRecord {
  /** Unique session ID matching the debate graph */
  sessionId: string
  /** Symbol analyzed */
  symbol: string
  /** When the debate occurred */
  timestamp: string
  /** Market data at time of analysis */
  marketSnapshot: MarketDataInput
  /** Final consensus decision */
  decision: FinalDecision
  /** All individual agent analyses */
  agentAnalyses: AgentAnalysis[]
  /** Number of rounds required */
  roundsRequired: number
  /** Did Risk Manager veto? */
  vetoApplied: boolean
  /** Which LLM provider each agent used */
  agentProviders: Record<AgentTradingRole, 'openai' | 'anthropic'>
  /** Which LLM model each agent used */
  agentModels: Record<AgentTradingRole, string>
  /** Prompt version hash used by each agent */
  promptVersions: Record<AgentTradingRole, string>
}

/** Trade outcome linked back to the debate that produced it */
export interface TradeOutcomeRecord {
  /** The debate that generated this trade */
  debateSessionId: string
  symbol: string
  /** Entry price */
  entryPrice: number
  /** Exit price (or current mark if still open) */
  exitPrice?: number
  /** Trade direction */
  direction: 'LONG' | 'SHORT'
  /** Outcome of the trade */
  outcome: TradeOutcome
  /** P&L in dollars */
  pnl: number
  /** P&L as percentage of entry */
  pnlPct: number
  /** Holding duration in milliseconds */
  holdingDurationMs?: number
  /** Timestamp of entry */
  entryTimestamp: string
  /** Timestamp of exit (if closed) */
  exitTimestamp?: string
  /** Maximum adverse excursion (worst drawdown) */
  maxAdversePct: number
  /** Maximum favorable excursion (best gain) */
  maxFavorablePct: number
}

/** Per-agent performance metrics computed from history */
export interface AgentPerformanceMetrics {
  role: AgentTradingRole
  /** Total debates participated in */
  totalAnalyses: number
  /** How often did the agent's recommendation match the eventual trade outcome? */
  recommendationAccuracy: number
  /** Average confidence when correct vs incorrect */
  avgConfidenceWhenCorrect: number
  avgConfidenceWhenWrong: number
  /** Calibration: are confidence scores well-calibrated? */
  calibrationError: number
  /** How often is agent on the winning side of consensus? */
  consensusAlignment: number
  /** Average contribution to weighted score in debates */
  avgWeightedContribution: number
  /** P&L attribution — total P&L from trades where this agent was on winning side */
  attributedPnl: number
  /** Sharpe-like ratio of agent's recommendations */
  recommendationSharpe: number
  /** Average round the agent converges (lower = faster conviction) */
  avgConvergenceRound: number
  /** Historical performance weight (evolved) */
  evolvedWeight: number
  /** Timestamp of last update */
  lastUpdated: string
}

/** Aggregate system-level performance metrics */
export interface SystemPerformanceMetrics {
  /** Total debates conducted */
  totalDebates: number
  /** Total trades executed */
  totalTrades: number
  /** Win rate */
  winRate: number
  /** Average P&L per trade (absolute $) */
  avgPnl: number
  /** Cumulative P&L */
  cumulativePnl: number
  /** Sharpe ratio */
  sharpeRatio: number
  /** Maximum drawdown % */
  maxDrawdownPct: number
  /** Average rounds per debate */
  avgRoundsPerDebate: number
  /** Veto rate (how often Risk Manager rejects) */
  vetoRate: number
  /** Hold rate (how often system decides to stay out) */
  holdRate: number
  /** Profit factor (gross profit / gross loss) */
  profitFactor: number
  /** Per-agent breakdown */
  agentMetrics: Record<AgentTradingRole, AgentPerformanceMetrics>
  /** Time period covered */
  periodStart: string
  periodEnd: string
}

// ═══════════════════════════════════════════════════════════════
// Genetic Algorithm — Strategy Evolution
// ═══════════════════════════════════════════════════════════════

/** A single gene in the chromosome */
export type GeneValue = number | boolean | string

export interface Gene {
  /** Parameter name (e.g. "macro_strategist.performanceWeight") */
  name: string
  /** Current value */
  value: GeneValue
  /** Gene type for mutation operators */
  type: 'float' | 'integer' | 'boolean' | 'categorical'
  /** Valid range or options */
  constraints: {
    min?: number
    max?: number
    step?: number
    options?: string[]
  }
  /** Mutation rate for this specific gene (0–1) */
  mutationRate: number
}

/** A full strategy chromosome — a candidate configuration */
export interface StrategyChromosome {
  /** Unique ID */
  id: string
  /** The genes (configurable parameters) */
  genes: Gene[]
  /** Fitness score (higher = better) */
  fitness: number
  /** Generation this chromosome was created in */
  generation: number
  /** Parent chromosome IDs */
  parents: string[]
  /** Timestamp */
  createdAt: string
}

/** The gene pool definition — which parameters are evolvable */
export interface GenePool {
  /** Agent performance weights (0.0–1.0) */
  agentWeights: Record<AgentTradingRole, { min: number; max: number; step: number }>
  /** Debate parameters */
  debate: {
    maxRounds: { min: number; max: number; step: number }
    consensusThreshold: { min: number; max: number; step: number }
    timeoutMs: { min: number; max: number; step: number }
  }
  /** Risk thresholds */
  risk: {
    maxPositionSizePct: { min: number; max: number; step: number }
    minConfidenceForAuto: { min: number; max: number; step: number }
  }
  /** LLM parameters per role */
  llm: Record<AgentTradingRole, {
    temperature: { min: number; max: number; step: number }
    provider: { options: string[] }
  }>
}

/** Configuration for the genetic algorithm */
export interface GAConfig {
  /** Population size per generation */
  populationSize: number
  /** Number of generations to evolve */
  generations: number
  /** Elite count — top N chromosomes preserved unchanged */
  eliteCount: number
  /** Base crossover rate (0–1) */
  crossoverRate: number
  /** Base mutation rate (0–1) */
  mutationRate: number
  /** Tournament size for selection */
  tournamentSize: number
  /** Fitness function weightings */
  fitnessWeights: {
    /** Weight for Sharpe ratio */
    sharpe: number
    /** Weight for win rate */
    winRate: number
    /** Weight for total P&L */
    totalPnl: number
    /** Weight for max drawdown penalty (negative) */
    maxDrawdown: number
    /** Weight for profit factor */
    profitFactor: number
    /** Weight for decision speed (avg rounds — higher speed = better) */
    decisionSpeed: number
  }
  /** Minimum training samples before evolution */
  minSamples: number
  /** Persist population to disk? */
  persist: boolean
  persistDir: string
}

/** Result of a genetic algorithm run */
export interface GARunResult {
  /** Best chromosome found */
  bestChromosome: StrategyChromosome
  /** Fitness history per generation (best, avg, worst) */
  fitnessHistory: Array<{
    generation: number
    best: number
    average: number
    worst: number
  }>
  /** Total generations evolved */
  generations: number
  /** Total time taken (ms) */
  durationMs: number
  /** Was convergence detected? */
  converged: boolean
  /** The full final population */
  finalPopulation: StrategyChromosome[]
}

// ═══════════════════════════════════════════════════════════════
// Prompt Optimization (DSPy-lite)
// ═══════════════════════════════════════════════════════════════

/** A prompt variant under test */
export interface PromptVariant {
  /** Unique ID */
  id: string
  /** Which agent role this prompt is for */
  role: AgentTradingRole
  /** The prompt text */
  text: string
  /** Version hash (SHA-256-like) */
  versionHash: string
  /** Parent prompt version (if evolved from another) */
  parentHash?: string
  /** How this version was created */
  creationMethod: 'manual' | 'mutation' | 'crossover' | 'few_shot_bootstrap' | 'instruction_refinement'
  /** Performance metrics for this prompt version */
  performance: {
    /** Total evaluations */
    evaluations: number
    /** Accuracy (recommendation aligned with outcome) */
    accuracy: number
    /** Average confidence calibration error */
    calibrationError: number
    /** Average response quality score (0–1, from LLM judge) */
    qualityScore: number
    /** Specificity of reasoning (token count / evidence refs) */
    specificity: number
  }
  /** Timestamps */
  createdAt: string
  lastEvaluated?: string
}

/** Few-shot example for prompt bootstrapping */
export interface FewShotExample {
  /** The market data input */
  marketData: MarketDataInput
  /** The correct/desired analysis output */
  analysis: AgentAnalysis
  /** The final trade outcome (for ground truth) */
  outcome: TradeOutcome
  /** Outcome P&L */
  outcomePnl: number
  /** Whether this is a positive example (good analysis) */
  isPositive: boolean
}

/** Optimization run result */
export interface PromptOptimizationResult {
  role: AgentTradingRole
  /** Best variant found */
  bestVariant: PromptVariant
  /** All variants tested */
  allVariants: PromptVariant[]
  /** Improvement over baseline */
  improvement: {
    accuracyDelta: number
    calibrationDelta: number
    qualityDelta: number
  }
  /** Number of iterations */
  iterations: number
  /** Duration */
  durationMs: number
}

// ═══════════════════════════════════════════════════════════════
// Multi-Armed Bandit — Model Routing
// ═══════════════════════════════════════════════════════════════

/** An arm in the bandit — a specific LLM provider + model combination */
export interface ModelArm {
  /** Unique arm ID */
  id: string
  /** LLM provider */
  provider: 'openai' | 'anthropic'
  /** Model name */
  model: string
  /** Which agent role this arm is for */
  role: AgentTradingRole
  /** UCB1 statistics */
  stats: {
    /** Number of times this arm was pulled */
    pulls: number
    /** Total accumulated reward */
    totalReward: number
    /** Empirical mean reward */
    meanReward: number
    /** Upper confidence bound value */
    ucb: number
    /** Last time this arm was pulled */
    lastPulled?: string
  }
  /** Last time this arm was pulled (deprecated — use stats.lastPulled) */
  lastPulled?: string
}

/** Reward components for evaluating a model's performance */
export interface ModelReward {
  /** Whether the agent's recommendation was directionally correct */
  directionalAccuracy: number // 0 or 1
  /** Quality of reasoning (LLM-judged, 0–1) */
  reasoningQuality: number
  /** Response latency (lower = better, normalized) */
  latencyScore: number
  /** Cost efficiency (tokens used normalized) */
  costEfficiency: number
  /** Composite reward (weighted sum) */
  composite: number
}

/** Bandit configuration */
export interface BanditConfig {
  /** Exploration strategy */
  strategy: 'epsilon_greedy' | 'ucb1' | 'thompson_sampling'
  /** Epsilon for epsilon-greedy (0–1) */
  epsilon?: number
  /** Decay rate for epsilon (0–1 per pull, 1 = no decay) */
  epsilonDecay?: number
  /** UCB1 exploration constant */
  ucbC?: number
  /** Minimum pulls before using bandit for selection */
  warmupPulls: number
  /** Reward component weights */
  rewardWeights: {
    directionalAccuracy: number
    reasoningQuality: number
    latencyScore: number
    costEfficiency: number
  }
}

/** Per-role bandit state */
export interface RoleBanditState {
  role: AgentTradingRole
  arms: ModelArm[]
  totalPulls: number
  strategy: BanditConfig['strategy']
}

// ═══════════════════════════════════════════════════════════════
// Backtesting
// ═══════════════════════════════════════════════════════════════

/** A historical market data point for backtesting */
export interface HistoricalMarketPoint {
  symbol: string
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  // Optional indicators (pre-computed for speed)
  rsi14?: number
  sma50?: number
  sma200?: number
  vwap?: number
}

/** A backtesting run configuration */
export interface BacktestConfig {
  /** Symbols to backtest */
  symbols: string[]
  /** Start date (ISO) */
  startDate: string
  /** End date (ISO) */
  endDate: string
  /** Timeframe resolution */
  timeframe: '1m' | '5m' | '15m' | '1h' | '4h' | '1d'
  /** Initial portfolio equity */
  initialEquity: number
  /** Commission per trade (basis points) */
  commissionBps: number
  /** Slippage model */
  slippageBps: number
  /** Use walk-forward optimization? */
  walkForward: boolean
  /** Walk-forward window size (days) */
  walkForwardWindowDays: number
  /** Out-of-sample period (days) */
  outOfSampleDays: number
}

/** A single backtest trade */
export interface BacktestTrade {
  symbol: string
  entryTimestamp: string
  exitTimestamp?: string
  direction: 'LONG' | 'SHORT'
  entryPrice: number
  exitPrice?: number
  quantity: number
  pnl: number
  pnlPct: number
  commission: number
  slippage: number
  debateSessionId: string
  outcome: TradeOutcome
}

/** Full backtest result */
export interface BacktestResult {
  config: BacktestConfig
  /** Total trades */
  totalTrades: number
  /** Win rate */
  winRate: number
  /** Cumulative P&L */
  cumulativePnl: number
  /** Final equity */
  finalEquity: number
  /** Return on initial equity */
  totalReturnPct: number
  /** Sharpe ratio */
  sharpeRatio: number
  /** Sortino ratio */
  sortinoRatio: number
  /** Maximum drawdown % */
  maxDrawdownPct: number
  /** Profit factor */
  profitFactor: number
  /** Average trade P&L */
  avgTradePnl: number
  /** Average win / average loss ratio */
  avgWinLossRatio: number
  /** Number of consecutive wins */
  maxConsecutiveWins: number
  /** Number of consecutive losses */
  maxConsecutiveLosses: number
  /** Calmar ratio (return / max drawdown) */
  calmarRatio: number
  /** All individual trades */
  trades: BacktestTrade[]
  /** Equity curve (timestamp → equity) */
  equityCurve: Array<{ timestamp: string; equity: number }>
  /** Per-symbol breakdown */
  symbolBreakdown: Array<{
    symbol: string
    trades: number
    pnl: number
    winRate: number
  }>
  /** Duration */
  durationMs: number
}

/** Walk-forward optimization result */
export interface WalkForwardResult {
  /** In-sample windows */
  inSample: BacktestResult[]
  /** Out-of-sample windows */
  outOfSample: BacktestResult[]
  /** Aggregated OOS performance */
  aggregateOOS: {
    totalTrades: number
    winRate: number
    cumulativePnl: number
    sharpeRatio: number
    maxDrawdownPct: number
  }
  /** Robustness: OOS Sharpe / IS Sharpe */
  robustnessRatio: number
}

// ═══════════════════════════════════════════════════════════════
// Meta-Learning Pipeline
// ═══════════════════════════════════════════════════════════════

/** Evolution trigger types */
export type EvolutionTrigger = 'schedule' | 'drawdown' | 'manual' | 'sample_count' | 'performance_degradation'

/** Status of the meta-learning pipeline */
export interface MetaLearningStatus {
  /** Is the pipeline running? */
  running: boolean
  /** Last evolution run */
  lastEvolution?: {
    timestamp: string
    trigger: EvolutionTrigger
    generationsCompleted: number
    bestFitness: number
    fitnessDelta: number
  }
  /** Last prompt optimization */
  lastPromptOptimization?: {
    timestamp: string
    rolesOptimized: AgentTradingRole[]
    avgAccuracyImprovement: number
  }
  /** Last backtest */
  lastBacktest?: {
    timestamp: string
    symbols: string[]
    sharpeRatio: number
    winRate: number
  }
  /** Current system metrics */
  currentMetrics?: SystemPerformanceMetrics
  /** Bandit state summary */
  banditState: {
    totalPulls: number
    dominantModels: Record<AgentTradingRole, string>
  }
  /** Chromosome generation count */
  generationCount: number
  /** Prompt version count */
  promptVersionCount: number
}

/** Full meta-learning system configuration */
export interface MetaLearningConfig {
  /** Genetic algorithm config */
  ga: GAConfig
  /** Gene pool definition */
  genePool: GenePool
  /** Bandit config */
  bandit: BanditConfig
  /** Backtest config */
  backtest: BacktestConfig
  /** Prompt optimization config */
  promptOptimization: {
    /** Minimum evaluations before optimization */
    minEvaluations: number
    /** Maximum few-shot examples to bootstrap */
    maxFewShotExamples: number
    /** Only use positive examples (successful trades) */
    positiveExamplesOnly: boolean
    /** Number of mutation iterations */
    mutationIterations: number
  }
  /** Evolution schedule */
  schedule: {
    /** Cron expression for scheduled evolution */
    evolutionCron: string
    /** Trigger evolution after this many new trade outcomes */
    evolutionSampleThreshold: number
    /** Trigger evolution if Sharpe drops below this */
    sharpeDegradationThreshold: number
    /** Trigger evolution if drawdown exceeds this % */
    drawdownTriggerPct: number
  }
  /** Performance history retention */
  retention: {
    /** Max debate records to keep in memory */
    maxDebateRecords: number
    /** Max trade records to keep */
    maxTradeRecords: number
    /** Persist records to disk */
    persistRecords: boolean
    /** Persistence directory */
    persistDir: string
  }
}

// ═══════════════════════════════════════════════════════════════
// Optimization Suggestions (for human review)
// ═══════════════════════════════════════════════════════════════

/** A suggested configuration change from the meta-learning system */
export interface OptimizationSuggestion {
  id: string
  type: 'weight_update' | 'threshold_update' | 'prompt_update' | 'model_switch' | 'parameter_tune'
  /** Human-readable explanation */
  description: string
  /** The parameter to change */
  parameter: string
  /** Current value */
  currentValue: GeneValue
  /** Suggested value */
  suggestedValue: GeneValue
  /** Expected improvement */
  expectedImprovement: {
    metric: string
    current: number
    projected: number
    delta: number
  }
  /** Confidence in this suggestion (0–1) */
  confidence: number
  /** Whether this was auto-applied or requires human approval */
  autoApplied: boolean
  /** Timestamp */
  timestamp: string
}
