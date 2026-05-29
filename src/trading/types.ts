/**
 * Layer 4 — Multi-Agent Collaborative Reasoning Types
 *
 * Defines the schemas for agent analyses, debate state, consensus decisions,
 * and trading signals that flow through the LangGraph supervisor graph.
 */

// ── Market Data Input ──

export interface MarketDataInput {
  symbol: string
  currentPrice: number
  dailyChangePct: number
  volume: number
  avgVolume: number
  bidAskSpread: number
  marketCap?: number
  sector?: string
  industry?: string
  // Technical indicators
  rsi14?: number
  macdSignal?: number
  macdHistogram?: number
  sma50?: number
  sma200?: number
  ema20?: number
  bollingerUpper?: number
  bollingerLower?: number
  atr14?: number
  vwap?: number
  // Macro context
  fedRate?: number
  vix?: number
  usdIndex?: number
  yield10y?: number
  yield2y?: number
  goldPrice?: number
  oilPrice?: number
  // Sentiment context
  newsSentiment?: number          // -1.0 to 1.0
  socialSentiment?: number        // -1.0 to 1.0
  insiderTransactionRatio?: number // buy/sell ratio
  analystConsensus?: string        // 'Strong Buy' | 'Buy' | 'Hold' | 'Sell' | 'Strong Sell'
  recentFilings?: string[]
  // Sector context
  sectorPerformance?: number
  peerAvgReturn?: number
  relativeStrengthVsSector?: number
  // ── Layer 3 Knowledge Pipeline enrichment ──
  /** RAG-augmented context from SEC filings, news, and vector search */
  ragContext?: string
  /**
   * Aggregated alternative data (news sentiment, insider trades, social).
   * Uses inline type import from knowledge layer — intentional coupling
   * between Layer 3 and Layer 4 type definitions.
   */
  altDataSnapshot?: import('../knowledge/types').AltDataSnapshot
  /** Knowledge graph stats at time of enrichment */
  knowledgeGraphStats?: { entityCount: number; relationCount: number }
  /** Whether this market data was enriched via Layer 3 */
  enriched?: boolean
}

// ── Agent Analysis Output ──

export type TradingRecommendation = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL'

export interface AgentAnalysis {
  /** Which agent produced this analysis */
  role: AgentTradingRole
  /** Debate round number (0-indexed) */
  round: number
  /** Trading recommendation */
  recommendation: TradingRecommendation
  /** Confidence score 0.0–1.0 */
  confidence: number
  /** Narrative reasoning behind the recommendation */
  reasoning: string
  /** References to specific data points used */
  evidenceRefs: string[]
  /** Role-specific metrics (e.g. RSI for technical, VaR for risk) */
  keyMetrics: Record<string, number>
  /** Counter-arguments addressed from previous rounds */
  rebuttals?: string[]
  /** Timestamp */
  timestamp: string
  /** Runtime metadata for meta-learning (Layer 5 model routing + performance tracking) */
  llmProvider?: 'openai' | 'anthropic'
  /** Specific LLM model used for this analysis */
  llmModel?: string
  /** LLM inference latency in milliseconds */
  latencyMs?: number
  /** Estimated tokens used (approximate — structured output mode limits accuracy) */
  tokensUsed?: number
}

// ── Trading Agent Roles ──

export type AgentTradingRole =
  | 'macro_strategist'
  | 'sector_analyst'
  | 'sentiment_agent'
  | 'technical_analyst'
  | 'risk_manager'
  | 'execution_optimizer'

export interface TradingAgentConfig {
  id: string
  name: string
  role: AgentTradingRole
  llmProvider: 'openai' | 'anthropic'
  llmModel: string
  temperature: number
  maxTokens: number
  /** Historical accuracy weight for consensus voting (0.0–1.0) */
  performanceWeight: number
  /** Custom system prompt override */
  systemPromptOverride?: string
  /** Whether this agent is enabled */
  enabled: boolean
}

// ── Final Consensus Decision ──

export interface FinalDecision {
  /** Aggregated trading action */
  action: 'BUY' | 'SELL' | 'HOLD'
  /** Weighted confidence (0.0–1.0) */
  overallConfidence: number
  /** Target price (from Execution Optimizer + Technical Analyst) */
  targetPrice?: number
  /** Stop-loss price (from Risk Manager) */
  stopLoss?: number
  /** Take-profit price */
  takeProfit?: number
  /** Recommended position size as % of portfolio (from Kelly/Risk) */
  positionSizePct?: number
  /** Synthesized reasoning from the winning side */
  reasoningSummary: string
  /** Was the Risk Manager veto applied? */
  vetoApplied: boolean
  /** Veto reason (if applicable) */
  vetoReason?: string
  /** How many debate rounds were required */
  roundsRequired: number
  /** All individual analyses for audit trail */
  allAnalyses: AgentAnalysis[]
  /** Aggregated agent votes with weights */
  votingBreakdown: VotingBreakdown[]
  /** Timestamp */
  timestamp: string
  /** Whether this decision should be auto-executed or requires human review */
  requiresHumanReview: boolean
}

export interface VotingBreakdown {
  role: AgentTradingRole
  vote: TradingRecommendation
  confidence: number
  weight: number
  weightedScore: number
  contribution: string // description of impact on final decision
}

// ── Debate State (flows through LangGraph) ──

export interface DebateState {
  /** Input market data snapshot */
  marketData: MarketDataInput
  /** Symbol being analyzed */
  symbol: string
  /** Current debate round */
  currentRound: number
  /** Maximum debate rounds (configurable) */
  maxRounds: number
  /** All agent analyses accumulated across rounds */
  agentAnalyses: AgentAnalysis[]
  /** Whether consensus threshold has been reached */
  consensusReached: boolean
  /** Whether Risk Manager veto was triggered */
  vetoTriggered: boolean
  /** Veto reason if applicable */
  vetoReason?: string
  /** Final trading decision */
  finalDecision: FinalDecision | null
  /** Historical performance weights per role */
  historicalWeights: Record<string, number>
  /** Consensus threshold (e.g., 0.6 = 60% weighted agreement required) */
  consensusThreshold: number
  /** Supervisor instruction for the current round */
  supervisorInstruction?: string
  /** Session/trace ID for audit */
  sessionId: string
  /** Error state if graph fails */
  error?: string
}

// ── LLM Provider Types ──

export interface LLMProviderConfig {
  provider: 'openai' | 'anthropic'
  apiKey: string
  defaultModel: string
  maxRetries: number
  timeoutMs: number
}

export interface LLMResponse {
  content: string
  model: string
  tokensUsed: number
  latencyMs: number
  finishReason: string
}

// ── Structured Output Schemas (used for LLM tool calling) ──

export const AgentAnalysisSchema = {
  type: 'object' as const,
  properties: {
    recommendation: { type: 'string', enum: ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL'] },
    confidence: { type: 'number', minimum: 0, maximum: 1 },
    reasoning: { type: 'string', description: 'Detailed reasoning behind the recommendation' },
    evidenceRefs: { type: 'array', items: { type: 'string' }, description: 'Specific data points used' },
    keyMetrics: { type: 'object', description: 'Role-specific metrics' },
    rebuttals: { type: 'array', items: { type: 'string' }, description: 'Counter-arguments to other agents' }
  },
  required: ['recommendation', 'confidence', 'reasoning', 'keyMetrics']
}

export const FinalDecisionSchema = {
  type: 'object' as const,
  properties: {
    action: { type: 'string', enum: ['BUY', 'SELL', 'HOLD'] },
    overallConfidence: { type: 'number', minimum: 0, maximum: 1 },
    targetPrice: { type: 'number' },
    stopLoss: { type: 'number' },
    takeProfit: { type: 'number' },
    positionSizePct: { type: 'number', minimum: 0, maximum: 1 },
    reasoningSummary: { type: 'string' },
    requiresHumanReview: { type: 'boolean' }
  },
  required: ['action', 'overallConfidence', 'reasoningSummary']
}

// ── Layer 1 Integration Types ──

/** Order intent produced by the Execution Optimizer, passed to Layer 1 */
export interface OrderIntent {
  symbol: string
  side: 'BUY' | 'SELL' | 'SELL_SHORT'
  orderType: 'MARKET' | 'LIMIT' | 'STOP' | 'STOP_LIMIT'
  quantity: number
  price?: number
  stopPrice?: number
  timeInForce: 'DAY' | 'GTC' | 'IOC' | 'FOK'
  strategyId: string
}

/** Risk check request sent to Layer 1 pre-trade validation */
export interface RiskCheckRequest {
  orderIntent: OrderIntent
  currentPositions: {
    symbol: string
    quantity: number
    avgPrice: number
    marketValue: number
    unrealizedPnl: number
  }[]
  portfolioEquity: number
  dailyPnl: number
  currentDrawdownPct: number
}

/** Risk check response from Layer 1 */
export interface RiskCheckResponse {
  approved: boolean
  rejectReason?: string
  maxPositionSize?: number
  recommendedSize?: number
  currentVar?: number
  circuitBreakerActive: boolean
  drawdownLevel: 'NORMAL' | 'WARNING' | 'CRITICAL'
}
