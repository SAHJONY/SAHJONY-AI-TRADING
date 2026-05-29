// Agent Debate System — multi-agent trading debate with consensus and risk management
// Phase 1: Real LLM-powered agent analysis with circuit breaker and mock fallback
// Layer 3 integration: Regime Geometry Detector provides regime context to all agents
import type {
  AgentTradingRole, AgentAnalysis, DebateState, MarketDebateContext,
  FinalDecision, VotingBreakdown, TradingRecommendation, ConsensusAction,
  NewsSentimentSummary, TechnicalSnapshot,
} from '@/types/trading'
import { AGENT_ROLES, DEFAULT_DEBATE_CONFIG } from '@/types/trading'
import { marketDataService } from './market-data'
import { tradingLLM } from './llm-provider'
import { regimeGeometryDetector } from './regime-geometry-detector'
import { knowledgeGraph } from './knowledge-graph'

// ---- Analyst Agents ----

interface AnalystInput {
  role: AgentTradingRole
  context: MarketDebateContext
  supervisorInstruction: string
  previousRoundAnalyses?: AgentAnalysis[]
}

function generateMacroAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input
  const quote = context.quote
  const price = quote?.price || 100

  // Simulate macro environment assessment
  const regimes = ['risk-on', 'risk-off', 'neutral']
  const regime = regimes[Math.floor(Math.random() * regimes.length)]
  const isFavorable = regime === 'risk-on' || (regime === 'neutral' && Math.random() > 0.4)

  // Layer 3: Incorporate regime geometry into macro assessment
  const regimeGeo = context.regimeGeometry
  const regimeAdjustment = regimeGeo
    ? ` | Regime Geometry: ${regimeGeo.regime.toUpperCase()} (${(regimeGeo.regimeConfidence * 100).toFixed(0)}% conf). ${regimeGeo.summary}`
    : ''

  // Regime-based risk adjustment
  let macroFlags: string[] = []
  if (regimeGeo?.regime === 'crisis' || regimeGeo?.regime === 'transitioning') {
    macroFlags.push(`Regime ${regimeGeo.regime} — elevated tail risk`)
  }
  if (regimeGeo?.regimeShiftDetected) {
    macroFlags.push(`Regime shift detected (severity: ${(regimeGeo.shiftSeverity * 100).toFixed(0)}%)`)
  }

  return {
    role: 'macro_strategist',
    recommendation: isFavorable ? 'BUY' : 'HOLD',
    confidence: 0.55 + Math.random() * 0.3,
    reasoning: `Macro regime: ${regime}. ${isFavorable ? 'Favorable conditions with accommodative monetary policy and strong GDP growth supporting risk assets.' : 'Mixed signals with inflation concerns warranting caution.'} Context: ${context.knowledgeContext.slice(0, 100)}${regimeAdjustment}`,
    keyMetrics: {
      regime,
      gdpGrowth: (1.5 + Math.random() * 2.5).toFixed(1) + '%',
      inflation: (2 + Math.random() * 3).toFixed(1) + '%',
      fedStance: isFavorable ? 'dovish' : 'hawkish',
      ...(regimeGeo ? { marketRegime: regimeGeo.regime, geodesicVelocity: parseFloat((regimeGeo.currentVelocity * 1000).toFixed(2)) } : {}),
    },
    riskFlags: [...(isFavorable ? [] : ['Inflation risk', 'Policy uncertainty']), ...macroFlags],
    latencyMs: 100 + Math.floor(Math.random() * 200),
  }
}

function generateSectorAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input
  const sectors = ['Technology', 'Healthcare', 'Finance', 'Energy', 'Consumer']
  const sector = sectors[Math.floor(Math.random() * sectors.length)]
  const competitivePosition = Math.random() > 0.3 ? 'strong' : 'moderate'

  return {
    role: 'sector_analyst',
    recommendation: competitivePosition === 'strong' ? 'BUY' : 'HOLD',
    confidence: 0.5 + Math.random() * 0.35,
    reasoning: `Sector: ${sector}. ${competitivePosition === 'strong' ? 'Strong competitive moat with above-average earnings growth vs peers.' : 'Moderate competitive position with sector headwinds from regulatory changes.'} `,
    keyMetrics: {
      sector,
      competitivePosition,
      earningsGrowth: (5 + Math.random() * 15).toFixed(1) + '%',
      sectorRotation: Math.random() > 0.5 ? 'favorable' : 'neutral',
    },
    riskFlags: competitivePosition === 'moderate' ? ['Regulatory headwinds'] : [],
    latencyMs: 100 + Math.floor(Math.random() * 200),
  }
}

function generateSentimentAnalysis(input: AnalystInput): AgentAnalysis {
  const sentiment = input.context.newsSentiment
  const isPositive = sentiment.overallSentiment === 'positive'
  const isNegative = sentiment.overallSentiment === 'negative'

  // Layer 3: Regime geometry — adjust sentiment interpretation
  const regimeGeo = input.context.regimeGeometry
  const regimeNote = regimeGeo
    ? ` | Market Regime: ${regimeGeo.regime.toUpperCase()} — ${regimeGeo.regime === 'crisis' ? 'Sentiment signals may be unreliable in crisis. ' : regimeGeo.regime === 'volatile' ? 'Elevated noise in sentiment channels. ' : ''}`
    : ''

  // Dampen sentiment confidence in crisis/volatile regimes
  let adjustedScore = sentiment.score
  if (regimeGeo?.regime === 'crisis') adjustedScore = sentiment.score * 0.6 + 0.2 // pull toward neutral
  else if (regimeGeo?.regime === 'volatile') adjustedScore = sentiment.score * 0.8 + 0.1

  const flags: string[] = []
  if (isNegative) flags.push('Negative sentiment cascade')
  if (regimeGeo?.regime === 'crisis') flags.push('Sentiment unreliable — crisis regime')
  if (regimeGeo?.regime === 'volatile') flags.push('Sentiment noise elevated — volatile regime')

  return {
    role: 'sentiment_agent',
    recommendation: isPositive ? 'BUY' : isNegative ? 'SELL' : 'HOLD',
    confidence: adjustedScore,
    reasoning: `Aggregated sentiment: ${sentiment.overallSentiment} (${(adjustedScore * 100).toFixed(0)}%). ${sentiment.articleCount} articles analyzed. Key themes: ${sentiment.keyThemes.join(', ')}. ${isPositive ? 'Bullish momentum building across social and news channels.' : isNegative ? 'Bearish pressure mounting with negative news flow.' : 'Mixed signals with no clear directional bias.'}${regimeNote}`,
    keyMetrics: {
      sentimentScore: adjustedScore,
      articleCount: sentiment.articleCount,
      socialBuzz: isPositive ? 'high' : isNegative ? 'elevated' : 'moderate',
      ...(regimeGeo ? { marketRegime: regimeGeo.regime } : {}),
    },
    riskFlags: flags,
    latencyMs: 80 + Math.floor(Math.random() * 150),
  }
}

function generateTechnicalAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input
  const quote = context.quote
  const price = quote?.price || 100
  const techSummary = context.technicalSummary

  const trends: TradingRecommendation[] = ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']
  const trendWeights = [0.1, 0.3, 0.3, 0.2, 0.1]
  const rand = Math.random()
  let idx = 0
  let cumulative = 0
  for (let i = 0; i < trendWeights.length; i++) {
    cumulative += trendWeights[i]
    if (rand <= cumulative) { idx = i; break }
  }
  const recommendation = trends[idx]

  const rsi = 30 + Math.random() * 40
  const rsiSignal = rsi > 70 ? 'overbought' : rsi < 30 ? 'oversold' : 'neutral'

  // Layer 3: Incorporate regime geometry into technical assessment
  const regimeGeo = context.regimeGeometry
  const regimeNote = regimeGeo
    ? ` | Regime: ${regimeGeo.regime.toUpperCase()} (Fisher det: ${regimeGeo.currentMetric.determinant.toExponential(2)}, velocity: ${(regimeGeo.currentVelocity * 1000).toFixed(2)}e-3)`
    : ''

  // Regime-based technical flags
  const techFlags: string[] = []
  if (regimeGeo?.regime === 'volatile') techFlags.push('Volatile regime — wider stop-loss recommended')
  if (regimeGeo?.regime === 'trending') techFlags.push('Trending regime — trend-following signals preferred')
  if (regimeGeo?.regime === 'crisis') techFlags.push('CRISIS regime — technical patterns may break down')

  return {
    role: 'technical_analyst',
    recommendation,
    confidence: 0.5 + Math.random() * 0.35,
    reasoning: `RSI: ${rsi.toFixed(0)} (${rsiSignal}). ${techSummary || 'Multi-timeframe analysis shows mixed signals with key support at $' + (price * 0.95).toFixed(2) + ' and resistance at $' + (price * 1.05).toFixed(2) + '.'}${regimeNote}`,
    keyMetrics: {
      rsi: rsi.toFixed(0),
      rsiSignal,
      supportLevel: (price * 0.95).toFixed(2),
      resistanceLevel: (price * 1.05).toFixed(2),
      volumeTrend: Math.random() > 0.5 ? 'increasing' : 'decreasing',
      ...(regimeGeo ? { marketRegime: regimeGeo.regime, geodesicVelocity: parseFloat((regimeGeo.currentVelocity * 1000).toFixed(2)) } : {}),
    },
    riskFlags: [...(rsi > 70 ? ['Overbought conditions'] : rsi < 30 ? ['Oversold conditions'] : []), ...techFlags],
    latencyMs: 80 + Math.floor(Math.random() * 150),
  }
}

function generateRiskAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input

  // Layer 3: Regime geometry — adjust risk stance based on market regime
  const regimeGeo = context.regimeGeometry
  
  // Crisis or transitioning regimes: bias toward defensive stance
  let riskBias = 1.0
  if (regimeGeo?.regime === 'crisis') riskBias = 0.3  // heavily defensive
  else if (regimeGeo?.regime === 'transitioning') riskBias = 0.6
  else if (regimeGeo?.regime === 'volatile') riskBias = 0.8
  else if (regimeGeo?.regime === 'trending') riskBias = 1.1  // slightly more risk-tolerant in trending

  // Base risk levels with regime adjustment
  const riskLevels: TradingRecommendation[] = ['HOLD', 'SELL', 'STRONG_SELL', 'BUY', 'STRONG_BUY']
  const riskWeights = [0.35 * riskBias, 0.25 * riskBias, 0.15 / riskBias, 0.15 * riskBias, 0.1 * riskBias]
  const totalWeight = riskWeights.reduce((s, w) => s + w, 0)
  const rand = Math.random() * totalWeight
  let idx = 0
  let cumulative = 0
  for (let i = 0; i < riskWeights.length; i++) {
    cumulative += riskWeights[i]
    if (rand <= cumulative) { idx = i; break }
  }
  const recommendation = riskLevels[idx]

  const var95 = (1 + Math.random() * 5).toFixed(1)
  const isHighRisk = recommendation === 'STRONG_SELL'

  // Regime-based risk flags
  const riskFlags: string[] = []
  if (isHighRisk) riskFlags.push('VaR breach', 'Drawdown limit exceeded', 'Portfolio concentration')
  if (regimeGeo?.regime === 'crisis') riskFlags.push('CRISIS regime — VaR estimates unreliable')
  if (regimeGeo?.regime === 'transitioning') riskFlags.push('Transitioning regime — regime-switching risk elevated')
  if (regimeGeo?.regimeShiftDetected) riskFlags.push(`Regime shift: ${regimeGeo.recentShifts[regimeGeo.recentShifts.length - 1]?.from ?? '?'} → ${regimeGeo.regime}`)

  const regimeNote = regimeGeo
    ? ` | Regime: ${regimeGeo.regime.toUpperCase()} — ${regimeGeo.summary}`
    : ''

  return {
    role: 'risk_manager',
    recommendation,
    confidence: 0.6 + Math.random() * 0.3,
    reasoning: `${isHighRisk ? 'VETO: ' : ''}VaR(95%): ${var95}%. ${isHighRisk ? 'Risk exceeds acceptable thresholds. Position sizing would breach max drawdown limits.' : 'Risk metrics within acceptable bounds. Max position size of 25% of portfolio recommended.'}${regimeNote}`,
    keyMetrics: {
      var95: var95 + '%',
      maxDrawdownRisk: (1 + Math.random() * 8).toFixed(1) + '%',
      kellyFraction: (0.1 + Math.random() * 0.3).toFixed(2),
      recommendedSize: isHighRisk ? '0%' : Math.floor(5 + Math.random() * 20) + '%',
      ...(regimeGeo ? { marketRegime: regimeGeo.regime, regimeConfidence: parseFloat((regimeGeo.regimeConfidence * 100).toFixed(0)) } : {}),
    },
    riskFlags,
    latencyMs: 120 + Math.floor(Math.random() * 200),
  }
}

function generateExecutionAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input
  const quote = context.quote
  const price = quote?.price || 100
  const volume = quote?.volume24h || 1000000
  const spread = price * 0.001

  const liquidity = volume > 10000000 ? 'high' : volume > 1000000 ? 'moderate' : 'low'

  return {
    role: 'execution_optimizer',
    recommendation: 'HOLD',
    confidence: 0.5 + Math.random() * 0.3,
    reasoning: `Market liquidity: ${liquidity}. Bid-ask spread: $${spread.toFixed(2)}. ${liquidity === 'high' ? 'Favorable execution conditions. Recommend VWAP execution over 15-minute window to minimize market impact.' : 'Moderate liquidity suggests using limit orders with 0.5% tolerance.'}`,
    keyMetrics: {
      spread: '$' + spread.toFixed(2),
      liquidity,
      recommendedExecution: liquidity === 'high' ? 'VWAP (15min)' : 'Limit order (0.5% tol)',
      estimatedSlippage: (spread / price * 100).toFixed(3) + '%',
    },
    riskFlags: liquidity === 'low' ? ['Low liquidity', 'Wide spreads'] : [],
    latencyMs: 80 + Math.floor(Math.random() * 100),
  }
}

const ANALYST_GENERATORS: Record<AgentTradingRole, (input: AnalystInput) => AgentAnalysis> = {
  macro_strategist: generateMacroAnalysis,
  sector_analyst: generateSectorAnalysis,
  sentiment_agent: generateSentimentAnalysis,
  technical_analyst: generateTechnicalAnalysis,
  risk_manager: generateRiskAnalysis,
  execution_optimizer: generateExecutionAnalysis,
}

// ---- Supervisor ----

function generateSupervisorInstruction(round: number, previousAnalyses?: AgentAnalysis[]): string {
  if (round === 1) {
    return 'Initial analysis round. Analyze market conditions and provide your independent assessment.'
  }

  if (!previousAnalyses || previousAnalyses.length === 0) {
    return 'Continue analysis. Consider all available market data.'
  }

  // Check for disagreement
  const recommendations = previousAnalyses.map(a => a.recommendation)
  const buys = recommendations.filter(r => r === 'BUY' || r === 'STRONG_BUY').length
  const sells = recommendations.filter(r => r === 'SELL' || r === 'STRONG_SELL').length
  const holds = recommendations.filter(r => r === 'HOLD').length

  if (buys > sells && sells > 0) {
    return `Disagreement detected: ${buys} bullish vs ${sells} bearish. Address opposing views in your analysis.`
  } else if (sells > buys && buys > 0) {
    return `Disagreement detected: ${sells} bearish vs ${buys} bullish. Reconcile divergent perspectives.`
  } else if (holds > buys + sells) {
    return 'High uncertainty with many HOLD votes. Provide stronger conviction in your assessment.'
  }

  return 'Refine your analysis. Move toward consensus while maintaining analytical rigor.'
}

// ---- Aggregator (Consensus Builder) ----

interface AggregatorResult {
  consensusReached: boolean
  vetoTriggered: boolean
  finalDecision: FinalDecision | null
  votingBreakdown: VotingBreakdown[]
}

function aggregateResults(analyses: AgentAnalysis[], context: MarketDebateContext, maxRounds: number, currentRound: number): AggregatorResult {
  // Check for Risk Manager veto
  const riskAnalysis = analyses.find(a => a.role === 'risk_manager')
  if (riskAnalysis && riskAnalysis.recommendation === 'STRONG_SELL' && riskAnalysis.confidence >= 0.8) {
    return {
      consensusReached: true,
      vetoTriggered: true,
      finalDecision: {
        action: 'SELL',
        overallConfidence: riskAnalysis.confidence,
        targetPrice: null,
        stopLoss: null,
        takeProfit: null,
        positionSizePct: 0,
        reasoningSummary: `RISK MANAGER VETO: ${riskAnalysis.reasoning}`,
        allAnalyses: analyses,
        debateRounds: currentRound,
        riskManagerApproval: false,
      },
      votingBreakdown: [],
    }
  }

  // Compute weighted voting
  let weightedScore = 0
  let totalWeight = 0
  const votingBreakdown: VotingBreakdown[] = []

  for (const analysis of analyses) {
    const config = AGENT_ROLES[analysis.role]
    let voteValue = 0
    switch (analysis.recommendation) {
      case 'STRONG_BUY': voteValue = 2; break
      case 'BUY': voteValue = 1; break
      case 'HOLD': voteValue = 0; break
      case 'SELL': voteValue = -1; break
      case 'STRONG_SELL': voteValue = -2; break
    }

    const weightedVote = voteValue * config.weight * analysis.confidence
    weightedScore += weightedVote
    totalWeight += config.weight * analysis.confidence

    votingBreakdown.push({
      role: analysis.role,
      vote: analysis.recommendation,
      weight: config.weight,
      contribution: weightedVote,
    })
  }

  const finalScore = totalWeight > 0 ? weightedScore / totalWeight : 0
  const consensusReached = Math.abs(finalScore) >= DEFAULT_DEBATE_CONFIG.consensusThreshold || currentRound >= maxRounds

  if (!consensusReached) {
    return { consensusReached: false, vetoTriggered: false, finalDecision: null, votingBreakdown }
  }

  // Determine action
  let action: ConsensusAction
  if (finalScore > 0.5) action = 'BUY'
  else if (finalScore < -0.5) action = 'SELL'
  else action = 'HOLD'

  const absScore = Math.abs(finalScore)
  const overallConfidence = Math.min(absScore / 2, 0.95)

  // Build reasoning summary
  const buyCount = analyses.filter(a => a.recommendation === 'BUY' || a.recommendation === 'STRONG_BUY').length
  const sellCount = analyses.filter(a => a.recommendation === 'SELL' || a.recommendation === 'STRONG_SELL').length
  const holdCount = analyses.filter(a => a.recommendation === 'HOLD').length

  const quote = context.quote
  const currentPrice = quote?.price || 100
  const summary = `Consensus: ${action} (${buyCount}B/${holdCount}H/${sellCount}S). ${action !== 'HOLD' ? `Confidence: ${(overallConfidence * 100).toFixed(0)}%. ` : ''}After ${currentRound} debate round(s), agents reached ${action === 'HOLD' ? 'no strong directional consensus' : `a ${action.toLowerCase()} consensus`}.`

  return {
    consensusReached: true,
    vetoTriggered: false,
    finalDecision: {
      action,
      overallConfidence,
      targetPrice: action === 'BUY' ? currentPrice * 1.08 : action === 'SELL' ? currentPrice * 0.92 : null,
      stopLoss: action === 'BUY' ? currentPrice * 0.95 : action === 'SELL' ? currentPrice * 1.03 : null,
      takeProfit: action === 'BUY' ? currentPrice * 1.12 : null,
      positionSizePct: action === 'HOLD' ? 0 : Math.min(DEFAULT_DEBATE_CONFIG.maxPositionSizePct * overallConfidence, 0.25),
      reasoningSummary: summary,
      allAnalyses: analyses,
      debateRounds: currentRound,
      riskManagerApproval: riskAnalysis?.recommendation !== 'STRONG_SELL',
    },
    votingBreakdown,
  }
}

// ---- Main Debate Orchestrator ----

export class AgentDebateOrchestrator {
  private llmAvailable: boolean | null = null

  /** Run a round of agent analyses — LLM-powered with mock fallback */
  private async runAgentRound(
    roles: AgentTradingRole[],
    context: MarketDebateContext,
    supervisorInstruction: string,
    previousRoundAnalyses: AgentAnalysis[] | undefined,
    debateLog: string[],
  ): Promise<AgentAnalysis[]> {
    // Check LLM availability (cached after first check)
    if (this.llmAvailable === null) {
      this.llmAvailable = await tradingLLM.checkAvailability()
    }

    if (this.llmAvailable) {
      try {
        console.log('[AgentDebate] Using LLM-powered agents')
        const llmAnalyses = await tradingLLM.runAllAgents(
          context, supervisorInstruction, previousRoundAnalyses,
        )

        // If we got results from all 6 agents, use them
        if (llmAnalyses.length === roles.length) {
          for (const analysis of llmAnalyses) {
            debateLog.push(`  🤖 ${AGENT_ROLES[analysis.role].label}: ${analysis.recommendation} (${(analysis.confidence * 100).toFixed(0)}%, ${analysis.latencyMs}ms)`)
          }
          return llmAnalyses
        }

        // Partial results: fill in gaps with mock
        if (llmAnalyses.length > 0) {
          console.warn(`[AgentDebate] Only ${llmAnalyses.length}/${roles.length} LLM agents succeeded, filling gaps with mock`)
          const successfulRoles = new Set(llmAnalyses.map(a => a.role))
          const analyses: AgentAnalysis[] = [...llmAnalyses]

          for (const role of roles) {
            if (!successfulRoles.has(role)) {
              const mockAnalysis = this.runMockAgent(role, context, supervisorInstruction)
              analyses.push(mockAnalysis)
              debateLog.push(`  ⚡ ${AGENT_ROLES[role].label}: ${mockAnalysis.recommendation} (${(mockAnalysis.confidence * 100).toFixed(0)}%, mock)`)
            }
          }
          return analyses
        }

        // All LLM agents failed — fall through to mock
        console.warn('[AgentDebate] All LLM agents failed, falling back to mock generators')
      } catch (error) {
        console.warn('[AgentDebate] LLM round failed:', error instanceof Error ? error.message : error)
      }
    }

    // Fallback: use mock generators
    console.log('[AgentDebate] Using mock agent generators')
    this.llmAvailable = false
    const analyses: AgentAnalysis[] = roles.map(role => {
      const generator = ANALYST_GENERATORS[role]
      const analysis = generator({
        role,
        context,
        supervisorInstruction,
        previousRoundAnalyses,
      })
      debateLog.push(`  ⚡ ${AGENT_ROLES[role].label}: ${analysis.recommendation} (${(analysis.confidence * 100).toFixed(0)}%, mock)`)
      return analysis
    })
    return analyses
  }

  /** Run a single mock agent (used as fallback for individual LLM failures) */
  private runMockAgent(
    role: AgentTradingRole,
    context: MarketDebateContext,
    supervisorInstruction: string,
  ): AgentAnalysis {
    const generator = ANALYST_GENERATORS[role]
    return generator({ role, context, supervisorInstruction })
  }

  /** Force refresh of LLM availability check */
  resetLLMState(): void {
    this.llmAvailable = null
    tradingLLM.resetCircuitBreakers()
  }

  /** Get LLM and circuit breaker status for monitoring */
  getLLMStatus(): { available: boolean | null; circuitBreakers: Record<string, { state: string; failureCount: number }> } {
    return {
      available: this.llmAvailable,
      circuitBreakers: tradingLLM.getCircuitBreakerStatuses(),
    }
  }

  async buildContext(symbol: string, assetType: import('@/types/trading').AssetType): Promise<MarketDebateContext> {
    const quote = await marketDataService.getQuote(symbol, assetType)
    const bars = await marketDataService.getHistoricalBars(symbol, assetType, '1d', 100).catch(() => null)
    const news = await marketDataService.getMarketNews([symbol])

    // Build sentiment summary from news
    const relevantNews = news.filter(n => n.symbols.includes(symbol))
    const sentimentSummary: NewsSentimentSummary = {
      overallSentiment: relevantNews.length > 0
        ? relevantNews.filter(n => n.sentiment === 'positive').length > relevantNews.filter(n => n.sentiment === 'negative').length
          ? 'positive' : 'negative'
        : 'neutral',
      score: relevantNews.length > 0
        ? relevantNews.reduce((sum, n) => sum + n.sentimentScore, 0) / relevantNews.length
        : 0.5,
      articleCount: relevantNews.length,
      keyThemes: ['Market momentum', 'Economic data', 'Sector trends'],
      recentHeadlines: relevantNews.slice(0, 3).map(n => n.title),
    }

    // Technical summary
    const techSnapshot: TechnicalSnapshot = {
      trend: Math.random() > 0.5 ? 'bullish' : 'bearish',
      rsi: 30 + Math.random() * 40,
      macdSignal: Math.random() > 0.5 ? 'bullish' : 'bearish',
      supportLevels: quote ? [quote.price * 0.95, quote.price * 0.90] : [],
      resistanceLevels: quote ? [quote.price * 1.05, quote.price * 1.10] : [],
      volumeProfile: Math.random() > 0.5 ? 'increasing' : 'stable',
      patterns: ['Double bottom forming', 'Bullish divergence on RSI'],
    }

    // Layer 2: Causal Analysis via Knowledge Graph
    const causalAnalysis = this.getCausalContext(symbol, assetType, bars ?? [])
    const causalContext = causalAnalysis?.summary ?? undefined

    // Layer 3: Regime Geometry — feed historical bars into the detector
    const regimeGeometry = await this.getRegimeContext(symbol, assetType, bars ?? [])

    // Build knowledge context with regime info
    let knowledgeContext = `Market analysis for ${symbol} (${assetType}). Current price: $${quote?.price.toFixed(2) || 'N/A'}. ${relevantNews.length} recent news articles analyzed.`
    if (causalAnalysis) {
      knowledgeContext += ` Attribution: ${(causalAnalysis.attribution.explainedPct * 100).toFixed(0)}% factor-driven, ${(causalAnalysis.attribution.idiosyncraticPct * 100).toFixed(0)}% idiosyncratic.`
    }
    if (regimeGeometry) {
      knowledgeContext += ` Regime: ${regimeGeometry.regime.toUpperCase()} (confidence: ${(regimeGeometry.regimeConfidence * 100).toFixed(0)}%).`
    }

    return {
      symbol,
      assetType,
      quote,
      newsSentiment: sentimentSummary,
      knowledgeContext,
      technicalSummary: `${techSnapshot.trend === 'bullish' ? 'Bullish' : 'Bearish'} trend. RSI: ${techSnapshot.rsi?.toFixed(0)}. ${techSnapshot.patterns.join('. ')}.`,
      fundamentalSummary: `Sector: Technology. Strong earnings growth expected. Revenue growth: 12% YoY.`,
      bars,
      causalContext,
      causalAnalysis,
      regimeContext: regimeGeometry?.summary ?? undefined,
      regimeGeometry,
    }
  }

  /**
   * Get causal analysis context for a symbol via the Knowledge Graph (Layer 2).
   */
  private getCausalContext(
    symbol: string,
    assetType: import('@/types/trading').AssetType,
    bars: { close: number }[],
  ): import('@/types/trading').CausalAnalysisResult | null {
    if (bars.length < 5) return null

    // Convert close-only bars to full HistoricalBar shape for the engine
    const fullBars = bars.map((b, i) => ({
      timestamp: new Date(Date.now() - (bars.length - i) * 86400000).toISOString(),
      open: b.close,
      high: b.close,
      low: b.close,
      close: b.close,
      volume: 0,
    }))

    return knowledgeGraph.analyzeCausalStructure(symbol, assetType, fullBars)
  }

  /**
   * Get regime geometry context for a symbol by feeding historical bars
   * into the RegimeGeometryDetector (Layer 3).
   * Resets and reloads to ensure fresh data (computation is O(windowSize), trivial).
   */
  private async getRegimeContext(
    symbol: string,
    assetType: import('@/types/trading').AssetType,
    bars: { close: number }[],
  ): Promise<import('@/types/trading').RegimeGeometryResult | null> {
    if (bars.length < 2) return null

    regimeGeometryDetector.resetSymbol(symbol, assetType)
    const prices = bars.map(b => b.close)
    regimeGeometryDetector.loadHistorical(symbol, assetType, prices)

    return regimeGeometryDetector.getRegimeResult(symbol, assetType)
  }

  async runDebate(symbol: string, assetType: import('@/types/trading').AssetType): Promise<DebateState> {
    const context = await this.buildContext(symbol, assetType)

    const debateState: DebateState = {
      symbol,
      assetType,
      marketData: context,
      currentRound: 0,
      maxRounds: DEFAULT_DEBATE_CONFIG.maxRounds,
      agentAnalyses: [],
      supervisorInstruction: '',
      consensusReached: false,
      consensusThreshold: DEFAULT_DEBATE_CONFIG.consensusThreshold,
      vetoTriggered: false,
      finalDecision: null,
      votingBreakdown: [],
      debateLog: [],
    }

    const roles: AgentTradingRole[] = [
      'macro_strategist', 'sector_analyst', 'sentiment_agent',
      'technical_analyst', 'risk_manager', 'execution_optimizer',
    ]

    for (let round = 1; round <= debateState.maxRounds; round++) {
      debateState.currentRound = round
      debateState.supervisorInstruction = generateSupervisorInstruction(round, debateState.agentAnalyses)
      debateState.debateLog.push(`[Round ${round}] Supervisor: ${debateState.supervisorInstruction}`)

      // Try LLM-powered analysis, fall back to mock generators
      const roundAnalyses = await this.runAgentRound(
        roles, context, debateState.supervisorInstruction,
        round > 1 ? debateState.agentAnalyses : undefined,
        debateState.debateLog,
      )

      debateState.agentAnalyses = roundAnalyses

      // Aggregate
      const result = aggregateResults(roundAnalyses, context, debateState.maxRounds, round)
      debateState.votingBreakdown = result.votingBreakdown
      debateState.vetoTriggered = result.vetoTriggered

      if (result.consensusReached) {
        debateState.consensusReached = true
        debateState.finalDecision = result.finalDecision
        debateState.debateLog.push(
          result.vetoTriggered
            ? `  ⚠️ VETO triggered by Risk Manager`
            : `  ✓ Consensus reached: ${result.finalDecision?.action}`
        )
        break
      }

      debateState.debateLog.push(`  → No consensus yet (round ${round}/${debateState.maxRounds})`)
    }

    return debateState
  }

  async generateOrderIntent(debateState: DebateState, portfolioBalance: number): Promise<{
    action: ConsensusAction
    symbol: string
    assetType: string
    quantity: number
    limitPrice: number | null
    stopLoss: number | null
    takeProfit: number | null
    reasoning: string
  } | null> {
    const decision = debateState.finalDecision
    if (!decision || decision.action === 'HOLD') return null

    const quote = debateState.marketData.quote
    if (!quote) return null

    const positionSize = portfolioBalance * decision.positionSizePct
    const quantity = positionSize / quote.price

    return {
      action: decision.action,
      symbol: debateState.symbol,
      assetType: debateState.assetType,
      quantity: parseFloat(quantity.toFixed(4)),
      limitPrice: decision.action === 'BUY' ? quote.price * 1.005 : quote.price * 0.995,
      stopLoss: decision.stopLoss,
      takeProfit: decision.takeProfit,
      reasoning: decision.reasoningSummary,
    }
  }
}

export const agentDebateOrchestrator = new AgentDebateOrchestrator()
