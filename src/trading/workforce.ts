/**
 * Layer 4 — Trading Workforce Builder
 *
 * Convenience class that wires together all Layer 4 components:
 * agents, debate graph, and Layer 1 integration into a single callable system.
 *
 * Usage:
 *   const workforce = buildTradingWorkforce()
 *   const decision = await workforce.analyze(marketData, portfolioState)
 *   if (decision.action === 'EXECUTED') {
 *     console.log('Order filled:', decision.execution)
 *   }
 */

import { EventEmitter } from 'events'
import {
  MarketDataInput,
  DebateState,
  FinalDecision,
  AgentTradingRole,
  RiskCheckResponse,
} from './types'
import { TradingAgent, ExecutionOptimizerAgent, MacroStrategistAgent, SectorAnalystAgent, SentimentAgent, TechnicalAnalystAgent, RiskManagerAgent } from './agents'
import { buildDebateGraph, DebateGraphConfig } from './supervisor'
import { Layer1IntegrationClient, ExecutionReport, createLayer1Client } from './integration'
import { TradingSystemConfig, DEFAULT_TRADING_CONFIG, buildAgentConfigs, buildHistoricalWeights } from './config'
// Layer 5 meta-learning imports (optional — workforce works without them)
import type { MetaLearningPipeline } from '../meta/pipeline'
import type { DebateRecord, TradeOutcomeRecord } from '../meta/types'
// Layer 3 knowledge pipeline imports (optional — workforce works without them)
import type { KnowledgePipeline } from '../knowledge/pipeline'
// ── Portfolio State (fed into risk checks) ──

export interface PortfolioState {
  equity: number
  dailyPnl: number
  currentDrawdownPct: number
  positions: Array<{
    symbol: string
    quantity: number
    avgPrice: number
    marketValue: number
    unrealizedPnl: number
  }>
}

// ── Analysis Result ──

export interface AnalysisResult {
  /** The final consensus decision from the debate */
  decision: FinalDecision
  /** The full debate state (for audit trail) */
  debateState: DebateState
  /** Whether the decision was auto-executed or held */
  action: 'EXECUTED' | 'REJECTED' | 'HELD'
  /** Risk check response from Layer 1 */
  riskCheck?: RiskCheckResponse
  /** Execution report from Layer 1 (if executed) */
  execution?: ExecutionReport
  /** Error if something went wrong */
  error?: string
  /** Duration of the entire pipeline (ms) */
  durationMs: number
}

// ── Trading Workforce ──

export class TradingWorkforce extends EventEmitter {
  private config: TradingSystemConfig
  private agents!: Record<AgentTradingRole, TradingAgent>
  private executionAgent!: ExecutionOptimizerAgent
  private graph: ReturnType<typeof buildDebateGraph>
  private layer1Client: Layer1IntegrationClient
  private initialized = false

  /** Optional Layer 5 meta-learning pipeline for continuous performance tracking */
  private metaPipeline: MetaLearningPipeline | null = null

  /** Optional Layer 3 knowledge pipeline for RAG + alt data enrichment */
  private knowledgePipeline: KnowledgePipeline | null = null

  constructor(config?: Partial<TradingSystemConfig>, metaPipeline?: MetaLearningPipeline) {
    super()

    this.config = { ...DEFAULT_TRADING_CONFIG, ...config }

    // Build agent configs
    const agentConfigs = buildAgentConfigs(this.config)

    // Instantiate all agents
    this.agents = {
      macro_strategist: new MacroStrategistAgent(agentConfigs.macro_strategist),
      sector_analyst: new SectorAnalystAgent(agentConfigs.sector_analyst),
      sentiment_agent: new SentimentAgent(agentConfigs.sentiment_agent),
      technical_analyst: new TechnicalAnalystAgent(agentConfigs.technical_analyst),
      risk_manager: new RiskManagerAgent(agentConfigs.risk_manager),
      execution_optimizer: new ExecutionOptimizerAgent(agentConfigs.execution_optimizer),
    }

    this.executionAgent = this.agents.execution_optimizer as ExecutionOptimizerAgent

    // Build debate graph
    const graphConfig: DebateGraphConfig = {
      maxRounds: this.config.debate.maxRounds,
      consensusThreshold: this.config.debate.consensusThreshold,
      agents: {
        macro: this.agents.macro_strategist,
        sector: this.agents.sector_analyst,
        sentiment: this.agents.sentiment_agent,
        technical: this.agents.technical_analyst,
        risk: this.agents.risk_manager,
        execution: this.executionAgent,
      },
      historicalWeights: buildHistoricalWeights(this.config),
    }

    this.graph = buildDebateGraph(graphConfig)

    // Initialize Layer 1 client
    this.layer1Client = createLayer1Client(this.config.layer1)

    // Attach optional meta-learning pipeline
    if (metaPipeline) {
      this.attachMetaPipeline(metaPipeline)
    }
  }

  // ── Initialization ──

  /**
   * Attach a Layer 5 MetaLearningPipeline for continuous performance
   * tracking, model routing, and strategy evolution.
   */
  attachMetaPipeline(pipeline: MetaLearningPipeline): void {
    this.metaPipeline = pipeline
    console.log('[TradingWorkforce] Meta-learning pipeline attached')
  }

  /**
   * Attach a Layer 3 KnowledgePipeline for enriching market data with
   * RAG context, alt data, and knowledge graph insights before each debate.
   */
  attachKnowledgePipeline(pipeline: KnowledgePipeline): void {
    this.knowledgePipeline = pipeline
    console.log('[TradingWorkforce] Knowledge pipeline attached')
  }

  /**
   * Initialize the workforce: connect to Layer 1 and warm up LLM connections.
   */
  async initialize(): Promise<void> {
    if (this.initialized) return

    await this.layer1Client.connect()

    // Forward Layer 1 events
    this.layer1Client.on('orderExecuted', (data) => this.emit('orderExecuted', data))
    this.layer1Client.on('orderRejected', (data) => this.emit('orderRejected', data))
    this.layer1Client.on('orderAdjusted', (data) => this.emit('orderAdjusted', data))
    this.layer1Client.on('humanReviewRequired', (data) => this.emit('humanReviewRequired', data))

    this.initialized = true
    this.emit('initialized', {
      agentCount: Object.values(this.agents).filter(a => a.isEnabled()).length,
      simulationMode: this.layer1Client.isSimulationMode(),
      debateConfig: this.config.debate,
    })
  }

  // ── Main Entry Point: Analyze + Optionally Execute ──

  /**
   * Run the full analysis pipeline:
   * 1. Multi-agent debate → consensus decision
   * 2. If decision is actionable (BUY/SELL), generate order intent
   * 3. Submit to Layer 1 for risk check + execution
   *
   * @param marketData - The market data snapshot to analyze
   * @param portfolio - Current portfolio state (optional, required for auto-execution)
   * @param autoExecute - If true, submit actionable decisions to Layer 1 automatically
   */
  async analyze(
    marketData: MarketDataInput,
    portfolio?: PortfolioState,
    autoExecute = false
  ): Promise<AnalysisResult> {
    const startTime = Date.now()

    if (!this.initialized) {
      await this.initialize()
    }

    // Step 1: Run the debate graph (with timeout from config)
    const initialState: DebateState = {
      marketData,
      symbol: marketData.symbol,
      currentRound: 0,
      maxRounds: this.config.debate.maxRounds,
      agentAnalyses: [],
      consensusReached: false,
      vetoTriggered: false,
      finalDecision: null,
      historicalWeights: buildHistoricalWeights(this.config),
      consensusThreshold: this.config.debate.consensusThreshold,
      sessionId: `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    }

    this.emit('debateStarted', { symbol: marketData.symbol, sessionId: initialState.sessionId })

    // ── Layer 3: Enrich market data with RAG context + alt data ──
    if (this.knowledgePipeline) {
      try {
        const enrichment = await this.knowledgePipeline.getEnrichedMarketContext(marketData.symbol)
        // Merge enrichment into market data so agents can access it
        // Single spread avoids intermediate garbage objects
        marketData = {
          ...marketData,
          // Empty RAG context has no signal value for agents — strip to undefined
          ragContext: enrichment.ragContext || undefined,
          altDataSnapshot: enrichment.altSnapshot ?? undefined,
          // Surface top-level signals from alt data for agent convenience
          newsSentiment: marketData.newsSentiment ?? enrichment.altSnapshot?.news.avgSentiment,
          socialSentiment: marketData.socialSentiment ?? enrichment.altSnapshot?.compositeSentiment,
          knowledgeGraphStats: enrichment.graphStats,
          enriched: true,
        }
        // Update the debate initial state with enriched market data
        initialState.marketData = marketData
      } catch (err) {
        console.warn(
          `[TradingWorkforce] Knowledge enrichment failed for ${marketData.symbol}:`,
          err instanceof Error ? err.message : String(err)
        )
        // Continue with unenriched data — enrichment is best-effort
      }
    }

    // Apply debate timeout if configured
    const debateTimeout = this.config.debate.timeoutMs > 0 ? this.config.debate.timeoutMs : undefined

    let debateState: DebateState
    try {
      const debatePromise = this.graph.invoke(initialState)
      debateState = debateTimeout
        ? await Promise.race([
            debatePromise,
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error(`Debate timed out after ${debateTimeout}ms`)), debateTimeout)
            ),
          ])
        : await debatePromise

      if (debateState.error) {
        return {
          decision: debateState.finalDecision || createErrorDecision(debateState.error),
          debateState,
          action: 'REJECTED',
          error: debateState.error,
          durationMs: Date.now() - startTime,
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err)
      return {
        decision: createErrorDecision(errorMsg),
        debateState: { ...initialState, error: errorMsg, finalDecision: null },
        action: 'REJECTED',
        error: errorMsg,
        durationMs: Date.now() - startTime,
      }
    }

    const decision = debateState.finalDecision!
    this.emit('debateComplete', { decision, rounds: decision.roundsRequired })

    // ── Layer 5: Record debate outcome for meta-learning ──
    // Called AFTER error checking (finalDecision is guaranteed non-null)
    if (this.metaPipeline) {
      this.recordDebateForMetaLearning(debateState)
    }

    // Step 2: If HOLD or VETO, return immediately
    if (decision.action === 'HOLD' || decision.vetoApplied) {
      return {
        decision,
        debateState,
        action: decision.vetoApplied ? 'REJECTED' : 'HELD',
        durationMs: Date.now() - startTime,
      }
    }

    // Step 3: If not auto-executing or no portfolio provided, return decision only
    if (!autoExecute || !portfolio) {
      return {
        decision,
        debateState,
        action: 'HELD',
        durationMs: Date.now() - startTime,
      }
    }

    // Step 4: Generate order intent from Execution Optimizer
    const orderIntent = await this.executionAgent.generateOrderIntent({
      symbol: marketData.symbol,
      action: decision.action,
      targetPrice: decision.targetPrice,
      stopLoss: decision.stopLoss,
      positionSizePct: decision.positionSizePct,
      marketData,
    })

    if (!orderIntent) {
      return {
        decision,
        debateState,
        action: 'HELD',
        error: 'Execution Optimizer could not generate order intent',
        durationMs: Date.now() - startTime,
      }
    }

    // Step 5: Submit to Layer 1
    const result = await this.layer1Client.executeDecision({
      decision,
      orderIntent,
      portfolioEquity: portfolio.equity,
      dailyPnl: portfolio.dailyPnl,
      currentDrawdownPct: portfolio.currentDrawdownPct,
      positions: portfolio.positions.filter(p => p.symbol === marketData.symbol),
    })

    // ── Layer 5: Record trade outcome for meta-learning ──
    if (this.metaPipeline && result.action === 'EXECUTED' && result.execution) {
      this.recordTradeForMetaLearning(debateState.sessionId, marketData.symbol, result.execution)
    }

    return {
      decision,
      debateState,
      action: result.action,
      riskCheck: result.riskCheck,
      execution: result.execution,
      error: result.error,
      durationMs: Date.now() - startTime,
    }
  }

  /**
   * Analyze only (no execution) — returns the consensus decision.
   */
  async analyzeOnly(marketData: MarketDataInput): Promise<{ decision: FinalDecision; debateState: DebateState }> {
    const result = await this.analyze(marketData, undefined, false)
    return { decision: result.decision, debateState: result.debateState }
  }

  /**
   * Analyze and auto-execute — full pipeline.
   */
  async analyzeAndExecute(
    marketData: MarketDataInput,
    portfolio: PortfolioState
  ): Promise<AnalysisResult> {
    return this.analyze(marketData, portfolio, true)
  }

  // ── Accessors ──

  getAgent(role: AgentTradingRole): TradingAgent | undefined {
    return this.agents[role]
  }

  getLayer1Client(): Layer1IntegrationClient {
    return this.layer1Client
  }

  getConfig(): Readonly<TradingSystemConfig> {
    return { ...this.config }
  }

  isInitialized(): boolean {
    return this.initialized
  }

  getMetaPipeline(): MetaLearningPipeline | null {
    return this.metaPipeline
  }

  getKnowledgePipeline(): KnowledgePipeline | null {
    return this.knowledgePipeline
  }

  // ── Private: Layer 5 Meta-Learning Integration ──

  /**
   * Build a DebateRecord from the completed debate state and feed it
   * to the meta-learning pipeline for performance tracking.
   */
  private recordDebateForMetaLearning(debateState: DebateState): void {
    const pipeline = this.metaPipeline!

    // Build agent provider/model maps from agent configs
    const agentProviders = {} as Record<AgentTradingRole, 'openai' | 'anthropic'>
    const agentModels = {} as Record<AgentTradingRole, string>
    const promptVersions = {} as Record<AgentTradingRole, string>

    for (const [role, agent] of Object.entries(this.agents)) {
      const cfg = agent.getTradingConfig?.()
      agentProviders[role as AgentTradingRole] = cfg?.llmProvider ?? 'openai'
      agentModels[role as AgentTradingRole] = cfg?.llmModel ?? 'unknown'
      promptVersions[role as AgentTradingRole] = cfg?.id ?? 'v1'
    }

    const debateRecord: DebateRecord = {
      sessionId: debateState.sessionId,
      symbol: debateState.symbol,
      timestamp: new Date().toISOString(),
      marketSnapshot: debateState.marketData,
      decision: debateState.finalDecision!,
      agentAnalyses: debateState.agentAnalyses,
      roundsRequired: debateState.currentRound + 1,
      vetoApplied: debateState.vetoTriggered,
      agentProviders,
      agentModels,
      promptVersions,
    }

    // 1. Record the debate first (required before onAgentAnalysis can look it up)
    pipeline.onDebateComplete(debateRecord)

    // 2. Feed each agent's analysis into the bandit for model routing
    for (const analysis of debateState.agentAnalyses) {
      const provider = analysis.llmProvider ?? agentProviders[analysis.role] ?? 'openai'
      const model = analysis.llmModel ?? agentModels[analysis.role] ?? 'unknown'
      const latencyMs = analysis.latencyMs ?? 0
      const tokensUsed = analysis.tokensUsed ?? 0

      pipeline.onAgentAnalysis(
        debateState.sessionId,
        analysis.role,
        analysis,
        provider,
        model,
        latencyMs,
        tokensUsed
      )
    }
  }

  /**
   * Build a TradeOutcomeRecord from the Layer 1 execution report and
   * feed it to the meta-learning pipeline for P&L tracking.
   */
  private recordTradeForMetaLearning(
    sessionId: string,
    symbol: string,
    execution: ExecutionReport
  ): void {
    const pipeline = this.metaPipeline!
    const isBuy = execution.side === 'BUY'

    const outcome: TradeOutcomeRecord = {
      debateSessionId: sessionId,
      symbol,
      entryPrice: execution.avgFillPrice,
      direction: isBuy ? 'LONG' : 'SHORT',
      outcome: 'PENDING', // Updated when trade closes
      pnl: 0, // Will be updated on close
      pnlPct: 0,
      entryTimestamp: execution.timestamp,
      maxAdversePct: 0,
      maxFavorablePct: 0,
    }

    pipeline.onTradeExecuted(outcome)
  }

  // ── Cleanup ──

  async shutdown(): Promise<void> {
    await this.layer1Client.disconnect()
    for (const agent of Object.values(this.agents)) {
      agent.destroy()
    }
    this.initialized = false
    this.emit('shutdown')
  }
}

// ── Convenience Factory ──

export function buildTradingWorkforce(
  config?: Partial<TradingSystemConfig>,
  metaPipeline?: MetaLearningPipeline
): TradingWorkforce {
  return new TradingWorkforce(config, metaPipeline)
}

// ── Helpers ──

function createErrorDecision(error: string): FinalDecision {
  return {
    action: 'HOLD',
    overallConfidence: 0,
    reasoningSummary: `Error during debate: ${error}`,
    vetoApplied: false,
    roundsRequired: 0,
    allAnalyses: [],
    votingBreakdown: [],
    timestamp: new Date().toISOString(),
    requiresHumanReview: true,
  }
}
