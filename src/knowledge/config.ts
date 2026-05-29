/**
 * Layer 3 — Knowledge System Configuration
 *
 * Centralized configuration for the SEC pipeline, knowledge graph,
 * vector store, alternative data, and pipeline orchestration.
 * All values overridable via environment variables.
 */

import * as path from 'path'
import { KnowledgeSystemConfig, SecFormType } from './types'
import { DEFAULT_SEC_CONFIG } from './sec-client'
import { DEFAULT_GRAPH_CONFIG } from './knowledge-graph'
import { DEFAULT_VECTOR_CONFIG } from './vector-store'
import { DEFAULT_ALT_DATA_CONFIG } from './alt-data'

// ── Environment Helpers ──

const env = (key: string, fallback: string): string => process.env[key] || fallback
const envNum = (key: string, fallback: number): number => {
  const val = process.env[key]
  return val ? parseFloat(val) : fallback
}
const envBool = (key: string, fallback: boolean): boolean => {
  const val = process.env[key]
  return val !== undefined ? val === 'true' || val === '1' : fallback
}
const envList = (key: string, fallback: string[]): string[] => {
  const val = process.env[key]
  return val ? val.split(',').map(s => s.trim()).filter(Boolean) : fallback
}

// ── Default Knowledge System Config ──

export const DEFAULT_KNOWLEDGE_CONFIG: KnowledgeSystemConfig = {
  secEdgar: {
    ...DEFAULT_SEC_CONFIG,
    userAgent: env('SEC_USER_AGENT', 'TradingWorkforce/1.0 (contact@example.com)'),
    rateLimitPerSecond: envNum('SEC_RATE_LIMIT', 9),
    cacheDir: env('SEC_CACHE_DIR', path.resolve(process.cwd(), 'data', 'sec-cache')),
    factsCacheTtlMs: envNum('SEC_FACTS_CACHE_HOURS', 24) * 3600 * 1000,
    filingsCacheTtlMs: envNum('SEC_FILINGS_CACHE_HOURS', 1) * 3600 * 1000,
    watchedFormTypes: envList(
      'SEC_WATCHED_FORMS',
      ['10-K', '10-Q', '8-K', 'Form 4', '13F']
    ) as SecFormType[],
    lookbackHours: envNum('SEC_LOOKBACK_HOURS', 168),
    trackedTickers: envList('TRACKED_SYMBOLS', []),
  },

  vectorStore: {
    ...DEFAULT_VECTOR_CONFIG,
    dbPath: env('VECTOR_DB_PATH', path.resolve(process.cwd(), 'data', 'lancedb')),
    tableName: env('VECTOR_TABLE', 'rag_documents'),
    embeddingModel: env('EMBEDDING_MODEL', 'text-embedding-3-small'),
    embeddingDimensions: envNum('EMBEDDING_DIMENSIONS', 1536),
    chunkSize: envNum('CHUNK_SIZE', 1000),
    chunkOverlap: envNum('CHUNK_OVERLAP', 200),
    minSimilarity: envNum('MIN_SIMILARITY', 0.65),
  },

  knowledgeGraph: {
    ...DEFAULT_GRAPH_CONFIG,
    persist: envBool('GRAPH_PERSIST', true),
    persistDir: env('GRAPH_PERSIST_DIR', path.resolve(process.cwd(), 'data', 'knowledge-graph')),
    maxEntities: envNum('GRAPH_MAX_ENTITIES', 50000),
    maxRelations: envNum('GRAPH_MAX_RELATIONS', 200000),
  },

  altData: {
    ...DEFAULT_ALT_DATA_CONFIG,
    newsApiKey: env('NEWSAPI_KEY', ''),
    newsRefreshIntervalMs: envNum('NEWS_REFRESH_MINUTES', 15) * 60 * 1000,
    maxArticlesPerSymbol: envNum('MAX_ARTICLES_PER_SYMBOL', 20),
    newsLookbackDays: envNum('NEWS_LOOKBACK_DAYS', 3),
    fetchInsiderTransactions: envBool('FETCH_INSIDER_TRANSACTIONS', true),
    insiderLookbackDays: envNum('INSIDER_LOOKBACK_DAYS', 90),
    fetchSocialSentiment: envBool('FETCH_SOCIAL_SENTIMENT', false),
  },

  trackedSymbols: envList('TRACKED_SYMBOLS', []),
  refreshCron: env('REFRESH_CRON', '0 */6 * * *'),
  autoStart: envBool('AUTO_START_PIPELINE', false),
}

// ── Config Builder ──

/**
 * Build a KnowledgeSystemConfig with overrides.
 * Convenience for programmatic construction.
 */
export function buildKnowledgeConfig(
  overrides: Partial<KnowledgeSystemConfig> = {}
): KnowledgeSystemConfig {
  return {
    ...DEFAULT_KNOWLEDGE_CONFIG,
    ...overrides,
    secEdgar: { ...DEFAULT_KNOWLEDGE_CONFIG.secEdgar, ...overrides.secEdgar },
    vectorStore: { ...DEFAULT_KNOWLEDGE_CONFIG.vectorStore, ...overrides.vectorStore },
    knowledgeGraph: { ...DEFAULT_KNOWLEDGE_CONFIG.knowledgeGraph, ...overrides.knowledgeGraph },
    altData: { ...DEFAULT_KNOWLEDGE_CONFIG.altData, ...overrides.altData },
  }
}
