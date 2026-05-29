/**
 * Unit tests for TradingWorkforce.recordDebateForMetaLearning() and
 * recordTradeForMetaLearning() — verifying that DebateRecord and
 * TradeOutcomeRecord are built correctly from debate states and
 * execution reports.
 */

import { TradingWorkforce } from '../../src/trading/workforce'
import type {
  AgentAnalysis,
  AgentTradingRole,
  DebateState,
  FinalDecision,
  MarketDataInput,
  TradingRecommendation,
} from '../../src/trading/types'
import type { ExecutionReport } from '../../src/trading/integration'
import type { DebateRecord, TradeOutcomeRecord } from '../../src/meta/types'
import type { MetaLearningPipeline } from '../../src/meta/pipeline'
import { DEFAULT_TRADING_CONFIG } from '../../src/trading/config'

// ----------------------------------------------------------------
// Test Helpers
// ----------------------------------------------------------------

/** Build a minimal MarketDataInput for test debates */
function makeMarketSnapshot(overrides: Partial<MarketDataInput> = {}): MarketDataInput {
  return {
    symbol: 'AAPL',
    currentPrice: 175.0,
    dailyChangePct: 1.5,
    volume: 50_000_000,
    avgVolume: 45_000_000,
    bidAskSpread: 0.02,
    ...overrides,
  }
}

/** Build a full FinalDecision */
function makeFinalDecision(overrides: Partial<FinalDecision> = {}): FinalDecision {
  return {
    action: 'BUY',
    overallConfidence: 0.82,
    reasoningSummary: 'Strong macroeconomic tailwinds and bullish technicals.',
    vetoApplied: false,
    roundsRequired: 2,
    allAnalyses: [],
    votingBreakdown: [],
    timestamp: new Date().toISOString(),
    requiresHumanReview: false,
    ...overrides,
  }
}

/** Build a single AgentAnalysis */
function makeAnalysis(
  role: AgentTradingRole,
  recommendation: TradingRecommendation,
  overrides: Partial<AgentAnalysis> = {}
): AgentAnalysis {
  return {
    role,
    round: 0,
    recommendation,
    confidence: 0.85,
    reasoning: `${role} analysis: recommending ${recommendation}`,
    evidenceRefs: ['price', 'volume', 'rsi'],
    keyMetrics: { rsi: 55 },
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

/** Build a DebateState with sensible defaults */
function makeDebateState(overrides: Partial<DebateState> = {}): DebateState {
  const analyses: AgentAnalysis[] = [
    makeAnalysis('macro_strategist', 'BUY', { round: 0, confidence: 0.9 }),
    makeAnalysis('sector_analyst', 'STRONG_BUY', { round: 0, confidence: 0.85 }),
    makeAnalysis('sentiment_agent', 'BUY', { round: 1, confidence: 0.7 }),
    makeAnalysis('technical_analyst', 'STRONG_BUY', { round: 0, confidence: 0.8 }),
    makeAnalysis('risk_manager', 'BUY', { round: 1, confidence: 0.6 }),
    makeAnalysis('execution_optimizer', 'BUY', { round: 1, confidence: 0.75 }),
  ]

  return {
    marketData: makeMarketSnapshot(),
    symbol: 'AAPL',
    currentRound: 1,
    maxRounds: 3,
    agentAnalyses: analyses,
    consensusReached: true,
    vetoTriggered: false,
    finalDecision: makeFinalDecision({ action: 'BUY', roundsRequired: 2 }),
    historicalWeights: {},
    consensusThreshold: 0.6,
    sessionId: 'session-test-001',
    ...overrides,
  }
}

/** Build an ExecutionReport */
function makeExecutionReport(overrides: Partial<ExecutionReport> = {}): ExecutionReport {
  return {
    orderId: 'order-abc-123',
    correlationId: 'corr-xyz-456',
    symbol: 'AAPL',
    side: 'BUY',
    orderType: 'MARKET',
    quantity: 100,
    filledQuantity: 100,
    avgFillPrice: 175.25,
    status: 'FILLED',
    timestamp: '2026-05-28T14:30:00.000Z',
    ...overrides,
  }
}

// ----------------------------------------------------------------
// Mock MetaLearningPipeline
// ----------------------------------------------------------------

type PipelineCall = {
  method: string
  args: unknown[]
}

function createMockPipeline() {
  const calls: PipelineCall[] = []

  const mock = {
    onDebateComplete: jest.fn((record: DebateRecord) => {
      calls.push({ method: 'onDebateComplete', args: [record] })
    }),
    onAgentAnalysis: jest.fn((
      debateId: string,
      role: AgentTradingRole,
      analysis: AgentAnalysis,
      provider: string,
      model: string,
      latencyMs: number,
      tokensUsed: number
    ) => {
      calls.push({ method: 'onAgentAnalysis', args: [debateId, role, analysis, provider, model, latencyMs, tokensUsed] })
    }),
    onTradeExecuted: jest.fn((outcome: TradeOutcomeRecord) => {
      calls.push({ method: 'onTradeExecuted', args: [outcome] })
    }),
    registerPrompt: jest.fn(),
    getStatus: jest.fn(() => ({ running: false, banditState: { totalPulls: 0, dominantModels: {} as Record<AgentTradingRole, string> }, generationCount: 0, promptVersionCount: 0 })),
    // Private method access for clearing
    _calls: calls,
    _reset() { calls.length = 0 },
  }

  return mock as unknown as MetaLearningPipeline & { _calls: PipelineCall[]; _reset(): void }
}

/** Access a private method on TradingWorkforce */
function callPrivate(workforce: TradingWorkforce, method: string, ...args: unknown[]): unknown {
  return (workforce as any)[method](...args)
}

// ----------------------------------------------------------------
// Tests: recordDebateForMetaLearning
// ----------------------------------------------------------------

describe('TradingWorkforce.recordDebateForMetaLearning', () => {
  let workforce: TradingWorkforce
  let pipeline: MetaLearningPipeline & { _calls: PipelineCall[]; _reset(): void }

  beforeEach(() => {
    pipeline = createMockPipeline()
    workforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  // ── Basic Record Construction ──

  describe('basic record construction', () => {
    it('builds DebateRecord with correct top-level fields from the debate state', () => {
      const debateState = makeDebateState({ sessionId: 'session-abc' })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      expect(record.sessionId).toBe('session-abc')
      expect(record.symbol).toBe('AAPL')
      expect(record.marketSnapshot.symbol).toBe('AAPL')
      expect(record.marketSnapshot.currentPrice).toBe(175)
      expect(record.decision.action).toBe('BUY')
      expect(record.decision.overallConfidence).toBe(0.82)
      expect(record.agentAnalyses).toHaveLength(6)
      expect(record.roundsRequired).toBe(2) // currentRound(1) + 1
      expect(record.vetoApplied).toBe(false)
    })

    it('computes roundsRequired as currentRound + 1', () => {
      const debateState = makeDebateState({ currentRound: 3 })
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.roundsRequired).toBe(4)
    })

    it('captures vetoApplied from vetoTriggered', () => {
      const debateState = makeDebateState({ vetoTriggered: true, vetoReason: 'Drawdown limit exceeded' })
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.vetoApplied).toBe(true)
    })

    it('records a timestamp close to now', () => {
      const before = new Date().toISOString()
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const after = new Date().toISOString()
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      expect(record.timestamp >= before).toBe(true)
      expect(record.timestamp <= after).toBe(true)
    })
  })

  // ── Agent Provider/Model Maps ──

  describe('agent provider, model, and prompt version maps', () => {
    it('builds agentProviders map from agent configs', () => {
      const debateState = makeDebateState()

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      expect(record.agentProviders.macro_strategist).toBe('openai')
      expect(record.agentProviders.sector_analyst).toBe('openai')
      expect(record.agentProviders.sentiment_agent).toBe('openai')
      expect(record.agentProviders.technical_analyst).toBe('openai')
      expect(record.agentProviders.risk_manager).toBe('openai')
      expect(record.agentProviders.execution_optimizer).toBe('openai')
    })

    it('builds agentModels map from agent configs', () => {
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      // Default provider is 'openai' with gptModel = 'gpt-4o'
      expect(typeof record.agentModels.macro_strategist).toBe('string')
      expect(record.agentModels.macro_strategist.length).toBeGreaterThan(0)
      // All roles should have model entries
      for (const role of ['macro_strategist', 'sector_analyst', 'sentiment_agent', 'technical_analyst', 'risk_manager', 'execution_optimizer'] as AgentTradingRole[]) {
        expect(record.agentModels[role]).toBeTruthy()
      }
    })

    it('builds promptVersions map from agent config IDs', () => {
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      // Config IDs follow pattern `trading-agent-{role}`
      expect(record.promptVersions.macro_strategist).toBe('trading-agent-macro_strategist')
      expect(record.promptVersions.risk_manager).toBe('trading-agent-risk_manager')
    })

    it('includes all 6 roles in agentProviders, agentModels, and promptVersions', () => {
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord

      const expectedRoles: AgentTradingRole[] = [
        'macro_strategist', 'sector_analyst', 'sentiment_agent',
        'technical_analyst', 'risk_manager', 'execution_optimizer',
      ]

      for (const role of expectedRoles) {
        expect(record.agentProviders[role]).toBeDefined()
        expect(record.agentModels[role]).toBeDefined()
        expect(record.promptVersions[role]).toBeDefined()
      }
    })
  })

  // ── Pipeline Call Ordering ──

  describe('pipeline call ordering', () => {
    it('calls onDebateComplete before any onAgentAnalysis', () => {
      const debateState = makeDebateState()

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      // First call must be onDebateComplete
      expect(pipeline._calls[0].method).toBe('onDebateComplete')
      // Remaining calls are onAgentAnalysis
      const remainingCalls = pipeline._calls.slice(1)
      expect(remainingCalls.every(c => c.method === 'onAgentAnalysis')).toBe(true)
    })

    it('calls onDebateComplete exactly once', () => {
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const debateCalls = pipeline._calls.filter(c => c.method === 'onDebateComplete')
      expect(debateCalls).toHaveLength(1)
    })

    it('calls onAgentAnalysis once per agent analysis (6 agents)', () => {
      const debateState = makeDebateState()
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)
      const analysisCalls = pipeline._calls.filter(c => c.method === 'onAgentAnalysis')
      expect(analysisCalls).toHaveLength(6)
    })

    it('passes the correct debate sessionId to onAgentAnalysis', () => {
      const debateState = makeDebateState({ sessionId: 'debate-42' })
      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const analysisCalls = pipeline._calls.filter(c => c.method === 'onAgentAnalysis')
      for (const call of analysisCalls) {
        expect(call.args[0]).toBe('debate-42')
      }
    })
  })

  // ── LLM Metadata Precedence ──

  describe('LLM metadata precedence in onAgentAnalysis', () => {
    it('uses analysis.llmProvider when present in the analysis', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { llmProvider: 'anthropic' }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const provider = call.args[3] as string
      expect(provider).toBe('anthropic')
    })

    it('falls back to agentProviders map when analysis has no llmProvider', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { llmProvider: undefined }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const provider = call.args[3] as string
      // Should fall back to the agent config default ('openai')
      expect(provider).toBe('openai')
    })

    it('uses analysis.llmModel when present in the analysis', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { llmModel: 'claude-opus-4' }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const model = call.args[4] as string
      expect(model).toBe('claude-opus-4')
    })

    it('falls back to agentModels map when analysis has no llmModel', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { llmModel: undefined }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const model = call.args[4] as string
      // Should fall back to agent config model (gpt-4o by default)
      expect(model).toBeTruthy()
      expect(model).not.toBe('unknown')
    })

    it('uses analysis.latencyMs when present', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { latencyMs: 1234 }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const latency = call.args[5] as number
      expect(latency).toBe(1234)
    })

    it('defaults latencyMs to 0 when not present', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { latencyMs: undefined }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const latency = call.args[5] as number
      expect(latency).toBe(0)
    })

    it('uses analysis.tokensUsed when present', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { tokensUsed: 2500 }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const tokens = call.args[6] as number
      expect(tokens).toBe(2500)
    })

    it('defaults tokensUsed to 0 when not present', () => {
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', { tokensUsed: undefined }),
      ]
      const debateState = makeDebateState({ agentAnalyses: analyses })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const call = pipeline._calls.find(c => c.method === 'onAgentAnalysis')!
      const tokens = call.args[6] as number
      expect(tokens).toBe(0)
    })
  })

  // ── Edge Cases ──

  describe('edge cases', () => {
    it('handles empty agentAnalyses gracefully', () => {
      const debateState = makeDebateState({ agentAnalyses: [] })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      // Should still call onDebateComplete
      expect(pipeline.onDebateComplete).toHaveBeenCalledTimes(1)
      // But no onAgentAnalysis calls
      const analysisCalls = pipeline._calls.filter(c => c.method === 'onAgentAnalysis')
      expect(analysisCalls).toHaveLength(0)
    })

    it('handles a vetoED debate where finalDecision.vetoApplied is true', () => {
      const debateState = makeDebateState({
        vetoTriggered: true,
        vetoReason: 'Risk limit breached',
        finalDecision: makeFinalDecision({ action: 'HOLD', vetoApplied: true }),
      })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.vetoApplied).toBe(true)
      expect(record.decision.vetoApplied).toBe(true)
      expect(record.decision.action).toBe('HOLD')
    })

    it('handles a SELL decision correctly', () => {
      const debugState = makeDebateState({
        finalDecision: makeFinalDecision({ action: 'SELL' }),
      })

      callPrivate(workforce, 'recordDebateForMetaLearning', debugState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.decision.action).toBe('SELL')
    })

    it('handles multi-round debates (round > 0)', () => {
      const debateState = makeDebateState({ currentRound: 4 })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.roundsRequired).toBe(5)
    })

    it('passes full market data snapshot including indicators', () => {
      const debateState = makeDebateState({
        marketData: makeMarketSnapshot({ rsi14: 65, sma50: 170, vix: 18.5 }),
      })

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const record: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
      expect(record.marketSnapshot.rsi14).toBe(65)
      expect(record.marketSnapshot.sma50).toBe(170)
      expect(record.marketSnapshot.vix).toBe(18.5)
    })

    it('passes each analysis with its correct role to onAgentAnalysis', () => {
      const debateState = makeDebateState()

      callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

      const analysisCalls = pipeline._calls.filter(c => c.method === 'onAgentAnalysis')
      const rolesSeen = analysisCalls.map(c => c.args[1] as AgentTradingRole).sort()

      expect(rolesSeen).toEqual([
        'execution_optimizer', 'macro_strategist', 'risk_manager',
        'sector_analyst', 'sentiment_agent', 'technical_analyst',
      ])
    })
  })
})

// ----------------------------------------------------------------
// Tests: recordTradeForMetaLearning
// ----------------------------------------------------------------

describe('TradingWorkforce.recordTradeForMetaLearning', () => {
  let workforce: TradingWorkforce
  let pipeline: MetaLearningPipeline & { _calls: PipelineCall[]; _reset(): void }

  beforeEach(() => {
    pipeline = createMockPipeline()
    workforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  // ── Basic Record Construction ──

  describe('basic record construction', () => {
    it('builds TradeOutcomeRecord with correct fields from execution report', () => {
      const execution: ExecutionReport = {
        orderId: 'ord-001',
        correlationId: 'corr-001',
        symbol: 'AAPL',
        side: 'BUY',
        orderType: 'MARKET',
        quantity: 100,
        filledQuantity: 100,
        avgFillPrice: 175.50,
        status: 'FILLED',
        timestamp: '2026-05-28T14:30:00.000Z',
      }

      callPrivate(workforce, 'recordTradeForMetaLearning', 'session-xyz', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord

      expect(outcome.debateSessionId).toBe('session-xyz')
      expect(outcome.symbol).toBe('AAPL')
      expect(outcome.entryPrice).toBe(175.50)
      expect(outcome.entryTimestamp).toBe('2026-05-28T14:30:00.000Z')
    })

    it('maps BUY side to LONG direction', () => {
      const execution = makeExecutionReport({ side: 'BUY' })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.direction).toBe('LONG')
    })

    it('maps SELL side to SHORT direction', () => {
      const execution = makeExecutionReport({ side: 'SELL' })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.direction).toBe('SHORT')
    })

    it('maps SELL_SHORT side to SHORT direction', () => {
      const execution = makeExecutionReport({ side: 'SELL_SHORT' })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.direction).toBe('SHORT')
    })

    it('outcome is always PENDING on entry', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.outcome).toBe('PENDING')
    })

    it('pnl is always 0 on entry', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.pnl).toBe(0)
    })

    it('pnlPct is always 0 on entry', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.pnlPct).toBe(0)
    })

    it('maxAdversePct and maxFavorablePct start at 0', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.maxAdversePct).toBe(0)
      expect(outcome.maxFavorablePct).toBe(0)
    })

    it('exitPrice, exitTimestamp, and holdingDurationMs are not set on entry', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.exitPrice).toBeUndefined()
      expect(outcome.exitTimestamp).toBeUndefined()
      expect(outcome.holdingDurationMs).toBeUndefined()
    })
  })

  // ── Pipeline Integration ──

  describe('pipeline integration', () => {
    it('calls pipeline.onTradeExecuted exactly once', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      expect(pipeline.onTradeExecuted).toHaveBeenCalledTimes(1)
    })

    it('passes the full TradeOutcomeRecord to onTradeExecuted', () => {
      const execution = makeExecutionReport({ avgFillPrice: 200.75 })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's99', 'MSFT', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.debateSessionId).toBe('s99')
      expect(outcome.symbol).toBe('MSFT')
      expect(outcome.entryPrice).toBe(200.75)
      expect(outcome.direction).toBe('LONG')
    })
  })

  // ── Edge Cases ──

  describe('edge cases', () => {
    it('handles partially filled orders (uses avgFillPrice from partial fill)', () => {
      const execution = makeExecutionReport({
        status: 'PARTIALLY_FILLED',
        quantity: 200,
        filledQuantity: 150,
        avgFillPrice: 178.25,
      })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.entryPrice).toBe(178.25)
      expect(outcome.outcome).toBe('PENDING')
    })

    it('handles execution with commission in report', () => {
      const execution = makeExecutionReport({
        avgFillPrice: 150.0,
        commission: 5.99,
      })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.entryPrice).toBe(150.0)
      // Commission not currently stored in TradeOutcomeRecord — expected behavior
    })

    it('handles zero avgFillPrice gracefully', () => {
      const execution = makeExecutionReport({ avgFillPrice: 0 })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.entryPrice).toBe(0)
    })

    it('handles very high avgFillPrice', () => {
      const execution = makeExecutionReport({ avgFillPrice: 1_000_000 })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'BRK.A', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.entryPrice).toBe(1_000_000)
    })

    it('preserves the correct debateSessionId for trade attribution', () => {
      const execution = makeExecutionReport()

      callPrivate(workforce, 'recordTradeForMetaLearning', 'session-unique-789', 'AAPL', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.debateSessionId).toBe('session-unique-789')
    })

    it('different symbols produce correct symbol in outcome', () => {
      const execution = makeExecutionReport({ symbol: 'TSLA' })

      callPrivate(workforce, 'recordTradeForMetaLearning', 's1', 'TSLA', execution)

      const outcome: TradeOutcomeRecord = pipeline._calls[0].args[0] as TradeOutcomeRecord
      expect(outcome.symbol).toBe('TSLA')
    })
  })
})

// ----------------------------------------------------------------
// Integration: full debate → trade flow
// ----------------------------------------------------------------

describe('recordDebateForMetaLearning → recordTradeForMetaLearning flow', () => {
  let workforce: TradingWorkforce
  let pipeline: MetaLearningPipeline & { _calls: PipelineCall[]; _reset(): void }

  beforeEach(() => {
    pipeline = createMockPipeline()
    workforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  it('debate sessionId in TradeOutcomeRecord links back to the DebateRecord', () => {
    const sessionId = 'linked-session-42'

    // Step 1: record the debate
    const debateState = makeDebateState({ sessionId })
    callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

    // Step 2: record the trade from that debate
    const execution = makeExecutionReport()
    callPrivate(workforce, 'recordTradeForMetaLearning', sessionId, 'AAPL', execution)

    // Verify the debate record uses the sessionId
    const debateRecord: DebateRecord = pipeline._calls[0].args[0] as DebateRecord
    expect(debateRecord.sessionId).toBe(sessionId)

    // Verify the trade outcome links back to the same session
    const tradeOutcome: TradeOutcomeRecord = pipeline._calls[pipeline._calls.length - 1].args[0] as TradeOutcomeRecord
    expect(tradeOutcome.debateSessionId).toBe(sessionId)
  })

  it('recordDebateForMetaLearning throws when metaPipeline is null (caller must guard)', () => {
    // Create a workforce WITHOUT a meta pipeline
    const noPipelineWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, undefined)
    const debateState = makeDebateState()

    // The private method uses `this.metaPipeline!` (non-null assertion).
    // Calling it without a pipeline throws. The caller (analyze method)
    // is responsible for the `if (this.metaPipeline)` guard.
    expect(() =>
      callPrivate(noPipelineWorkforce, 'recordDebateForMetaLearning', debateState)
    ).toThrow()
  })

  it('recordDebateForMetaLearning does not mutate the original debateState', () => {
    const debateState = makeDebateState({ sessionId: 'immutable-test' })
    const originalAnalysesLength = debateState.agentAnalyses.length
    const originalSessionId = debateState.sessionId

    callPrivate(workforce, 'recordDebateForMetaLearning', debateState)

    // Original state should be unchanged
    expect(debateState.sessionId).toBe(originalSessionId)
    expect(debateState.agentAnalyses).toHaveLength(originalAnalysesLength)
  })
})
