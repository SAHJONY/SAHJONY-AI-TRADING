// Knowledge Enrichment Pipeline — news aggregation, sentiment analysis, market context
import type {
  KnowledgeContext, MarketNewsItem, NewsSentimentSummary,
  TechnicalSnapshot, CompanyProfile, AssetType,
} from '@/types/trading'
import { marketDataService } from './market-data'

export class KnowledgePipeline {
  private symbolCache: Map<string, { context: KnowledgeContext; expiresAt: number }> = new Map()
  private cacheTtlMs = 5 * 60 * 1000 // 5 minutes

  async enrichMarketContext(symbol: string, assetType: AssetType): Promise<KnowledgeContext> {
    const cacheKey = `${symbol}:${assetType}`
    const cached = this.symbolCache.get(cacheKey)
    if (cached && cached.expiresAt > Date.now()) {
      return cached.context
    }

    const [news, quote, companyProfile] = await Promise.all([
      marketDataService.getMarketNews([symbol]),
      marketDataService.getQuote(symbol, assetType),
      this.getCompanyProfile(symbol, assetType),
    ])

    const sentimentSummary = this.buildSentimentSummary(news)
    const technicalSnapshot = this.buildTechnicalSnapshot(quote, assetType)

    const context: KnowledgeContext = {
      symbol,
      assetType,
      companyProfile,
      newsItems: news,
      sentimentSummary,
      technicalSnapshot,
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

    return parts.join('\n')
  }

  clearCache(): void {
    this.symbolCache.clear()
  }
}

export const knowledgePipeline = new KnowledgePipeline()
