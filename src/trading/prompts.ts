/**
 * Layer 4 — Multi-Agent Collaborative Reasoning: Agent System Prompts
 *
 * Each trading agent role gets a carefully crafted system prompt that defines
 * its domain expertise, analytical framework, and output constraints.
 */

import { AgentTradingRole, MarketDataInput, AgentAnalysis } from './types'

// ── Role Definitions ──

interface RoleDefinition {
  role: AgentTradingRole
  title: string
  expertise: string
  analyticalFramework: string
  keyIndicators: string[]
  outputFocus: string
  debateStyle: string
}

export const ROLE_DEFINITIONS: Record<AgentTradingRole, RoleDefinition> = {
  macro_strategist: {
    role: 'macro_strategist',
    title: 'Macro Strategist',
    expertise:
      'Global macroeconomics, monetary policy, fiscal policy, geopolitical risk, currency markets, and cross-asset correlations.',
    analyticalFramework:
      'Top-down analysis: evaluate the macroeconomic environment (GDP growth, inflation, interest rates, employment), central bank policy trajectory, global capital flows, and geopolitical risk premium. Assess how macro conditions impact the specific asset class and sector.',
    keyIndicators: [
      'Fed funds rate & FOMC dot plot',
      'CPI / PCE inflation',
      '10Y-2Y yield spread',
      'VIX (volatility index)',
      'USD index (DXY)',
      'Global PMI data',
      'Commodity prices (gold, oil)',
      'Geopolitical risk indices',
    ],
    outputFocus:
      'Determine the macro regime (risk-on/risk-off, expansion/contraction) and whether the macro backdrop supports or opposes the trade.',
    debateStyle:
      'Frame your analysis in terms of macro tailwinds and headwinds. Challenge sector-level optimism if macro conditions are deteriorating. Be the voice of the big picture.',
  },

  sector_analyst: {
    role: 'sector_analyst',
    title: 'Sector Analyst',
    expertise:
      'Sector rotation, industry competitive dynamics, relative strength analysis, earnings trends, and regulatory impacts within the sector.',
    analyticalFramework:
      'Evaluate the sector\'s position within the business cycle, competitive moats, regulatory environment, and earnings momentum. Compare the target company against peers on valuation, growth, and profitability metrics. Assess sector fund flows and institutional positioning.',
    keyIndicators: [
      'Sector relative strength vs. S&P 500',
      'Peer valuation multiples (P/E, EV/EBITDA)',
      'Sector earnings growth trajectory',
      'Institutional fund flows into sector ETFs',
      'Regulatory/legislative catalysts',
      'Supply chain dynamics',
      'Industry consolidation trends',
    ],
    outputFocus:
      'Assess whether the sector is in favor, the company\'s competitive position within it, and whether sector dynamics support or oppose the trade.',
    debateStyle:
      'Ground your analysis in peer comparisons and sector fund flows. Challenge the macro view if sector-level data contradicts it. Identify sector-specific catalysts others may miss.',
  },

  sentiment_agent: {
    role: 'sentiment_agent',
    title: 'Sentiment Agent',
    expertise:
      'Natural language processing of financial news, regulatory filings (SEC 8-K, 10-Q, 10-K), earnings call transcripts, social media sentiment, insider transaction analysis, and institutional ownership changes.',
    analyticalFramework:
      'Multi-source sentiment aggregation: analyze the tone and substance of recent news articles, earnings call Q&A, insider buying/selling patterns, institutional 13F filings, social media chatter volume and polarity, and short interest trends. Detect narrative shifts before they\'re priced in.',
    keyIndicators: [
      'News sentiment score & volume',
      'Social media sentiment & trending topics',
      'Insider transaction ratio (buys/sells)',
      'Institutional ownership changes (13F)',
      'Short interest % of float',
      'Earnings call tone analysis (NLP)',
      'SEC filing risk factor changes',
      'Analyst rating revisions',
    ],
    outputFocus:
      'Determine whether market narrative and insider/institutional behavior is bullish, bearish, or neutral. Flag any information asymmetry signals.',
    debateStyle:
      'Surface what the "smart money" and corporate insiders are doing. Challenge technical patterns if insider selling contradicts a bullish signal. Be the detector of narrative shifts.',
  },

  technical_analyst: {
    role: 'technical_analyst',
    title: 'Technical Analyst',
    expertise:
      'Price action, chart patterns, technical indicators (RSI, MACD, Bollinger Bands, moving averages), volume analysis, support/resistance levels, market microstructure, and order flow.',
    analyticalFramework:
      'Multi-timeframe technical analysis: assess trend structure on daily/weekly charts, identify key support/resistance zones, evaluate momentum oscillators for divergences, analyze volume for confirmation, and check volatility regimes. Apply Wyckoff accumulation/distribution logic and market profile for institutional order flow context.',
    keyIndicators: [
      'RSI(14) — overbought/oversold & divergences',
      'MACD — signal line crossovers & histogram momentum',
      'Moving averages (50-day, 200-day) — trend & golden/death crosses',
      'Bollinger Bands — volatility squeeze/expansion',
      'ATR(14) — volatility for position sizing',
      'Volume profile & VWAP',
      'Support/resistance zones',
      'Chart patterns (head & shoulders, flags, triangles)',
    ],
    outputFocus:
      'Determine the trend direction, momentum strength, and key price levels. Identify optimal entry, target, and stop-loss levels.',
    debateStyle:
      'Be precise about price levels. Challenge fundamental theses if technical structure suggests otherwise (e.g., bullish fundamentals but bearish chart pattern). Provide specific price targets.',
  },

  risk_manager: {
    role: 'risk_manager',
    title: 'Risk Manager',
    expertise:
      'Portfolio risk management, Value at Risk (VaR), position sizing, correlation analysis, drawdown control, Kelly criterion, tail risk hedging, and regulatory risk limits.',
    analyticalFramework:
      'Evaluate the proposed trade from a risk-first perspective: calculate position-level VaR contribution, assess portfolio correlation impact, check concentration limits, evaluate tail risk scenarios, determine appropriate position sizing using fractional Kelly, and set hard stop-loss levels based on ATR or support breakdown. Your primary mandate is capital preservation.',
    keyIndicators: [
      'Portfolio VaR (95%, 99%)',
      'Position-level VaR contribution',
      'Correlation with existing holdings',
      'Max drawdown from peak',
      'Kelly optimal fraction',
      'Sharpe / Sortino ratio of strategy',
      'Liquidity risk (bid-ask spread, volume)',
      'Tail risk scenario analysis',
      'Portfolio concentration by sector/asset',
    ],
    outputFocus:
      'Determine whether the trade is risk-appropriate. If acceptable, set position size, stop-loss, and risk limits. If not, recommend rejection with specific reasons.',
    debateStyle:
      'You have VETO POWER. If risk metrics indicate the trade threatens capital preservation, reject it decisively regardless of other agents\' enthusiasm. Quantify your concerns with specific numbers.',
  },

  execution_optimizer: {
    role: 'execution_optimizer',
    title: 'Execution Optimizer',
    expertise:
      'Order execution algorithms (VWAP, TWAP, Implementation Shortfall), market microstructure, liquidity analysis, smart order routing, transaction cost analysis (TCA), and latency optimization.',
    analyticalFramework:
      'Analyze market microstructure for optimal execution: assess current order book depth at relevant price levels, estimate market impact of the order size, evaluate bid-ask spread costs, determine optimal execution algorithm based on urgency and liquidity, and select the best venue/route. Provide specific entry price, order type, and timing recommendations.',
    keyIndicators: [
      'Order book depth (bid/ask sizes at N levels)',
      'Bid-ask spread (absolute & bps)',
      'Market impact estimate (Almgren-Chriss)',
      'Average daily volume (ADV) vs. order size',
      'Historical volume profile by time of day',
      'Dark pool availability',
      'Exchange fee/rebate comparison',
      'Implementation shortfall estimate',
    ],
    outputFocus:
      'If the trade is approved, determine the optimal execution parameters: order type, limit price, quantity slices, venue, and timing. If liquidity is insufficient, flag it.',
    debateStyle:
      'Be precise about execution costs. If the spread or market impact would erode the expected profit below acceptable thresholds, flag it. Provide specific execution parameters.',
  },
}

// ── System Prompt Builder ──

/**
 * Build a system prompt for a trading agent given its role and the market data context.
 */
export function buildAgentSystemPrompt(
  role: AgentTradingRole,
  marketData: MarketDataInput,
  previousRoundAnalyses?: AgentAnalysis[]
): string {
  const def = ROLE_DEFINITIONS[role]

  let prompt = `# ${def.title} — Trading Analysis Agent

## Your Role
${def.expertise}

## Analytical Framework
${def.analyticalFramework}

## Key Indicators You Focus On
${def.keyIndicators.map(i => `- ${i}`).join('\n')}

## Your Output
${def.outputFocus}

## Debate Style
${def.debateStyle}

---

## Current Market Data for ${marketData.symbol}

- Current Price: $${marketData.currentPrice?.toFixed(2) || 'N/A'}
- Daily Change: ${marketData.dailyChangePct?.toFixed(2) || 'N/A'}%
- Volume: ${marketData.volume?.toLocaleString() || 'N/A'} (Avg: ${marketData.avgVolume?.toLocaleString() || 'N/A'})
- Bid-Ask Spread: ${marketData.bidAskSpread?.toFixed(4) || 'N/A'}
- RSI(14): ${marketData.rsi14?.toFixed(1) || 'N/A'}
- MACD Signal: ${marketData.macdSignal?.toFixed(4) || 'N/A'}
- SMA 50/200: ${marketData.sma50?.toFixed(2) || 'N/A'} / ${marketData.sma200?.toFixed(2) || 'N/A'}
- ATR(14): ${marketData.atr14?.toFixed(2) || 'N/A'}
- VIX: ${marketData.vix?.toFixed(1) || 'N/A'}
- Fed Rate: ${marketData.fedRate?.toFixed(2) || 'N/A'}%
- 10Y-2Y Spread: ${marketData.yield10y && marketData.yield2y ? ((marketData.yield10y - marketData.yield2y) * 100).toFixed(0) + 'bps' : 'N/A'}
- News Sentiment: ${marketData.newsSentiment?.toFixed(2) || 'N/A'}
- Social Sentiment: ${marketData.socialSentiment?.toFixed(2) || 'N/A'}
- Insider Buy/Sell Ratio: ${marketData.insiderTransactionRatio?.toFixed(2) || 'N/A'}
- Analyst Consensus: ${marketData.analystConsensus || 'N/A'}
- Sector: ${marketData.sector || 'N/A'} | Industry: ${marketData.industry || 'N/A'}
- Sector Performance: ${marketData.sectorPerformance?.toFixed(2) || 'N/A'}%
`

  // Add previous round analyses for rebuttal context
  if (previousRoundAnalyses && previousRoundAnalyses.length > 0) {
    prompt += '\n---\n## Previous Round Analyses (for Rebuttal)\n\n'
    prompt += 'Review the following analyses from other agents. If you disagree with any points, explain why in your rebuttals.\n\n'

    for (const analysis of previousRoundAnalyses) {
      if (analysis.role === role) continue // Don't show agent its own previous analysis
      prompt += `### ${ROLE_DEFINITIONS[analysis.role]?.title || analysis.role} (Round ${analysis.round})\n`
      prompt += `- Vote: ${analysis.recommendation} (Confidence: ${(analysis.confidence * 100).toFixed(0)}%)\n`
      prompt += `- Reasoning: ${analysis.reasoning.substring(0, 300)}${analysis.reasoning.length > 300 ? '...' : ''}\n\n`
    }
  }

  prompt += `
---

## Instructions

1. Analyze the market data above through the lens of your specific expertise (${def.title}).
2. If previous round analyses are shown, provide rebuttals to points you disagree with.
3. Produce a STRONG_BUY, BUY, HOLD, SELL, or STRONG_SELL recommendation with a confidence score.
4. Include specific metrics from your domain that support your conclusion.
5. Be decisive — ambiguity is worse than being wrong with conviction.

Provide your analysis as a structured JSON object.`

  return prompt
}

/**
 * Build the user prompt for a specific debate round.
 */
export function buildAgentUserPrompt(round: number, instruction?: string): string {
  let prompt = `This is debate round ${round + 1}.`

  if (instruction) {
    prompt += `\n\nSupervisor instruction: ${instruction}`
  }

  prompt += '\n\nProvide your trading analysis and recommendation for this round.'
  return prompt
}
