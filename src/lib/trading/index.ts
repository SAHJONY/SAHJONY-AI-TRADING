// Trading Module - Main entry point
export { MarketDataService, marketDataService } from './market-data'
export { PortfolioService, portfolioService } from './portfolio'
export { StrategyEngine, strategyEngine } from './strategy-engine'
export { BacktestEngine, backtestEngine } from './backtest-engine'
export { AgentDebateOrchestrator, agentDebateOrchestrator } from './agent-debate'
export { KnowledgePipeline, knowledgePipeline } from './knowledge-pipeline'
export { MetaLearningSystem, metaLearning } from './meta-learning'
export { TradingLLMProvider, tradingLLM } from './llm-provider'
export type { LLMProviderType, TradingLLMConfig } from './llm-provider'

// Layer 3: Regime Geometry Detector (Information Geometry)
export { RegimeGeometryDetector, regimeGeometryDetector } from './regime-geometry-detector'

// Layer 5: Pod Manager
export { PodManager, createPod } from './pod-manager'

// Layer 6: CIO Agent
export { CIOAgent, cioAgent } from './cio-agent'
