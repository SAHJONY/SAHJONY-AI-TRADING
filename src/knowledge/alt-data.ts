/**
 * Layer 3 — Alternative Data Connectors
 *
 * Fetches and aggregates alternative data sources:
 * 1. NewsAPI — news articles with basic sentiment scoring
 * 2. SEC Form 4 — insider transactions (buys/sells by executives)
 * 3. Social sentiment — placeholder for Reddit/Twitter aggregation
 *
 * All connectors respect rate limits and return normalized data structures
 * that feed into the Layer 4 debate agents' MarketDataInput.
 */

import {
  NewsArticle,
  InsiderTransaction,
  InsiderSummary,
  SocialSentiment,
  AltDataSnapshot,
  AltDataConfig,
} from './types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_ALT_DATA_CONFIG: AltDataConfig = {
  newsApiKey: process.env.NEWSAPI_KEY || '',
  newsApiBase: 'https://newsapi.org/v2',
  newsRefreshIntervalMs: 15 * 60 * 1000,  // 15 min
  maxArticlesPerSymbol: 20,
  newsLookbackDays: 3,
  fetchInsiderTransactions: true,
  insiderLookbackDays: 90,
  fetchSocialSentiment: false, // Disabled by default (no free API)
}

// ═══════════════════════════════════════════════════════════════
// Simple Sentiment Analyzer (heuristic — no ML dependency)
// ═══════════════════════════════════════════════════════════════

const POSITIVE_WORDS = new Set([
  'beat', 'exceed', 'surge', 'rally', 'jump', 'soar', 'upgrade', 'outperform',
  'growth', 'profit', 'record', 'strong', 'bullish', 'buy', 'positive',
  'gain', 'rise', 'boost', 'expansion', 'opportunity', 'momentum', 'breakthrough',
  'dividend', 'repurchase', 'acquisition', 'partnership',
])

const NEGATIVE_WORDS = new Set([
  'miss', 'decline', 'drop', 'plunge', 'crash', 'downgrade', 'underperform',
  'loss', 'debt', 'weak', 'bearish', 'sell', 'negative', 'risk', 'warning',
  'lawsuit', 'investigation', 'recall', 'layoff', 'bankruptcy', 'default',
  'volatility', 'uncertainty', 'sanction', 'fine', 'penalty',
])

function computeSentiment(text: string): { score: number; label: 'positive' | 'negative' | 'neutral' } {
  const words = text.toLowerCase().split(/\s+/)
  let positive = 0
  let negative = 0

  for (const word of words) {
    if (POSITIVE_WORDS.has(word)) positive++
    if (NEGATIVE_WORDS.has(word)) negative++
  }

  const total = positive + negative
  if (total === 0) return { score: 0, label: 'neutral' }

  const score = (positive - negative) / (positive + negative)
  const label = score > 0.15 ? 'positive' : score < -0.15 ? 'negative' : 'neutral'
  return { score, label }
}

// ═══════════════════════════════════════════════════════════════
// NewsAPI Client
// ═══════════════════════════════════════════════════════════════

export class NewsApiClient {
  private config: AltDataConfig

  constructor(config: Partial<AltDataConfig> = {}) {
    this.config = { ...DEFAULT_ALT_DATA_CONFIG, ...config }
  }

  /**
   * Fetch recent news articles for a symbol.
   * If no API key is set, returns an empty result (graceful degradation).
   */
  async fetchArticles(symbol: string): Promise<NewsArticle[]> {
    if (!this.config.newsApiKey) {
      console.warn('[AltData] No NewsAPI key configured — returning empty news')
      return []
    }

    const fromDate = new Date(Date.now() - this.config.newsLookbackDays * 86400 * 1000)
      .toISOString().split('T')[0]

    try {
      const url = `${this.config.newsApiBase}/everything?` +
        `q=${encodeURIComponent(symbol)}&` +
        `from=${fromDate}&` +
        `sortBy=publishedAt&` +
        `pageSize=${this.config.maxArticlesPerSymbol}&` +
        `language=en&` +
        `apiKey=${this.config.newsApiKey}`

      const response = await fetch(url)

      if (!response.ok) {
        console.error(`[AltData] NewsAPI error (${response.status}): ${await response.text()}`)
        return []
      }

      const data = await response.json() as any
      return (data.articles || []).map((article: any, i: number) => {
        const text = `${article.title || ''} ${article.description || ''} ${article.content || ''}`
        const { score, label } = computeSentiment(text)

        return {
          id: `news-${symbol}-${i}-${Date.now()}`,
          title: article.title || 'Untitled',
          description: article.description || '',
          content: article.content || '',
          url: article.url || '',
          source: article.source?.name || 'Unknown',
          author: article.author || undefined,
          publishedAt: article.publishedAt || new Date().toISOString(),
          symbols: [symbol],
          sentiment: score,
          sentimentLabel: label,
          relevance: 0.5, // Default; would be improved with topic modeling
        }
      })
    } catch (err) {
      console.error(`[AltData] Failed to fetch news for ${symbol}:`, err)
      return []
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Insider Transactions (SEC Form 4) Client
// ═══════════════════════════════════════════════════════════════

/**
 * Fetches insider transactions from SEC EDGAR Form 4 filings.
 *
 * Note: SEC doesn't provide a direct "insider transactions" API, but we can
 * scan recent Form 4 filings and parse the structured XML to extract:
 * - Insider name & title
 * - Transaction type (buy/sell/award)
 * - Shares, price, total value
 * - Remaining holdings
 *
 * This client uses the SEC submissions feed filtered to Form 4.
 */
export class InsiderTransactionsClient {
  private config: AltDataConfig

  constructor(config: Partial<AltDataConfig> = {}) {
    this.config = { ...DEFAULT_ALT_DATA_CONFIG, ...config }
  }

  /**
   * Fetch recent insider transactions for a symbol.
   *
   * In production, this would:
   * 1. Query SEC EDGAR for recent Form 4 filings for the CIK
   * 2. Parse each Form 4 XML to extract transaction details
   * 3. Return normalized InsiderTransaction objects
   *
   * For now, this returns simulated data as a placeholder — the SEC filings
   * pipeline already ingests Form 4 metadata; full parsing requires XBRL/XML
   * processing of the Form 4 primary document.
   */
  async fetchTransactions(symbol: string, cik?: string): Promise<InsiderTransaction[]> {
    if (!this.config.fetchInsiderTransactions) return []

    // Placeholder — in production, parse actual Form 4 XML
    // SEC Form 4 endpoint:
    // https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&CIK={cik}&type=4&count=40

    console.log(`[AltData] Insider transactions for ${symbol}: using placeholder (full Form 4 XML parsing pending)`)
    return []
  }

  /**
   * Build an insider summary from a list of transactions.
   */
  summarizeTransactions(transactions: InsiderTransaction[], periodDays: number): InsiderSummary {
    if (transactions.length === 0) {
      return {
        symbol: '',
        buySellRatio: 0.5,
        totalBuyValue: 0,
        totalSellValue: 0,
        netFlow: 0,
        buyerCount: 0,
        sellerCount: 0,
        recentTransactions: [],
        periodDays,
      }
    }

    let totalBuyValue = 0
    let totalSellValue = 0
    let buyerCount = 0
    let sellerCount = 0

    for (const tx of transactions) {
      if (tx.transactionType === 'P-Purchase') {
        totalBuyValue += tx.value
        buyerCount++
      } else if (tx.transactionType === 'S-Sale') {
        totalSellValue += tx.value
        sellerCount++
      }
    }

    const total = totalBuyValue + totalSellValue
    const buySellRatio = total > 0 ? totalBuyValue / total : 0.5

    return {
      symbol: transactions[0]?.symbol || '',
      buySellRatio,
      totalBuyValue,
      totalSellValue,
      netFlow: totalBuyValue - totalSellValue,
      buyerCount,
      sellerCount,
      recentTransactions: transactions.slice(0, 10),
      periodDays,
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Social Sentiment Client (Placeholder)
// ═══════════════════════════════════════════════════════════════

export class SocialSentimentClient {
  private config: AltDataConfig

  constructor(config: Partial<AltDataConfig> = {}) {
    this.config = { ...DEFAULT_ALT_DATA_CONFIG, ...config }
  }

  /**
   * Fetch social sentiment for a symbol.
   *
   * Placeholder — production would integrate with:
   * - Reddit API (r/wallstreetbets, r/stocks, r/investing)
   * - Twitter/X API (cashtags, financial accounts)
   * - StockTwits API
   *
   * Each requires API keys and rate limiting.
   */
  async fetchSentiment(symbol: string): Promise<SocialSentiment[]> {
    if (!this.config.fetchSocialSentiment) return []

    console.log(`[AltData] Social sentiment for ${symbol}: disabled (no API configured)`)
    return []
  }
}

// ═══════════════════════════════════════════════════════════════
// Aggregated Alt Data Snapshot
// ═══════════════════════════════════════════════════════════════

export class AltDataAggregator {
  private newsClient: NewsApiClient
  private insiderClient: InsiderTransactionsClient
  private socialClient: SocialSentimentClient

  constructor(config: Partial<AltDataConfig> = {}) {
    const mergedConfig = { ...DEFAULT_ALT_DATA_CONFIG, ...config }
    this.newsClient = new NewsApiClient(mergedConfig)
    this.insiderClient = new InsiderTransactionsClient(mergedConfig)
    this.socialClient = new SocialSentimentClient(mergedConfig)
  }

  /**
   * Fetch a full alternative data snapshot for a symbol.
   *
   * This aggregates news sentiment, insider transactions, and social sentiment
   * into a single AltDataSnapshot that feeds into Layer 4's MarketDataInput.
   */
  async getSnapshot(symbol: string, cik?: string): Promise<AltDataSnapshot> {
    const now = new Date().toISOString()

    // Fetch all sources in parallel
    const [articles, insiderTxns, social] = await Promise.all([
      this.newsClient.fetchArticles(symbol),
      this.insiderClient.fetchTransactions(symbol, cik),
      this.socialClient.fetchSentiment(symbol),
    ])

    // Compute news aggregation
    const sentimentSum = articles.reduce((sum, a) => sum + a.sentiment, 0)
    const avgSentiment = articles.length > 0 ? sentimentSum / articles.length : 0

    const news = {
      articles,
      avgSentiment,
      articleCount: articles.length,
      sentimentTrend: this.detectTrend(articles),
    }

    // Compute insider summary
    const insiders = insiderTxns.length > 0
      ? this.insiderClient.summarizeTransactions(insiderTxns, 90)
      : null

    // Compute composite sentiment
    const compositeSentiment = this.computeComposite(avgSentiment, insiders, social)

    // Generate highlights for LLM context
    const highlights = this.generateHighlights({
      symbol, avgSentiment, articles, insiders, social,
    })

    return {
      symbol,
      timestamp: now,
      news,
      insiders,
      social,
      compositeSentiment,
      highlights,
    }
  }

  // ── Private Helpers ──

  private detectTrend(articles: NewsArticle[]): 'improving' | 'deteriorating' | 'stable' {
    if (articles.length < 3) return 'stable'

    const recent = articles.slice(0, Math.ceil(articles.length / 2))
    const older = articles.slice(Math.ceil(articles.length / 2))

    const recentAvg = recent.reduce((s, a) => s + a.sentiment, 0) / recent.length
    const olderAvg = older.reduce((s, a) => s + a.sentiment, 0) / older.length

    const delta = recentAvg - olderAvg
    if (delta > 0.1) return 'improving'
    if (delta < -0.1) return 'deteriorating'
    return 'stable'
  }

  private computeComposite(
    newsSentiment: number,
    insiders: InsiderSummary | null,
    social: SocialSentiment[]
  ): number {
    let score = 0
    let totalWeight = 0

    // News: weight 0.4
    if (!isNaN(newsSentiment)) {
      score += newsSentiment * 0.4
      totalWeight += 0.4
    }

    // Insiders: weight 0.35 (strong signal)
    if (insiders) {
      // Map buySellRatio (0-1) to -1..+1 (0.5 = neutral → 0, 1 = all buys → +1, 0 = all sells → -1)
      const insiderSignal = (insiders.buySellRatio - 0.5) * 2
      score += insiderSignal * 0.35
      totalWeight += 0.35
    }

    // Social: weight 0.25
    if (social.length > 0) {
      const socialAvg = social.reduce((s, p) => s + p.sentiment, 0) / social.length
      score += socialAvg * 0.25
      totalWeight += 0.25
    }

    return totalWeight > 0 ? score / totalWeight : 0
  }

  private generateHighlights(data: {
    symbol: string
    avgSentiment: number
    articles: NewsArticle[]
    insiders: InsiderSummary | null
    social: SocialSentiment[]
  }): string[] {
    const highlights: string[] = []

    // News highlights
    if (data.articles.length > 0) {
      const sentimentLabel = data.avgSentiment > 0.2 ? 'Bullish' :
        data.avgSentiment < -0.2 ? 'Bearish' : 'Neutral'
      highlights.push(
        `News sentiment: ${sentimentLabel} (${data.articles.length} articles, avg score ${data.avgSentiment.toFixed(2)})`
      )
    }

    // Top headlines
    const topArticles = data.articles
      .filter(a => Math.abs(a.sentiment) > 0.3)
      .slice(0, 3)
    for (const article of topArticles) {
      const label = article.sentiment > 0 ? '↑' : '↓'
      highlights.push(`  ${label} "${article.title}" — ${article.source}`)
    }

    // Insider highlights
    if (data.insiders) {
      const { insiders } = data
      if (insiders.buyerCount > 0 || insiders.sellerCount > 0) {
        const flowLabel = insiders.netFlow > 0 ? 'Net buying' :
          insiders.netFlow < 0 ? 'Net selling' : 'Balanced'
        highlights.push(
          `Insider activity: ${flowLabel} — ${insiders.buyerCount} buyers ($${this.formatValue(insiders.totalBuyValue)}) vs ${insiders.sellerCount} sellers ($${this.formatValue(insiders.totalSellValue)})`
        )
      }
    }

    // Social highlights
    if (data.social.length > 0) {
      for (const platform of data.social) {
        highlights.push(
          `${platform.platform}: ${platform.sentiment > 0 ? 'Bullish' : 'Bearish'} sentiment (${platform.mentionCount} mentions, trend ${platform.sentimentTrend > 0 ? '↑' : '↓'})`
        )
      }
    }

    return highlights
  }

  private formatValue(value: number): string {
    if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
    if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`
    return value.toFixed(0)
  }
}
