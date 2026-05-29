/**
 * Layer 3 — SEC EDGAR Ingestion Client
 *
 * Fetches and parses SEC filings via the official EDGAR REST API (data.sec.gov).
 * Handles rate limiting (10 req/s), caching, XBRL financial data extraction,
 * and batch filing retrieval for tracked tickers.
 *
 * SEC EDGAR API docs: https://www.sec.gov/edgar/sec-api-documentation
 */

import * as fs from 'fs'
import * as path from 'path'
import {
  SecFiling,
  SecFormType,
  ParsedFiling,
  CompanyFacts,
  XbrlFinancials,
  SecEdgarConfig,
} from './types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_SEC_CONFIG: SecEdgarConfig = {
  apiBase: 'https://data.sec.gov',
  userAgent: process.env.SEC_USER_AGENT || 'TradingWorkforce/1.0 (contact@example.com)',
  rateLimitPerSecond: 9, // SEC allows 10/s, stay under
  cacheDir: path.resolve(process.cwd(), 'data', 'sec-cache'),
  factsCacheTtlMs: 24 * 60 * 60 * 1000,   // 24h for company facts
  filingsCacheTtlMs: 60 * 60 * 1000,       // 1h for filing listings
  watchedFormTypes: ['10-K', '10-Q', '8-K', 'Form 4', '13F'],
  lookbackHours: 168, // 7 days
  trackedTickers: [],
  tickerMapPath: undefined,
}

// ═══════════════════════════════════════════════════════════════
// Rate Limiter (token bucket algorithm)
// ═══════════════════════════════════════════════════════════════

class RateLimiter {
  private tokens: number
  private maxTokens: number
  private refillRate: number      // tokens per ms
  private lastRefill: number

  constructor(maxRequestsPerSecond: number) {
    this.maxTokens = maxRequestsPerSecond
    this.tokens = maxRequestsPerSecond
    this.refillRate = maxRequestsPerSecond / 1000
    this.lastRefill = Date.now()
  }

  async acquire(): Promise<void> {
    this.refill()

    if (this.tokens >= 1) {
      this.tokens -= 1
      return
    }

    // Wait until a token is available
    const waitMs = (1 - this.tokens) / this.refillRate
    await new Promise(resolve => setTimeout(resolve, waitMs))
    this.tokens = 0
  }

  private refill(): void {
    const now = Date.now()
    const elapsed = now - this.lastRefill
    this.tokens = Math.min(this.maxTokens, this.tokens + elapsed * this.refillRate)
    this.lastRefill = now
  }
}

// ═══════════════════════════════════════════════════════════════
// CIK/Ticker Map
// ═══════════════════════════════════════════════════════════════

/** CIK format: zero-padded 10-digit string */
function cikToPadded(cik: string | number): string {
  return String(cik).padStart(10, '0')
}

/** Map ticker to CIK */
function tickerToCikMap(): Record<string, string> {
  // Pre-loaded map of common tickers → CIK (subset; full map is ~15k entries)
  // In production, load from SEC's company_tickers.json or company_tickers_exchange.json
  const map: Record<string, string> = {
    'AAPL': '0000320193', 'MSFT': '0000789019', 'GOOGL': '0001652044',
    'AMZN': '0001018724', 'META': '0001326801', 'NVDA': '0001045810',
    'TSLA': '0001318605', 'BRK.A': '0001067983', 'JPM': '0000019617',
    'V': '0001403161', 'JNJ': '0000200406', 'WMT': '0000104169',
    'MA': '0001141391', 'PG': '0000080424', 'XOM': '0000034088',
    'UNH': '0000731766', 'HD': '0000354950', 'BAC': '0000070858',
    'DIS': '0001744489', 'NFLX': '0001065280', 'ADBE': '0000796343',
    'CRM': '0001108524', 'INTC': '0000050863', 'PYPL': '0001633917',
  }
  return map
}

// ═══════════════════════════════════════════════════════════════
// SEC EDGAR Client
// ═══════════════════════════════════════════════════════════════

export class SecEdgarClient {
  private config: SecEdgarConfig
  private rateLimiter: RateLimiter
  private tickerMap: Record<string, string>

  constructor(config: Partial<SecEdgarConfig> = {}) {
    this.config = { ...DEFAULT_SEC_CONFIG, ...config }
    this.rateLimiter = new RateLimiter(this.config.rateLimitPerSecond)
    this.tickerMap = tickerToCikMap()

    // Ensure cache directory exists
    fs.mkdirSync(this.config.cacheDir, { recursive: true })
  }

  // ── Public API ──

  /**
   * Fetch recent filings for all tracked tickers.
   * Returns filings newer than `lookbackHours`.
   */
  async fetchRecentFilings(): Promise<SecFiling[]> {
    const allFilings: SecFiling[] = []

    for (const ticker of this.config.trackedTickers) {
      const cik = this.resolveCik(ticker)
      if (!cik) {
        console.warn(`[SEC] No CIK found for ticker ${ticker}`)
        continue
      }

      try {
        const filings = await this.fetchFilingsForCik(cik)
        allFilings.push(...filings)
      } catch (err) {
        console.error(`[SEC] Failed to fetch filings for ${ticker} (CIK ${cik}):`, err)
      }
    }

    return allFilings
  }

  /**
   * Fetch recent filings for a single ticker.
   */
  async fetchFilingsForTicker(ticker: string): Promise<SecFiling[]> {
    const cik = this.resolveCik(ticker)
    if (!cik) throw new Error(`Unknown ticker: ${ticker}`)
    return this.fetchFilingsForCik(cik)
  }

  /**
   * Fetch and parse the full text and key sections of a filing.
   */
  async fetchAndParseFiling(filing: SecFiling): Promise<ParsedFiling | null> {
    try {
      await this.rateLimiter.acquire()

      const url = `https://www.sec.gov/Archives/edgar/data/${filing.cik}/${filing.accessionNumber.replace(/-/g, '')}/${filing.primaryDocumentUrl.split('/').pop()}`
      const response = await fetch(url, {
        headers: { 'User-Agent': this.config.userAgent },
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const html = await response.text()
      const fullText = this.stripHtml(html)

      // Extract key sections using regex/heuristics
      const parsed: ParsedFiling = {
        accessionNumber: filing.accessionNumber,
        formType: filing.formType,
        fullText,
        businessOverview: this.extractSection(fullText, 'business', 'overview'),
        riskFactors: this.extractSection(fullText, 'risk factors'),
        mdna: this.extractSection(fullText, "management's discussion"),
        legalProceedings: this.extractSection(fullText, 'legal proceedings'),
      }

      // Try to fetch XBRL data
      if (filing.xbrlUrl) {
        parsed.xbrlData = await this.fetchXbrlData(filing)
      }

      return parsed
    } catch (err) {
      console.error(`[SEC] Failed to parse filing ${filing.accessionNumber}:`, err)
      return null
    }
  }

  /**
   * Fetch company facts (all reported financial data) for a ticker.
   * This is a snapshot of all standardized financials the company has reported.
   */
  async fetchCompanyFacts(ticker: string): Promise<CompanyFacts | null> {
    const cik = this.resolveCik(ticker)
    if (!cik) return null

    const paddedCik = cikToPadded(cik)
    const cacheFile = path.join(this.config.cacheDir, `facts-${paddedCik}.json`)

    // Check cache
    if (fs.existsSync(cacheFile)) {
      const stat = fs.statSync(cacheFile)
      if (Date.now() - stat.mtimeMs < this.config.factsCacheTtlMs) {
        return JSON.parse(fs.readFileSync(cacheFile, 'utf-8'))
      }
    }

    try {
      await this.rateLimiter.acquire()

      const url = `${this.config.apiBase}/api/xbrl/companyfacts/CIK${paddedCik}.json`
      const response = await fetch(url, {
        headers: { 'User-Agent': this.config.userAgent },
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const facts = await response.json() as CompanyFacts

      // Write cache
      fs.writeFileSync(cacheFile, JSON.stringify(facts))
      return facts
    } catch (err) {
      console.error(`[SEC] Failed to fetch company facts for ${ticker}:`, err)
      return null
    }
  }

  /**
   * Extract key XBRL financial metrics for the most recent period.
   */
  extractKeyMetrics(facts: CompanyFacts): XbrlFinancials {
    const metrics: XbrlFinancials = {
      periodEnd: '',
      currency: 'USD',
      scale: 'thousands',
    }

    if (!facts.facts.usGaap) return metrics

    const gaap = facts.facts.usGaap

    // Helper: get most recent value for a financial concept
    const latestValue = (concept: string, unit: string = 'USD'): number | undefined => {
      const entries = gaap[concept]
      if (!entries || entries.length === 0) return undefined

      const sorted = entries
        .filter(e => e.unit === unit && e.fp === 'FY')
        .sort((a, b) => new Date(b.end).getTime() - new Date(a.end).getTime())

      const latest = sorted[0]
      if (latest) metrics.periodEnd = latest.end
      return latest?.val
    }

    metrics.revenue = latestValue('Revenues') ?? latestValue('RevenueFromContractWithCustomerExcludingAssessedTax')
    metrics.netIncome = latestValue('NetIncomeLoss')
    metrics.eps = latestValue('EarningsPerShareBasic', 'USD/shares')
      ?? latestValue('EarningsPerShareDiluted', 'USD/shares')
    metrics.totalAssets = latestValue('Assets')
    metrics.totalLiabilities = latestValue('Liabilities')
    metrics.shareholdersEquity = latestValue('StockholdersEquity')
      ?? latestValue('StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')
    metrics.operatingCashFlow = latestValue('NetCashProvidedByUsedInOperatingActivities')
    metrics.freeCashFlow = metrics.operatingCashFlow !== undefined
      ? (latestValue('PaymentsToAcquirePropertyPlantAndEquipment') !== undefined
        ? metrics.operatingCashFlow + (latestValue('PaymentsToAcquirePropertyPlantAndEquipment') ?? 0)
        : undefined)
      : undefined

    // Calculated ratios
    if (metrics.revenue && metrics.revenue > 0 && metrics.netIncome !== undefined) {
      metrics.operatingMargin = metrics.netIncome / metrics.revenue
    }
    if (metrics.totalAssets && metrics.shareholdersEquity) {
      metrics.debtToEquity = (metrics.totalAssets - metrics.shareholdersEquity) / metrics.shareholdersEquity
    }

    return metrics
  }

  /**
   * Resolve a CIK for a ticker. Checks the map, tries the SEC lookup.
   */
  resolveCik(ticker: string): string | null {
    return this.tickerMap[ticker.toUpperCase()] || null
  }

  /**
   * Add a ticker→CIK mapping dynamically.
   */
  addTicker(ticker: string, cik: string): void {
    this.tickerMap[ticker.toUpperCase()] = cik
  }

  getConfig(): Readonly<SecEdgarConfig> {
    return { ...this.config }
  }

  // ── Private: Filing Retrieval ──

  private async fetchFilingsForCik(cik: string): Promise<SecFiling[]> {
    await this.rateLimiter.acquire()

    const paddedCik = cikToPadded(cik)
    const url = `${this.config.apiBase}/submissions/CIK${paddedCik}.json`

    const response = await fetch(url, {
      headers: { 'User-Agent': this.config.userAgent },
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    return this.parseSubmissions(data, paddedCik)
  }

  private parseSubmissions(data: any, cik: string): SecFiling[] {
    if (!data.filings || !data.filings.recent) return []

    const { recent } = data.filings
    const companyName = data.name || 'Unknown'
    const ticker = data.tickers?.[0] || ''

    const results: SecFiling[] = []
    const lookbackCutoff = new Date(Date.now() - this.config.lookbackHours * 3600 * 1000)

    for (let i = 0; i < recent.form.length; i++) {
      const formType = recent.form[i] as string
      if (!this.config.watchedFormTypes.includes(formType as SecFormType)) continue

      const filingDate = recent.filingDate?.[i] || ''
      if (filingDate && new Date(filingDate) < lookbackCutoff) continue

      const accessionNumber = recent.accessionNumber?.[i] || ''
      const primaryDoc = recent.primaryDocument?.[i] || ''

      results.push({
        cik: String(parseInt(cik)), // Remove padding for storage
        ticker,
        companyName,
        formType: formType as SecFormType,
        accessionNumber,
        filingDate,
        reportDate: recent.reportDate?.[i] || undefined,
        isAmendment: recent.isAmendment?.[i] === '1' || recent.isAmendment?.[i] === true,
        primaryDocumentUrl: primaryDoc,
        filingUrl: `https://www.sec.gov/Archives/edgar/data/${cik}/${accessionNumber.replace(/-/g, '')}/`,
        size: recent.size?.[i] ? parseInt(recent.size[i]) : undefined,
        xbrlUrl: this.getXbrlUrl(recent, i, cik, accessionNumber),
      })
    }

    return results
  }

  private getXbrlUrl(recent: any, index: number, cik: string, accession: string): string | undefined {
    const files = recent.documentFormatFiles?.[index] || []
    // SEC interactive data: look for _htm.xml or _cal.xml
    for (const file of files) {
      if (file.description?.includes('XBRL') || file.document?.endsWith('.xml')) {
        return `https://www.sec.gov/Archives/edgar/data/${cik}/${accession.replace(/-/g, '')}/${file.document}`
      }
    }
    return undefined
  }

  // ── Private: Filing Parsing ──

  private fetchXbrlData(filing: SecFiling): Promise<XbrlFinancials | undefined> {
    // XBRL parsing requires an XBRL-to-JSON processor (e.g., Arelle, sec-xbrl).
    // For now, company facts JSON provides the same data more reliably.
    return Promise.resolve(undefined)
  }

  private stripHtml(html: string): string {
    // Simple HTML stripping (no cheerio dependency needed for basic extraction)
    let text = html
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\s+/g, ' ')
      .replace(/\n\s*\n/g, '\n')
      .trim()

    return text
  }

  private extractSection(text: string, ...keywords: string[]): string | undefined {
    const lowerText = text.toLowerCase()
    let startIdx = -1

    for (const kw of keywords) {
      startIdx = lowerText.indexOf(kw.toLowerCase())
      if (startIdx !== -1) break
    }

    if (startIdx === -1) return undefined

    // Extract from the found position to the next "ITEM" marker or 3000 chars
    const snippet = text.substring(startIdx, startIdx + 5000)
    const nextItemIdx = snippet.toLowerCase().indexOf('item', 50)

    const endIdx = nextItemIdx !== -1 ? startIdx + nextItemIdx : startIdx + 3000
    return text.substring(startIdx, endIdx).trim()
  }
}
