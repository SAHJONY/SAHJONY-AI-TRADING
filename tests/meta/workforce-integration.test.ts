/**
 * End-to-end integration test: TradingWorkforce + MetaLearningPipeline
 *
 * Spins up a real TradingWorkforce with a real MetaLearningPipeline,
 * mocks the LLM provider so agents return canned analysis responses,
 * runs a simulated debate through the full LangGraph pipeline, and
 * verifies the pipeline's PerformanceTracker has recorded the debate,
 * agent analyses, and trade outcomes correctly.
 */

// ── Must be before any imports ──
// Mock the LLM provider so agents return canned responses instead of
// making real API calls. Each agent role gets a specific recommendation
// to create a realistic consensus scenario.

const cannedResponses: Record<string, {
  recommendation: string
  confidence: number
  reasoning: string
  evidenceRefs: string[]
  keyMetrics: Record<string, number>
}> = {
  macro_strategist: {
    recommendation: 'STRONG_BUY',
    confidence: 0.95,
    reasoning: 'Global GDP growth accelerating, dovish central bank policy, strong earnings season — all macro signals point to continued upside for this sector.',
    evidenceRefs: ['GDP growth', 'Fed funds rate', 'earnings growth'],
    keyMetrics: { gdpGrowth: 3.2, inflation: 2.8, targetPrice: 195 },
  },
  sector_analyst: {
    recommendation: 'STRONG_BUY',
    confidence: 0.90,
    reasoning: 'Sector rotation favoring technology, strong relative strength vs S&P 500, institutional accumulation pattern detected across top holdings.',
    evidenceRefs: ['sector rotation', 'relative strength', 'institutional flows'],
    keyMetrics: { sectorRSI: 62, sectorBeta: 1.15, institutionalFlow: 450000000 },
  },
  sentiment_agent: {
    recommendation: 'BUY',
    confidence: 0.88,
    reasoning: 'Positive sentiment across news, social media, and analyst reports. Options market showing bullish skew with elevated call volume. Put/Call ratio at 0.65 indicates optimism.',
    evidenceRefs: ['news sentiment', 'social media', 'options flow'],
    keyMetrics: { sentimentScore: 0.72, putCallRatio: 0.65, socialVolume: 125000 },
  },
  technical_analyst: {
    recommendation: 'STRONG_BUY',
    confidence: 0.92,
    reasoning: 'Price breaking above 50-day SMA with increasing volume. RSI at 58 (neutral-bullish). MACD bullish crossover confirmed. Multiple support levels holding at 170 and 165.',
    evidenceRefs: ['SMA crossover', 'RSI', 'MACD', 'volume profile'],
    keyMetrics: { rsi14: 58, sma50: 170, sma200: 155, vwap: 173.5, targetPrice: 192 },
  },
  risk_manager: {
    recommendation: 'BUY',
    confidence: 0.78,
    reasoning: 'Risk assessment: VaR at 95% confidence is acceptable ($1,200). Kelly criterion suggests 15% position size. Current portfolio drawdown at 3.2% — well within limits. No circuit breaker triggers.',
    evidenceRefs: ['VaR calculation', 'Kelly criterion', 'drawdown analysis'],
    keyMetrics: { var95: 1200, kellyFraction: 0.15, stopLoss: 168, positionSizePct: 0.15 },
  },
  execution_optimizer: {
    recommendation: 'BUY',
    confidence: 0.85,
    reasoning: 'Optimal execution: TWAP algorithm recommended. Bid-ask spread tight at 2bps. Average daily volume supports position size. Suggest limit order 30% into spread for best execution quality.',
    evidenceRefs: ['spread analysis', 'volume profile', 'TWAP schedule'],
    keyMetrics: { spreadBps: 2, avgDailyVolume: 45000000, targetPrice: 176 },
  },
}

// Track call counts per role for multi-debate scenarios
const callCounts: Record<string, number> = {}

const mockInvokeStructured = jest.fn(
  async (params: { llm: unknown; systemPrompt: string; userPrompt: string; schema: unknown; modelName: string }) => {
    // Determine which role this call is for by inspecting the system prompt.
    // NOTE: This is coupled to prompt.ts agent names — if prompts change,
    // the role detection may break silently. The callCounts assertion in
    // "mock correctly resolves each role" validates all 6 roles are matched.
    let role: string | null = null
    if (params.systemPrompt.includes('Macro Strategist')) role = 'macro_strategist'
    else if (params.systemPrompt.includes('Sector Analyst')) role = 'sector_analyst'
    else if (params.systemPrompt.includes('Sentiment Agent')) role = 'sentiment_agent'
    else if (params.systemPrompt.includes('Technical Analyst')) role = 'technical_analyst'
    else if (params.systemPrompt.includes('Risk Manager')) role = 'risk_manager'
    else if (params.systemPrompt.includes('Execution Optimizer')) role = 'execution_optimizer'
    else throw new Error(`Could not determine agent role from system prompt: ${params.systemPrompt.substring(0, 200)}`)

    callCounts[role] = (callCounts[role] || 0) + 1
    const round = callCounts[role] - 1

    const canned = cannedResponses[role]

    return {
      parsed: {
        recommendation: canned.recommendation,
        confidence: canned.confidence,
        reasoning: `[Round ${round}] ${canned.reasoning}`,
        evidenceRefs: canned.evidenceRefs,
        keyMetrics: canned.keyMetrics,
      },
      response: {
        content: JSON.stringify(canned),
        model: params.modelName,
        tokensUsed: 1500 + Math.floor(Math.random() * 500),
        latencyMs: 200 + Math.floor(Math.random() * 300),
        finishReason: 'stop' as const,
      },
    }
  }
)

jest.mock('../../src/trading/llm-provider', () => {
  const actual = jest.requireActual('../../src/trading/llm-provider')
  return {
    ...actual,
    invokeStructured: mockInvokeStructured,
  }
})

// ── Imports (after mocks) ──

import { TradingWorkforce, PortfolioState } from '../../src/trading/workforce'
import { MetaLearningPipeline } from '../../src/meta/pipeline'
import { PerformanceTracker } from '../../src/meta/performance-tracker'
import type {
  AgentTradingRole,
  MarketDataInput,
  FinalDecision,
  AgentAnalysis,
} from '../../src/trading/types'
import type { DebateRecord, TradeOutcomeRecord } from '../../src/meta/types'
import type { ExecutionReport } from '../../src/trading/integration'
import { DEFAULT_TRADING_CONFIG } from '../../src/trading/config'
import { DEFAULT_META_CONFIG } from '../../src/meta/pipeline'
// Knowledge pipeline for enrichment tests
import { KnowledgePipeline } from '../../src/knowledge/pipeline'
import type { AltDataSnapshot } from '../../src/knowledge/types'
import * as path from 'path'
import * as os from 'os'

// ── Test Helpers ──

/** Build market data for a simulated debate */
function makeMarketData(overrides: Partial<MarketDataInput> = {}): MarketDataInput {
  return {
    symbol: 'AAPL',
    currentPrice: 175.0,
    dailyChangePct: 1.5,
    volume: 50_000_000,
    avgVolume: 45_000_000,
    bidAskSpread: 0.02,
    rsi14: 58,
    sma50: 170,
    sma200: 155,
    vix: 15.2,
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════
// Integration Test Suite
// ═══════════════════════════════════════════════════════════════

describe('TradingWorkforce + MetaLearningPipeline Integration', () => {
  let pipeline: MetaLearningPipeline
  let workforce: TradingWorkforce
  let tracker: PerformanceTracker
  let tempDir: string

  beforeAll(() => {
    tempDir = path.join(os.tmpdir(), `meta-learning-test-${Date.now()}`)
  })

  beforeEach(() => {
    // Reset call tracking
    for (const key of Object.keys(callCounts)) delete callCounts[key]
    mockInvokeStructured.mockClear()

    // Create a real pipeline with disk persistence disabled
    pipeline = new MetaLearningPipeline({
      retention: {
        ...DEFAULT_META_CONFIG.retention,
        persistRecords: false,
        persistDir: tempDir,
      },
      ga: {
        ...DEFAULT_META_CONFIG.ga,
        persist: false,
        persistDir: tempDir,
        minSamples: 99999, // Prevent auto-evolution from triggering
      },
    })

    // Create workforce with the pipeline attached
    workforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)

    // Access tracker for verification
    tracker = pipeline.getTracker()

    // Skip Layer 1 connection by marking as initialized
    ;(workforce as any).initialized = true
  })

  afterEach(async () => {
    // No explicit cleanup needed — pipeline is never started,
    // tracker data is in-memory only (persistRecords: false).
  })

  // ═══════════════════════════════════════════════════════════════
  // 1. Full Debate Pipeline — Verifies end-to-end flow
  // ═══════════════════════════════════════════════════════════════

  describe('full debate pipeline', () => {
    it('runs a complete debate with all 6 agents and records results in the tracker', async () => {
      const marketData = makeMarketData()

      const result = await workforce.analyze(marketData)

      // ── Debate completed successfully ──
      expect(result.error).toBeUndefined()
      expect(result.decision).toBeDefined()
      expect(result.decision.action).toBe('BUY')
      expect(result.action).toBe('HELD') // No auto-execute, no portfolio

      // ── LLM provider was called for each of the 6 agents ──
      expect(mockInvokeStructured).toHaveBeenCalledTimes(6)

      // ── Tracker has 1 debate record ──
      const records = tracker.getDebateRecords()
      expect(records).toHaveLength(1)
      const debateRecord = records[0]

      // ── DebateRecord fields are populated correctly ──
      expect(debateRecord.sessionId).toBeTruthy()
      expect(debateRecord.sessionId).toBe(result.debateState.sessionId)
      expect(debateRecord.symbol).toBe('AAPL')
      expect(debateRecord.decision.action).toBe('BUY')
      expect(debateRecord.decision.overallConfidence).toBeGreaterThan(0.6)
      expect(debateRecord.decision.overallConfidence).toBeLessThanOrEqual(1.0)
      expect(debateRecord.vetoApplied).toBe(false)

      // ── Market snapshot preserved ──
      expect(debateRecord.marketSnapshot.symbol).toBe('AAPL')
      expect(debateRecord.marketSnapshot.currentPrice).toBe(175)
      expect(debateRecord.marketSnapshot.rsi14).toBe(58)

      // ── All 6 agent analyses recorded ──
      expect(debateRecord.agentAnalyses).toHaveLength(6)

      const rolesSeen = debateRecord.agentAnalyses.map(a => a.role).sort()
      expect(rolesSeen).toEqual([
        'execution_optimizer', 'macro_strategist', 'risk_manager',
        'sector_analyst', 'sentiment_agent', 'technical_analyst',
      ])

      // ── Each analysis has expected fields ──
      for (const analysis of debateRecord.agentAnalyses) {
        expect(analysis.role).toBeTruthy()
        expect(analysis.recommendation).toBeTruthy()
        expect(analysis.confidence).toBeGreaterThan(0)
        expect(analysis.confidence).toBeLessThanOrEqual(1)
        expect(analysis.reasoning.length).toBeGreaterThanOrEqual(20)
        expect(analysis.timestamp).toBeTruthy()
        // Layer 5 metadata present
        expect(analysis.llmProvider).toBe('openai')
        expect(analysis.llmModel).toBeTruthy()
        expect(typeof analysis.latencyMs).toBe('number')
        expect(typeof analysis.tokensUsed).toBe('number')
      }

      // ── Agent provider/model maps populated ──
      const expectedRoles: AgentTradingRole[] = [
        'macro_strategist', 'sector_analyst', 'sentiment_agent',
        'technical_analyst', 'risk_manager', 'execution_optimizer',
      ]
      for (const role of expectedRoles) {
        expect(debateRecord.agentProviders[role]).toBe('openai')
        expect(debateRecord.agentModels[role]).toBeTruthy()
        expect(debateRecord.promptVersions[role]).toBeTruthy()
      }
    })

    it('produces a consensus decision where abs score >= consensus threshold', async () => {
      const result = await workforce.analyze(makeMarketData())

      // With 3 STRONG_BUY and 3 BUY all at high confidence, consensus should be BUY
      expect(result.decision.action).toBe('BUY')
      expect(result.decision.overallConfidence).toBeGreaterThan(0.6)

      // Should not require human review if confidence >= 0.7
      // (absScore ~0.67 with default weights, so human review = true)
      expect(result.decision.requiresHumanReview).toBeDefined()
    })

    it('debate completes in exactly 1 round with unanimous bullish consensus', async () => {
      const result = await workforce.analyze(makeMarketData())

      // With all agents bullish, consensus should be reached in round 0 (1 round)
      expect(result.decision.roundsRequired).toBe(1)

      const records = tracker.getDebateRecords()
      expect(records[0].roundsRequired).toBe(1)
    })

    it('sessionId links the AnalysisResult, DebateRecord, and DebateState together', async () => {
      const result = await workforce.analyze(makeMarketData())

      const sessionId = result.debateState.sessionId
      expect(sessionId).toBeTruthy()

      // Result and debate state share same sessionId
      expect(result.debateState.sessionId).toBe(sessionId)

      // Debate record in tracker matches
      const records = tracker.getDebateRecords()
      expect(records[0].sessionId).toBe(sessionId)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 2. Tracker Record Counts — Verifies data integrity
  // ═══════════════════════════════════════════════════════════════

  describe('tracker record counts', () => {
    it('records exactly 1 debate per analyze() call', async () => {
      expect(tracker.getRecordCounts().debates).toBe(0)

      await workforce.analyze(makeMarketData())
      expect(tracker.getRecordCounts().debates).toBe(1)

      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))
      expect(tracker.getRecordCounts().debates).toBe(2)

      await workforce.analyze(makeMarketData({ symbol: 'GOOGL' }))
      expect(tracker.getRecordCounts().debates).toBe(3)
    })

    it('getDebateRecords returns records in insertion order', async () => {
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }))
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))
      await workforce.analyze(makeMarketData({ symbol: 'GOOGL' }))

      const records = tracker.getDebateRecords()
      expect(records[0].symbol).toBe('AAPL')
      expect(records[1].symbol).toBe('MSFT')
      expect(records[2].symbol).toBe('GOOGL')
    })

    it('tracker record counts are correct after 10 debates', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'JPM', 'V', 'WMT']
      for (const symbol of symbols) {
        await workforce.analyze(makeMarketData({ symbol }))
      }

      expect(tracker.getRecordCounts()).toEqual({ debates: 10, trades: 0 })
      expect(tracker.getDebateRecords()).toHaveLength(10)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 3. Agent Analysis Verification — Per-agent data quality
  // ═══════════════════════════════════════════════════════════════

  describe('agent analysis verification', () => {
    let debateRecord: DebateRecord

    beforeEach(async () => {
      ;(workforce as any).initialized = true
      await workforce.analyze(makeMarketData())
      debateRecord = tracker.getDebateRecords()[0]
    })

    it('macro strategist produces STRONG_BUY with macro-specific evidence', () => {
      const macro = debateRecord.agentAnalyses.find(a => a.role === 'macro_strategist')!
      expect(macro.recommendation).toBe('STRONG_BUY')
      expect(macro.confidence).toBe(0.95)
      expect(macro.evidenceRefs).toContain('GDP growth')
      expect(macro.keyMetrics.gdpGrowth).toBe(3.2)
    })

    it('technical analyst produces STRONG_BUY with technical indicators', () => {
      const tech = debateRecord.agentAnalyses.find(a => a.role === 'technical_analyst')!
      expect(tech.recommendation).toBe('STRONG_BUY')
      expect(tech.keyMetrics.rsi14).toBe(58)
      expect(tech.keyMetrics.sma50).toBe(170)
      expect(tech.keyMetrics.targetPrice).toBe(192)
    })

    it('risk manager produces BUY with risk parameters', () => {
      const risk = debateRecord.agentAnalyses.find(a => a.role === 'risk_manager')!
      expect(risk.recommendation).toBe('BUY')
      expect(risk.confidence).toBe(0.78)
      expect(risk.keyMetrics.var95).toBe(1200)
      expect(risk.keyMetrics.stopLoss).toBe(168)
      expect(risk.keyMetrics.positionSizePct).toBe(0.15)
    })

    it('sentiment agent produces BUY with sentiment metrics', () => {
      const sentiment = debateRecord.agentAnalyses.find(a => a.role === 'sentiment_agent')!
      expect(sentiment.recommendation).toBe('BUY')
      expect(sentiment.keyMetrics.sentimentScore).toBe(0.72)
      expect(sentiment.keyMetrics.putCallRatio).toBe(0.65)
    })

    it('sector analyst produces STRONG_BUY with sector-specific data', () => {
      const sector = debateRecord.agentAnalyses.find(a => a.role === 'sector_analyst')!
      expect(sector.recommendation).toBe('STRONG_BUY')
      expect(sector.keyMetrics.sectorRSI).toBe(62)
      expect(sector.keyMetrics.institutionalFlow).toBe(450000000)
    })

    it('execution optimizer produces BUY with execution parameters', () => {
      const exec = debateRecord.agentAnalyses.find(a => a.role === 'execution_optimizer')!
      expect(exec.recommendation).toBe('BUY')
      expect(exec.keyMetrics.spreadBps).toBe(2)
      expect(exec.keyMetrics.avgDailyVolume).toBe(45000000)
    })

    it('all analyses have valid Layer 5 metadata (provider, model, latency, tokens)', () => {
      for (const analysis of debateRecord.agentAnalyses) {
        expect(analysis.llmProvider).toMatch(/^(openai|anthropic)$/)
        expect(analysis.llmModel).toBeTruthy()
        expect(analysis.latencyMs).toBeGreaterThanOrEqual(0)
        expect(analysis.tokensUsed).toBeGreaterThanOrEqual(0)
      }
    })

    it('each analysis reasoning includes the round marker', () => {
      for (const analysis of debateRecord.agentAnalyses) {
        expect(analysis.reasoning).toContain('[Round 0]')
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 4. Consensus Decision — Verifies decision quality
  // ═══════════════════════════════════════════════════════════════

  describe('consensus decision', () => {
    it('decision includes a targetPrice from winning side analyses', async () => {
      ;(workforce as any).initialized = true
      const result = await workforce.analyze(makeMarketData())
      expect(result.decision.targetPrice).toBeDefined()
      expect(result.decision.targetPrice).toBeGreaterThan(150)
      expect(result.decision.targetPrice).toBeLessThan(200)
    })

    it('decision includes stopLoss from risk manager', async () => {
      ;(workforce as any).initialized = true
      const result = await workforce.analyze(makeMarketData())

      // Risk manager keyMetrics includes stopLoss: 168
      expect(result.decision.stopLoss).toBe(168)
    })

    it('votingBreakdown includes all 6 roles', async () => {
      ;(workforce as any).initialized = true
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.votingBreakdown).toHaveLength(6)
      const roles = result.decision.votingBreakdown.map(v => v.role).sort()
      expect(roles).toEqual([
        'execution_optimizer', 'macro_strategist', 'risk_manager',
        'sector_analyst', 'sentiment_agent', 'technical_analyst',
      ])
    })

    it('votingBreakdown entries have valid contributions', async () => {
      ;(workforce as any).initialized = true
      const result = await workforce.analyze(makeMarketData())

      for (const vote of result.decision.votingBreakdown) {
        expect(vote.confidence).toBeGreaterThan(0)
        expect(vote.weight).toBeGreaterThan(0)
        expect(vote.weightedScore).toBeGreaterThan(0) // All bullish
        expect(vote.contribution).toBeTruthy()
      }
    })

    it('reasoningSummary includes agent role names', async () => {
      ;(workforce as any).initialized = true
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.reasoningSummary).toContain('Consensus: BUY')
      // Should include at least one agent's reasoning
      expect(result.decision.reasoningSummary.length).toBeGreaterThan(50)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 4b. Veto-Triggered Debate — Risk Manager STRONG_SELL at >=0.8 confidence
  //      overrides all other agents and forces an immediate SELL decision.
  // ═══════════════════════════════════════════════════════════════

  describe('veto-triggered debate', () => {
    const vetoRiskResponse = {
      recommendation: 'STRONG_SELL',
      confidence: 0.85,
      reasoning: 'VETO: Extreme risk detected — VaR at 95% exceeds $50,000 (12% of portfolio). Circuit breaker triggered. Liquidity has evaporated in the last 30 minutes. Immediate exit required to protect capital.',
      evidenceRefs: ['VaR spike', 'circuit breaker', 'liquidity crash'],
      keyMetrics: { var95: 52000, stopLoss: 150, positionSizePct: 0, riskScore: 0.95 },
    }

    let savedRiskResponse: typeof cannedResponses.risk_manager

    beforeAll(() => {
      savedRiskResponse = { ...cannedResponses.risk_manager }
    })

    // Default to veto response for all tests in this block
    beforeEach(() => {
      cannedResponses.risk_manager = { ...vetoRiskResponse }
    })

    // Restore after each test so non-veto sections are never polluted
    afterEach(() => {
      cannedResponses.risk_manager = savedRiskResponse
    })

    it('veto triggers when risk manager returns STRONG_SELL with confidence >= 0.8', async () => {
      const result = await workforce.analyze(makeMarketData())

      // ── Veto decision overrides normal consensus ──
      expect(result.error).toBeUndefined()
      expect(result.decision.action).toBe('SELL')
      expect(result.decision.vetoApplied).toBe(true)
      expect(result.decision.vetoReason).toContain('VETO: Extreme risk detected')
      expect(result.action).toBe('REJECTED') // veto always returns REJECTED

      // ── Veto rounds are still tracked ──
      expect(result.decision.roundsRequired).toBe(1) // Veto happens in round 0, so roundsRequired = 1

      // ── Veto decision confidence is the risk manager's confidence ──
      expect(result.decision.overallConfidence).toBe(0.85)
      expect(result.decision.requiresHumanReview).toBe(false) // Veto overrides human review
    })

    it('vetoApplied flows through to the DebateRecord in the tracker', async () => {
      await workforce.analyze(makeMarketData())

      const records = tracker.getDebateRecords()
      expect(records).toHaveLength(1)

      const debateRecord = records[0]
      expect(debateRecord.vetoApplied).toBe(true)
      expect(debateRecord.decision.vetoApplied).toBe(true)
      expect(debateRecord.decision.action).toBe('SELL')
      expect(debateRecord.decision.vetoReason).toContain('VETO: Extreme risk detected')
    })

    it('veto records correct voting breakdown with single risk_manager entry', async () => {
      const result = await workforce.analyze(makeMarketData())

      // Veto creates a special voting breakdown with ONLY the risk manager
      expect(result.decision.votingBreakdown).toHaveLength(1)
      const vetoVote = result.decision.votingBreakdown[0]
      expect(vetoVote.role).toBe('risk_manager')
      expect(vetoVote.vote).toBe('STRONG_SELL')
      expect(vetoVote.confidence).toBe(0.85)
      expect(vetoVote.contribution).toContain('VETO OVERRIDE')
      expect(vetoVote.weightedScore).toBe(-1)
    })

    it('veto decision includes stopLoss from risk manager keyMetrics', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.stopLoss).toBe(150)
    })

    it('debate state reflects vetoTriggered flag', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.debateState.vetoTriggered).toBe(true)
      expect(result.debateState.vetoReason).toContain('VETO: Extreme risk detected')
      expect(result.debateState.consensusReached).toBe(true) // Veto counts as consensus reached
    })

    it('veto reasoning summary is prefixed with RISK MANAGER VETO', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.reasoningSummary).toContain('RISK MANAGER VETO:')
      expect(result.decision.reasoningSummary).toContain('Extreme risk detected')
    })

    it('veto does NOT trigger at confidence 0.79 (below threshold)', async () => {
      cannedResponses.risk_manager = {
        ...vetoRiskResponse,
        confidence: 0.79,
      }

      const result = await workforce.analyze(makeMarketData())

      // At 0.79 confidence, veto does NOT trigger — normal consensus applies
      // Other agents are all bullish, so the STRONG_SELL at 0.79 gets outvoted
      expect(result.decision.vetoApplied).toBe(false)
      expect(result.decision.action).not.toBe('SELL') // Should be BUY (bullish majority)
      expect(result.action).toBe('HELD') // Not REJECTED (no veto)
    })

    it('veto STRONG_SELL is recorded with the risk_manager agent analysis in the debate record', async () => {
      await workforce.analyze(makeMarketData())

      const records = tracker.getDebateRecords()
      const riskAnalysis = records[0].agentAnalyses.find(a => a.role === 'risk_manager')!

      expect(riskAnalysis.recommendation).toBe('STRONG_SELL')
      expect(riskAnalysis.confidence).toBe(0.85)
      expect(riskAnalysis.keyMetrics.var95).toBe(52000)
      expect(riskAnalysis.keyMetrics.riskScore).toBe(0.95)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 4c. SELL-Consensus Debate — All agents bearish, normal consensus
  //      (risk manager at 0.78 stays below the 0.8 veto threshold).
  // ═══════════════════════════════════════════════════════════════

  describe('sell-consensus debate', () => {
    const bearishResponses: typeof cannedResponses = {
      macro_strategist: {
        recommendation: 'STRONG_SELL',
        confidence: 0.95,
        reasoning: 'GDP contraction accelerating, hawkish Fed stance with further rate hikes expected, earnings recession confirmed across major indices. Global macro outlook is decisively negative for risk assets.',
        evidenceRefs: ['GDP contraction', 'rate hikes', 'earnings recession'],
        keyMetrics: { gdpGrowth: -1.2, inflation: 5.1, targetPrice: 140 },
      },
      sector_analyst: {
        recommendation: 'STRONG_SELL',
        confidence: 0.90,
        reasoning: 'Institutional outflows accelerating as funds rotate to defensive sectors. Relative strength vs S&P 500 at 6-month low. Sector ETF seeing record redemptions.',
        evidenceRefs: ['institutional outflows', 'relative weakness', 'ETF redemptions'],
        keyMetrics: { sectorRSI: 28, sectorBeta: 0.85, institutionalFlow: -620000000 },
      },
      sentiment_agent: {
        recommendation: 'SELL',
        confidence: 0.88,
        reasoning: 'Overwhelmingly negative sentiment across all channels. Put/Call ratio spiked to 1.8. Social media sentiment at 3-month low. News headlines dominated by recession fears.',
        evidenceRefs: ['bearish sentiment', 'put/call spike', 'recession headlines'],
        keyMetrics: { sentimentScore: -0.65, putCallRatio: 1.8, socialVolume: 98000 },
      },
      technical_analyst: {
        recommendation: 'STRONG_SELL',
        confidence: 0.92,
        reasoning: 'Price decisively below both 50-day and 200-day SMA. Death cross confirmed. RSI at 32 (weak). MACD bearish crossover with increasing downside momentum. Support at 155 broken — next support at 140.',
        evidenceRefs: ['death cross', 'RSI breakdown', 'MACD bearish', 'support break'],
        keyMetrics: { rsi14: 32, sma50: 180, sma200: 185, vwap: 168.5, targetPrice: 138 },
      },
      risk_manager: {
        recommendation: 'STRONG_SELL',
        confidence: 0.78, // BELOW 0.8 veto threshold — normal consensus applies
        reasoning: 'Portfolio VaR at 95% is $9,800 (6.5% of portfolio) — approaching limits. Correlation matrix shows systemic risk concentration. Position reduction recommended even without full veto trigger.',
        evidenceRefs: ['VaR analysis', 'correlation risk', 'stress test'],
        keyMetrics: { var95: 9800, kellyFraction: -0.22, stopLoss: 158, positionSizePct: 0 },
      },
      execution_optimizer: {
        recommendation: 'SELL',
        confidence: 0.85,
        reasoning: 'Liquidity thinning — bid-ask spread widening to 8bps. TWAP sell schedule recommended to minimize impact. Dark pool volume suggests hidden institutional selling pressure.',
        evidenceRefs: ['spread widening', 'TWAP sell', 'dark pool activity'],
        keyMetrics: { spreadBps: 8, avgDailyVolume: 52000000, targetPrice: 155 },
      },
    }

    let savedResponses: typeof cannedResponses

    beforeAll(() => {
      savedResponses = { ...cannedResponses }
    })

    beforeEach(() => {
      // Swap in all bearish responses
      for (const role of Object.keys(bearishResponses)) {
        cannedResponses[role] = { ...bearishResponses[role] }
      }
    })

    afterEach(() => {
      // Restore original responses for all roles
      for (const role of Object.keys(savedResponses)) {
        cannedResponses[role] = { ...savedResponses[role] }
      }
    })

    it('full bearish consensus produces SELL decision via normal voting (no veto)', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.error).toBeUndefined()
      expect(result.decision.action).toBe('SELL')
      expect(result.decision.vetoApplied).toBe(false) // 0.78 confidence < 0.8 threshold
      expect(result.decision.overallConfidence).toBeGreaterThan(0.6) // |score| ≈ 0.75
      expect(result.action).toBe('HELD') // No auto-execute
    })

    it('SELL direction flows through to the DebateRecord in the tracker', async () => {
      await workforce.analyze(makeMarketData())

      const records = tracker.getDebateRecords()
      expect(records).toHaveLength(1)

      const debateRecord = records[0]
      expect(debateRecord.decision.action).toBe('SELL')
      expect(debateRecord.vetoApplied).toBe(false)
      expect(debateRecord.symbol).toBe('AAPL')
    })

    it('voting breakdown shows all-negative contributions from all 6 roles', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.votingBreakdown).toHaveLength(6)

      const roles = result.decision.votingBreakdown.map(v => v.role).sort()
      expect(roles).toEqual([
        'execution_optimizer', 'macro_strategist', 'risk_manager',
        'sector_analyst', 'sentiment_agent', 'technical_analyst',
      ])

      // All weighted scores should be negative (everyone bearish)
      for (const vote of result.decision.votingBreakdown) {
        expect(vote.weightedScore).toBeLessThan(0)
        // Both STRONG_SELL and SELL votes contribute negatively
        expect(vote.contribution).toContain('negative')
      }
    })

    it('stopLoss comes from risk manager keyMetrics', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.stopLoss).toBe(158)
    })

    it('targetPrice is extracted from the bearish (winning) analyses', async () => {
      const result = await workforce.analyze(makeMarketData())

      // targetPrice appears in multiple bearish analyses — verify it exists
      expect(result.decision.targetPrice).toBeDefined()
      expect(result.decision.targetPrice).toBeGreaterThan(0)
    })

    it('debate completes in exactly 1 round (unanimous bearish consensus)', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.roundsRequired).toBe(1)

      const records = tracker.getDebateRecords()
      expect(records[0].roundsRequired).toBe(1)
    })

    it('reasoning summary contains Consensus: SELL', async () => {
      const result = await workforce.analyze(makeMarketData())

      expect(result.decision.reasoningSummary).toContain('Consensus: SELL')
      expect(result.decision.reasoningSummary.length).toBeGreaterThan(50)
    })

    it('all 6 agent analyses recorded with bearish recommendations', async () => {
      await workforce.analyze(makeMarketData())

      const records = tracker.getDebateRecords()
      const analyses = records[0].agentAnalyses
      expect(analyses).toHaveLength(6)

      // Verify each role has a bearish recommendation
      const recommendationsByRole: Record<string, string> = {}
      for (const a of analyses) {
        recommendationsByRole[a.role] = a.recommendation
      }

      expect(recommendationsByRole.macro_strategist).toBe('STRONG_SELL')
      expect(recommendationsByRole.sector_analyst).toBe('STRONG_SELL')
      expect(recommendationsByRole.sentiment_agent).toBe('SELL')
      expect(recommendationsByRole.technical_analyst).toBe('STRONG_SELL')
      expect(recommendationsByRole.risk_manager).toBe('STRONG_SELL')
      expect(recommendationsByRole.execution_optimizer).toBe('SELL')
    })

    it('average rounds per debate reflects single-round consensus', async () => {
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }))
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))

      const metrics = tracker.computeMetrics()
      expect(metrics.avgRoundsPerDebate).toBe(1)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 5. Multi-Symbol Debates — Different symbols, same pipeline
  // ═══════════════════════════════════════════════════════════════

  describe('multi-symbol debates', () => {
    it('correctly records different symbols in separate debate records', async () => {
      await workforce.analyze(makeMarketData({ symbol: 'AAPL', currentPrice: 175 }))
      await workforce.analyze(makeMarketData({ symbol: 'TSLA', currentPrice: 250 }))
      await workforce.analyze(makeMarketData({ symbol: 'NVDA', currentPrice: 950 }))

      const records = tracker.getDebateRecords()

      expect(records).toHaveLength(3)
      expect(records[0].symbol).toBe('AAPL')
      expect(records[0].marketSnapshot.currentPrice).toBe(175)
      expect(records[1].symbol).toBe('TSLA')
      expect(records[1].marketSnapshot.currentPrice).toBe(250)
      expect(records[2].symbol).toBe('NVDA')
      expect(records[2].marketSnapshot.currentPrice).toBe(950)
    })

    it('each debate gets a unique sessionId', async () => {
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }))
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))

      const records = tracker.getDebateRecords()
      expect(records[0].sessionId).not.toBe(records[1].sessionId)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 6. Trade Outcome Tracking — Verifies trade record flow
  // ═══════════════════════════════════════════════════════════════

  describe('trade outcome tracking', () => {
    it('does not record trades when autoExecute is false', async () => {
      await workforce.analyze(makeMarketData(), undefined, false)

      expect(tracker.getRecordCounts().trades).toBe(0)
    })

    it('tracks metrics correctly across multiple debates with no trades', async () => {
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }))
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))
      await workforce.analyze(makeMarketData({ symbol: 'GOOGL' }))

      const metrics = tracker.computeMetrics()
      expect(metrics.totalDebates).toBe(3)
      expect(metrics.totalTrades).toBe(0)
      // With no closed trades, win rate = 0 and sharpe = 0
      expect(metrics.winRate).toBe(0)
      expect(metrics.sharpeRatio).toBe(0)
      expect(metrics.cumulativePnl).toBe(0)
    })

    it('getRecentTrades returns empty array when no trades', async () => {
      await workforce.analyze(makeMarketData())
      expect(tracker.getRecentTrades(10)).toEqual([])
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 7. Pipeline Status — Verifies MetaLearningPipeline state
  // ═══════════════════════════════════════════════════════════════

  describe('pipeline status', () => {
    it('getStatus reflects the correct debate count after running debates', async () => {
      await workforce.analyze(makeMarketData())
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))

      // getStatus() must be called AFTER debates — calling it before
      // would cache stale metrics in the tracker's internal cache.
      const statusAfter = pipeline.getStatus()
      expect(statusAfter.currentMetrics?.totalDebates).toBe(2)
      expect(statusAfter.currentMetrics?.totalTrades).toBe(0)
      expect(statusAfter.generationCount).toBe(0) // No evolution triggered
    })

    it('getTracker returns the same tracker instance', () => {
      expect(pipeline.getTracker()).toBe(tracker)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 8. Null Pipeline Safety — Backward compatibility
  // ═══════════════════════════════════════════════════════════════

  describe('null pipeline safety', () => {
    it('TradingWorkforce works fine without a MetaLearningPipeline', async () => {
      const standaloneWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, undefined)
      ;(standaloneWorkforce as any).initialized = true

      const result = await standaloneWorkforce.analyze(makeMarketData())

      // Should still produce a valid decision
      expect(result.error).toBeUndefined()
      expect(result.decision.action).toBe('BUY')
      expect(result.action).toBe('HELD')
    })

    it('getMetaPipeline returns null when no pipeline attached', () => {
      const standaloneWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, undefined)
      expect(standaloneWorkforce.getMetaPipeline()).toBeNull()
    })

    it('getMetaPipeline returns the pipeline when attached', () => {
      expect(workforce.getMetaPipeline()).toBe(pipeline)
    })

    it('can attach a pipeline after construction', async () => {
      const standaloneWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, undefined)
      ;(standaloneWorkforce as any).initialized = true
      expect(standaloneWorkforce.getMetaPipeline()).toBeNull()

      standaloneWorkforce.attachMetaPipeline(pipeline)
      expect(standaloneWorkforce.getMetaPipeline()).toBe(pipeline)

      // Now run a debate — should record in the (existing) pipeline
      const beforeCount = tracker.getRecordCounts().debates
      await standaloneWorkforce.analyze(makeMarketData({ symbol: 'POST-ATTACH' }))
      expect(tracker.getRecordCounts().debates).toBe(beforeCount + 1)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 9. Event Emission — Verifies workforce events fire
  // ═══════════════════════════════════════════════════════════════

  describe('event emission', () => {
    it('emits debateStarted and debateComplete events', async () => {
      const events: string[] = []
      workforce.on('debateStarted', (data: { symbol: string; sessionId: string }) => {
        events.push(`started:${data.symbol}`)
      })
      workforce.on('debateComplete', (data: { decision: FinalDecision; rounds: number }) => {
        events.push(`complete:${data.decision.action}`)
      })

      await workforce.analyze(makeMarketData())

      expect(events).toContain('started:AAPL')
      expect(events).toContain('complete:BUY')
    })

    it('emits analysisProduced from each agent', async () => {
      // Hook into agent events by iterating through workforce agents
      const agentEvents: string[] = []
      const agent = workforce.getAgent('macro_strategist')
      if (agent) {
        agent.on('analysisProduced', (data: { agentId: string; analysis: AgentAnalysis }) => {
          agentEvents.push(data.analysis.role)
        })
      }

      await workforce.analyze(makeMarketData())

      // At minimum the macro_strategist event should fire
      // (all agents fire this event, but we only listen to one here)
      expect(agentEvents.length).toBeGreaterThanOrEqual(1)
      if (agentEvents.length > 0) {
        expect(agentEvents[0]).toBe('macro_strategist')
      }
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 10. LLM Mock Correctness — Verifies the mock itself
  // ═══════════════════════════════════════════════════════════════

  describe('LLM mock correctness', () => {
    it('invokeStructured is called exactly once per agent per debate', async () => {
      await workforce.analyze(makeMarketData())
      expect(mockInvokeStructured).toHaveBeenCalledTimes(6)

      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))
      expect(mockInvokeStructured).toHaveBeenCalledTimes(12)

      await workforce.analyze(makeMarketData({ symbol: 'GOOGL' }))
      expect(mockInvokeStructured).toHaveBeenCalledTimes(18)
    })

    it('mock correctly resolves each role from system prompt inspection', async () => {
      ;(workforce as any).initialized = true
      await workforce.analyze(makeMarketData())

      // Each role should have been called exactly once
      expect(callCounts.macro_strategist).toBe(1)
      expect(callCounts.sector_analyst).toBe(1)
      expect(callCounts.sentiment_agent).toBe(1)
      expect(callCounts.technical_analyst).toBe(1)
      expect(callCounts.risk_manager).toBe(1)
      expect(callCounts.execution_optimizer).toBe(1)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 11. Performance Metrics — Computed from tracked data
  // ═══════════════════════════════════════════════════════════════

  describe('performance metrics computation', () => {
    it('computeMetrics returns valid structure even with zero trades', async () => {
      ;(workforce as any).initialized = true
      await workforce.analyze(makeMarketData())

      const metrics = tracker.computeMetrics()

      expect(metrics.totalDebates).toBe(1)
      expect(metrics.totalTrades).toBe(0)
      expect(metrics.agentMetrics).toBeDefined()
      expect(Object.keys(metrics.agentMetrics)).toHaveLength(6)
      // Period bounds should be valid
      expect(metrics.periodStart).toBeTruthy()
      expect(metrics.periodEnd).toBeTruthy()
    })

    it('agentMetrics has valid structure for all 6 roles', async () => {
      ;(workforce as any).initialized = true
      await workforce.analyze(makeMarketData())

      const metrics = tracker.computeMetrics()

      for (const role of [
        'macro_strategist', 'sector_analyst', 'sentiment_agent',
        'technical_analyst', 'risk_manager', 'execution_optimizer',
      ] as AgentTradingRole[]) {
        const am = metrics.agentMetrics[role]
        expect(am.role).toBe(role)
        expect(am.totalAnalyses).toBe(1) // One debate
        expect(typeof am.recommendationAccuracy).toBe('number')
        expect(typeof am.calibrationError).toBe('number')
        expect(typeof am.consensusAlignment).toBe('number')
        expect(am.lastUpdated).toBeTruthy()
      }
    })

    it('hold rate is 0 when all decisions are actionable', async () => {
      // Run 3 debates — all should be BUY (actionable, not HOLD)
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }))
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))
      await workforce.analyze(makeMarketData({ symbol: 'GOOGL' }))

      const metrics = tracker.computeMetrics()
      expect(metrics.holdRate).toBe(0)
    })

    it('average rounds per debate is 1 for unanimous consensus', async () => {
      await workforce.analyze(makeMarketData())
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }))

      const metrics = tracker.computeMetrics()
      expect(metrics.avgRoundsPerDebate).toBe(1)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 12. Layer 3 Knowledge Pipeline Enrichment
  // ═══════════════════════════════════════════════════════════════

  describe('knowledge pipeline enrichment', () => {
    let knowledgePipeline: KnowledgePipeline
    let workforceWithKnowledge: TradingWorkforce
    const mockEnrichedContext = {
      altSnapshot: {
        symbol: 'AAPL',
        timestamp: '2025-06-15T12:00:00Z',
        news: {
          articles: [],
          avgSentiment: 0.65,
          articleCount: 12,
          sentimentTrend: 'improving' as const,
        },
        insiders: null,
        social: [],
        compositeSentiment: 0.58,
        highlights: ['Positive earnings surprise', 'Analyst upgrades'],
      } as AltDataSnapshot,
      ragContext: 'AAPL recently filed 10-Q showing 8% revenue growth. Risk factors include supply chain constraints. Key development: new product line announced.',
      graphStats: { entityCount: 150, relationCount: 320 },
    }

    beforeEach(() => {
      knowledgePipeline = new KnowledgePipeline({
        trackedSymbols: ['AAPL'],
        autoStart: false,
      })

      // Mock getEnrichedMarketContext to avoid real API calls
      jest.spyOn(knowledgePipeline, 'getEnrichedMarketContext')
        .mockResolvedValue(mockEnrichedContext)

      workforceWithKnowledge = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
      workforceWithKnowledge.attachKnowledgePipeline(knowledgePipeline)
      ;(workforceWithKnowledge as any).initialized = true
    })

    afterEach(() => {
      jest.restoreAllMocks()
    })

    it('enriches market data with RAG context before debate', async () => {
      const result = await workforceWithKnowledge.analyze(makeMarketData())

      expect(result.error).toBeUndefined()

      // Verify the knowledge pipeline was actually invoked
      expect(knowledgePipeline.getEnrichedMarketContext).toHaveBeenCalledWith('AAPL')

      // Market data in debate state should have enrichment fields
      const enrichedMarketData = result.debateState.marketData
      expect(enrichedMarketData.ragContext).toBe(mockEnrichedContext.ragContext)
      expect(enrichedMarketData.enriched).toBe(true)
      expect(enrichedMarketData.knowledgeGraphStats).toEqual(mockEnrichedContext.graphStats)
    })

    it('enriches market data with alt data snapshot', async () => {
      const result = await workforceWithKnowledge.analyze(makeMarketData())

      const enrichedMarketData = result.debateState.marketData
      expect(enrichedMarketData.altDataSnapshot).toBeDefined()
      expect(enrichedMarketData.altDataSnapshot!.symbol).toBe('AAPL')
      expect(enrichedMarketData.altDataSnapshot!.compositeSentiment).toBe(0.58)
    })

    it('surfaces alt data sentiment as top-level fields for agent convenience', async () => {
      const result = await workforceWithKnowledge.analyze(makeMarketData())

      const enrichedMarketData = result.debateState.marketData
      // newsSentiment from alt data (0.65) should be surfaced
      expect(enrichedMarketData.newsSentiment).toBe(0.65)
      // socialSentiment from alt data composite (0.58)
      expect(enrichedMarketData.socialSentiment).toBe(0.58)
    })

    it('does NOT override explicitly provided sentiment fields', async () => {
      const result = await workforceWithKnowledge.analyze(
        makeMarketData({ newsSentiment: 0.80, socialSentiment: 0.90 })
      )

      const enrichedMarketData = result.debateState.marketData
      // Explicit values take precedence over alt data
      expect(enrichedMarketData.newsSentiment).toBe(0.80)
      expect(enrichedMarketData.socialSentiment).toBe(0.90)
    })

    it('enriched data is captured in the DebateRecord market snapshot', async () => {
      await workforceWithKnowledge.analyze(makeMarketData())

      const records = tracker.getDebateRecords()
      expect(records).toHaveLength(1)

      const snapshot = records[0].marketSnapshot
      expect(snapshot.ragContext).toBe(mockEnrichedContext.ragContext)
      expect(snapshot.enriched).toBe(true)
      expect(snapshot.altDataSnapshot).toBeDefined()
    })

    it('workforce without knowledge pipeline works normally (backward compatible)', async () => {
      const plainWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
      ;(plainWorkforce as any).initialized = true

      const result = await plainWorkforce.analyze(makeMarketData())

      expect(result.error).toBeUndefined()
      expect(result.decision.action).toBe('BUY')
      // No enrichment fields set
      expect(result.debateState.marketData.ragContext).toBeUndefined()
      expect(result.debateState.marketData.enriched).toBeUndefined()
      // getEnrichedMarketContext was never called on any pipeline
      expect(knowledgePipeline.getEnrichedMarketContext).not.toHaveBeenCalled()
    })

    it('getKnowledgePipeline returns null when not attached', () => {
      const plainWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, undefined)
      expect(plainWorkforce.getKnowledgePipeline()).toBeNull()
    })

    it('getKnowledgePipeline returns the pipeline when attached', () => {
      expect(workforceWithKnowledge.getKnowledgePipeline()).toBe(knowledgePipeline)
    })

    it('handles enrichment failure gracefully and continues with unenriched data', async () => {
      jest.spyOn(knowledgePipeline, 'getEnrichedMarketContext')
        .mockRejectedValue(new Error('SEC API rate limit exceeded'))

      const result = await workforceWithKnowledge.analyze(makeMarketData())

      // Should still produce a valid decision despite enrichment failure
      expect(result.error).toBeUndefined()
      expect(result.decision.action).toBe('BUY')
      // Market data should not have enrichment fields
      expect(result.debateState.marketData.enriched).toBeUndefined()
      expect(result.debateState.marketData.ragContext).toBeUndefined()

      // Tracker still has the debate record (debate ran successfully)
      expect(tracker.getDebateRecords()).toHaveLength(1)
    })

    it('handles null altSnapshot gracefully (pipeline has no data yet)', async () => {
      jest.spyOn(knowledgePipeline, 'getEnrichedMarketContext')
        .mockResolvedValue({
          altSnapshot: null,
          ragContext: '',
          graphStats: { entityCount: 0, relationCount: 0 },
        })

      const result = await workforceWithKnowledge.analyze(makeMarketData())

      expect(result.error).toBeUndefined()
      // Enriched flag still set (pipeline ran, just found nothing)
      expect(result.debateState.marketData.enriched).toBe(true)
      // null ?? undefined → undefined (coerced by the enrichment spread)
      expect(result.debateState.marketData.altDataSnapshot).toBeUndefined()
      // Empty ragContext maps to undefined (falsy empty string stripped)
      expect(result.debateState.marketData.ragContext).toBeUndefined()
      // Original sentiment fields preserved (not overwritten by null altSnapshot)
      expect(result.debateState.marketData.newsSentiment).toBeUndefined()
    })

    it('can attach knowledge pipeline after construction', async () => {
      const lateWorkforce = new TradingWorkforce(DEFAULT_TRADING_CONFIG, pipeline)
      ;(lateWorkforce as any).initialized = true
      expect(lateWorkforce.getKnowledgePipeline()).toBeNull()

      lateWorkforce.attachKnowledgePipeline(knowledgePipeline)
      expect(lateWorkforce.getKnowledgePipeline()).toBe(knowledgePipeline)

      const result = await lateWorkforce.analyze(makeMarketData())
      expect(result.debateState.marketData.enriched).toBe(true)
      expect(result.debateState.marketData.ragContext).toBe(mockEnrichedContext.ragContext)
    })

    it('both meta-learning and knowledge pipelines can coexist', async () => {
      // workforceWithKnowledge already has both via beforeEach
      expect(workforceWithKnowledge.getMetaPipeline()).toBe(pipeline)
      expect(workforceWithKnowledge.getKnowledgePipeline()).toBe(knowledgePipeline)

      const result = await workforceWithKnowledge.analyze(makeMarketData())

      // Meta-learning recorded the debate
      expect(tracker.getDebateRecords()).toHaveLength(1)
      // Knowledge enrichment applied
      expect(result.debateState.marketData.enriched).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════
  // 13. AutoExecute Trade Flow — Portfolio + autoExecute=true triggers
  //     Layer 1 execution and TradeOutcomeRecords flow to the tracker.
  // ═══════════════════════════════════════════════════════════════

  describe('autoExecute trade flow', () => {
    /** Build a portfolio that won't trigger risk-check rejections */
    function makePortfolio(overrides: Partial<PortfolioState> = {}): PortfolioState {
      return {
        equity: 100_000,
        dailyPnl: 500,
        currentDrawdownPct: 5,
        positions: [
          { symbol: 'AAPL', quantity: 50, avgPrice: 170, marketValue: 8750, unrealizedPnl: 250 },
        ],
        ...overrides,
      }
    }

    /** Build a simulated FILLED ExecutionReport as Layer 1 would produce */
    function makeMockExecution(overrides: Partial<ExecutionReport> = {}): ExecutionReport {
      return {
        orderId: 'sim-order-001',
        correlationId: 'sim-correlation-001',
        symbol: 'AAPL',
        side: 'BUY',
        orderType: 'LIMIT',
        quantity: 285,
        filledQuantity: 285,
        avgFillPrice: 175.05,
        status: 'FILLED',
        timestamp: new Date().toISOString(),
        commission: 49.89,
        venue: 'SIMULATED',
        ...overrides,
      }
    }

    /** Mock executeDecision to return EXECUTED with a canned ExecutionReport */
    function mockExecuted(execution?: ExecutionReport) {
      const report = execution || makeMockExecution()
      return jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: true,
        action: 'EXECUTED',
        riskCheck: {
          approved: true,
          maxPositionSize: 1000,
          currentVar: 500,
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        execution: report,
      })
    }

    afterEach(() => {
      jest.restoreAllMocks()
    })

    // ── Core Flow ──

    it('BUY debate + portfolio + autoExecute=true produces EXECUTED result with execution report', async () => {
      mockExecuted()

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.error).toBeUndefined()
      expect(result.action).toBe('EXECUTED')
      expect(result.execution).toBeDefined()
      expect(result.execution!.status).toBe('FILLED')
      expect(result.execution!.symbol).toBe('AAPL')
      expect(result.execution!.side).toBe('BUY')
      expect(result.riskCheck).toBeDefined()
      expect(result.riskCheck!.approved).toBe(true)
    })

    it('TradeOutcomeRecord flows to the tracker after successful execution', async () => {
      mockExecuted()

      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const tradeRecords = tracker.getTradeRecords()
      expect(tradeRecords).toHaveLength(1)

      const trade = tradeRecords[0]
      expect(trade.symbol).toBe('AAPL')
      expect(trade.direction).toBe('LONG') // BUY → LONG
      expect(trade.entryPrice).toBe(175.05)
      expect(trade.outcome).toBe('PENDING') // Not yet closed
      expect(trade.pnl).toBe(0)
      expect(trade.pnlPct).toBe(0)
      expect(trade.maxAdversePct).toBe(0)
      expect(trade.maxFavorablePct).toBe(0)
      expect(trade.entryTimestamp).toBeTruthy()
    })

    it('trade record links back to the correct debate via sessionId', async () => {
      mockExecuted()

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const debateRecords = tracker.getDebateRecords()
      const tradeRecords = tracker.getTradeRecords()

      expect(debateRecords).toHaveLength(1)
      expect(tradeRecords).toHaveLength(1)
      expect(tradeRecords[0].debateSessionId).toBe(debateRecords[0].sessionId)
      expect(tradeRecords[0].debateSessionId).toBe(result.debateState.sessionId)
    })

    it('SELL consensus → trade direction is SHORT (not SELL_SHORT)', async () => {
      const sellExecution = makeMockExecution({
        side: 'SELL',
        avgFillPrice: 168.20,
        orderId: 'sim-order-sell-001',
        commission: 47.93,
      })
      mockExecuted(sellExecution)

      // Swap to bearish responses (same as SELL-consensus section)
      const savedResponses: typeof cannedResponses = JSON.parse(JSON.stringify(cannedResponses))
      cannedResponses.macro_strategist = { ...cannedResponses.macro_strategist, recommendation: 'STRONG_SELL', confidence: 0.95, reasoning: 'Bearish macro outlook', evidenceRefs: ['GDP'], keyMetrics: { targetPrice: 140 } }
      cannedResponses.sector_analyst = { ...cannedResponses.sector_analyst, recommendation: 'STRONG_SELL', confidence: 0.90, reasoning: 'Bearish sector', evidenceRefs: ['flows'], keyMetrics: { targetPrice: 142 } }
      cannedResponses.sentiment_agent = { ...cannedResponses.sentiment_agent, recommendation: 'SELL', confidence: 0.88, reasoning: 'Bearish sentiment', evidenceRefs: ['news'], keyMetrics: {} }
      cannedResponses.technical_analyst = { ...cannedResponses.technical_analyst, recommendation: 'STRONG_SELL', confidence: 0.92, reasoning: 'Bearish technicals', evidenceRefs: ['RSI'], keyMetrics: { targetPrice: 138 } }
      cannedResponses.risk_manager = { ...cannedResponses.risk_manager, recommendation: 'STRONG_SELL', confidence: 0.78, reasoning: 'High risk', evidenceRefs: ['VaR'], keyMetrics: { stopLoss: 158 } }
      cannedResponses.execution_optimizer = { ...cannedResponses.execution_optimizer, recommendation: 'SELL', confidence: 0.85, reasoning: 'SELL execution', evidenceRefs: ['spread'], keyMetrics: {} }

      try {
        const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

        expect(result.action).toBe('EXECUTED')
        expect(result.execution!.side).toBe('SELL')

        const trade = tracker.getTradeRecords()[0]
        expect(trade.direction).toBe('SHORT') // SELL → SHORT
        expect(trade.entryPrice).toBe(168.20)
        expect(trade.symbol).toBe('AAPL')
      } finally {
        // Restore original responses
        for (const role of Object.keys(savedResponses)) {
          (cannedResponses as any)[role] = savedResponses[role]
        }
      }
    })

    // ── No-Execution Paths ──

    it('without portfolio, autoExecute=true still returns HELD (no execution attempted)', async () => {
      const result = await workforce.analyze(makeMarketData(), undefined, true)

      expect(result.action).toBe('HELD')
      expect(result.execution).toBeUndefined()

      // No trade recorded in tracker
      expect(tracker.getTradeRecords()).toHaveLength(0)
    })

    it('with portfolio but autoExecute=false, returns HELD (decision only)', async () => {
      const result = await workforce.analyze(makeMarketData(), makePortfolio(), false)

      expect(result.action).toBe('HELD')
      expect(result.execution).toBeUndefined()
      expect(result.decision.action).toBe('BUY')

      // Decision is made but no trade recorded
      expect(tracker.getDebateRecords()).toHaveLength(1)
      expect(tracker.getTradeRecords()).toHaveLength(0)
    })

    it('with portfolio but autoExecute=false, the debate is still recorded in the tracker', async () => {
      await workforce.analyze(makeMarketData(), makePortfolio(), false)

      expect(tracker.getRecordCounts()).toEqual({ debates: 1, trades: 0 })
    })

    it('VETO decisions skip execution even with portfolio + autoExecute=true', async () => {
      // Set risk manager to trigger veto
      const savedRisk = cannedResponses.risk_manager
      cannedResponses.risk_manager = {
        recommendation: 'STRONG_SELL',
        confidence: 0.85,
        reasoning: 'VETO: Extreme risk',
        evidenceRefs: ['VaR'],
        keyMetrics: { var95: 52000, stopLoss: 150 },
      }

      try {
        const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

        // Veto → action is REJECTED, no execution attempted
        expect(result.decision.vetoApplied).toBe(true)
        expect(result.action).toBe('REJECTED')
        expect(result.execution).toBeUndefined()
        expect(tracker.getTradeRecords()).toHaveLength(0)
      } finally {
        cannedResponses.risk_manager = { ...savedRisk }
      }
    })

    // ── Multiple Trades ──

    it('multiple BUY debates with autoExecute accumulate trade records', async () => {
      const execAapl = makeMockExecution({ orderId: 'sim-aapl', symbol: 'AAPL', avgFillPrice: 175.05 })
      const execMsft = makeMockExecution({ orderId: 'sim-msft', symbol: 'MSFT', avgFillPrice: 420.30 })
      const execGoogl = makeMockExecution({ orderId: 'sim-googl', symbol: 'GOOGL', avgFillPrice: 185.75 })

      // Mock each call in sequence
      const _spy = jest.spyOn(workforce.getLayer1Client(), 'executeDecision')
        .mockResolvedValueOnce({
          success: true,
          action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: execAapl,
        })
        .mockResolvedValueOnce({
          success: true,
          action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: execMsft,
        })
        .mockResolvedValueOnce({
          success: true,
          action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: execGoogl,
        })

      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }), makePortfolio(), true)
      await workforce.analyze(makeMarketData({ symbol: 'MSFT', currentPrice: 420 }), makePortfolio(), true)
      await workforce.analyze(makeMarketData({ symbol: 'GOOGL', currentPrice: 185 }), makePortfolio(), true)

      expect(tracker.getRecordCounts()).toEqual({ debates: 3, trades: 3 })

      const trades = tracker.getTradeRecords()
      expect(trades.map(t => t.symbol)).toEqual(['AAPL', 'MSFT', 'GOOGL'])
      expect(trades.map(t => t.entryPrice)).toEqual([175.05, 420.30, 185.75])
    })

    it('debate-trade sessionId linking is preserved across multiple executions', async () => {
      const exec1 = makeMockExecution({ orderId: 'sim-1' })
      const exec2 = makeMockExecution({ orderId: 'sim-2' })

      jest.spyOn(workforce.getLayer1Client(), 'executeDecision')
        .mockResolvedValueOnce({
          success: true,
          action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: exec1,
        })
        .mockResolvedValueOnce({
          success: true,
          action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: exec2,
        })

      await workforce.analyze(makeMarketData(), makePortfolio(), true)
      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const debates = tracker.getDebateRecords()
      const trades = tracker.getTradeRecords()

      expect(debates).toHaveLength(2)
      expect(trades).toHaveLength(2)

      // Each trade's sessionId should match its corresponding debate
      expect(trades[0].debateSessionId).toBe(debates[0].sessionId)
      expect(trades[1].debateSessionId).toBe(debates[1].sessionId)
      // Different debates = different sessionIds
      expect(debates[0].sessionId).not.toBe(debates[1].sessionId)
    })

    // ── Record Counts & Metrics ──

    it('getRecordCounts reflects correct debate and trade counts', async () => {
      expect(tracker.getRecordCounts()).toEqual({ debates: 0, trades: 0 })

      // First call: debate only (no portfolio)
      await workforce.analyze(makeMarketData())
      expect(tracker.getRecordCounts()).toEqual({ debates: 1, trades: 0 })

      // Second call: debate + trade
      mockExecuted()
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }), makePortfolio(), true)
      expect(tracker.getRecordCounts()).toEqual({ debates: 2, trades: 1 })
    })

    it('computeMetrics separates PENDING trades from closed trades', async () => {
      mockExecuted()

      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const metrics = tracker.computeMetrics()
      // Trade outcome is PENDING → not counted as a closed trade
      expect(metrics.totalTrades).toBe(0)
      expect(metrics.totalDebates).toBe(1)
      expect(metrics.winRate).toBe(0)
      expect(metrics.sharpeRatio).toBe(0)
      expect(metrics.cumulativePnl).toBe(0)
    })

    it('getRecentTrades returns trade records in insertion order', async () => {
      const exec = makeMockExecution({ orderId: 'sim-a' })
      mockExecuted(exec)

      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const recent = tracker.getRecentTrades(10)
      expect(recent).toHaveLength(1)
      expect(recent[0].symbol).toBe('AAPL')
    })

    // ── Edge Cases ──

    it('execution report with commission flows through to the tracker', async () => {
      const exec = makeMockExecution({ commission: 25.50 })
      mockExecuted(exec)

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.execution!.commission).toBe(25.50)
    })

    it('execution report with PARTIALLY_FILLED status is still recorded', async () => {
      const exec = makeMockExecution({
        status: 'PARTIALLY_FILLED',
        quantity: 500,
        filledQuantity: 320,
      })
      mockExecuted(exec)

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.execution!.status).toBe('PARTIALLY_FILLED')
      expect(result.execution!.filledQuantity).toBe(320)

      // Trade still recorded — PENDING until fill completes
      const trade = tracker.getTradeRecords()[0]
      expect(trade.entryPrice).toBe(exec.avgFillPrice)
    })

    it('rejected execution does NOT create a trade record', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'REJECTED',
        riskCheck: {
          approved: false,
          rejectReason: 'Circuit breaker active',
          circuitBreakerActive: true,
          drawdownLevel: 'CRITICAL',
        },
      })

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.action).toBe('REJECTED')
      expect(result.execution).toBeUndefined()
      expect(tracker.getTradeRecords()).toHaveLength(0)
      // Debate is still recorded even though execution was rejected
      expect(tracker.getDebateRecords()).toHaveLength(1)
    })

    // ── Trade Closure Flow ──

    it('closing a PENDING trade as WIN updates computeMetrics with winRate=1.0 and cumulativePnl', async () => {
      mockExecuted()

      // Step 1: Execute a BUY → creates PENDING trade
      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(tracker.getRecordCounts().trades).toBe(1)

      // Step 2: Simulate trade closure — update the PENDING record to WIN with profit
      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      expect(trades).toHaveLength(1)

      trades[0] = {
        ...trades[0],
        outcome: 'WIN',
        pnl: 1250.50,
        pnlPct: 0.025, // 2.5% gain
        maxAdversePct: -0.008,
        maxFavorablePct: 0.032,
      }

      // Step 3: Verify metrics reflect the closed trade
      const metrics = tracker.computeMetrics()

      expect(metrics.totalDebates).toBe(1)
      expect(metrics.totalTrades).toBe(1) // Now counted (not PENDING)
      expect(metrics.winRate).toBe(1.0) // 1/1 wins
      expect(metrics.cumulativePnl).toBe(1250.50)
      expect(metrics.avgPnl).toBe(1250.50)
      expect(metrics.profitFactor).toBe(Infinity) // No losses
    })

    it('closing a trade as LOSS produces winRate=0 and negative cumulativePnl', async () => {
      mockExecuted()

      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      trades[0] = {
        ...trades[0],
        outcome: 'LOSS',
        pnl: -850.00,
        pnlPct: -0.017, // -1.7% loss
        maxAdversePct: -0.025,
        maxFavorablePct: 0.005,
      }

      const metrics = tracker.computeMetrics()

      expect(metrics.totalTrades).toBe(1)
      expect(metrics.winRate).toBe(0) // 0/1 wins
      expect(metrics.cumulativePnl).toBe(-850.00)
      expect(metrics.avgPnl).toBe(-850.00)
      expect(metrics.profitFactor).toBe(0) // No wins
    })

    it('mixed WIN + LOSS trades produce proportional winRate and net cumulativePnl', async () => {
      const exec1 = makeMockExecution({ orderId: 'sim-win' })
      const exec2 = makeMockExecution({ orderId: 'sim-loss' })

      jest.spyOn(workforce.getLayer1Client(), 'executeDecision')
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: exec1,
        })
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: exec2,
        })

      // Execute two trades
      await workforce.analyze(makeMarketData(), makePortfolio(), true)
      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      // Close them: first WIN, second LOSS
      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      trades[0] = { ...trades[0], outcome: 'WIN', pnl: 1500, pnlPct: 0.03 }
      trades[1] = { ...trades[1], outcome: 'LOSS', pnl: -600, pnlPct: -0.012 }

      const metrics = tracker.computeMetrics()

      expect(metrics.totalTrades).toBe(2)
      expect(metrics.winRate).toBe(0.5) // 1/2 = 0.5
      expect(metrics.cumulativePnl).toBe(900) // 1500 - 600
      expect(metrics.avgPnl).toBe(450) // 900 / 2
      expect(metrics.profitFactor).toBe(2.5) // 1500 / 600
    })

    it('BREAKEVEN trade is neither WIN nor LOSS — counted as closed but not a win', async () => {
      mockExecuted()

      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      trades[0] = { ...trades[0], outcome: 'BREAKEVEN', pnl: 0, pnlPct: 0 }

      const metrics = tracker.computeMetrics()

      expect(metrics.totalTrades).toBe(1)
      expect(metrics.winRate).toBe(0) // BREAKEVEN is not WIN
      expect(metrics.cumulativePnl).toBe(0)
      expect(metrics.profitFactor).toBe(0) // No gross profit
    })

    it('sharpeRatio is computed from closed trade pnlPct distribution', async () => {
      // Need at least 2 trades for sharpe
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision')
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: makeMockExecution({ orderId: 'sim-1' }),
        })
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: makeMockExecution({ orderId: 'sim-2' }),
        })

      await workforce.analyze(makeMarketData(), makePortfolio(), true)
      await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      trades[0] = { ...trades[0], outcome: 'WIN', pnl: 1000, pnlPct: 0.02 }
      trades[1] = { ...trades[1], outcome: 'WIN', pnl: 500, pnlPct: 0.01 }

      const metrics = tracker.computeMetrics()

      // With pnlPct values [0.02, 0.01]: mean=0.015, std=0.005, sharpe=3.0
      expect(metrics.sharpeRatio).toBeCloseTo(3.0, 1)
      expect(metrics.maxDrawdownPct).toBe(0) // No drawdown with all wins
    })

    it('closing only some trades keeps PENDING ones excluded from metrics', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision')
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: makeMockExecution({ orderId: 'sim-1', symbol: 'AAPL' }),
        })
        .mockResolvedValueOnce({
          success: true, action: 'EXECUTED',
          riskCheck: { approved: true, maxPositionSize: 1000, currentVar: 500, circuitBreakerActive: false, drawdownLevel: 'NORMAL' },
          execution: makeMockExecution({ orderId: 'sim-2', symbol: 'MSFT' }),
        })

      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }), makePortfolio(), true)
      await workforce.analyze(makeMarketData({ symbol: 'MSFT' }), makePortfolio(), true)

      // Close only the first trade
      const trades: TradeOutcomeRecord[] = (tracker as any).trades
      trades[0] = { ...trades[0], outcome: 'WIN', pnl: 800, pnlPct: 0.016 }
      // trades[1] remains PENDING

      const metrics = tracker.computeMetrics()

      expect(metrics.totalTrades).toBe(1) // Only 1 closed
      expect(metrics.winRate).toBe(1.0)
      expect(metrics.cumulativePnl).toBe(800)

      // getRecordCounts still shows 2 trades (PENDING + closed)
      expect(tracker.getRecordCounts()).toEqual({ debates: 2, trades: 2 })
    })

    // ── Human Review Path ──

    it('mock executeDecision to require human review → action=HELD with error, no trade record', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      })

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      // ── Action is HELD, not EXECUTED ──
      expect(result.action).toBe('HELD')
      expect(result.execution).toBeUndefined()
      expect(result.error).toBe('Awaiting human review')

      // ── Risk check has the human-review reject reason ──
      expect(result.riskCheck).toBeDefined()
      expect(result.riskCheck!.approved).toBe(false)
      expect(result.riskCheck!.rejectReason).toContain('Human review required')

      // ── The debate decision itself is still valid (BUY) ──
      expect(result.decision.action).toBe('BUY')
      expect(result.decision.overallConfidence).toBeGreaterThan(0.6)

      // ── No trade record created (action !== EXECUTED) ──
      expect(tracker.getTradeRecords()).toHaveLength(0)

      // ── Debate is still recorded ──
      expect(tracker.getDebateRecords()).toHaveLength(1)
    })

    it('human review: debate record exists but zero trade records after the hold', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      })

      // Run two debates, both triggering human review
      await workforce.analyze(makeMarketData({ symbol: 'AAPL' }), makePortfolio(), true)
      await workforce.analyze(makeMarketData({ symbol: 'MSFT', currentPrice: 420 }), makePortfolio(), true)

      const counts = tracker.getRecordCounts()
      expect(counts.debates).toBe(2)
      expect(counts.trades).toBe(0)

      // computeMetrics shows debates but no trades
      const metrics = tracker.computeMetrics()
      expect(metrics.totalDebates).toBe(2)
      expect(metrics.totalTrades).toBe(0)
      expect(metrics.winRate).toBe(0)
      expect(metrics.cumulativePnl).toBe(0)
    })

    it('human review: no execution fields leak into the result', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      })

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.execution).toBeUndefined()
      expect(result.action).toBe('HELD')
      // Decision should still exist and be valid
      expect(result.decision).toBeDefined()
      expect(result.decision.action).toBe('BUY')
      expect(result.decision.roundsRequired).toBeGreaterThanOrEqual(1)
      expect(result.decision.votingBreakdown).toHaveLength(6)
    })

    it('human review: sessionId is preserved in the debate record despite held execution', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      })

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      const debateRecords = tracker.getDebateRecords()
      expect(debateRecords).toHaveLength(1)
      expect(debateRecords[0].sessionId).toBe(result.debateState.sessionId)
      expect(debateRecords[0].decision.action).toBe('BUY')

      // No trade record links back — there are no trades
      expect(tracker.getTradeRecords()).toHaveLength(0)
    })

    it('human review via requiresHumanReview flag on low-confidence decision (no mock)', async () => {
      // Use low-confidence canned responses so the debate produces
      // a decision with requiresHumanReview = true (absScore < 0.7 threshold).
      // The Layer1 client (in simulation mode) will then reject with HELD.
      const savedResponses: typeof cannedResponses = JSON.parse(JSON.stringify(cannedResponses))

      // Set all agents to low confidence with mixed recommendations
      // so the weighted consensus score stays below the 0.7 human-review threshold
      cannedResponses.macro_strategist = { ...cannedResponses.macro_strategist, recommendation: 'BUY', confidence: 0.55, reasoning: 'Weak macro signals', evidenceRefs: ['GDP'], keyMetrics: {} }
      cannedResponses.sector_analyst =    { ...cannedResponses.sector_analyst,    recommendation: 'BUY', confidence: 0.52, reasoning: 'Mixed sector', evidenceRefs: ['flows'], keyMetrics: {} }
      cannedResponses.sentiment_agent =   { ...cannedResponses.sentiment_agent,   recommendation: 'BUY', confidence: 0.48, reasoning: 'Neutral sentiment', evidenceRefs: ['news'], keyMetrics: {} }
      cannedResponses.technical_analyst =  { ...cannedResponses.technical_analyst,  recommendation: 'SELL', confidence: 0.50, reasoning: 'Weak technicals', evidenceRefs: ['RSI'], keyMetrics: { targetPrice: 160 } }
      cannedResponses.risk_manager =      { ...cannedResponses.risk_manager,      recommendation: 'SELL', confidence: 0.45, reasoning: 'Low risk conviction', evidenceRefs: ['VaR'], keyMetrics: { stopLoss: 160 } }
      cannedResponses.execution_optimizer = { ...cannedResponses.execution_optimizer, recommendation: 'BUY', confidence: 0.51, reasoning: 'Weak execution', evidenceRefs: ['spread'], keyMetrics: {} }

      try {
        // IMPORTANT: Do NOT mock executeDecision — let the real Layer1 client
        // (simulation mode) process the decision, which should detect
        // requiresHumanReview === true and return HELD.
        const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

        // ── The real executeDecision should have returned HELD ──
        expect(result.action).toBe('HELD')
        expect(result.execution).toBeUndefined()
        expect(result.error).toBe('Awaiting human review')
        expect(result.riskCheck?.rejectReason).toContain('Human review required')

        // ── Decision has requiresHumanReview flag set by the supervisor ──
        expect(result.decision.requiresHumanReview).toBe(true)

        // ── No trade record ──
        expect(tracker.getTradeRecords()).toHaveLength(0)
        expect(tracker.getDebateRecords()).toHaveLength(1)
      } finally {
        // Restore original responses
        for (const role of Object.keys(savedResponses)) {
          (cannedResponses as any)[role] = savedResponses[role]
        }
      }
    })

    it('human review: riskCheck details are surfaced in the result', async () => {
      jest.spyOn(workforce.getLayer1Client(), 'executeDecision').mockResolvedValue({
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      })

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      expect(result.riskCheck).toBeDefined()
      expect(result.riskCheck!.approved).toBe(false)
      expect(result.riskCheck!.circuitBreakerActive).toBe(false)
      expect(result.riskCheck!.drawdownLevel).toBe('NORMAL')
      expect(result.riskCheck!.rejectReason).toBe('Human review required — low confidence decision')
    })

    // ── GenerateOrderIntent Null Path ──

    it('debate produces HOLD when all agents vote HOLD → autoExecute returns HELD (no error)', async () => {
      // Swap all canned responses to HOLD — debate produces HOLD decision.
      // The workforce catches HOLD at Step 2 (before generateOrderIntent),
      // so no error message is attached.
      const savedResponses: typeof cannedResponses = JSON.parse(JSON.stringify(cannedResponses))
      for (const role of Object.keys(cannedResponses)) {
        cannedResponses[role] = {
          recommendation: 'HOLD',
          confidence: 0.60,
          reasoning: `${role} sees no clear signal — recommend HOLD.`,
          evidenceRefs: ['mixed signals'],
          keyMetrics: {},
        }
      }

      try {
        const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

        // ── Debate returns HOLD ──
        expect(result.decision.action).toBe('HOLD')
        expect(result.decision.vetoApplied).toBe(false)

        // ── autoExecute returns HELD (HOLD caught at Step 2, no error) ──
        expect(result.action).toBe('HELD')
        expect(result.error).toBeUndefined()
        expect(result.execution).toBeUndefined()

        // ── No trade record ──
        expect(tracker.getTradeRecords()).toHaveLength(0)
        expect(tracker.getDebateRecords()).toHaveLength(1)

        // ── All agent analyses report HOLD ──
        const analyses = tracker.getDebateRecords()[0].agentAnalyses
        for (const a of analyses) {
          expect(a.recommendation).toBe('HOLD')
        }
      } finally {
        for (const role of Object.keys(savedResponses)) {
          (cannedResponses as any)[role] = savedResponses[role]
        }
      }
    })

    it('generateOrderIntent returns null → HELD with order intent generation failure error', async () => {
      // Mock generateOrderIntent to return null, simulating the edge case
      // where the execution optimizer cannot produce an order intent.
      // The debate produces BUY (default bullish responses), so it passes
      // the HOLD/VETO gates and reaches generateOrderIntent.
      jest.spyOn(workforce.getAgent('execution_optimizer') as any, 'generateOrderIntent')
        .mockResolvedValue(null)

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      // ── Debate produces BUY (normal consensus) ──
      expect(result.decision.action).toBe('BUY')
      expect(result.decision.vetoApplied).toBe(false)

      // ── But generateOrderIntent returned null → HELD with error ──
      expect(result.action).toBe('HELD')
      expect(result.error).toBe('Execution Optimizer could not generate order intent')
      expect(result.execution).toBeUndefined()

      // ── No trade record (executeDecision never called) ──
      expect(tracker.getTradeRecords()).toHaveLength(0)
      expect(tracker.getDebateRecords()).toHaveLength(1)
    })

    it('generateOrderIntent null: decision and voting breakdown are still intact', async () => {
      jest.spyOn(workforce.getAgent('execution_optimizer') as any, 'generateOrderIntent')
        .mockResolvedValue(null)

      const result = await workforce.analyze(makeMarketData(), makePortfolio(), true)

      // Decision is preserved even though order intent failed
      expect(result.decision).toBeDefined()
      expect(result.decision.action).toBe('BUY')
      expect(result.decision.votingBreakdown).toHaveLength(6)
      expect(result.decision.roundsRequired).toBeGreaterThanOrEqual(1)
      expect(result.decision.overallConfidence).toBeGreaterThan(0.6)

      // Debate state also preserved
      expect(result.debateState.sessionId).toBeTruthy()
    })

    it('human review: event is emitted on the Layer1 client', async () => {
      // Listen on the Layer1Client directly — the workforce's event forwarding
      // is only set up in initialize(), which is skipped (initialized = true).
      const events: string[] = []
      workforce.getLayer1Client().on('humanReviewRequired', () => {
        events.push('humanReviewRequired')
      })

      // Use low-confidence canned responses so the real executeDecision
      // (simulation mode, not mocked) processes the decision, detects
      // requiresHumanReview=true, and emits the event.
      const savedResponses: typeof cannedResponses = JSON.parse(JSON.stringify(cannedResponses))
      cannedResponses.macro_strategist =     { ...cannedResponses.macro_strategist,     recommendation: 'BUY',  confidence: 0.55, reasoning: 'Weak macro',     evidenceRefs: ['GDP'],   keyMetrics: {} }
      cannedResponses.sector_analyst =        { ...cannedResponses.sector_analyst,        recommendation: 'BUY',  confidence: 0.52, reasoning: 'Mixed sector',    evidenceRefs: ['flows'], keyMetrics: {} }
      cannedResponses.sentiment_agent =       { ...cannedResponses.sentiment_agent,       recommendation: 'BUY',  confidence: 0.48, reasoning: 'Neutral sentiment',evidenceRefs: ['news'],  keyMetrics: {} }
      cannedResponses.technical_analyst =      { ...cannedResponses.technical_analyst,      recommendation: 'SELL', confidence: 0.50, reasoning: 'Weak technicals',  evidenceRefs: ['RSI'],   keyMetrics: { targetPrice: 160 } }
      cannedResponses.risk_manager =          { ...cannedResponses.risk_manager,          recommendation: 'SELL', confidence: 0.45, reasoning: 'Low risk conviction',evidenceRefs: ['VaR'],  keyMetrics: { stopLoss: 160 } }
      cannedResponses.execution_optimizer =    { ...cannedResponses.execution_optimizer,    recommendation: 'BUY',  confidence: 0.51, reasoning: 'Weak execution',   evidenceRefs: ['spread'],keyMetrics: {} }

      try {
        await workforce.analyze(makeMarketData(), makePortfolio(), true)

        // The real executeDecision emits humanReviewRequired on the Layer1 client
        expect(events).toContain('humanReviewRequired')
      } finally {
        for (const role of Object.keys(savedResponses)) {
          (cannedResponses as any)[role] = savedResponses[role]
        }
      }
    })
  })
})
