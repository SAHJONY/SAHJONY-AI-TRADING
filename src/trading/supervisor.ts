/**
 * Layer 4 — LangGraph Supervisor Debate Graph
 *
 * Implements the multi-agent collaborative reasoning loop using LangGraph.js StateGraph.
 * The Supervisor orchestrates parallel agent analysis rounds, aggregates with weighted
 * consensus, enforces Risk Manager veto, and produces a final trading decision.
 *
 * All node functions are extracted before the StateGraph builder chain to satisfy
 * LangGraph's strict literal-type tracking across addNode/addEdge calls.
 */

import { StateGraph, END, Annotation } from '@langchain/langgraph'
import { Task } from '../types'
import { v4 as uuid } from 'uuid'
import {
  DebateState,
  MarketDataInput,
  AgentAnalysis,
  FinalDecision,
  VotingBreakdown,
  TradingRecommendation,
  AgentTradingRole,
} from './types'
import { TradingAgent, ExecutionOptimizerAgent } from './agents'

// ── State Annotation (LangGraph state schema with reducers) ──

const DebateStateAnnotation = Annotation.Root({
  marketData: Annotation<MarketDataInput>({
    reducer: (_, next) => next,
    default: () => ({} as MarketDataInput),
  }),
  symbol: Annotation<string>({
    reducer: (_, next) => next,
    default: () => '',
  }),
  currentRound: Annotation<number>({
    reducer: (_, next) => next,
    default: () => 0,
  }),
  maxRounds: Annotation<number>({
    reducer: (_, next) => next,
    default: () => 3,
  }),
  agentAnalyses: Annotation<AgentAnalysis[]>({
    reducer: (current, next) => [...current, ...next],
    default: () => [],
  }),
  consensusReached: Annotation<boolean>({
    reducer: (_, next) => next,
    default: () => false,
  }),
  vetoTriggered: Annotation<boolean>({
    reducer: (_, next) => next,
    default: () => false,
  }),
  vetoReason: Annotation<string | undefined>({
    reducer: (_, next) => next,
    default: () => undefined,
  }),
  finalDecision: Annotation<FinalDecision | null>({
    reducer: (_, next) => next,
    default: () => null,
  }),
  historicalWeights: Annotation<Record<string, number>>({
    reducer: (current, next) => ({ ...current, ...next }),
    default: () => ({}),
  }),
  consensusThreshold: Annotation<number>({
    reducer: (_, next) => next,
    default: () => 0.6,
  }),
  supervisorInstruction: Annotation<string | undefined>({
    reducer: (_, next) => next,
    default: () => undefined,
  }),
  sessionId: Annotation<string>({
    reducer: (_, next) => next,
    default: () => uuid(),
  }),
  error: Annotation<string | undefined>({
    reducer: (_, next) => next ?? undefined,
    default: () => undefined,
  }),
})

// ── Score Map for Voting ──

const VOTE_SCORES: Record<TradingRecommendation, number> = {
  STRONG_BUY: 1.0,
  BUY: 0.5,
  HOLD: 0.0,
  SELL: -0.5,
  STRONG_SELL: -1.0,
}

// ── Graph Builder ──

export interface DebateGraphConfig {
  maxRounds: number
  consensusThreshold: number
  agents: {
    macro: TradingAgent
    sector: TradingAgent
    sentiment: TradingAgent
    technical: TradingAgent
    risk: TradingAgent
    execution: ExecutionOptimizerAgent
  }
  historicalWeights?: Record<string, number>
}

/** Node function type used by all agent/aggregator/supervisor nodes */
type DebateNodeFn = (state: DebateState) => Promise<Partial<DebateState>>

/**
 * Build the LangGraph StateGraph for the multi-agent debate.
 *
 * All node functions are extracted as variables before building the graph
 * so the StateGraph can be built in a single chain — satisfying LangGraph's
 * strict generic type tracking.
 */
export function buildDebateGraph(config: DebateGraphConfig) {
  // ── Factory: creates an agent debate node ──
  const makeAgentNode = (agent: TradingAgent, role: AgentTradingRole): DebateNodeFn => {
    return async (state: DebateState): Promise<Partial<DebateState>> => {
      if (!agent.isEnabled() || state.consensusReached || state.vetoTriggered) {
        return {}
      }

      try {
        const previousAnalyses = state.agentAnalyses.filter(a => a.round < state.currentRound)
        const task: Task = {
          id: `debate-${role}-${state.sessionId}-r${state.currentRound}`,
          type: 'debate_analysis',
          description: `Analyze ${state.symbol} market data. Round ${state.currentRound + 1}.`,
          priority: 'high',
          status: 'in_progress',
          dependencies: [],
          context: {
            userRequest: `Trading debate: ${state.symbol}`,
            sessionId: state.sessionId,
            variables: {
              marketData: state.marketData,
              round: state.currentRound,
              previousAnalyses,
              supervisorInstruction: state.supervisorInstruction,
            },
          },
          createdAt: new Date(),
          updatedAt: new Date(),
        }

        const result = await agent.runTask(task)

        if (result.success && result.output) {
          const analysis = result.output as AgentAnalysis
          return { agentAnalyses: [analysis] }
        }

        return {}
      } catch (err) {
        console.error(`Agent ${role} failed:`, err)
        return {}
      }
    }
  }

  // ── Node: Supervisor (generates round instructions) ──
  const supervisorNode: DebateNodeFn = async (state) => {
    if (state.consensusReached || state.vetoTriggered || state.error) {
      return {}
    }

    const round = state.currentRound
    const previousRoundAnalyses = state.agentAnalyses.filter(a => a.round === round - 1)

    let instruction = `Round ${round + 1} of ${state.maxRounds}.`

    if (round > 0 && previousRoundAnalyses.length > 0) {
      const buys = previousRoundAnalyses.filter(
        a => a.recommendation === 'BUY' || a.recommendation === 'STRONG_BUY'
      )
      const sells = previousRoundAnalyses.filter(
        a => a.recommendation === 'SELL' || a.recommendation === 'STRONG_SELL'
      )

      if (buys.length > 0 && sells.length > 0) {
        instruction += ' There is significant disagreement. Each agent should address the opposing viewpoint specifically in their rebuttals.'
      } else if (buys.length > sells.length) {
        instruction += ' The consensus is leaning bullish. Dissenting agents: strengthen your counter-arguments with specific data.'
      } else {
        instruction += ' The consensus is leaning bearish. Dissenting agents: strengthen your counter-arguments with specific data.'
      }
    }

    if (round === state.maxRounds - 1) {
      instruction += ' THIS IS THE FINAL ROUND. Be decisive.'
    }

    return { supervisorInstruction: instruction }
  }

  // ── Node: Macro Strategist ──
  const macroNode = makeAgentNode(config.agents.macro, 'macro_strategist')

  // ── Node: Sector Analyst ──
  const sectorNode = makeAgentNode(config.agents.sector, 'sector_analyst')

  // ── Node: Sentiment Agent ──
  const sentimentNode = makeAgentNode(config.agents.sentiment, 'sentiment_agent')

  // ── Node: Technical Analyst ──
  const technicalNode = makeAgentNode(config.agents.technical, 'technical_analyst')

  // ── Node: Risk Manager ──
  const riskNode = makeAgentNode(config.agents.risk, 'risk_manager')

  // ── Node: Execution Optimizer ──
  const executionNode = makeAgentNode(config.agents.execution, 'execution_optimizer')

  // ── Node: Aggregator (weighted consensus + veto) ──
  const aggregatorNode: DebateNodeFn = async (state) => {
    const currentRoundAnalyses = state.agentAnalyses.filter(
      a => a.round === state.currentRound
    )

    if (currentRoundAnalyses.length === 0) {
      return { error: 'No agent analyses produced this round' }
    }

    // 1. Risk Manager Veto Check
    const riskAnalysis = currentRoundAnalyses.find(a => a.role === 'risk_manager')
    if (riskAnalysis) {
      const isVeto = riskAnalysis.recommendation === 'STRONG_SELL' && riskAnalysis.confidence >= 0.8
      if (isVeto) {
        return {
          vetoTriggered: true,
          vetoReason: riskAnalysis.reasoning,
          consensusReached: true,
          finalDecision: createVetoDecision(riskAnalysis, state),
        }
      }
    }

    // 2. Weighted Voting
    let totalWeight = 0
    let weightedScore = 0
    const breakdown: VotingBreakdown[] = []

    for (const analysis of currentRoundAnalyses) {
      const weight = state.historicalWeights[analysis.role] || 0.5
      const voteScore = VOTE_SCORES[analysis.recommendation] || 0
      const weighted = voteScore * analysis.confidence * weight

      totalWeight += weight
      weightedScore += weighted

      breakdown.push({
        role: analysis.role,
        vote: analysis.recommendation,
        confidence: analysis.confidence,
        weight,
        weightedScore: weighted,
        contribution: weighted > 0.1
          ? 'Strong positive contribution'
          : weighted < -0.1
            ? 'Strong negative contribution'
            : 'Neutral contribution',
      })
    }

    const finalScore = totalWeight > 0 ? weightedScore / totalWeight : 0
    const absScore = Math.abs(finalScore)

    // 3. Decision
    const consensusReached = absScore >= state.consensusThreshold || state.currentRound >= state.maxRounds - 1

    if (consensusReached) {
      const action: 'BUY' | 'SELL' | 'HOLD' =
        finalScore > 0.15 ? 'BUY' :
        finalScore < -0.15 ? 'SELL' :
        'HOLD'

      const buyAnalyses = currentRoundAnalyses.filter(
        a => a.recommendation === 'BUY' || a.recommendation === 'STRONG_BUY'
      )
      const sellAnalyses = currentRoundAnalyses.filter(
        a => a.recommendation === 'SELL' || a.recommendation === 'STRONG_SELL'
      )
      const winningAnalyses = action === 'BUY' ? buyAnalyses : action === 'SELL' ? sellAnalyses : currentRoundAnalyses

      const targetPrice = extractMetric(winningAnalyses, 'targetPrice')
      const stopLoss = riskAnalysis?.keyMetrics?.['stopLoss'] || extractMetric(currentRoundAnalyses, 'stopLoss')
      const takeProfit = extractMetric(winningAnalyses, 'takeProfit')

      const finalDecision: FinalDecision = {
        action,
        overallConfidence: absScore,
        targetPrice,
        stopLoss,
        takeProfit,
        positionSizePct: riskAnalysis?.keyMetrics?.['positionSizePct']
          || config.agents.risk.getPerformanceWeight(),
        reasoningSummary: synthesizeSummary(winningAnalyses, action),
        vetoApplied: false,
        roundsRequired: state.currentRound + 1,
        allAnalyses: currentRoundAnalyses,
        votingBreakdown: breakdown,
        timestamp: new Date().toISOString(),
        requiresHumanReview: absScore < 0.7,
      }

      return {
        consensusReached: true,
        finalDecision,
      }
    }

    // Not enough consensus — advance to next round
    return {
      currentRound: state.currentRound + 1,
      supervisorInstruction: `Consensus not reached (score: ${absScore.toFixed(2)}). Each agent must address the strongest opposing arguments.`,
    }
  }

  // ── Build graph in single chain (required by LangGraph's strict generic tracking) ──
  const builder = new StateGraph(DebateStateAnnotation)
    // Nodes
    .addNode('supervisor', supervisorNode)
    .addNode('macro', macroNode)
    .addNode('sector', sectorNode)
    .addNode('sentiment', sentimentNode)
    .addNode('technical', technicalNode)
    .addNode('risk', riskNode)
    .addNode('execution', executionNode)
    .addNode('aggregator', aggregatorNode)

    // Edges: Supervisor → all agents (parallel dispatch)
    .addEdge('supervisor', 'macro')
    .addEdge('supervisor', 'sector')
    .addEdge('supervisor', 'sentiment')
    .addEdge('supervisor', 'technical')
    .addEdge('supervisor', 'risk')
    .addEdge('supervisor', 'execution')

    // Edges: Each agent → aggregator
    .addEdge('macro', 'aggregator')
    .addEdge('sector', 'aggregator')
    .addEdge('sentiment', 'aggregator')
    .addEdge('technical', 'aggregator')
    .addEdge('risk', 'aggregator')
    .addEdge('execution', 'aggregator')

    // Conditional: Aggregator → supervisor (loop) or END
    .addConditionalEdges(
      'aggregator',
      (state: DebateState): '__start__' | 'supervisor' | typeof END => {
        if (state.consensusReached || state.vetoTriggered || state.error) {
          return END
        }
        if (state.currentRound >= state.maxRounds) {
          return END
        }
        return 'supervisor'
      }
    )

    // Entry point
    .addEdge('__start__', 'supervisor')

  return builder.compile()
}

// ── Helper Functions ──

function createVetoDecision(riskAnalysis: AgentAnalysis, state: DebateState): FinalDecision {
  return {
    action: 'SELL',
    overallConfidence: riskAnalysis.confidence,
    stopLoss: riskAnalysis.keyMetrics?.['stopLoss'],
    reasoningSummary: `RISK MANAGER VETO: ${riskAnalysis.reasoning}`,
    vetoApplied: true,
    vetoReason: riskAnalysis.reasoning,
    roundsRequired: state.currentRound + 1,
    allAnalyses: state.agentAnalyses,
    votingBreakdown: [{
      role: 'risk_manager',
      vote: 'STRONG_SELL',
      confidence: riskAnalysis.confidence,
      weight: state.historicalWeights['risk_manager'] || 1.0,
      weightedScore: -1.0,
      contribution: 'VETO OVERRIDE — trade rejected on risk grounds',
    }],
    timestamp: new Date().toISOString(),
    requiresHumanReview: false,
  }
}

function extractMetric(analyses: AgentAnalysis[], key: string): number | undefined {
  for (const a of analyses) {
    if (a.keyMetrics?.[key] !== undefined) {
      return a.keyMetrics[key]
    }
  }
  return undefined
}

function synthesizeSummary(analyses: AgentAnalysis[], action: string): string {
  const topPoints = analyses
    .filter(a => {
      if (action === 'BUY') return a.recommendation === 'BUY' || a.recommendation === 'STRONG_BUY'
      if (action === 'SELL') return a.recommendation === 'SELL' || a.recommendation === 'STRONG_SELL'
      return true
    })
    .slice(0, 3)
    .map(a => {
      const roleTitle = a.role.replace(/_/g, ' ')
      return `[${roleTitle}] (${(a.confidence * 100).toFixed(0)}%): ${a.reasoning.substring(0, 120)}`
    })

  if (topPoints.length === 0) {
    return `Consensus: ${action}. Insufficient conviction from any single agent.`
  }

  return `Consensus: ${action}.\n\n` + topPoints.join('\n\n')
}
