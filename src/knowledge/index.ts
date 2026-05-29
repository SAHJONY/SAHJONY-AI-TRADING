/**
 * Layer 3 — Deep Intelligence & Knowledge Fusion
 *
 * Module index: exports everything needed for SEC filing ingestion,
 * knowledge graph queries, vector search (RAG), and alternative data.
 *
 * Architecture:
 *   1. Types → SEC filings, knowledge graph schema, RAG documents, alt data
 *   2. SEC Client → EDGAR ingestion with rate limiting & caching
 *   3. Knowledge Graph → In-memory typed graph with Cypher-like queries
 *   4. Vector Store → LanceDB-backed semantic search + embeddings
 *   5. RAG Orchestrator → Context assembly for Layer 4 agents
 *   6. Alt Data → NewsAPI sentiment, insider transactions, social sentiment
 *   7. Pipeline → Orchestrated data refresh with cron scheduling
 *   8. Config → Centralized configuration with env-var overrides
 *
 * Usage:
 *   import { KnowledgePipeline, buildKnowledgeConfig } from './knowledge'
 *   const pipeline = new KnowledgePipeline(buildKnowledgeConfig({
 *     trackedSymbols: ['AAPL', 'MSFT', 'GOOGL'],
 *   }))
 *   await pipeline.start()
 *   const context = await pipeline.getEnrichedMarketContext('AAPL')
 */

// ── Types ──
export type {
  // SEC
  SecFormType,
  SecFiling,
  ParsedFiling,
  XbrlFinancials,
  CompanyFacts,
  FactEntry,
  // Knowledge Graph
  EntityType,
  GraphEntity,
  RelationType,
  GraphRelation,
  GraphQueryResult,
  GraphQueryPattern,
  // RAG
  RagDocument,
  RagQuery,
  RagResult,
  // Alt Data
  NewsArticle,
  InsiderTransaction,
  InsiderSummary,
  SocialSentiment,
  AltDataSnapshot,
  // Pipeline Config
  SecEdgarConfig,
  VectorStoreConfig,
  KnowledgeGraphConfig,
  AltDataConfig,
  KnowledgeSystemConfig,
  // Pipeline Status
  PipelineStatus,
  PipelineError,
} from './types'

// ── SEC Client ──
export {
  SecEdgarClient,
  DEFAULT_SEC_CONFIG,
} from './sec-client'

// ── Knowledge Graph ──
export {
  KnowledgeGraph,
  DEFAULT_GRAPH_CONFIG,
} from './knowledge-graph'

// ── Vector Store ──
export {
  VectorStore,
  DEFAULT_VECTOR_CONFIG,
} from './vector-store'

// ── RAG Orchestrator ──
export {
  RagOrchestrator,
} from './rag-orchestrator'

// ── Alternative Data ──
export {
  NewsApiClient,
  InsiderTransactionsClient,
  SocialSentimentClient,
  AltDataAggregator,
  DEFAULT_ALT_DATA_CONFIG,
} from './alt-data'

// ── Pipeline Orchestrator ──
export {
  KnowledgePipeline,
  DEFAULT_SYSTEM_CONFIG,
} from './pipeline'

// ── Configuration ──
export {
  DEFAULT_KNOWLEDGE_CONFIG,
  buildKnowledgeConfig,
} from './config'
