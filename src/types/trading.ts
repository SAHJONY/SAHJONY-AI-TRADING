// ============================================================
// Trading Platform Type Definitions
// ============================================================

// ---- Enums ----

export type AssetType = 'stock' | 'crypto' | 'forex'
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit'
export type OrderSide = 'buy' | 'sell'
export type OrderStatus = 'pending' | 'filled' | 'partial' | 'cancelled' | 'rejected'
export type StrategyStatus = 'draft' | 'active' | 'paused' | 'archived'
export type RiskLevel = 'low' | 'medium' | 'high'
export type BacktestStatus = 'running' | 'completed' | 'failed'

// ---- Market Data ----

export interface MarketQuote {
  symbol: string
  assetType: AssetType
  name: string
  price: number
  change24h: number
  changePct24h: number
  high24h: number
  low24h: number
  volume24h: number
  marketCap?: number
  currency: string
  exchange?: string
  fetchedAt: string
}

export interface HistoricalBar {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface MarketNewsItem {
  id: string
  title: string
  summary: string
  url: string
  source: string
  publishedAt: string
  sentiment: 'positive' | 'negative' | 'neutral'
  sentimentScore: number
  symbols: string[]
  assetType: AssetType
}

// ---- Portfolio ----

export interface TradingPortfolio {
  id: string
  userId: string
  name: string
  description: string | null
  initialBalance: number
  currentBalance: number
  currency: string
  isPaper: boolean
  createdAt: string
  updatedAt: string
}

export interface Holding {
  id: string
  portfolioId: string
  userId: string
  symbol: string
  assetType: AssetType
  quantity: number
  averagePrice: number
  currentPrice: number | null
  lastUpdated: string | null
  createdAt: string
  updatedAt: string
}

export interface PortfolioSummary {
  portfolio: TradingPortfolio
  holdings: Holding[]
  totalValue: number
  totalPL: number
  totalPLPct: number
  assetAllocation: AssetAllocation[]
}

export interface AssetAllocation {
  assetType: AssetType
  value: number
  percentage: number
}

// ---- Orders ----

export interface TradingOrder {
  id: string
  userId: string
  portfolioId: string
  symbol: string
  assetType: AssetType
  orderType: OrderType
  side: OrderSide
  quantity: number
  price: number | null
  stopPrice: number | null
  limitPrice: number | null
  status: OrderStatus
  filledQuantity: number
  filledPrice: number | null
  totalValue: number | null
  notes: string | null
  executedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface CreateOrderInput {
  portfolioId: string
  symbol: string
  assetType: AssetType
  orderType: OrderType
  side: OrderSide
  quantity: number
  price?: number
  stopPrice?: number
  limitPrice?: number
  notes?: string
}

// ---- Strategies ----

export interface TradingStrategy {
  id: string
  userId: string
  name: string
  description: string | null
  strategyType: string
  assetTypes: AssetType[]
  indicators: Indicator[]
  conditions: StrategyConditions
  code: string | null
  status: StrategyStatus
  performanceMetrics: StrategyMetrics
  createdAt: string
  updatedAt: string
}

export interface Indicator {
  id: string
  name: string
  type: 'sma' | 'ema' | 'rsi' | 'macd' | 'bb' | 'volume' | 'custom'
  params: Record<string, number | string>
}

export interface StrategyConditions {
  entry: Condition[]
  exit: Condition[]
}

export interface Condition {
  id: string
  indicator: string
  operator: 'gt' | 'lt' | 'gte' | 'lte' | 'eq' | 'cross_above' | 'cross_below'
  value: number
  logic?: 'and' | 'or'
}

export interface StrategyMetrics {
  totalReturn: number
  maxDrawdown: number
  sharpeRatio: number
  winRate: number
  totalTrades: number
  profitableTrades: number
  avgWin: number
  avgLoss: number
}

// ---- Backtesting ----

export interface TradingBacktest {
  id: string
  userId: string
  strategyId: string | null
  name: string
  symbol: string
  assetType: AssetType
  timeframe: string
  startDate: string
  endDate: string
  initialCapital: number
  finalCapital: number | null
  totalReturn: number | null
  maxDrawdown: number | null
  sharpeRatio: number | null
  winRate: number | null
  totalTrades: number | null
  profitableTrades: number | null
  losingTrades: number | null
  avgWin: number | null
  avgLoss: number | null
  resultsJson: BacktestResults
  status: BacktestStatus
  createdAt: string
  updatedAt: string
}

export interface BacktestResults {
  equityCurve?: { timestamp: string; value: number }[]
  trades?: BacktestTrade[]
  drawdowns?: { start: string; end: string; depth: number }[]
  monthlyReturns?: { month: string; return: number }[]
}

export interface BacktestTrade {
  entryDate: string
  exitDate: string
  side: OrderSide
  entryPrice: number
  exitPrice: number
  quantity: number
  pnl: number
  pnlPct: number
}

// ---- Watchlists ----

export interface Watchlist {
  id: string
  userId: string
  name: string
  description: string | null
  isDefault: boolean
  createdAt: string
  updatedAt: string
  items?: WatchlistItem[]
}

export interface WatchlistItem {
  id: string
  watchlistId: string
  userId: string
  symbol: string
  assetType: AssetType
  addedPrice: number | null
  notes: string | null
  createdAt: string
}

// ---- Agent Trading Config ----

export interface TradingAgentConfig {
  id: string
  agentId: string
  userId: string
  portfolioId: string | null
  autoTrade: boolean
  maxPositionSize: number
  riskLevel: RiskLevel
  allowedAssets: AssetType[]
  tradingConfig: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

// ---- Asset Info ----

export const TRADING_ASSETS: Record<AssetType, {
  label: string
  icon: string
  color: string
  exampleSymbols: string[]
}> = {
  stock: {
    label: 'Stocks',
    icon: 'Building2',
    color: '#6366f1',
    exampleSymbols: ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
  },
  crypto: {
    label: 'Crypto',
    icon: 'Bitcoin',
    color: '#f59e0b',
    exampleSymbols: ['BTC', 'ETH', 'SOL', 'DOGE', 'ADA'],
  },
  forex: {
    label: 'Forex',
    icon: 'Globe',
    color: '#22c55e',
    exampleSymbols: ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD'],
  },
}

export const TIMEFRAMES = [
  { value: '1m', label: '1 min' },
  { value: '5m', label: '5 min' },
  { value: '15m', label: '15 min' },
  { value: '1h', label: '1 hour' },
  { value: '4h', label: '4 hour' },
  { value: '1d', label: '1 day' },
  { value: '1w', label: '1 week' },
  { value: '1M', label: '1 month' },
] as const

export const INDICATOR_TYPES = [
  { value: 'sma', label: 'Simple Moving Avg' },
  { value: 'ema', label: 'Exponential Moving Avg' },
  { value: 'rsi', label: 'Relative Strength Index' },
  { value: 'macd', label: 'MACD' },
  { value: 'bb', label: 'Bollinger Bands' },
  { value: 'volume', label: 'Volume' },
  { value: 'custom', label: 'Custom Indicator' },
] as const

// ---- Multi-Agent Trading Debate ----

export type AgentTradingRole =
  | 'macro_strategist'
  | 'sector_analyst'
  | 'sentiment_agent'
  | 'technical_analyst'
  | 'risk_manager'
  | 'execution_optimizer'

export type TradingRecommendation = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL'
export type ConsensusAction = 'BUY' | 'SELL' | 'HOLD'

export interface AgentRoleConfig {
  role: AgentTradingRole
  label: string
  expertise: string
  framework: string
  temperature: number
  weight: number
}

export interface AgentAnalysis {
  role: AgentTradingRole
  recommendation: TradingRecommendation
  confidence: number
  reasoning: string
  keyMetrics: Record<string, number | string>
  riskFlags: string[]
  latencyMs: number
  model?: string
}

export interface DebateState {
  symbol: string
  assetType: AssetType
  marketData: MarketDebateContext
  currentRound: number
  maxRounds: number
  agentAnalyses: AgentAnalysis[]
  supervisorInstruction: string
  consensusReached: boolean
  consensusThreshold: number
  vetoTriggered: boolean
  finalDecision: FinalDecision | null
  votingBreakdown: VotingBreakdown[]
  debateLog: string[]
}

export interface MarketDebateContext {
  symbol: string
  assetType: AssetType
  quote: MarketQuote | null
  newsSentiment: NewsSentimentSummary
  knowledgeContext: string
  technicalSummary: string
  fundamentalSummary: string
  bars?: HistoricalBar[]
}

export interface FinalDecision {
  action: ConsensusAction
  overallConfidence: number
  targetPrice: number | null
  stopLoss: number | null
  takeProfit: number | null
  positionSizePct: number
  reasoningSummary: string
  allAnalyses: AgentAnalysis[]
  debateRounds: number
  riskManagerApproval: boolean
}

export interface VotingBreakdown {
  role: AgentTradingRole
  vote: TradingRecommendation
  weight: number
  contribution: number
}

export interface NewsSentimentSummary {
  overallSentiment: 'positive' | 'negative' | 'neutral'
  score: number
  articleCount: number
  keyThemes: string[]
  recentHeadlines: string[]
}

// ---- Agent Debate Config ----

export const AGENT_ROLES: Record<AgentTradingRole, AgentRoleConfig> = {
  macro_strategist: {
    role: 'macro_strategist',
    label: 'Macro Strategist',
    expertise: 'Global macroeconomics, monetary/fiscal policy, geopolitical risk',
    framework: 'Evaluates macro variables (GDP, inflation, rates), central bank policy, global capital flows',
    temperature: 0.4,
    weight: 0.7,
  },
  sector_analyst: {
    role: 'sector_analyst',
    label: 'Sector Analyst',
    expertise: 'Sector rotation, industry dynamics, competitive landscape',
    framework: 'Analyzes sector position in business cycle, competitive moats, regulatory environment',
    temperature: 0.4,
    weight: 0.7,
  },
  sentiment_agent: {
    role: 'sentiment_agent',
    label: 'Sentiment Agent',
    expertise: 'NLP, news sentiment, social media analysis, insider transactions',
    framework: 'Aggregates multi-source sentiment from news, social media, insider/institutional behavior',
    temperature: 0.5,
    weight: 0.6,
  },
  technical_analyst: {
    role: 'technical_analyst',
    label: 'Technical Analyst',
    expertise: 'Price action, chart patterns, oscillators, volume analysis',
    framework: 'Multi-timeframe analysis: trend structure, support/resistance, momentum divergence',
    temperature: 0.3,
    weight: 0.65,
  },
  risk_manager: {
    role: 'risk_manager',
    label: 'Risk Manager',
    expertise: 'Portfolio risk (VaR), position sizing, drawdown control, Kelly criterion',
    framework: 'Risk-first evaluation: VaR contributions, concentration limits, correlation analysis',
    temperature: 0.1,
    weight: 0.9,
  },
  execution_optimizer: {
    role: 'execution_optimizer',
    label: 'Execution Optimizer',
    expertise: 'Order execution, market microstructure, liquidity analysis, TCA',
    framework: 'Assesses order book depth, market impact, execution costs to select optimal algorithm',
    temperature: 0.2,
    weight: 0.6,
  },
}

export const DEFAULT_DEBATE_CONFIG = {
  maxRounds: 3,
  consensusThreshold: 0.6,
  requireRiskAgreement: true,
  minConfidenceForAuto: 0.7,
  maxPositionSizePct: 0.25,
  maxDailyLossPct: 0.05,
} as const

// ---- Knowledge Enrichment ----

export interface KnowledgeContext {
  symbol: string
  assetType: AssetType
  companyProfile: CompanyProfile | null
  newsItems: MarketNewsItem[]
  sentimentSummary: NewsSentimentSummary
  technicalSnapshot: TechnicalSnapshot | null
  enrichedAt: string
}

export interface CompanyProfile {
  name: string
  sector: string
  industry: string
  marketCap: number
  peRatio: number | null
  eps: number | null
  revenue: number | null
  description: string
  employees: number | null
  website: string | null
}

export interface TechnicalSnapshot {
  trend: 'bullish' | 'bearish' | 'neutral'
  rsi: number | null
  macdSignal: 'bullish' | 'bearish' | 'neutral'
  supportLevels: number[]
  resistanceLevels: number[]
  volumeProfile: 'increasing' | 'decreasing' | 'stable'
  patterns: string[]
}

// ---- Meta-Learning ----

export interface DebateRecord {
  id: string
  symbol: string
  assetType: AssetType
  timestamp: string
  finalDecision: FinalDecision
  debateState: DebateState
  outcome: 'pending' | 'win' | 'loss' | 'breakeven'
  pnl: number | null
  pnlPct: number | null
}

export interface AgentPerformance {
  role: AgentTradingRole
  accuracy: number
  totalPredictions: number
  correctPredictions: number
  averageConfidence: number
  calibrationError: number
  attributedPnl: number
  lastUpdated: string
}

export interface PerformanceMetrics {
  winRate: number
  sharpeRatio: number
  maxDrawdown: number
  profitFactor: number
  totalTrades: number
  winningTrades: number
  losingTrades: number
  avgWin: number
  avgLoss: number
  cumulativePnl: number
  agentPerformances: Record<AgentTradingRole, AgentPerformance>
}

export interface OptimizationSuggestion {
  type: 'weight' | 'threshold' | 'risk' | 'prompt'
  target: string
  currentValue: number | string
  suggestedValue: number | string
  confidence: number
  reasoning: string
}
