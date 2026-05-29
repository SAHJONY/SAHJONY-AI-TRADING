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

// ============================================================
// Layer 5: Pod Manager (Portfolio Manager Agent Hierarchy)
// ============================================================

export interface PodConfig {
  podId: string
  name: string
  description: string
  /** Assets this pod is responsible for */
  assets: PodAsset[]
  /** Strategy IDs deployed in this pod */
  strategyIds: string[]
  /** Hard risk limits — if breached, PM MUST liquidate */
  riskLimits: PodRiskLimits
  /** Capital allocated to this pod by CIO */
  allocatedCapital: number
  /** Current PM performance metrics */
  performance: PodPerformance
  /** PM's current conviction level (0-1) for their strategy */
  conviction: number
  createdAt: string
  updatedAt: string
}

export interface PodAsset {
  symbol: string
  assetType: AssetType
  /** Target allocation % of pod capital */
  targetAllocationPct: number
  /** Whether this asset is currently active in debates */
  active: boolean
}

export interface PodRiskLimits {
  /** Max position size as % of pod capital */
  maxPositionSizePct: number
  /** Max drawdown before forced liquidation */
  maxDrawdownPct: number
  /** Max daily loss before trading halted */
  dailyLossLimitPct: number
  /** Max single-asset concentration */
  maxSingleAssetPct: number
  /** Max correlation between pod assets */
  maxCorrelation: number
  /** Stop-loss as % below entry price */
  hardStopLossPct: number
}

export interface PodPerformance {
  totalPnl: number
  totalPnlPct: number
  sharpeRatio: number
  maxDrawdown: number
  winRate: number
  totalTrades: number
  currentDrawdown: number
  dailyPnl: number
  weeklyPnl: number
  monthlyPnl: number
}

export interface PodState {
  pod: PodConfig
  /** Latest debate results per asset */
  assetDebates: Record<string, DebateState>
  /** Active holdings in this pod */
  holdings: Holding[]
  /** Current cash balance */
  cashBalance: number
  /** Total portfolio value (cash + holdings) */
  totalValue: number
  /** Whether risk limits are currently breached */
  riskBreached: boolean
  /** Which risk limits are breached */
  breachedLimits: string[]
  /** PM's latest decision for this cycle */
  latestDecision: PMDecision | null
  /** Pod activity log */
  activityLog: string[]
}

export interface PMDecision {
  podId: string
  timestamp: string
  /** Overall action: deploy, reduce, hold, liquidate */
  overallAction: 'deploy' | 'reduce' | 'hold' | 'liquidate'
  /** Per-asset allocation decisions */
  assetDecisions: AssetDecision[]
  /** Total capital to deploy this cycle */
  capitalToDeploy: number
  /** Reasoning behind the PM's decision */
  reasoning: string
  /** Risk assessment summary */
  riskAssessment: string
  /** CIO directives that influenced this decision */
  cioDirectives: CIODirective[]
  /** Confidence in this decision (0-1) */
  confidence: number
}

export interface AssetDecision {
  symbol: string
  assetType: AssetType
  action: ConsensusAction
  allocationPct: number
  /** The debate that produced this decision */
  debate: DebateState | null
  /** PM override reason (if PM overrode debate consensus) */
  overrideReason?: string
  targetPrice: number | null
  stopLoss: number | null
  takeProfit: number | null
  quantity: number
}

// ============================================================
// Layer 6: Chief Investment Officer (CIO Meta-Agent)
// ============================================================

export interface CIODirective {
  id: string
  targetPodId: string
  type: 'allocation' | 'risk' | 'strategy' | 'halt' | 'liquidate'
  instruction: string
  /** New risk limits to enforce (overrides pod's own limits) */
  riskLimitOverrides?: Partial<PodRiskLimits>
  /** Target allocation shift */
  allocationShift?: { fromPodId?: string; toPodId?: string; amount: number }
  /** Priority: critical directives must be followed immediately */
  priority: 'critical' | 'high' | 'medium' | 'advisory'
  reasoning: string
  issuedAt: string
  expiresAt?: string
}

export interface CIODecision {
  id: string
  timestamp: string
  /** Pod-level capital allocations */
  podAllocations: PodCapitalAllocation[]
  /** Directives issued to PMs this cycle */
  directives: CIODirective[]
  /** Overall workforce risk assessment */
  riskAssessment: CIORiskAssessment
  /** CIO's macro outlook driving these decisions */
  macroOutlook: string
  /** Overall reasoning */
  reasoning: string
  /** Previous cycle performance since last CIO decision */
  sinceLastCycle: {
    totalPnl: number
    totalPnlPct: number
    bestPod: string
    worstPod: string
  }
}

export interface PodCapitalAllocation {
  podId: string
  podName: string
  allocatedCapital: number
  allocationPct: number
  /** Risk budget assigned to this pod (% of total) */
  riskBudget: number
  /** Performance score used for allocation (0-1) */
  performanceScore: number
  /** CIO's assessment of this pod */
  assessment: string
}

export interface CIORiskAssessment {
  totalPortfolioValue: number
  totalDrawdown: number
  totalDailyPnl: number
  /** Value at Risk (95% confidence) */
  var95: number
  /** Expected shortfall / CVaR */
  cvar95: number
  /** Correlation matrix between pods */
  podCorrelations: { podA: string; podB: string; correlation: number }[]
  /** Overall risk level */
  overallRisk: RiskLevel
  /** Whether any risk limits are breached */
  anyBreached: boolean
  /** Concentration risk warnings */
  warnings: string[]
}

export interface CIOSelfReflection {
  id: string
  timestamp: string
  /** The decision being reflected on */
  decisionId: string
  /** Time period being reviewed */
  reviewPeriod: { start: string; end: string }
  /** What the CIO got right */
  strengths: string[]
  /** What the CIO got wrong */
  weaknesses: string[]
  /** Pattern recognition: recurring themes in CIO mistakes */
  patterns: string[]
  /** Specific lessons learned */
  lessons: string[]
  /** Proposed adjustments to CIO behavior */
  adjustments: {
    type: 'allocation' | 'risk' | 'timing' | 'pod_creation' | 'pod_dissolution'
    description: string
    confidence: number
  }[]
  /** Performance impact of this decision */
  impact: {
    pnlAttributed: number
    sharpeImpact: number
    drawdownImpact: number
    overall: 'positive' | 'neutral' | 'negative'
  }
}

export interface WorkforceState {
  /** All pods in the workforce */
  pods: PodState[]
  /** CIO's latest decision */
  latestCIODecision: CIODecision | null
  /** CIO's recent self-reflections */
  recentReflections: CIOSelfReflection[]
  /** Aggregate workforce performance */
  aggregatePerformance: {
    totalCapital: number
    totalValue: number
    totalPnl: number
    totalPnlPct: number
    sharpeRatio: number
    maxDrawdown: number
    winRate: number
    dailyPnl: number
    podCount: number
    activeDebates: number
  }
  /** Workforce-level activity log */
  workforceLog: string[]
}

// ============================================================
// Pod & CIO Defaults
// ============================================================

export const DEFAULT_POD_RISK_LIMITS: PodRiskLimits = {
  maxPositionSizePct: 0.25,
  maxDrawdownPct: 0.15,
  dailyLossLimitPct: 0.05,
  maxSingleAssetPct: 0.30,
  maxCorrelation: 0.7,
  hardStopLossPct: 0.08,
}

// ============================================================
// Layer 3: Regime Geometry Detector (Information Geometry)
// ============================================================

/** Market regime classification from Fisher geodesic analysis */
export type MarketRegime = 'calm' | 'trending' | 'volatile' | 'transitioning' | 'crisis'

/** Historical record of a detected regime shift */
export interface RegimeShiftEvent {
  id: string
  from: MarketRegime
  to: MarketRegime
  severity: number
  timestamp: string
  geodesicDistance: number
  fisherDeterminant: number
}

/** The Fisher Information Metric tensor at a point in distribution space */
export interface FisherMetric {
  /** First parameter (mu) Fisher information */
  iMu: number
  /** Second parameter (sigma2) Fisher information */
  iSigma2: number
  /** Determinant of the Fisher metric (volume element) */
  determinant: number
  /** Estimated mean return from the window */
  mu: number
  /** Estimated variance from the window */
  sigma2: number
  /** Window size used for estimation */
  windowSize: number
  /** Timestamp of this metric snapshot */
  computedAt: string
}

/** A point along the geodesic path through distribution space */
export interface GeodesicPathPoint {
  /** Index in the geodesic sequence */
  index: number
  /** Fisher metric at this point */
  metric: FisherMetric
  /** KL divergence from the previous point (local distance) */
  klDistance: number
  /** Cumulative geodesic distance from the anchor point */
  cumulativeDistance: number
  /** Geodesic velocity (rate of change, smoothed) */
  velocity: number
  /** Detected regime at this point */
  regime: MarketRegime
  /** Timestamp */
  timestamp: string
}

/** Complete regime geometry analysis result */
export interface RegimeGeometryResult {
  symbol: string
  assetType: AssetType
  /** Current regime classification */
  regime: MarketRegime
  /** Confidence in the regime classification (0-1) */
  regimeConfidence: number
  /** Current Fisher metric snapshot */
  currentMetric: FisherMetric
  /** Recent geodesic path (last N points) */
  geodesicPath: GeodesicPathPoint[]
  /** Latest geodesic distance from the anchor point */
  totalGeodesicDistance: number
  /** Current geodesic velocity (smoothed) */
  currentVelocity: number
  /** Velocity threshold for regime detection */
  velocityThreshold: number
  /** Whether a regime shift has been detected recently */
  regimeShiftDetected: boolean
  /** Regime shift severity (0-1, higher = more severe) */
  shiftSeverity: number
  /** Time since last regime shift in milliseconds */
  timeSinceLastShift: number
  /** Recent regime shift events (last 10) */
  recentShifts: RegimeShiftEvent[]
  /** Human-readable summary for debate agents */
  summary: string
  /** Number of observations in the tracking window */
  observationCount: number
  /** When this result was computed */
  computedAt: string
}

/** Configuration for the Regime Geometry Detector */
export interface RegimeGeometryConfig {
  /** Window size for return estimation */
  windowSize: number
  /** Number of historical geodesic points to retain */
  historyLength: number
  /** Smoothing factor for velocity (EMA alpha) */
  velocitySmoothing: number
  /** Number of standard deviations for shift detection threshold */
  shiftThresholdSigma: number
  /** Minimum observations before regime detection activates */
  minObservations: number
  /** KL divergence smoothing window for stable velocity estimation */
  klSmoothingWindow: number
}

export const DEFAULT_REGIME_GEOMETRY_CONFIG: RegimeGeometryConfig = {
  windowSize: 50,
  historyLength: 500,
  velocitySmoothing: 0.1,
  shiftThresholdSigma: 3.0,
  minObservations: 30,
  klSmoothingWindow: 10,
}

// ============================================================
// Pod & CIO Defaults
// ============================================================

export const DEFAULT_CIO_CONFIG = {
  maxPods: 5,
  minPodAllocationPct: 0.10,
  maxPodAllocationPct: 0.40,
  rebalanceThreshold: 0.05,   // Rebalance if allocation drifts >5%
  reflectionInterval: 7,       // Self-reflect every 7 cycles
  maxDrawdownBeforeHalt: 0.20, // Halt all trading if drawdown >20%
  riskFreeRate: 0.05,          // For Sharpe calculations
} as const
