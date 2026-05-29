/**
 * Layer 5 — Self-Evolving Meta-Learning System
 *
 * @module meta
 *
 * The meta-learning layer enables the trading workforce to improve
 * autonomously over time through:
 *
 * 1. Performance Tracking — records every debate, trade, and analysis
 * 2. Genetic Algorithm — evolves strategy parameters (weights, thresholds, temps)
 * 3. Prompt Optimization — DSPy-lite auto-tuning of agent prompts
 * 4. Multi-Armed Bandit — optimal LLM model selection per agent role
 * 5. Backtesting — evaluates strategies against historical data
 * 6. Meta-Learning Pipeline — orchestrates continuous improvement cycles
 */

// ── Types ──
export {
  // Performance
  DebateRecord,
  TradeOutcomeRecord,
  AgentPerformanceMetrics,
  SystemPerformanceMetrics,
  TradeOutcome,
  // Genetic algorithm
  Gene,
  GeneValue,
  GenePool,
  StrategyChromosome,
  GAConfig,
  GARunResult,
  // Prompt optimization
  PromptVariant,
  FewShotExample,
  PromptOptimizationResult,
  // Model routing
  ModelArm,
  ModelReward,
  RoleBanditState,
  BanditConfig,
  // Backtesting
  HistoricalMarketPoint,
  BacktestConfig,
  BacktestTrade,
  BacktestResult,
  WalkForwardResult,
  // Pipeline
  MetaLearningConfig,
  MetaLearningStatus,
  EvolutionTrigger,
  OptimizationSuggestion,
} from './types'

// ── Performance Tracker ──
export {
  PerformanceTracker,
  DEFAULT_TRACKER_CONFIG,
  TrackerConfig,
} from './performance-tracker'

// ── Genetic Algorithm ──
export {
  StrategyGA,
  DEFAULT_GA_CONFIG,
  DEFAULT_GENE_POOL,
} from './strategy-ga'

// ── Prompt Optimizer ──
export {
  PromptOptimizer,
  DEFAULT_PROMPT_OPTIMIZER_CONFIG,
  PromptOptimizerConfig,
} from './prompt-optimizer'

// ── Model Router ──
export {
  ModelRouter,
  DEFAULT_BANDIT_CONFIG,
  DEFAULT_ARM_DEFINITIONS,
  ArmDefinition,
} from './model-router'

// ── Backtest Engine ──
export {
  BacktestEngine,
  DEFAULT_BACKTEST_CONFIG,
} from './backtest-engine'

// ── Meta-Learning Pipeline ──
export {
  MetaLearningPipeline,
  DEFAULT_META_CONFIG,
} from './pipeline'

// ── Configuration ──
export {
  DEFAULT_META_LEARNING_CONFIG,
  buildMetaLearningConfig,
} from './config'
