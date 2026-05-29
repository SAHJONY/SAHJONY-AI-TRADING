/**
 * Layer 3 — Deep Intelligence & Knowledge Fusion Types
 *
 * Defines schemas for the SEC filing ingestion pipeline, knowledge graph
 * entities and relations, RAG retrieval documents, and alternative data feeds.
 */

// ═══════════════════════════════════════════════════════════════
// SEC EDGAR Filing Types
// ═══════════════════════════════════════════════════════════════

/** SEC filing form types relevant to trading */
export type SecFormType =
  | '10-K'    // Annual report
  | '10-Q'    // Quarterly report
  | '8-K'     // Current report (material events)
  | 'S-1'     // IPO registration
  | 'DEF 14A' // Proxy statement
  | '13F'     // Institutional holdings
  | 'Form 4'  // Insider transactions
  | 'SC 13G'  // Beneficial ownership (>5%)
  | 'SC 13D'  // Activist stake (>5% with intent to influence)

/** SEC filing metadata (from EDGAR submissions endpoint) */
export interface SecFiling {
  /** CIK (Central Index Key) — SEC's company identifier */
  cik: string
  /** Ticker symbol */
  ticker: string
  /** Company name */
  companyName: string
  /** Filing form type */
  formType: SecFormType
  /** SEC accession number (unique filing ID) */
  accessionNumber: string
  /** Filing date */
  filingDate: string
  /** Report period end date */
  reportDate?: string
  /** Whether the filing is an amendment */
  isAmendment: boolean
  /** Primary document URL (HTML/plaintext) */
  primaryDocumentUrl: string
  /** Filing detail page URL */
  filingUrl: string
  /** File size in bytes */
  size?: number
  /** Interactive data URL (XBRL) if available */
  xbrlUrl?: string
}

/** Parsed key sections from an SEC filing */
export interface ParsedFiling {
  accessionNumber: string
  formType: SecFormType
  /** Business overview / description */
  businessOverview?: string
  /** Risk factors section */
  riskFactors?: string
  /** Management discussion & analysis */
  mdna?: string
  /** Legal proceedings */
  legalProceedings?: string
  /** Selected financial statements (text extracted) */
  financialStatements?: string
  /** Recent events triggering 8-K filing */
  materialEvents?: string[]
  /** Executive compensation section */
  executiveCompensation?: string
  /** Related party transactions */
  relatedPartyTransactions?: string
  /** Full plaintext of the filing (may be large) */
  fullText: string
  /** Parsed XBRL financial data (if available) */
  xbrlData?: XbrlFinancials
}

/** Structured financial data extracted from XBRL */
export interface XbrlFinancials {
  revenue?: number
  revenueGrowth?: number
  netIncome?: number
  eps?: number
  totalAssets?: number
  totalLiabilities?: number
  shareholdersEquity?: number
  operatingCashFlow?: number
  freeCashFlow?: number
  grossMargin?: number
  operatingMargin?: number
  debtToEquity?: number
  currentRatio?: number
  /** Segment revenue breakdown */
  segmentRevenue?: Record<string, number>
  /** Fiscal period */
  periodEnd: string
  /** Currency */
  currency: string
  /** Unit scale (e.g., millions, thousands) */
  scale: string
}

/** SEC Company Facts response (snapshot of all reported financials) */
export interface CompanyFacts {
  cik: string
  entityName: string
  facts: {
    /** US GAAP taxonomy facts */
    usGaap?: Record<string, FactEntry[]>
    /** IFRS taxonomy facts */
    ifrs?: Record<string, FactEntry[]>
  }
}

export interface FactEntry {
  /** Unit (USD, shares, pure) */
  unit: string
  /** Value */
  val: number
  /** Fiscal year */
  fy?: number
  /** Fiscal period (Q1, Q2, Q3, Q4, FY) */
  fp?: string
  /** Form type of source filing */
  form: string
  /** Filing date */
  filed: string
  /** End date of reporting period */
  end: string
  /** Start date (for duration facts) */
  start?: string
  /** SEC frame (for standardized facts) */
  frame?: string
}

// ═══════════════════════════════════════════════════════════════
// Knowledge Graph Types
// ═══════════════════════════════════════════════════════════════

/** Node/entity types in the financial knowledge graph */
export type EntityType =
  | 'Company'
  | 'Person'         // Executive, board member, major shareholder
  | 'Sector'
  | 'Industry'
  | 'Filing'
  | 'FinancialMetric'
  | 'Product'
  | 'Competitor'
  | 'Supplier'
  | 'Customer'
  | 'Event'
  | 'SentimentSignal'

/** Graph entity (node) */
export interface GraphEntity {
  id: string
  type: EntityType
  labels: string[]
  properties: Record<string, unknown>
  /** Source of this entity (e.g., 'sec_edgar', 'newsapi', 'manual') */
  source: string
  createdAt: string
  updatedAt: string
}

/** Relationship between two entities */
export type RelationType =
  // Corporate structure
  | 'IS_SUBSIDIARY_OF'
  | 'PARENT_OF'
  | 'ACQUIRED_BY'
  // Employment
  | 'CEO_OF'
  | 'CFO_OF'
  | 'DIRECTOR_OF'
  | 'EXECUTIVE_OF'
  // Ownership & trading
  | 'OWNS'
  | 'BOUGHT_SHARES'
  | 'SOLD_SHARES'
  | 'HAS_MAJORITY_OWNER'
  // Filing relationships
  | 'FILED'
  | 'AMENDED'
  | 'DISCLOSES'
  // Industry & competition
  | 'OPERATES_IN'
  | 'COMPETES_WITH'
  | 'SUPPLIES_TO'
  | 'CUSTOMER_OF'
  | 'PARTNERS_WITH'
  // Financial
  | 'HAS_METRIC'
  | 'REPORTED'
  // Events & sentiment
  | 'INVOLVED_IN'
  | 'MENTIONS'
  | 'HAS_SENTIMENT'

/** Directed relationship (edge) between two entities */
export interface GraphRelation {
  id: string
  from: string      // Entity ID
  to: string        // Entity ID
  type: RelationType
  properties: Record<string, unknown>
  source: string
  weight: number    // 0.0–1.0; relevance/confidence of the relationship
  createdAt: string
}

/** Result of a knowledge graph query */
export interface GraphQueryResult {
  entities: GraphEntity[]
  relations: GraphRelation[]
  /** Query time in ms */
  durationMs: number
}

/** Cypher-like query pattern */
export interface GraphQueryPattern {
  /** Find entities matching these type/label/property filters */
  match: {
    type?: EntityType
    labels?: string[]
    properties?: Record<string, unknown>
  }
  /** Traverse outward by this many hops */
  traverseDepth: number
  /** Relation types to traverse (empty = all) */
  traversRelations?: RelationType[]
  /** Max entities to return */
  limit: number
}

// ═══════════════════════════════════════════════════════════════
// RAG Document & Vector Store Types
// ═══════════════════════════════════════════════════════════════

/** A chunked document stored in the vector DB for RAG */
export interface RagDocument {
  /** Unique ID */
  id: string
  /** Symbol(s) this document relates to */
  symbols: string[]
  /** Document type */
  docType: 'sec_filing' | 'news_article' | 'earnings_transcript' | 'analyst_report' | 'social_post'
  /** Source URL or origin */
  source: string
  /** Section heading or title */
  title: string
  /** The actual text content of this chunk */
  content: string
  /** Chunk index within the source document */
  chunkIndex: number
  /** Total chunks in the source document */
  totalChunks: number
  /** Metadata for filtering */
  metadata: {
    /** SEC form type (if applicable) */
    formType?: SecFormType
    /** Publication date (ISO) */
    publishedAt: string
    /** Filing date (if SEC) */
    filingDate?: string
    /** Report period end (if SEC) */
    reportDate?: string
    /** Company CIK (if SEC) */
    cik?: string
    /** Author / publisher */
    author?: string
    /** Language */
    language?: string
  }
  /** Pre-computed embedding (populated by LanceDB) */
  embedding?: number[]
  /** Timestamp of ingestion */
  ingestedAt: string
}

/** RAG query request from a Layer 4 agent */
export interface RagQuery {
  /** Natural language query */
  query: string
  /** Symbols to scope the query to */
  symbols: string[]
  /** Document types to include (empty = all) */
  docTypes?: RagDocument['docType'][]
  /** Maximum number of chunks to retrieve */
  topK: number
  /** Minimum similarity threshold (0.0–1.0) */
  minSimilarity: number
  /** Optional: SEC form types to filter by */
  formTypes?: SecFormType[]
  /** Optional: date range filter (ISO) */
  dateRange?: {
    start: string
    end: string
  }
}

/** RAG query result with retrieved context */
export interface RagResult {
  /** Original query */
  query: string
  /** Retrieved document chunks (sorted by relevance) */
  chunks: RagDocument[]
  /** Similarity scores (aligned with chunks) */
  scores: number[]
  /** Number of chunks found */
  totalFound: number
  /** Query latency */
  latencyMs: number
  /** Assembled context string ready for LLM prompts */
  assembledContext: string
}

// ═══════════════════════════════════════════════════════════════
// Alternative Data Types
// ═══════════════════════════════════════════════════════════════

/** News article from NewsAPI or similar */
export interface NewsArticle {
  id: string
  title: string
  description: string
  content: string
  url: string
  source: string
  author?: string
  publishedAt: string
  symbols: string[]
  /** Computed sentiment */
  sentiment: number         // -1.0 to 1.0
  sentimentLabel: 'positive' | 'negative' | 'neutral'
  relevance: number         // 0.0–1.0; how relevant to trading
}

/** Insider transaction (from SEC Form 4) */
export interface InsiderTransaction {
  id: string
  symbol: string
  companyName: string
  insiderName: string
  insiderTitle: string         // e.g., "Chief Executive Officer"
  isDirector: boolean
  isOfficer: boolean
  isTenPercentOwner: boolean
  transactionType: 'P-Purchase' | 'S-Sale' | 'A-Award' | 'G-Gift' | 'M-Exercise'
  securityType: string
  shares: number
  price: number
  value: number
  filingDate: string
  transactionDate: string
  /** Remaining shares owned after transaction */
  sharesOwnedAfter: number
}

/** Insider transaction summary for a symbol */
export interface InsiderSummary {
  symbol: string
  /** Ratio of insider buys to sells (0 = all sells, 1 = all buys, 0.5 = balanced) */
  buySellRatio: number
  /** Total value of insider buys (last 90 days) */
  totalBuyValue: number
  /** Total value of insider sells (last 90 days) */
  totalSellValue: number
  /** Net insider flow (buy value - sell value) */
  netFlow: number
  /** Number of insiders buying */
  buyerCount: number
  /** Number of insiders selling */
  sellerCount: number
  /** Recent transactions */
  recentTransactions: InsiderTransaction[]
  /** Period covered */
  periodDays: number
}

/** Social sentiment snapshot */
export interface SocialSentiment {
  symbol: string
  /** Platform */
  platform: string
  /** Overall sentiment score (-1.0 to 1.0) */
  sentiment: number
  /** Volume of mentions */
  mentionCount: number
  /** Trend vs previous period (sentiment delta) */
  sentimentTrend: number
  /** Trending topics/keywords */
  trendingTopics: string[]
  /** Timestamp */
  timestamp: string
}

/** Aggregated alternative data for a symbol */
export interface AltDataSnapshot {
  symbol: string
  timestamp: string
  /** News aggregation */
  news: {
    articles: NewsArticle[]
    avgSentiment: number
    articleCount: number
    sentimentTrend: 'improving' | 'deteriorating' | 'stable'
  }
  /** Insider transactions */
  insiders: InsiderSummary | null
  /** Social sentiment */
  social: SocialSentiment[]
  /** Aggregated composite score (-1.0 to +1.0) */
  compositeSentiment: number
  /** Key highlights for LLM context */
  highlights: string[]
}

// ═══════════════════════════════════════════════════════════════
// Pipeline Configuration Types
// ═══════════════════════════════════════════════════════════════

/** SEC EDGAR ingestion configuration */
export interface SecEdgarConfig {
  /** Base URL for SEC EDGAR API */
  apiBase: string
  /** User agent (required by SEC — must contain org name + email) */
  userAgent: string
  /** Max requests per second (SEC limit: 10/s) */
  rateLimitPerSecond: number
  /** Cache directory for filing data */
  cacheDir: string
  /** Cache TTL for company facts (ms) */
  factsCacheTtlMs: number
  /** Cache TTL for filing listings (ms) */
  filingsCacheTtlMs: number
  /** Which form types to ingest */
  watchedFormTypes: SecFormType[]
  /** How many hours back to look for new filings */
  lookbackHours: number
  /** Company tickers to track (empty = all) */
  trackedTickers: string[]
  /** CIK-to-ticker mapping URL or file */
  tickerMapPath?: string
}

/** Vector store configuration */
export interface VectorStoreConfig {
  /** LanceDB database path */
  dbPath: string
  /** Table name */
  tableName: string
  /** Embedding model provider */
  embeddingProvider: 'openai'
  /** Embedding model name */
  embeddingModel: string
  /** Embedding dimensionality */
  embeddingDimensions: number
  /** Chunk size for text splitting (characters) */
  chunkSize: number
  /** Chunk overlap (characters) */
  chunkOverlap: number
  /** Minimum similarity for search results */
  minSimilarity: number
}

/** Knowledge graph configuration */
export interface KnowledgeGraphConfig {
  /** Persist graph to disk */
  persist: boolean
  /** Persistence directory */
  persistDir: string
  /** Max entities before pruning least-recently-updated */
  maxEntities: number
  /** Max relations before pruning lowest-weight */
  maxRelations: number
}

/** Alternative data configuration */
export interface AltDataConfig {
  /** NewsAPI key */
  newsApiKey: string
  /** NewsAPI base URL */
  newsApiBase: string
  /** News refresh interval (ms, for cron) */
  newsRefreshIntervalMs: number
  /** Max news articles per symbol */
  maxArticlesPerSymbol: number
  /** Days to look back for news */
  newsLookbackDays: number
  /** Whether to fetch insider transactions */
  fetchInsiderTransactions: boolean
  /** SEC Form 4 lookback days */
  insiderLookbackDays: number
  /** Whether to fetch social sentiment */
  fetchSocialSentiment: boolean
}

/** Full Layer 3 system configuration */
export interface KnowledgeSystemConfig {
  /** SEC EDGAR pipeline */
  secEdgar: SecEdgarConfig
  /** Vector store / RAG */
  vectorStore: VectorStoreConfig
  /** Knowledge graph */
  knowledgeGraph: KnowledgeGraphConfig
  /** Alternative data */
  altData: AltDataConfig
  /** Symbols being tracked */
  trackedSymbols: string[]
  /** Cron expression for full data refresh */
  refreshCron: string
  /** Whether to auto-start the pipeline on init */
  autoStart: boolean
}

// ═══════════════════════════════════════════════════════════════
// Pipeline State Types
// ═══════════════════════════════════════════════════════════════

/** Current state of the knowledge pipeline */
export interface PipelineStatus {
  /** Is the pipeline running? */
  running: boolean
  /** Last successful full refresh */
  lastRefresh: string | null
  /** Last SEC EDGAR ingestion */
  lastSecIngestion: string | null
  /** Last alt data refresh */
  lastAltDataRefresh: string | null
  /** Total entities in knowledge graph */
  entityCount: number
  /** Total relations in knowledge graph */
  relationCount: number
  /** Total documents in vector store */
  vectorDocCount: number
  /** Total SEC filings ingested */
  filingsIngested: number
  /** Errors since last restart */
  recentErrors: PipelineError[]
}

export interface PipelineError {
  timestamp: string
  component: string
  message: string
  symbol?: string
  recovered: boolean
}
