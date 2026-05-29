/**
 * Layer 3 — Knowledge Pipeline Orchestrator
 *
 * Ties together all Layer 3 components into a scheduled data pipeline:
 * - SEC EDGAR filing ingestion (every 6 hours)
 * - Knowledge graph construction from filings
 * - Vector store embedding of new documents
 * - Alternative data refresh (every 15 minutes)
 *
 * Provides a clean API for the TradingWorkforce to get enriched
 * market data context before running the Layer 4 debate.
 */

import {
  SecFiling,
  ParsedFiling,
  PipelineStatus,
  PipelineError,
  KnowledgeSystemConfig,
  CompanyFacts,
  AltDataSnapshot,
} from './types'
import { SecEdgarClient, DEFAULT_SEC_CONFIG } from './sec-client'
import { KnowledgeGraph, DEFAULT_GRAPH_CONFIG } from './knowledge-graph'
import { VectorStore, DEFAULT_VECTOR_CONFIG } from './vector-store'
import { RagOrchestrator } from './rag-orchestrator'
import { AltDataAggregator, DEFAULT_ALT_DATA_CONFIG } from './alt-data'

// ═══════════════════════════════════════════════════════════════
// Default System Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_SYSTEM_CONFIG: KnowledgeSystemConfig = {
  secEdgar: DEFAULT_SEC_CONFIG,
  vectorStore: DEFAULT_VECTOR_CONFIG,
  knowledgeGraph: DEFAULT_GRAPH_CONFIG,
  altData: DEFAULT_ALT_DATA_CONFIG,
  trackedSymbols: [],
  refreshCron: '0 */6 * * *', // Every 6 hours
  autoStart: false,
}

// ═══════════════════════════════════════════════════════════════
// Knowledge Pipeline
// ═══════════════════════════════════════════════════════════════

export class KnowledgePipeline {
  private config: KnowledgeSystemConfig
  private secClient: SecEdgarClient
  private graph: KnowledgeGraph
  private vectorStore: VectorStore
  private ragOrchestrator: RagOrchestrator
  private altAggregator: AltDataAggregator

  private status: PipelineStatus
  private running = false
  private cronInterval: NodeJS.Timeout | null = null

  constructor(config: Partial<KnowledgeSystemConfig> = {}) {
    this.config = { ...DEFAULT_SYSTEM_CONFIG, ...config }

    // Initialize sub-components
    this.secClient = new SecEdgarClient(this.config.secEdgar)
    this.graph = new KnowledgeGraph(this.config.knowledgeGraph)
    this.vectorStore = new VectorStore(this.config.vectorStore)
    this.ragOrchestrator = new RagOrchestrator(this.vectorStore, this.graph)
    this.altAggregator = new AltDataAggregator(this.config.altData)

    this.status = {
      running: false,
      lastRefresh: null,
      lastSecIngestion: null,
      lastAltDataRefresh: null,
      entityCount: 0,
      relationCount: 0,
      vectorDocCount: 0,
      filingsIngested: 0,
      recentErrors: [],
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Lifecycle
  // ═══════════════════════════════════════════════════════════

  /**
   * Start the knowledge pipeline. Begins periodic SEC ingestion and alt data refresh.
   */
  async start(): Promise<void> {
    if (this.running) return

    this.running = true
    this.status.running = true

    console.log('[KnowledgePipeline] Starting...')

    // Initial full refresh
    await this.refreshAll()

    // Schedule periodic refreshes using node-cron
    try {
      const cron = require('node-cron')
      this.cronInterval = cron.schedule(this.config.refreshCron, async () => {
        console.log('[KnowledgePipeline] Cron-triggered refresh')
        await this.refreshAll()
      })
      console.log(`[KnowledgePipeline] Cron scheduled: ${this.config.refreshCron}`)
    } catch {
      // node-cron may not be available — use simple interval as fallback
      console.log('[KnowledgePipeline] Using setInterval (node-cron not available)')
      this.cronInterval = setInterval(
        () => this.refreshAll(),
        6 * 60 * 60 * 1000 // 6 hours
      )
    }

    console.log('[KnowledgePipeline] Started')
  }

  /**
   * Stop the pipeline gracefully.
   */
  async stop(): Promise<void> {
    this.running = false
    this.status.running = false

    if (this.cronInterval) {
      clearInterval(this.cronInterval)
      this.cronInterval = null
    }

    await this.graph.shutdown()
    console.log('[KnowledgePipeline] Stopped')
  }

  // ═══════════════════════════════════════════════════════════
  // Full Refresh
  // ═══════════════════════════════════════════════════════════

  /**
   * Run a complete refresh cycle:
   * 1. Ingest new SEC filings
   * 2. Update knowledge graph
   * 3. Embed new documents in vector store
   */
  async refreshAll(): Promise<PipelineStatus> {
    console.log('[KnowledgePipeline] Running full refresh...')

    try {
      // Step 1: SEC ingestion
      await this.ingestSecFilings()

      // Step 2: Alt data refresh
      await this.refreshAltData()

      // Step 3: Update stats
      this.status.lastRefresh = new Date().toISOString()
      this.status.entityCount = this.graph.getStats().entityCount
      this.status.relationCount = this.graph.getStats().relationCount
      this.status.vectorDocCount = this.vectorStore.getDocumentCount()

    } catch (err) {
      this.recordError('refreshAll', err instanceof Error ? err.message : String(err))
    }

    return { ...this.status }
  }

  /**
   * Ingest SEC filings for all tracked symbols.
   */
  async ingestSecFilings(): Promise<number> {
    const filings = await this.secClient.fetchRecentFilings()
    console.log(`[KnowledgePipeline] Found ${filings.length} recent filings`)

    let ingested = 0

    for (const filing of filings) {
      try {
        // Step 1: Parse the filing
        const parsed = await this.secClient.fetchAndParseFiling(filing)
        if (!parsed) continue

        // Step 2: Update knowledge graph
        await this.updateGraphFromFiling(filing, parsed)

        // Step 3: Chunk and embed the filing text
        const chunksIngested = await this.vectorStore.ingestDocument(
          {
            symbols: [filing.ticker],
            docType: 'sec_filing',
            source: filing.filingUrl,
            title: `${filing.companyName} — Form ${filing.formType}`,
            metadata: {
              formType: filing.formType,
              publishedAt: filing.filingDate,
              filingDate: filing.filingDate,
              reportDate: filing.reportDate,
              cik: filing.cik,
            },
          },
          parsed.fullText
        )

        ingested += chunksIngested > 0 ? 1 : 0

      } catch (err) {
        this.recordError('ingestSecFilings', err instanceof Error ? err.message : String(err), filing.ticker)
      }
    }

    this.status.filingsIngested += ingested
    this.status.lastSecIngestion = new Date().toISOString()
    console.log(`[KnowledgePipeline] Ingested ${ingested} filings (${this.vectorStore.getDocumentCount()} total chunks)`)

    return ingested
  }

  // ═══════════════════════════════════════════════════════════
  // Knowledge Graph Construction
  // ═══════════════════════════════════════════════════════════

  /**
   * Update the knowledge graph from a parsed SEC filing.
   * Creates entities (Company, Person, Sector, Filing) and relationships.
   */
  private async updateGraphFromFiling(filing: SecFiling, parsed: ParsedFiling): Promise<void> {
    // 1. Ensure Company entity exists
    const companyId = `company-${filing.ticker.toUpperCase()}`
    const existingCompany = this.graph.getEntity(companyId)

    if (!existingCompany) {
      this.graph.upsertEntity({
        id: companyId,
        type: 'Company',
        labels: [filing.ticker.toUpperCase(), 'PublicCompany'],
        properties: {
          ticker: filing.ticker,
          cik: filing.cik,
          name: filing.companyName,
        },
        source: 'sec_edgar',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    }

    // 2. Create Filing entity
    const filingId = `filing-${filing.accessionNumber}`
    this.graph.upsertEntity({
      id: filingId,
      type: 'Filing',
      labels: [filing.formType, filing.ticker.toUpperCase()],
      properties: {
        accessionNumber: filing.accessionNumber,
        formType: filing.formType,
        filingDate: filing.filingDate,
        reportDate: filing.reportDate,
        ticker: filing.ticker,
        url: filing.filingUrl,
      },
      source: 'sec_edgar',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    })

    // 3. Link Filing → Company (FILED relationship)
    this.graph.addRelation({
      id: `rel-filed-${filing.accessionNumber}`,
      from: filingId,
      to: companyId,
      type: 'FILED',
      properties: {
        formType: filing.formType,
        filingDate: filing.filingDate,
      },
      source: 'sec_edgar',
      weight: 1.0,
      createdAt: new Date().toISOString(),
    })

    // 4. If XBRL financials extracted, create FinancialMetric entities
    if (parsed.xbrlData) {
      const metricId = `metric-${filing.ticker}-${filing.accessionNumber}`
      this.graph.upsertEntity({
        id: metricId,
        type: 'FinancialMetric',
        labels: ['XBRL', filing.ticker.toUpperCase()],
        properties: {
          ...parsed.xbrlData,
          ticker: filing.ticker,
          periodEnd: parsed.xbrlData.periodEnd,
        },
        source: 'sec_edgar',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })

      this.graph.addRelation({
        id: `rel-reported-${filing.accessionNumber}`,
        from: companyId,
        to: metricId,
        type: 'REPORTED',
        properties: { periodEnd: parsed.xbrlData.periodEnd },
        source: 'sec_edgar',
        weight: 1.0,
        createdAt: new Date().toISOString(),
      })
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Alternative Data
  // ═══════════════════════════════════════════════════════════

  /**
   * Refresh alternative data for all tracked symbols.
   */
  async refreshAltData(): Promise<Map<string, AltDataSnapshot>> {
    const snapshots = new Map<string, AltDataSnapshot>()

    for (const symbol of this.config.trackedSymbols) {
      try {
        const cik = this.secClient.resolveCik(symbol) || undefined
        const snapshot = await this.altAggregator.getSnapshot(symbol, cik)
        snapshots.set(symbol.toUpperCase(), snapshot)

        // Index news articles into vector store for RAG
        for (const article of snapshot.news.articles) {
          if (article.content || article.description) {
            const text = `${article.title}\n${article.description}\n${article.content}`
            await this.vectorStore.ingestDocument(
              {
                symbols: article.symbols,
                docType: 'news_article',
                source: article.source,
                title: article.title,
                metadata: {
                  publishedAt: article.publishedAt,
                  author: article.author,
                },
              },
              text
            )
          }
        }
      } catch (err) {
        this.recordError('refreshAltData', err instanceof Error ? err.message : String(err), symbol)
      }
    }

    this.status.lastAltDataRefresh = new Date().toISOString()
    return snapshots
  }

  /**
   * Get an alt data snapshot for a single symbol (on-demand).
   */
  async getAltSnapshot(symbol: string): Promise<AltDataSnapshot | null> {
    try {
      const cik = this.secClient.resolveCik(symbol) || undefined
      return await this.altAggregator.getSnapshot(symbol, cik)
    } catch (err) {
      this.recordError('getAltSnapshot', err instanceof Error ? err.message : String(err), symbol)
      return null
    }
  }

  // ═══════════════════════════════════════════════════════════
  // RAG Context for Layer 4
  // ═══════════════════════════════════════════════════════════

  /**
   * Get enriched context for a Layer 4 trading debate.
   *
   * This is the primary integration point: Layer 4 calls this before
   * launching a debate to get RAG-augmented context.
   */
  async getEnrichedMarketContext(symbol: string): Promise<{
    altSnapshot: AltDataSnapshot | null
    ragContext: string
    graphStats: { entityCount: number; relationCount: number }
  }> {
    // Fetch alt data and RAG context in parallel
    const [altSnapshot, ragContext] = await Promise.all([
      this.getAltSnapshot(symbol),
      this.ragOrchestrator.getContextForAgent(symbol, 'Key developments, risks, and opportunities', 5),
    ])

    return {
      altSnapshot,
      ragContext,
      graphStats: this.graph.getStats(),
    }
  }

  /**
   * Search filings for a specific topic.
   */
  async searchFilingsByTopic(symbol: string, topic: string) {
    return this.ragOrchestrator.searchFilings(symbol, topic)
  }

  // ═══════════════════════════════════════════════════════════
  // Company Facts (on-demand)
  // ═══════════════════════════════════════════════════════════

  /**
   * Get key financial metrics for a company from SEC company facts.
   */
  async getCompanyMetrics(ticker: string) {
    const facts = await this.secClient.fetchCompanyFacts(ticker)
    if (!facts) return null
    return this.secClient.extractKeyMetrics(facts)
  }

  // ═══════════════════════════════════════════════════════════
  // Status & Monitoring
  // ═══════════════════════════════════════════════════════════

  getStatus(): PipelineStatus {
    return { ...this.status }
  }

  isRunning(): boolean {
    return this.running
  }

  getGraph(): KnowledgeGraph {
    return this.graph
  }

  getVectorStore(): VectorStore {
    return this.vectorStore
  }

  getRagOrchestrator(): RagOrchestrator {
    return this.ragOrchestrator
  }

  /**
   * Add symbols to track.
   */
  addSymbols(...symbols: string[]): void {
    for (const symbol of symbols) {
      const upper = symbol.toUpperCase()
      if (!this.config.trackedSymbols.includes(upper)) {
        this.config.trackedSymbols.push(upper)
        this.config.secEdgar.trackedTickers.push(upper)
      }
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Internal Helpers
  // ═══════════════════════════════════════════════════════════

  private recordError(component: string, message: string, symbol?: string): void {
    const error: PipelineError = {
      timestamp: new Date().toISOString(),
      component,
      message,
      symbol,
      recovered: false,
    }

    this.status.recentErrors.push(error)

    // Keep only last 50 errors
    if (this.status.recentErrors.length > 50) {
      this.status.recentErrors = this.status.recentErrors.slice(-50)
    }

    console.error(`[KnowledgePipeline] ${component}${symbol ? ` (${symbol})` : ''}: ${message}`)
  }
}
