// Trading LLM Provider — real LLM-powered trading agent analysis
// Wraps OpenAI/Anthropic providers with structured JSON output, circuit breaker, parallel execution
import type {
  AgentTradingRole, AgentAnalysis, TradingRecommendation,
  MarketDebateContext,
} from '@/types/trading'
import { AGENT_ROLES } from '@/types/trading'
import { OpenAIProvider } from '@/lib/agent/providers/openai-provider'
import { AnthropicProvider } from '@/lib/agent/providers/anthropic-provider'
import { hermesBridge } from '@/lib/agent/hermes-bridge'
import type { Message } from '@/lib/agent/types'

// ---- Circuit Breaker ---- 

interface CircuitBreakerState {
  failureCount: number
  lastFailureTime: number
  state: 'closed' | 'open' | 'half-open'
  consecutiveSuccesses: number
}

interface CircuitBreakerConfig {
  failureThreshold: number       // failures before opening
  resetTimeoutMs: number         // how long to stay open before half-open
  halfOpenMaxRequests: number    // max requests in half-open state
  failureWindowMs: number        // window for counting failures
}

const DEFAULT_CB_CONFIG: CircuitBreakerConfig = {
  failureThreshold: 3,
  resetTimeoutMs: 60_000,        // 1 minute
  halfOpenMaxRequests: 2,
  failureWindowMs: 300_000,      // 5 minutes
}

class CircuitBreaker {
  private state: CircuitBreakerState = {
    failureCount: 0,
    lastFailureTime: 0,
    state: 'closed',
    consecutiveSuccesses: 0,
  }
  private config: CircuitBreakerConfig
  private name: string

  constructor(name: string, config?: Partial<CircuitBreakerConfig>) {
    this.name = name
    this.config = { ...DEFAULT_CB_CONFIG, ...config }
  }

  get isOpen(): boolean {
    if (this.state.state === 'open') {
      const elapsed = Date.now() - this.state.lastFailureTime
      if (elapsed >= this.config.resetTimeoutMs) {
        this.state.state = 'half-open'
        this.state.consecutiveSuccesses = 0
        console.log(`[CircuitBreaker:${this.name}] Half-open — testing recovery`)
        return false
      }
      return true
    }
    return false
  }

  recordSuccess(): void {
    if (this.state.state === 'half-open') {
      this.state.consecutiveSuccesses++
      if (this.state.consecutiveSuccesses >= this.config.halfOpenMaxRequests) {
        this.state.state = 'closed'
        this.state.failureCount = 0
        console.log(`[CircuitBreaker:${this.name}] Closed — recovered`)
      }
    }
    // Reset failure window in closed state
    if (this.state.state === 'closed' && this.state.failureCount > 0) {
      const elapsed = Date.now() - this.state.lastFailureTime
      if (elapsed > this.config.failureWindowMs) {
        this.state.failureCount = 0
      }
    }
  }

  recordFailure(): void {
    const now = Date.now()
    // Reset failure count if last failure is outside the window
    if (this.state.lastFailureTime > 0 && (now - this.state.lastFailureTime) > this.config.failureWindowMs) {
      this.state.failureCount = 0
    }
    this.state.failureCount++
    this.state.lastFailureTime = now
    if (this.state.failureCount >= this.config.failureThreshold) {
      this.state.state = 'open'
      console.warn(`[CircuitBreaker:${this.name}] OPEN — ${this.state.failureCount} failures, blocking LLM calls`)
    }
  }

  getStatus(): { state: string; failureCount: number } {
    return { state: this.state.state, failureCount: this.state.failureCount }
  }
}

// ---- Agent System Prompts ----

function buildAgentSystemPrompt(role: AgentTradingRole, roleConfig: typeof AGENT_ROLES[AgentTradingRole]): string {
  const basePrompt = `You are the ${roleConfig.label}, a specialized AI trading agent inside a multi-agent debate workforce.

**Your Expertise:** ${roleConfig.expertise}

**Your Analytical Framework:** ${roleConfig.framework}

**Your Role in the Debate:**
You are one of 6 specialized agents debating whether to BUY, SELL, or HOLD a specific asset. Your analysis will be weighted by your expertise and combined with other agents to reach a consensus.

**Instructions:**
1. Analyze the provided market data, news sentiment, and context thoroughly
2. Form a clear recommendation: STRONG_BUY, BUY, HOLD, SELL, or STRONG_SELL
3. Provide detailed reasoning that references specific data points
4. Assign a confidence score (0.0 to 1.0) reflecting your certainty
5. Include relevant key metrics that support your analysis
6. Flag any risks you identify

**Output Format:**
You MUST respond with a valid JSON object matching this structure (use real data, not placeholders):
{
  "recommendation": "BUY",
  "confidence": 0.75,
  "reasoning": "Your detailed analysis with specific data references...",
  "keyMetrics": { "gdpGrowth": "2.1%", "inflation": "3.2%", "fedStance": "hawkish" },
  "riskFlags": ["Inflation concerns", "Geopolitical tension"]
}

Do NOT include any text outside the JSON object. Do NOT wrap in markdown code blocks.`

  // Role-specific additions
  const roleAdditions: Record<AgentTradingRole, string> = {
    macro_strategist: `
**MACRO STRATEGIST FOCUS:**
- Assess the global macroeconomic environment: GDP growth, inflation, interest rates, central bank policy
- Consider geopolitical risks, capital flows, and currency dynamics
- Evaluate whether the macro regime is risk-on or risk-off
- Key metrics to include: GDP growth rate, inflation rate, monetary policy stance, global risk appetite`,
    sector_analyst: `
**SECTOR ANALYST FOCUS:**
- Analyze the asset's sector/industry position within the business cycle
- Assess competitive dynamics, moat strength, and regulatory environment
- Compare earnings growth and valuations vs sector peers
- Key metrics to include: sector growth rate, competitive position, earnings growth, regulatory risk`,
    sentiment_agent: `
**SENTIMENT AGENT FOCUS:**
- Analyze aggregated news sentiment, social media trends, and market psychology
- Evaluate the credibility and weight of different sentiment sources
- Detect sentiment extremes that might signal reversals
- Key metrics to include: sentiment score, article volume, social buzz, insider activity signals`,
    technical_analyst: `
**TECHNICAL ANALYST FOCUS:**
- Analyze price action, trend structure, support/resistance levels
- Evaluate momentum oscillators, volume patterns, and chart formations
- Consider multiple timeframes for confirmation
- Key metrics to include: RSI, trend direction, support/resistance levels, volume profile, chart patterns`,
    risk_manager: `
**RISK MANAGER FOCUS:**
- Your PRIMARY responsibility is capital preservation
- Evaluate position sizing, Value at Risk (VaR), drawdown scenarios
- You have VETO power: recommend STRONG_SELL with high confidence (>0.8) to block trades
- Be conservative — err on the side of caution
- Key metrics to include: VaR(95%), max drawdown risk, Kelly fraction, recommended position size`,
    execution_optimizer: `
**EXECUTION OPTIMIZER FOCUS:**
- You do NOT decide whether to trade — you advise HOW to execute
- CRITICAL: Your recommendation MUST be HOLD. Your analysis is about execution quality, not market direction.
- Assess liquidity, bid-ask spread, market depth, and execution costs
- Recommend execution strategy: VWAP, TWAP, limit orders, etc.
- Key metrics to include: bid-ask spread, liquidity assessment, recommended execution algo, estimated slippage`,
  }

  return basePrompt + '\n' + (roleAdditions[role] || '')
}

function buildUserMessage(
  role: AgentTradingRole,
  context: MarketDebateContext,
  supervisorInstruction: string,
  previousRoundAnalyses?: AgentAnalysis[],
): string {
  const quote = context.quote
  const price = quote?.price ? `$${quote.price.toFixed(2)}` : 'N/A'

  let message = `## Market Context for Analysis

**Symbol:** ${context.symbol} (${context.assetType})
**Current Price:** ${price}
**24h Change:** ${quote ? `${quote.changePct24h.toFixed(2)}%` : 'N/A'}

### Knowledge Context
${context.knowledgeContext}

### News Sentiment
${context.newsSentiment.overallSentiment.toUpperCase()} (Score: ${(context.newsSentiment.score * 100).toFixed(0)}%)
Articles analyzed: ${context.newsSentiment.articleCount}
Key themes: ${context.newsSentiment.keyThemes.join(', ')}
Recent: ${context.newsSentiment.recentHeadlines.slice(0, 3).join(' | ')}

### Technical Summary
${context.technicalSummary}

### Fundamental Summary
${context.fundamentalSummary}
`

  // Add price data if available
  if (context.bars && context.bars.length > 0) {
    const recentBars = context.bars.slice(-5)
    const prices = recentBars.map(b => `${new Date(b.timestamp).toLocaleDateString()}: O:${b.open} H:${b.high} L:${b.low} C:${b.close} V:${b.volume}`)
    message += `\n### Recent Price Data (Last 5 bars)\n${prices.join('\n')}\n`
  }

  // Supervisor instruction
  message += `\n## Supervisor Instruction\n${supervisorInstruction}\n`

  // Previous round analyses for debate evolution
  if (previousRoundAnalyses && previousRoundAnalyses.length > 0) {
    message += `\n## Previous Round Analyses (for reference)\n`
    for (const a of previousRoundAnalyses) {
      message += `- ${AGENT_ROLES[a.role].label}: ${a.recommendation} (confidence: ${(a.confidence * 100).toFixed(0)}%)\n`
    }
    message += `\nConsider these perspectives in your analysis. Address disagreements if present.\n`
  }

  message += `\nProvide your analysis as a JSON object with fields: recommendation, confidence, reasoning, keyMetrics, riskFlags.`

  return message
}

// ---- JSON Parser ----

function parseAgentAnalysisJson(jsonStr: string, role: AgentTradingRole): AgentAnalysis | null {
  // Try direct parse
  try {
    const parsed = JSON.parse(jsonStr.trim())
    return validateAndBuild(parsed, role)
  } catch {
    // Try extracting JSON from text (handles occasional markdown wrapping)
    const jsonMatch = jsonStr.match(/\{[\s\S]*"recommendation"[\s\S]*\}/)
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0])
        return validateAndBuild(parsed, role)
      } catch {
        return null
      }
    }
    return null
  }
}

function validateAndBuild(parsed: Record<string, unknown>, role: AgentTradingRole): AgentAnalysis | null {
  const validRecommendations: TradingRecommendation[] = ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']
  const recommendation = parsed.recommendation as string
  if (!validRecommendations.includes(recommendation as TradingRecommendation)) return null
  const confidence = typeof parsed.confidence === 'number' ? parsed.confidence : parseFloat(String(parsed.confidence))
    if (isNaN(confidence) || confidence < 0 || confidence > 1) return null

    // Execution optimizer MUST recommend HOLD
    const finalRecommendation = role === 'execution_optimizer' ? 'HOLD' : (recommendation as TradingRecommendation)

    return {
      role,
      recommendation: finalRecommendation as TradingRecommendation,
      confidence: role === 'execution_optimizer' ? Math.round(Math.min(confidence, 0.5) * 100) / 100 : Math.round(confidence * 100) / 100,
    reasoning: String(parsed.reasoning || 'No reasoning provided'),
    keyMetrics: (typeof parsed.keyMetrics === 'object' && parsed.keyMetrics !== null)
      ? parsed.keyMetrics as Record<string, number | string>
      : {},
    riskFlags: Array.isArray(parsed.riskFlags)
      ? parsed.riskFlags.map(String)
      : [],
    latencyMs: 0, // set by caller
    model: 'llm',
  }
}

// ---- Main Trading LLM Provider ----

export type LLMProviderType = 'openai' | 'anthropic' | 'hermes' | 'auto'

export interface TradingLLMConfig {
  provider: LLMProviderType
  model?: string
  timeoutMs?: number
  enableCircuitBreaker?: boolean
  maxRetries?: number
}

const DEFAULT_CONFIG: TradingLLMConfig = {
  provider: 'auto',
  timeoutMs: 30_000,
  enableCircuitBreaker: true,
  maxRetries: 1,
}

export class TradingLLMProvider {
  private config: TradingLLMConfig
  private openaiProvider: OpenAIProvider
  private anthropicProvider: AnthropicProvider
  private circuitBreakers: Map<string, CircuitBreaker> = new Map()
  private isAvailable: boolean | null = null // cached availability check

  constructor(config?: Partial<TradingLLMConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.openaiProvider = new OpenAIProvider()
    this.anthropicProvider = new AnthropicProvider()
  }

  /** Check if ANY LLM provider has valid API keys configured */
  async checkAvailability(): Promise<boolean> {
    if (this.isAvailable !== null) return this.isAvailable

    const openaiKey = process.env.OPENAI_API_KEY
    const anthropicKey = process.env.ANTHROPIC_API_KEY
    const hermesAvailable = await hermesBridge.healthCheck().catch(() => false)

    this.isAvailable = !!(openaiKey || anthropicKey || hermesAvailable)
    console.log(`[TradingLLM] Availability: ${this.isAvailable} (OpenAI: ${!!openaiKey}, Anthropic: ${!!anthropicKey}, Hermes: ${hermesAvailable})`)
    return this.isAvailable
  }

  /** Run a single agent analysis via LLM */
  async runAgentAnalysis(
    role: AgentTradingRole,
    context: MarketDebateContext,
    supervisorInstruction: string,
    previousRoundAnalyses?: AgentAnalysis[],
  ): Promise<AgentAnalysis> {
    const startTime = Date.now()
    const roleConfig = AGENT_ROLES[role]

    // Check circuit breaker
    if (this.config.enableCircuitBreaker) {
      const cb = this.getCircuitBreaker(role)
      if (cb.isOpen) {
        console.log(`[TradingLLM] Circuit breaker OPEN for ${role}, failing fast`)
        throw new Error(`Circuit breaker open for ${role}`)
      }
    }

    const systemPrompt = buildAgentSystemPrompt(role, roleConfig)
    const userMessage = buildUserMessage(role, context, supervisorInstruction, previousRoundAnalyses)

    // Determine provider
    const provider = this.resolveProvider()

    try {
      const messages: Message[] = [
        { id: 'system', role: 'system', content: systemPrompt, timestamp: Date.now() },
        { id: 'user', role: 'user', content: userMessage, timestamp: Date.now() },
      ]

      const modelConfig = {
        provider: provider === 'anthropic' ? 'anthropic' as const : 'openai' as const,
        model: this.config.model || (provider === 'anthropic' ? 'claude-3-5-sonnet-20241022' : 'gpt-4-turbo'),
        temperature: roleConfig.temperature,
        max_tokens: 1024,
      }

      let rawResponse: string
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), this.config.timeoutMs || 30_000)

      try {
        if (provider === 'anthropic') {
          rawResponse = await this.callWithRetry(
            () => this.anthropicProvider.createCompletion(messages, modelConfig),
            controller.signal,
          )
        } else if (provider === 'hermes') {
          rawResponse = await this.callWithRetry(
            () => hermesBridge.complete({
              model: 'hermes-3',
              messages,
              temperature: roleConfig.temperature,
              max_tokens: 1024,
            }),
            controller.signal,
          )
        } else {
          rawResponse = await this.callWithRetry(
            () => this.openaiProvider.createCompletion(messages, modelConfig),
            controller.signal,
          )
        }
      } finally {
        clearTimeout(timeoutId)
      }

      const latencyMs = Date.now() - startTime

      // Parse JSON from response
      const analysis = parseAgentAnalysisJson(rawResponse, role)
      if (!analysis) {
        throw new Error(`Failed to parse JSON from ${role} response: ${rawResponse.slice(0, 200)}`)
      }

      analysis.latencyMs = latencyMs
      analysis.model = modelConfig.model

      // Record success
      if (this.config.enableCircuitBreaker) {
        this.getCircuitBreaker(role).recordSuccess()
      }

      console.log(`[TradingLLM] ${roleConfig.label}: ${analysis.recommendation} (${(analysis.confidence * 100).toFixed(0)}%, ${latencyMs}ms, ${provider}/${modelConfig.model})`)
      return analysis

    } catch (error) {
      const latencyMs = Date.now() - startTime
      console.error(`[TradingLLM] ${roleConfig.label} failed (${latencyMs}ms):`, error instanceof Error ? error.message : error)

      if (this.config.enableCircuitBreaker) {
        this.getCircuitBreaker(role).recordFailure()
      }

      throw error
    }
  }

  /** Run ALL 6 agents in parallel via LLM */
  async runAllAgents(
    context: MarketDebateContext,
    supervisorInstruction: string,
    previousRoundAnalyses?: AgentAnalysis[],
  ): Promise<AgentAnalysis[]> {
    const roles: AgentTradingRole[] = [
      'macro_strategist', 'sector_analyst', 'sentiment_agent',
      'technical_analyst', 'risk_manager', 'execution_optimizer',
    ]

    console.log(`[TradingLLM] Running all ${roles.length} agents in parallel`)

    const results = await Promise.allSettled(
      roles.map(role =>
        this.runAgentAnalysis(role, context, supervisorInstruction, previousRoundAnalyses)
      )
    )

    const analyses: AgentAnalysis[] = []
    const failures: string[] = []

    for (let i = 0; i < results.length; i++) {
      const result = results[i]
      if (result.status === 'fulfilled') {
        analyses.push(result.value)
      } else {
        failures.push(`${AGENT_ROLES[roles[i]].label}: ${result.reason}`)
        console.warn(`[TradingLLM] ${AGENT_ROLES[roles[i]].label} FAILED: ${result.reason}`)
      }
    }

    if (failures.length > 0) {
      console.warn(`[TradingLLM] ${failures.length}/${roles.length} agents failed: ${failures.join('; ')}`)
    }

    return analyses
  }

  /** Retry wrapper with exponential backoff */
  private async callWithRetry<T>(
    fn: () => Promise<T>,
    signal?: AbortSignal,
    attempt: number = 1,
  ): Promise<T> {
    try {
      if (signal?.aborted) throw new Error('Request aborted')
      return await fn()
    } catch (error) {
      const maxRetries = this.config.maxRetries || 1
      if (attempt < maxRetries && !signal?.aborted) {
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 8000)
        console.log(`[TradingLLM] Retry ${attempt}/${maxRetries} after ${delay}ms`)
        await new Promise(resolve => setTimeout(resolve, delay))
        return this.callWithRetry(fn, signal, attempt + 1)
      }
      throw error
    }
  }

  /** Get circuit breaker status for monitoring */
  getCircuitBreakerStatuses(): Record<string, { state: string; failureCount: number }> {
    const statuses: Record<string, { state: string; failureCount: number }> = {}
    for (const [role, cb] of this.circuitBreakers) {
      statuses[role] = cb.getStatus()
    }
    return statuses
  }

  /** Reset all circuit breakers */
  resetCircuitBreakers(): void {
    this.circuitBreakers.clear()
    this.isAvailable = null
  }

  private getCircuitBreaker(role: string): CircuitBreaker {
    if (!this.circuitBreakers.has(role)) {
      this.circuitBreakers.set(role, new CircuitBreaker(role))
    }
    return this.circuitBreakers.get(role)!
  }

  private resolveProvider(): 'openai' | 'anthropic' | 'hermes' {
    if (this.config.provider !== 'auto') {
      return this.config.provider
    }

    // Auto-detect: prefer Anthropic (better reasoning), then OpenAI, then Hermes
    if (process.env.ANTHROPIC_API_KEY) return 'anthropic'
    if (process.env.OPENAI_API_KEY) return 'openai'
    return 'hermes'
  }
}

// Singleton
export const tradingLLM = new TradingLLMProvider()
