/**
 * Unit tests for StrategyGA.simulateConsensus()
 *
 * Covers edge cases: all-HOLD, missing agents, extreme weights,
 * empty input, zero division, threshold boundaries, tied votes.
 */

import { StrategyGA } from '../../src/meta/strategy-ga'
import type { DebateRecord, AgentAnalysis } from '../../src/meta/types'
import type { AgentTradingRole, MarketDataInput, FinalDecision, TradingRecommendation } from '../../src/trading/types'

// ----------------------------------------------------------------
// Test Helpers
// ----------------------------------------------------------------

/** A minimal viable market snapshot for test debates */
function makeMarketSnapshot(overrides: Partial<MarketDataInput> = {}): MarketDataInput {
  return {
    symbol: 'TEST',
    currentPrice: 100,
    dailyChangePct: 0,
    volume: 1_000_000,
    avgVolume: 1_000_000,
    bidAskSpread: 0.01,
    ...overrides,
  }
}

/** A minimal viable final decision for test debates */
function makeFinalDecision(overrides: Partial<FinalDecision> = {}): FinalDecision {
  return {
    action: 'BUY',
    overallConfidence: 0.7,
    reasoningSummary: 'Consensus reached by majority vote.',
    vetoApplied: false,
    roundsRequired: 1,
    allAnalyses: [],
    votingBreakdown: [],
    timestamp: new Date().toISOString(),
    requiresHumanReview: false,
    ...overrides,
  }
}

/** Create a single agent analysis with a given recommendation, confidence, and role */
function makeAnalysis(
  role: AgentTradingRole,
  recommendation: TradingRecommendation,
  confidence: number,
  overrides: Partial<AgentAnalysis> = {}
): AgentAnalysis {
  return {
    role,
    round: 0,
    recommendation,
    confidence,
    reasoning: `Analysis from ${role}`,
    evidenceRefs: ['price', 'volume'],
    keyMetrics: {},
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

/** Build a DebateRecord from agent analyses */
function makeDebate(
  analyses: AgentAnalysis[],
  overrides: Partial<DebateRecord> = {}
): DebateRecord {
  return {
    sessionId: `debate-${Math.random().toString(36).slice(2, 8)}`,
    symbol: 'TEST',
    timestamp: new Date().toISOString(),
    marketSnapshot: makeMarketSnapshot(),
    decision: makeFinalDecision(),
    agentAnalyses: analyses,
    roundsRequired: 1,
    vetoApplied: false,
    agentProviders: {} as Record<AgentTradingRole, 'openai' | 'anthropic'>,
    agentModels: {} as Record<AgentTradingRole, string>,
    promptVersions: {} as Record<AgentTradingRole, string>,
    ...overrides,
  }
}

/** Call the private simulateConsensus method via type-cast */
function callSimulateConsensus(
  ga: StrategyGA,
  debate: DebateRecord,
  weights: Record<string, number>
): { consensusDirection: string; weightedConfidence: number } {
  return (ga as any).simulateConsensus(debate, weights)
}

const ALL_ROLES: AgentTradingRole[] = [
  'macro_strategist',
  'sector_analyst',
  'sentiment_agent',
  'technical_analyst',
  'risk_manager',
  'execution_optimizer',
]

/** Create a default GA instance (no tracker needed — simulateConsensus is stateless) */
function makeGA(): StrategyGA {
  return new StrategyGA({ persist: false })
}

// ----------------------------------------------------------------
// Tests
// ----------------------------------------------------------------

describe('StrategyGA.simulateConsensus', () => {
  // ── Basic Direction Tests ──

  describe('basic direction deduction', () => {
    it('returns LONG when all agents are STRONG_BUY at full confidence', () => {
      const ga = makeGA()
      const analyses = ALL_ROLES.map(role =>
        makeAnalysis(role, 'STRONG_BUY', 1.0)
      )
      const debate = makeDebate(analyses)
      const weights = Object.fromEntries(ALL_ROLES.map(r => [r, 0.5]))

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('LONG')
      expect(result.weightedConfidence).toBeGreaterThan(0.5)
    })

    it('returns SHORT when all agents are STRONG_SELL at full confidence', () => {
      const ga = makeGA()
      const analyses = ALL_ROLES.map(role =>
        makeAnalysis(role, 'STRONG_SELL', 1.0)
      )
      const debate = makeDebate(analyses)
      const weights = Object.fromEntries(ALL_ROLES.map(r => [r, 0.5]))

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
      expect(result.weightedConfidence).toBeGreaterThan(0.5)
    })

    it('returns NEUTRAL when 3 BUY and 3 SELL cancel out at equal weights', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_BUY', 1.0),
        makeAnalysis('sentiment_agent', 'STRONG_BUY', 1.0),
        makeAnalysis('technical_analyst', 'STRONG_SELL', 1.0),
        makeAnalysis('risk_manager', 'STRONG_SELL', 1.0),
        makeAnalysis('execution_optimizer', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      const weights = Object.fromEntries(ALL_ROLES.map(r => [r, 1.0]))

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBeCloseTo(0, 5)
    })

    it('BUY recommendations contribute half as much as STRONG_BUY', () => {
      const ga = makeGA()
      // One agent with BUY, another with STRONG_SELL (half strength)
      // BUY contributes +0.5, STRONG_SELL contributes -1.0 → net SHORT
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
    })

    it('confidence scales the contribution (low confidence = muted signal)', () => {
      const ga = makeGA()
      // Macro has STRONG_BUY at 0.1 confidence (0.1 signal)
      // Sector has SELL at 1.0 confidence (1.0 signal) → net SHORT
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 0.1),
        makeAnalysis('sector_analyst', 'SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
    })
  })

  // ── All-HOLD Edge Case ──

  describe('all-HOLD debate', () => {
    it('returns NEUTRAL with zero confidence when every agent is HOLD', () => {
      const ga = makeGA()
      const analyses = ALL_ROLES.map(role =>
        makeAnalysis(role, 'HOLD', 0.5)
      )
      const debate = makeDebate(analyses)
      const weights = Object.fromEntries(ALL_ROLES.map(r => [r, 1.0]))

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBe(0)
    })

    it('HOLD agents at different confidences still produce NEUTRAL', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'HOLD', 0.9),
        makeAnalysis('sector_analyst', 'HOLD', 0.1),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBe(0)
    })

    it('a single HOLD among BUY agents still produces LONG', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_BUY', 1.0),
        makeAnalysis('sentiment_agent', 'HOLD', 1.0), // this one abstains
      ]
      const debate = makeDebate(analyses)
      const weights = {
        macro_strategist: 1.0,
        sector_analyst: 1.0,
        sentiment_agent: 1.0,
      }

      const result = callSimulateConsensus(ga, debate, weights)

      // 2 STRONG_BUY × 1.0 = 2.0 long, 0 short, 3 total weight → 0.67 signal
      expect(result.consensusDirection).toBe('LONG')
      expect(result.weightedConfidence).toBeGreaterThan(0)
    })
  })

  // ── Missing Agents (partial debate) ──

  describe('missing agents', () => {
    it('works with only 2 of 6 agents present', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_BUY', 1.0),
      ]
      const debate = makeDebate(analyses)
      // Weights only for present agents
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('LONG')
      expect(result.weightedConfidence).toBeGreaterThan(0.5)
    })

    it('missing agent defaults to weight 0.5 when not in weights map', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      // Purposely omit sector_analyst from weights — should default to 0.5
      const weights = { macro_strategist: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      // Macro: 1.0 * 1.0 * 1.0 = 1.0 LONG
      // Sector: 0.5 (default) * 1.0 * 1.0 = 0.5 SHORT
      // Total weight = 1.5, normLong = 0.667, normShort = 0.333, net = 0.334 > 0.15
      expect(result.consensusDirection).toBe('LONG')
    })

    it('works with a single agent present', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('risk_manager', 'STRONG_SELL', 0.8),
      ]
      const debate = makeDebate(analyses)
      const weights = { risk_manager: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
    })
  })

  // ── Extreme Weights ──

  describe('extreme weights', () => {
    it('weight 0.0 effectively removes an agent from the vote', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      // Macro weight 0 — their BUY doesn't count
      const weights = { macro_strategist: 0.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
      // Only sector_analyst contributes: totalWeight = 1.0
      // sector: 1.0 * | -1.0 | * 1.0 = 1.0 short
      // normShort = 1.0, netSignal = -1.0
      expect(result.weightedConfidence).toBeCloseTo(1.0, 5)
    })

    it('all weights 0.0 produces NEUTRAL (zero division guard)', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 0.0, sector_analyst: 0.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBe(0)
    })

    it('extreme weight of 100.0 still normalizes correctly', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 100.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      // Macro: 100 * 1.0 * 1.0 = 100 LONG
      // Sector: 1 * 1.0 * 1.0 = 1 SHORT
      // totalWeight = 101, normLong = 0.990, normShort = 0.010, net = 0.98 > 0.15
      expect(result.consensusDirection).toBe('LONG')
      expect(result.weightedConfidence).toBeGreaterThan(0.9)
    })

    it('a single dominant agent (weight 1.0) overrides five zero-weighted agents', () => {
      const ga = makeGA()
      const analyses = ALL_ROLES.map((role, i) =>
        makeAnalysis(role, i === 0 ? 'STRONG_BUY' : 'STRONG_SELL', 1.0)
      )
      const debate = makeDebate(analyses)
      // Only macro_strategist gets weight > 0
      const weights: Record<string, number> = {}
      for (const r of ALL_ROLES) weights[r] = r === 'macro_strategist' ? 1.0 : 0.0

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('LONG')
    })
  })

  // ── Empty / Edge Input ──

  describe('empty and edge input', () => {
    it('returns NEUTRAL with zero confidence for empty agentAnalyses', () => {
      const ga = makeGA()
      const debate = makeDebate([])
      const weights = Object.fromEntries(ALL_ROLES.map(r => [r, 1.0]))

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBe(0)
    })

    it('handles confidence of exactly 0', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 0.0),
        makeAnalysis('sector_analyst', 'STRONG_SELL', 0.0),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBe(0)
    })
  })

  // ── Threshold Boundary Tests ──

  describe('threshold boundaries', () => {
    it('netSignal exactly at +0.15 boundary is NEUTRAL (not > 0.15)', () => {
      const ga = makeGA()
      // Need netSignal exactly 0.15
      // Macro: w=1.0, BUY (0.5), conf=0.6 → 1.0 * 0.5 * 0.6 = 0.3 LONG
      // Sector: w=1.0, SELL (-0.5), conf=0.3 → 1.0 * 0.5 * 0.3 = 0.15 SHORT
      // totalWeight = 2, normLong = 0.15, normShort = 0.075, net = 0.075
      // Let me recalculate: w * |directionMultiplier| * confidence
      // BUY: 1.0 * 0.5 * 0.6 = 0.3 on longScore
      // SELL: 1.0 * |-0.5| * 0.3 = 1.0 * 0.5 * 0.3 = 0.15 on shortScore
      // totalWeight = 2.0
      // normLong = 0.3 / 2.0 = 0.15
      // normShort = 0.15 / 2.0 = 0.075
      // netSignal = 0.15 - 0.075 = 0.075 — too low

      // Let me try: one agent BUY at conf 1.0, one agent at BUY conf ~0.3
      // BUY1: w=1.0, BUY 0.5, conf=1.0 → 0.5 LONG
      // BUY2: w=1.0, BUY 0.5, conf=0.2 → 0.1 LONG
      // totalWeight = 2.0, normLong = 0.6/2 = 0.3, normShort=0, netSignal=0.3 > 0.15

      // For exactly 0.15: need two equal-weight agents, one BUY one HOLD
      // BUY: w=1.0, BUY 0.5, conf=0.6 → 0.3 LONG
      // HOLD: w=1.0, HOLD → 0
      // totalWeight = 2.0, normLong = 0.15, normShort = 0, netSignal = 0.15
      // Since condition is netSignal > 0.15 (strict), this should be NEUTRAL
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', 0.6),
        makeAnalysis('sector_analyst', 'HOLD', 0.5),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      // netSignal = 0.15 exactly — NOT > 0.15, so NEUTRAL
      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBeCloseTo(0.15, 10)
    })

    it('netSignal just above +0.15 produces LONG', () => {
      const ga = makeGA()
      // BUY: w=1.0, BUY 0.5, conf=0.61 → 0.305 LONG
      // HOLD: w=1.0, HOLD → 0
      // totalWeight = 2.0, normLong = 0.1525, netSignal = 0.1525 > 0.15
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', 0.61),
        makeAnalysis('sector_analyst', 'HOLD', 0.5),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('LONG')
      expect(result.weightedConfidence).toBeGreaterThan(0.15)
    })

    it('netSignal exactly at -0.15 boundary is NEUTRAL', () => {
      const ga = makeGA()
      // SELL: w=1.0, SELL (-0.5), conf=0.6 → 1.0 * 0.5 * 0.6 = 0.3 SHORT
      // HOLD: w=1.0, HOLD → 0
      // totalWeight = 2.0, normShort = 0.15, netSignal = -0.15
      // NOT < -0.15, so NEUTRAL
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'SELL', 0.6),
        makeAnalysis('sector_analyst', 'HOLD', 0.5),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('NEUTRAL')
      expect(result.weightedConfidence).toBeCloseTo(0.15, 10)
    })

    it('netSignal just below -0.15 produces SHORT', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'SELL', 0.61),
        makeAnalysis('sector_analyst', 'HOLD', 0.5),
      ]
      const debate = makeDebate(analyses)
      const weights = { macro_strategist: 1.0, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      expect(result.consensusDirection).toBe('SHORT')
    })
  })

  // ── Mixed Scenarios ──

  describe('mixed scenarios', () => {
    it('STRONG_BUY at low weight loses to SELL at high weight', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'SELL', 1.0),
      ]
      const debate = makeDebate(analyses)
      // STRONG_BUY has multiplier 1.0, SELL has 0.5 — but sector gets 10x weight
      const weights = { macro_strategist: 0.1, sector_analyst: 1.0 }

      const result = callSimulateConsensus(ga, debate, weights)

      // Macro: 0.1 * 1.0 * 1.0 = 0.1 LONG
      // Sector: 1.0 * 0.5 * 1.0 = 0.5 SHORT
      // totalWeight = 1.1, normLong = 0.091, normShort = 0.455, net = -0.364
      expect(result.consensusDirection).toBe('SHORT')
    })

    it('unequal agent counts with mixed recommendations', () => {
      const ga = makeGA()
      // 3 BUY, 1 SELL — BUY should win
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'BUY', 0.8),
        makeAnalysis('sector_analyst', 'BUY', 0.8),
        makeAnalysis('sentiment_agent', 'BUY', 0.8),
        makeAnalysis('risk_manager', 'SELL', 0.8),
      ]
      const debate = makeDebate(analyses)
      const weights = {
        macro_strategist: 1.0, sector_analyst: 1.0,
        sentiment_agent: 1.0, risk_manager: 1.0,
      }

      const result = callSimulateConsensus(ga, debate, weights)

      // 3 * 0.5 * 0.8 = 1.2 LONG, 1 * 0.5 * 0.8 = 0.4 SHORT
      // totalWeight = 4, normLong = 0.3, normShort = 0.1, net = 0.2 > 0.15
      expect(result.consensusDirection).toBe('LONG')
    })

    it('Risk Manager with extreme weight can veto consensus', () => {
      const ga = makeGA()
      const analyses: AgentAnalysis[] = [
        makeAnalysis('macro_strategist', 'STRONG_BUY', 1.0),
        makeAnalysis('sector_analyst', 'STRONG_BUY', 1.0),
        makeAnalysis('sentiment_agent', 'STRONG_BUY', 1.0),
        makeAnalysis('technical_analyst', 'STRONG_BUY', 1.0),
        makeAnalysis('risk_manager', 'STRONG_SELL', 0.3),
        makeAnalysis('execution_optimizer', 'BUY', 0.5),
      ]
      const debate = makeDebate(analyses)
      // Give risk_manager 100x weight
      const weights: Record<string, number> = {
        macro_strategist: 1.0, sector_analyst: 1.0,
        sentiment_agent: 1.0, technical_analyst: 1.0,
        risk_manager: 100.0, execution_optimizer: 1.0,
      }

      const result = callSimulateConsensus(ga, debate, weights)

      // Risk: 100 * 1.0 * 0.3 = 30.0 SHORT
      // Others: 4 * 1.0 * 1.0 * 1.0 = 4.0 LONG + 1 * 0.5 * 0.5 = 0.25 LONG
      // totalWeight = 105, normShort dominates
      expect(result.consensusDirection).toBe('SHORT')
    })
  })
})
