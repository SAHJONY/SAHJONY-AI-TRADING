/**
 * Agent Workforce - Main Entry Point
 * Multi-Agent Orchestration System with Autonomous Task Execution
 *
 * Layers:
 *   Layer 3: Deep Intelligence & Knowledge Fusion (knowledge module)
 *   Layer 4: Multi-Agent Collaborative Reasoning (trading module)
 *   Layer 5: Self-Evolving Meta-Learning (meta module)
 *   Core: Agent orchestration, task management, workflow engine
 */

// ── Core Types ──
export * from './types'

// ── Core Agents (orchestrator, researcher, coder, reviewer, executor, hermes) ──
export * from './agents'

// ── Orchestration Engine ──
export * from './orchestration'

// Re-export engine for convenience
export { getEngine, createEngine, OrchestrationEngine } from './orchestration/engine'

// Re-export ToolResult specifically
export type { ToolResult } from './agents/base-agent'

// ── Layer 4: Multi-Agent Trading Workforce ──
export {
  // Types
  MarketDataInput,
  AgentAnalysis,
  TradingRecommendation,
  AgentTradingRole,
  TradingAgentConfig,
  FinalDecision,
  VotingBreakdown,
  DebateState,
  LLMProviderConfig,
  LLMResponse,
  OrderIntent,
  RiskCheckRequest,
  RiskCheckResponse,
} from './trading/types'

export {
  // Agents
  TradingAgent,
  MacroStrategistAgent,
  SectorAnalystAgent,
  SentimentAgent,
  TechnicalAnalystAgent,
  RiskManagerAgent,
  ExecutionOptimizerAgent,
} from './trading/agents'

export {
  // Supervisor
  buildDebateGraph,
  DebateGraphConfig,
} from './trading/supervisor'

export {
  // Integration
  Layer1IntegrationClient,
  Layer1IntegrationConfig,
  ExecutionReport,
  getLayer1Client,
  createLayer1Client,
} from './trading/integration'

export {
  // Configuration
  TradingSystemConfig,
  DEFAULT_TRADING_CONFIG,
  buildAgentConfigs,
  buildHistoricalWeights,
} from './trading/config'

export {
  // Workforce
  TradingWorkforce,
  buildTradingWorkforce,
  PortfolioState,
  AnalysisResult,
} from './trading/workforce'

// ── Layer 3: Knowledge Graph & Alternative Data Pipeline ──
export {
  // Pipeline
  KnowledgePipeline,
  KnowledgeGraph,
  VectorStore,
  RagOrchestrator,
  SecEdgarClient,
  AltDataAggregator,
  NewsApiClient,
  DEFAULT_KNOWLEDGE_CONFIG,
  buildKnowledgeConfig,
} from './knowledge'

// ── Layer 5: Self-Evolving Meta-Learning ──
export {
  // Pipeline
  MetaLearningPipeline,
  DEFAULT_META_CONFIG,
  DEFAULT_META_LEARNING_CONFIG,
  buildMetaLearningConfig,
} from './meta'

export {
  // Performance Tracker
  PerformanceTracker,
  DEFAULT_TRACKER_CONFIG,
} from './meta'

export {
  // Genetic Algorithm
  StrategyGA,
  DEFAULT_GA_CONFIG,
  DEFAULT_GENE_POOL,
} from './meta'

export {
  // Prompt Optimizer
  PromptOptimizer,
  DEFAULT_PROMPT_OPTIMIZER_CONFIG,
} from './meta'

export {
  // Model Router
  ModelRouter,
  DEFAULT_BANDIT_CONFIG,
  DEFAULT_ARM_DEFINITIONS,
} from './meta'

export {
  // Backtest Engine
  BacktestEngine,
  DEFAULT_BACKTEST_CONFIG,
} from './meta'

export type {
  // Performance
  DebateRecord,
  TradeOutcomeRecord,
  AgentPerformanceMetrics,
  SystemPerformanceMetrics,
  TradeOutcome,
  // Genetic algorithm
  Gene,
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
} from './meta'