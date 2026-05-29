/**
 * Layer 4 — Multi-Agent Collaborative Reasoning System
 *
 * Module index: exports everything needed to build and run the trading debate system.
 *
 * Architecture:
 *   1. Types → trading decision schemas & debate state
 *   2. LLM Provider → unified OpenAI/Anthropic interface
 *   3. Prompts → role-specific system prompts for each agent
 *   4. Agents → 6 specialized trading agents (Macro, Sector, Sentiment, Technical, Risk, Execution)
 *   5. Supervisor → LangGraph debate graph with weighted consensus
 *   6. Integration → Layer 1 hooks (risk check, order submission, execution)
 *   7. Config → centralized configuration
 *
 * Usage:
 *   import { buildTradingWorkforce, getLayer1Client } from './trading'
 *   const workforce = buildTradingWorkforce()
 *   const result = await workforce.analyze(marketData)
 */

// ── Types ──
export type {
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
} from './types'

export {
  AgentAnalysisSchema,
  FinalDecisionSchema,
} from './types'

// ── LLM Provider ──
export {
  createLLM,
  setProviderConfig,
  getProviderConfig,
  invokeStructured,
  invokeText,
} from './llm-provider'

// ── Prompts ──
export {
  ROLE_DEFINITIONS,
  buildAgentSystemPrompt,
  buildAgentUserPrompt,
} from './prompts'

// ── Agents ──
export {
  TradingAgent,
  MacroStrategistAgent,
  SectorAnalystAgent,
  SentimentAgent,
  TechnicalAnalystAgent,
  RiskManagerAgent,
  ExecutionOptimizerAgent,
} from './agents'

// ── Supervisor (Debate Graph) ──
export type { DebateGraphConfig } from './supervisor'
export { buildDebateGraph } from './supervisor'

// ── Integration (Layer 1 Bridge) ──
export type {
  Layer1IntegrationConfig,
  ExecutionReport,
} from './integration'
export {
  Layer1IntegrationClient,
  getLayer1Client,
  createLayer1Client,
} from './integration'

// ── Configuration ──
export type {
  LLMDefaults,
  AgentRoleConfig,
  TradingSystemConfig,
} from './config'
export {
  LLM_DEFAULTS,
  DEFAULT_TRADING_CONFIG,
  buildAgentConfigs,
  buildHistoricalWeights,
} from './config'

// ── Workforce Builder (convenience) ──
export { buildTradingWorkforce, TradingWorkforce } from './workforce'
