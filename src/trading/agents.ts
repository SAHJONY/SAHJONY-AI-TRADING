/**
 * Layer 4 — Trading Agent Base
 *
 * Shared base class for all trading agents. Extends the existing BaseAgent
 * with LLM-powered analysis, structured output, and debate capabilities.
 */

import { BaseAgent } from '../agents/base-agent'
import { Task, TaskResult, AgentConfig } from '../types'
import { BaseChatModel } from '@langchain/core/language_models/chat_models'
import { z } from 'zod'
import { MarketDataInput, AgentAnalysis, AgentTradingRole, TradingAgentConfig } from './types'
import { ROLE_DEFINITIONS, buildAgentSystemPrompt, buildAgentUserPrompt } from './prompts'
import { createLLM, invokeStructured } from './llm-provider'

// ── Zod Schema for Agent Analysis Output ──

const AgentAnalysisOutputSchema = z.object({
  recommendation: z.enum(['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']),
  confidence: z.number().min(0).max(1),
  reasoning: z.string().min(20),
  evidenceRefs: z.array(z.string()).default([]),
  keyMetrics: z.record(z.string(), z.number()).default({}),
  rebuttals: z.array(z.string()).optional(),
})

// ── Trading Agent Base ──

export abstract class TradingAgent extends BaseAgent {
  protected tradingConfig: TradingAgentConfig
  protected llm: BaseChatModel
  protected agentRole: AgentTradingRole

  constructor(tradingConfig: TradingAgentConfig) {
    const agentConfig: AgentConfig = {
      id: tradingConfig.id,
      name: tradingConfig.name,
      role: tradingConfig.role as any,
      capabilities: [
        {
          name: tradingConfig.role,
          description: ROLE_DEFINITIONS[tradingConfig.role]?.expertise || '',
          tools: ['market_analysis', 'debate_rebuttal'],
          maxConcurrentTasks: 1,
        },
      ],
    }

    super(agentConfig)

    this.tradingConfig = tradingConfig
    this.agentRole = tradingConfig.role

    this.llm = createLLM({
      provider: tradingConfig.llmProvider,
      model: tradingConfig.llmModel,
      temperature: tradingConfig.temperature,
      maxTokens: tradingConfig.maxTokens,
    })

    // Register analysis tool (with runtime validation for type safety)
    this.registerTool({
      name: 'analyze_market',
      description: `Analyze market data as a ${ROLE_DEFINITIONS[this.agentRole]?.title}`,
      execute: (params: unknown) => {
        if (!params || typeof params !== 'object' || !('marketData' in params)) {
          return Promise.resolve({ success: false, error: 'Invalid analysis params: marketData required', duration: 0 })
        }
        return this.executeAnalysis(params as AnalysisParams)
      },
    })
  }

  getCapabilities(): string[] {
    return [
      'market_analysis',
      'trading_recommendation',
      'debate_participation',
      'counter_argument',
    ]
  }

  /**
   * Main entry point: execute a debate analysis task.
   */
  async executeTask(task: Task): Promise<TaskResult> {
    const variables = task.context?.variables || {}
    const marketData = variables.marketData as MarketDataInput
    const round = (variables.round as number) || 0
    const previousAnalyses = variables.previousAnalyses as AgentAnalysis[] | undefined
    const supervisorInstruction = variables.supervisorInstruction as string | undefined

    if (!marketData) {
      return { success: false, error: 'No market data provided' }
    }

    try {
      const analysis = await this.produceAnalysis(marketData, round, previousAnalyses, supervisorInstruction)

      return {
        success: true,
        output: analysis,
        metrics: { duration: 0 },
      }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  /**
   * Produce a trading analysis using the LLM.
   */
  async produceAnalysis(
    marketData: MarketDataInput,
    round: number,
    previousAnalyses?: AgentAnalysis[],
    supervisorInstruction?: string
  ): Promise<AgentAnalysis> {
    const systemPrompt = this.buildSystemPrompt(marketData, previousAnalyses)
    const userPrompt = buildAgentUserPrompt(round, supervisorInstruction)

    const { parsed, response } = await invokeStructured({
      llm: this.llm,
      systemPrompt,
      userPrompt,
      schema: AgentAnalysisOutputSchema,
      modelName: this.tradingConfig.llmModel,
    })

    const analysis: AgentAnalysis = {
      role: this.agentRole,
      round,
      recommendation: parsed.recommendation,
      confidence: parsed.confidence,
      reasoning: parsed.reasoning,
      evidenceRefs: parsed.evidenceRefs,
      keyMetrics: parsed.keyMetrics,
      rebuttals: parsed.rebuttals,
      timestamp: new Date().toISOString(),
      // Runtime metadata for Layer 5 meta-learning (model routing + performance tracking)
      llmProvider: this.tradingConfig.llmProvider,
      llmModel: this.tradingConfig.llmModel,
      latencyMs: response.latencyMs,
      tokensUsed: response.tokensUsed,
    }

    this.emit('analysisProduced', { agentId: this.id, analysis })
    return analysis
  }

  /**
   * Override in subclasses for role-specific system prompt customization.
   */
  protected buildSystemPrompt(
    marketData: MarketDataInput,
    previousAnalyses?: AgentAnalysis[]
  ): string {
    let prompt = buildAgentSystemPrompt(this.agentRole, marketData, previousAnalyses)

    if (this.tradingConfig.systemPromptOverride) {
      prompt += `\n\n## Additional Instructions\n${this.tradingConfig.systemPromptOverride}`
    }

    return prompt
  }

  /**
   * Execute tool-based analysis (used via tool registration).
   */
  private async executeAnalysis(params: AnalysisParams): Promise<{
    success: boolean
    output?: AgentAnalysis
    error?: string
    duration: number
  }> {
    const startTime = Date.now()
    try {
      const analysis = await this.produceAnalysis(
        params.marketData,
        params.round || 0,
        params.previousAnalyses
      )
      return { success: true, output: analysis, duration: Date.now() - startTime }
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        duration: Date.now() - startTime,
      }
    }
  }

  getRole(): AgentTradingRole {
    return this.agentRole
  }

  isEnabled(): boolean {
    return this.tradingConfig.enabled
  }

  getPerformanceWeight(): number {
    return this.tradingConfig.performanceWeight
  }

  /** Expose trading config for Layer 5 meta-learning integration */
  getTradingConfig(): TradingAgentConfig {
    return { ...this.tradingConfig }
  }
}

interface AnalysisParams {
  marketData: MarketDataInput
  round: number
  previousAnalyses?: AgentAnalysis[]
  instruction?: string
}

// ── Concrete Trading Agent Implementations ──

export class MacroStrategistAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'macro_strategist' })
  }
}

export class SectorAnalystAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'sector_analyst' })
  }
}

export class SentimentAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'sentiment_agent' })
  }
}

export class TechnicalAnalystAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'technical_analyst' })
  }
}

export class RiskManagerAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'risk_manager' })

    // TODO: Wire these tools to the Layer 1 risk engine (Rust) for real VaR/Kelly calculations.
    // Currently returns placeholder values — the LLM-based risk analysis is the primary mechanism.
    // When Layer 1 is connected, these will call the risk engine via Layer1IntegrationClient.
    this.registerTool({
      name: 'calculate_var',
      description: 'Calculate Value at Risk for the proposed position (placeholder — TODO: wire to Layer 1)',
      execute: async () => ({
        success: true,
        output: { var95: 0, var99: 0 },
        duration: 0,
      }),
    })

    this.registerTool({
      name: 'calculate_kelly',
      description: 'Calculate optimal position size using Kelly criterion (placeholder — TODO: wire to Layer 1)',
      execute: async () => ({
        success: true,
        output: { kellyFraction: 0, adjustedFraction: 0 },
        duration: 0,
      }),
    })
  }
}

export class ExecutionOptimizerAgent extends TradingAgent {
  constructor(tradingConfig: TradingAgentConfig) {
    super({ ...tradingConfig, role: 'execution_optimizer' })
  }

  /**
   * Generate an order intent from the consensus decision.
   */
  async generateOrderIntent(params: {
    symbol: string
    action: 'BUY' | 'SELL' | 'HOLD'
    targetPrice?: number
    stopLoss?: number
    positionSizePct?: number
    marketData: MarketDataInput
  }): Promise<{
    symbol: string
    side: 'BUY' | 'SELL' | 'SELL_SHORT'
    orderType: 'MARKET' | 'LIMIT' | 'STOP' | 'STOP_LIMIT'
    quantity: number
    price?: number
    stopPrice?: number
    timeInForce: 'DAY' | 'GTC' | 'IOC' | 'FOK'
    strategyId: string
  } | null> {
    if (params.action === 'HOLD') return null

    const price = params.targetPrice || params.marketData.currentPrice
    const spread = params.marketData.bidAskSpread || 0.01
    const volume = params.marketData.volume || 100000

    // Determine optimal order type based on spread and urgency
    const useLimit = spread > price * 0.001 // Use limit if spread > 10bps
    const orderType = useLimit ? 'LIMIT' : 'MARKET'

    // Calculate quantity based on position size (default 1% of daily volume)
    const positionPct = params.positionSizePct || 0.01
    const quantity = Math.floor(volume * positionPct / price)

    // Use limit price slightly inside the spread for better execution
    const limitPrice = params.action === 'BUY'
      ? price + spread * 0.3 // Buy at 30% into spread
      : price - spread * 0.3  // Sell at 30% into spread

    return {
      symbol: params.symbol,
      side: params.action === 'BUY' ? 'BUY' : 'SELL',
      orderType: orderType as 'MARKET' | 'LIMIT',
      quantity: Math.max(1, quantity),
      price: useLimit ? Math.round(limitPrice * 100) / 100 : undefined,
      stopPrice: params.stopLoss ? Math.round(params.stopLoss * 100) / 100 : undefined,
      timeInForce: 'DAY' as const,
      strategyId: `trading-workforce-${params.symbol.toLowerCase()}`,
    }
  }
}
