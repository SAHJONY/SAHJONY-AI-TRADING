// Agent Debate System — multi-agent trading debate with consensus and risk management
import type {
  AgentTradingRole, AgentAnalysis, DebateState, MarketDebateContext,
  FinalDecision, VotingBreakdown, TradingRecommendation, ConsensusAction,
  NewsSentimentSummary, TechnicalSnapshot,
} from '@/types/trading'
import { AGENT_ROLES, DEFAULT_DEBATE_CONFIG } from '@/types/trading'
import { marketDataService } from './market-data'

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

  return {
    role: 'macro_strategist',
    recommendation: isFavorable ? 'BUY' : 'HOLD',
    confidence: 0.55 + Math.random() * 0.3,
    reasoning: `Macro regime: ${regime}. ${isFavorable ? 'Favorable conditions with accommodative monetary policy and strong GDP growth supporting risk assets.' : 'Mixed signals with inflation concerns warranting caution.'} Context: ${context.knowledgeContext.slice(0, 100)}`,
    keyMetrics: {
      regime,
      gdpGrowth: (1.5 + Math.random() * 2.5).toFixed(1) + '%',
      inflation: (2 + Math.random() * 3).toFixed(1) + '%',
      fedStance: isFavorable ? 'dovish' : 'hawkish',
    },
    riskFlags: isFavorable ? [] : ['Inflation risk', 'Policy uncertainty'],
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

  return {
    role: 'sentiment_agent',
    recommendation: isPositive ? 'BUY' : isNegative ? 'SELL' : 'HOLD',
    confidence: sentiment.score,
    reasoning: `Aggregated sentiment: ${sentiment.overallSentiment} (${(sentiment.score * 100).toFixed(0)}%). ${sentiment.articleCount} articles analyzed. Key themes: ${sentiment.keyThemes.join(', ')}. ${isPositive ? 'Bullish momentum building across social and news channels.' : isNegative ? 'Bearish pressure mounting with negative news flow.' : 'Mixed signals with no clear directional bias.'}`,
    keyMetrics: {
      sentimentScore: sentiment.score,
      articleCount: sentiment.articleCount,
      socialBuzz: isPositive ? 'high' : isNegative ? 'elevated' : 'moderate',
    },
    riskFlags: isNegative ? ['Negative sentiment cascade'] : [],
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

  return {
    role: 'technical_analyst',
    recommendation,
    confidence: 0.5 + Math.random() * 0.35,
    reasoning: `RSI: ${rsi.toFixed(0)} (${rsiSignal}). ${techSummary || 'Multi-timeframe analysis shows mixed signals with key support at $' + (price * 0.95).toFixed(2) + ' and resistance at $' + (price * 1.05).toFixed(2) + '.'}`,
    keyMetrics: {
      rsi: rsi.toFixed(0),
      rsiSignal,
      supportLevel: (price * 0.95).toFixed(2),
      resistanceLevel: (price * 1.05).toFixed(2),
      volumeTrend: Math.random() > 0.5 ? 'increasing' : 'decreasing',
    },
    riskFlags: rsi > 70 ? ['Overbought conditions'] : rsi < 30 ? ['Oversold conditions'] : [],
    latencyMs: 80 + Math.floor(Math.random() * 150),
  }
}

function generateRiskAnalysis(input: AnalystInput): AgentAnalysis {
  const { context } = input

  // Risk Manager is conservative by design
  const riskLevels: TradingRecommendation[] = ['HOLD', 'SELL', 'STRONG_SELL', 'BUY', 'STRONG_BUY']
  const riskWeights = [0.35, 0.25, 0.15, 0.15, 0.1]
  const rand = Math.random()
  let idx = 0
  let cumulative = 0
  for (let i = 0; i < riskWeights.length; i++) {
    cumulative += riskWeights[i]
    if (rand <= cumulative) { idx = i; break }
  }
  const recommendation = riskLevels[idx]

  const var95 = (1 + Math.random() * 5).toFixed(1)
  const isHighRisk = recommendation === 'STRONG_SELL'

  return {
    role: 'risk_manager',
    recommendation,
    confidence: 0.6 + Math.random() * 0.3,
    reasoning: `${isHighRisk ? 'VETO: ' : ''}VaR(95%): ${var95}%. ${isHighRisk ? 'Risk exceeds acceptable thresholds. Position sizing would breach max drawdown limits.' : 'Risk metrics within acceptable bounds. Max position size of 25% of portfolio recommended.'}`,
    keyMetrics: {
      var95: var95 + '%',
      maxDrawdownRisk: (1 + Math.random() * 8).toFixed(1) + '%',
      kellyFraction: (0.1 + Math.random() * 0.3).toFixed(2),
      recommendedSize: isHighRisk ? '0%' : Math.floor(5 + Math.random() * 20) + '%',
    },
    riskFlags: isHighRisk ? ['VaR breach', 'Drawdown limit exceeded', 'Portfolio concentration'] : [],
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
  async buildContext(symbol: string, assetType: import('@/types/trading').AssetType): Promise<MarketDebateContext> {
    const quote = await marketDataService.getQuote(symbol, assetType)
    const bars = await marketDataService.getHistoricalBars(symbol, assetType, '1d', 50)
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

    return {
      symbol,
      assetType,
      quote,
      newsSentiment: sentimentSummary,
      knowledgeContext: `Market analysis for ${symbol} (${assetType}). Current price: $${quote?.price.toFixed(2) || 'N/A'}. ${relevantNews.length} recent news articles analyzed.`,
      technicalSummary: `${techSnapshot.trend === 'bullish' ? 'Bullish' : 'Bearish'} trend. RSI: ${techSnapshot.rsi?.toFixed(0)}. ${techSnapshot.patterns.join('. ')}.`,
      fundamentalSummary: `Sector: Technology. Strong earnings growth expected. Revenue growth: 12% YoY.`,
      bars,
    }
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

      // All agents analyze in parallel
      const roundAnalyses: AgentAnalysis[] = roles.map(role => {
        const generator = ANALYST_GENERATORS[role]
        const analysis = generator({
          role,
          context,
          supervisorInstruction: debateState.supervisorInstruction,
          previousRoundAnalyses: round > 1 ? debateState.agentAnalyses : undefined,
        })
        debateState.debateLog.push(`  ${AGENT_ROLES[role].label}: ${analysis.recommendation} (${(analysis.confidence * 100).toFixed(0)}%)`)
        return analysis
      })

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
