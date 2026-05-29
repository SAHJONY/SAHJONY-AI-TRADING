// Knowledge Enrichment Pipeline — news aggregation, sentiment analysis, market context
// Layer 2 integration: Knowledge Graph provides causal inference
// Layer 3 integration: Regime Geometry Detector provides Fisher metric / geodesic analysis
import type {
  KnowledgeContext, MarketNewsItem, NewsSentimentSummary,
  TechnicalSnapshot, CompanyProfile, AssetType,
} from '@/types/trading'
import { marketDataService } from './market-data'
import { knowledgeGraph } from './knowledge-graph'
import { regimeGeometryDetector } from './regime-geometry-detector'

export class KnowledgePipeline {
  private symbolCache: Map<string, { context: KnowledgeContext; expiresAt: number }> = new Map()
  private cacheTtlMs = 5 * 60 * 1000 // 5 minutes

  async enrichMarketContext(symbol: string, assetType: AssetType): Promise<KnowledgeContext> {
    const cacheKey = `${symbol}:${assetType}`
    const cached = this.symbolCache.get(cacheKey)
    if (cached && cached.expiresAt > Date.now()) {
      return cached.context
    }

    const [news, quote, companyProfile, bars] = await Promise.all([
      marketDataService.getMarketNews([symbol]),
      marketDataService.getQuote(symbol, assetType),
      this.getCompanyProfile(symbol, assetType),
      marketDataService.getHistoricalBars(symbol, assetType, '1d', 100).catch(() => null),
    ])

    const sentimentSummary = this.buildSentimentSummary(news)
    const technicalSnapshot = this.buildTechnicalSnapshot(quote, assetType)

    // Layer 2: Causal Analysis via Knowledge Graph
    const causalAnalysis = await this.getCausalAnalysis(symbol, assetType, bars)

    // Layer 3: Regime Geometry Analysis
    const regimeGeometry = await this.getRegimeGeometry(symbol, assetType, bars)

    const context: KnowledgeContext = {
      symbol,
      assetType,
      companyProfile,
      newsItems: news,
      sentimentSummary,
      technicalSnapshot,
      causalAnalysis,
      regimeGeometry,
      enrichedAt: new Date().toISOString(),
    }

    this.symbolCache.set(cacheKey, { context, expiresAt: Date.now() + this.cacheTtlMs })
    return context
  }

  private buildSentimentSummary(news: MarketNewsItem[]): NewsSentimentSummary {
    if (news.length === 0) {
      return {
        overallSentiment: 'neutral',
        score: 0.5,
        articleCount: 0,
        keyThemes: [],
        recentHeadlines: [],
      }
    }

    const positiveCount = news.filter(n => n.sentiment === 'positive').length
    const negativeCount = news.filter(n => n.sentiment === 'negative').length
    const avgScore = news.reduce((sum, n) => sum + n.sentimentScore, 0) / news.length

    const overallSentiment: 'positive' | 'negative' | 'neutral' =
      avgScore > 0.6 ? 'positive' : avgScore < 0.4 ? 'negative' : 'neutral'

    // Extract key themes from headlines
    const themeWords = news.flatMap(n => n.title.toLowerCase().split(' '))
    const wordFreq = new Map<string, number>()
    const stopWords = new Set(['the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'is', 'are', 'as', 'be'])
    for (const word of themeWords) {
      if (word.length > 3 && !stopWords.has(word)) {
        wordFreq.set(word, (wordFreq.get(word) || 0) + 1)
      }
    }
    const keyThemes = [...wordFreq.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([word]) => word.charAt(0).toUpperCase() + word.slice(1))

    return {
      overallSentiment,
      score: avgScore,
      articleCount: news.length,
      keyThemes,
      recentHeadlines: news.slice(0, 5).map(n => n.title),
    }
  }

  private buildTechnicalSnapshot(quote: { price: number; changePct24h: number } | null, _assetType: AssetType): TechnicalSnapshot {
    if (!quote) {
      return {
        trend: 'neutral',
        rsi: 50,
        macdSignal: 'neutral',
        supportLevels: [],
        resistanceLevels: [],
        volumeProfile: 'stable',
        patterns: [],
      }
    }

    const trend = quote.changePct24h > 1 ? 'bullish' : quote.changePct24h < -1 ? 'bearish' : 'neutral'
    const rsi = 50 + quote.changePct24h * 2 // Rough approximation
    const clampedRsi = Math.max(10, Math.min(90, rsi))

    return {
      trend,
      rsi: clampedRsi,
      macdSignal: quote.changePct24h > 0.5 ? 'bullish' : quote.changePct24h < -0.5 ? 'bearish' : 'neutral',
      supportLevels: [quote.price * 0.95, quote.price * 0.90],
      resistanceLevels: [quote.price * 1.05, quote.price * 1.10],
      volumeProfile: Math.abs(quote.changePct24h) > 2 ? 'increasing' : 'stable',
      patterns: quote.changePct24h > 0 ? ['Uptrend continuation', 'Higher lows forming'] : ['Downtrend', 'Lower highs'],
    }
  }

  private async getCompanyProfile(symbol: string, assetType: AssetType): Promise<CompanyProfile | null> {
    if (assetType !== 'stock') return null

    // Mock company profiles for demo
    const profiles: Record<string, CompanyProfile> = {
      AAPL: {
        name: 'Apple Inc.',
        sector: 'Technology',
        industry: 'Consumer Electronics',
        marketCap: 2850000000000,
        peRatio: 28.5,
        eps: 6.43,
        revenue: 383000000000,
        description: 'Designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.',
        employees: 164000,
        website: 'https://www.apple.com',
      },
      GOOGL: {
        name: 'Alphabet Inc.',
        sector: 'Technology',
        industry: 'Internet Content & Information',
        marketCap: 1750000000000,
        peRatio: 25.2,
        eps: 5.80,
        revenue: 307000000000,
        description: 'Provides online advertising, search, cloud computing, and other internet services.',
        employees: 182000,
        website: 'https://www.abc.xyz',
      },
      MSFT: {
        name: 'Microsoft Corporation',
        sector: 'Technology',
        industry: 'Software Infrastructure',
        marketCap: 3100000000000,
        peRatio: 36.8,
        eps: 11.06,
        revenue: 211000000000,
        description: 'Develops and supports software, services, devices, and solutions worldwide.',
        employees: 221000,
        website: 'https://www.microsoft.com',
      },
      TSLA: {
        name: 'Tesla Inc.',
        sector: 'Consumer Cyclical',
        industry: 'Auto Manufacturers',
        marketCap: 780000000000,
        peRatio: 55.0,
        eps: 3.56,
        revenue: 96000000000,
        description: 'Designs, develops, manufactures, and sells electric vehicles and energy storage systems.',
        employees: 140000,
        website: 'https://www.tesla.com',
      },
    }

    return profiles[symbol] || {
      name: symbol,
      sector: 'Unknown',
      industry: 'Unknown',
      marketCap: 0,
      peRatio: null,
      eps: null,
      revenue: null,
      description: `Publicly traded company (${symbol}).`,
      employees: null,
      website: null,
    }
  }

  /**
   * Get causal analysis for a symbol via the Knowledge Graph (Layer 2).
   */
  private getCausalAnalysis(
    symbol: string,
    assetType: AssetType,
    bars: { close: number }[] | null,
  ): import('@/types/trading').CausalAnalysisResult | null {
    if (!bars || bars.length < 5) return null

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
   * Get regime geometry analysis for a symbol by feeding historical bars
   * into the RegimeGeometryDetector (Layer 3).
   * Resets and reloads to ensure fresh data (computation is O(windowSize), trivial).
   */
  private async getRegimeGeometry(
    symbol: string,
    assetType: AssetType,
    bars: { close: number }[] | null,
  ): Promise<import('@/types/trading').RegimeGeometryResult | null> {
    if (!bars || bars.length < 2) return null

    // Reset and reload to ensure fresh regime detection
    regimeGeometryDetector.resetSymbol(symbol, assetType)
    const prices = bars.map(b => b.close)
    regimeGeometryDetector.loadHistorical(symbol, assetType, prices)

    return regimeGeometryDetector.getRegimeResult(symbol, assetType)
  }

  async getEnrichedContext(symbol: string, assetType: AssetType): Promise<string> {
    const context = await this.enrichMarketContext(symbol, assetType)
    const parts: string[] = []

    if (context.companyProfile) {
      const p = context.companyProfile
      parts.push(`Company: ${p.name} (${p.sector})`)
      parts.push(`Market Cap: $${(p.marketCap / 1e9).toFixed(1)}B`)
      if (p.peRatio) parts.push(`P/E: ${p.peRatio.toFixed(1)}`)
      parts.push(`Description: ${p.description}`)
    }

    parts.push(`\nSentiment: ${context.sentimentSummary.overallSentiment} (${(context.sentimentSummary.score * 100).toFixed(0)}%)`)
    parts.push(`Key Themes: ${context.sentimentSummary.keyThemes.join(', ')}`)
    parts.push(`Recent: ${context.sentimentSummary.recentHeadlines.slice(0, 2).join(' | ')}`)

    if (context.technicalSnapshot) {
      const t = context.technicalSnapshot
      parts.push(`\nTechnical: ${t.trend} trend, RSI: ${t.rsi?.toFixed(0)}, Patterns: ${t.patterns.join(', ')}`)
    }

    // Layer 2: Causal Graph context
    if (context.causalAnalysis) {
      const ca = context.causalAnalysis
      parts.push(`\n[Causal Graph] Attribution: ${(ca.attribution.explainedPct * 100).toFixed(0)}% factor-driven, ${(ca.attribution.idiosyncraticPct * 100).toFixed(0)}% idiosyncratic`)
      if (ca.factorExposures.filter(e => e.significant).length > 0) {
        const topExposures = ca.factorExposures
          .filter(e => e.significant)
          .sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta))
          .slice(0, 3)
        parts.push(`  Exposures: ${topExposures.map(e => `${e.factorId}(β=${e.beta.toFixed(2)})`).join(', ')}`)
      }
      if (ca.grangerResults.length > 0) {
        parts.push(`  Granger: ${ca.grangerResults.map(g => `${g.cause}→${g.effect}`).join(', ')}`)
      }
    }

    // Layer 3: Regime Geometry context
    if (context.regimeGeometry) {
      const rg = context.regimeGeometry
      parts.push(`\n[Regime Geometry] Status: ${rg.regime.toUpperCase()} (confidence: ${(rg.regimeConfidence * 100).toFixed(0)}%)`)
      parts.push(`  Geodesic velocity: ${(rg.currentVelocity * 1000).toFixed(2)}e-3 | Threshold: ${(rg.velocityThreshold * 1000).toFixed(2)}e-3`)
      if (rg.regimeShiftDetected) {
        parts.push(`  ⚠️ REGIME SHIFT DETECTED (severity: ${(rg.shiftSeverity * 100).toFixed(0)}%). ${rg.summary}`)
      } else {
        parts.push(`  ${rg.summary}`)
      }
    }

    return parts.join('\n')
  }

  clearCache(): void {
    this.symbolCache.clear()
  }
}

export const knowledgePipeline = new KnowledgePipeline()
