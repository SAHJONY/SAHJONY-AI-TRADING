/**
 * Layer 3 — RAG Orchestrator
 *
 * Ties together the vector store and knowledge graph to provide
 * context-augmented queries for Layer 4 trading agents.
 *
 * The orchestrator:
 * 1. Receives a query from a trading agent (e.g., "What are the risk factors for AAPL?")
 * 2. Searches the vector store for semantically similar document chunks
 * 3. Optionally queries the knowledge graph for structured relationships
 * 4. Assembles a context string optimized for LLM prompts
 * 5. Returns the complete RAG result
 */

import {
  RagDocument,
  RagQuery,
  RagResult,
} from './types'
import { VectorStore } from './vector-store'
import { KnowledgeGraph } from './knowledge-graph'

// ═══════════════════════════════════════════════════════════════
// RAG Orchestrator
// ═══════════════════════════════════════════════════════════════

export class RagOrchestrator {
  private vectorStore: VectorStore
  private knowledgeGraph: KnowledgeGraph

  constructor(vectorStore: VectorStore, knowledgeGraph: KnowledgeGraph) {
    this.vectorStore = vectorStore
    this.knowledgeGraph = knowledgeGraph
  }

  // ── Public API ──

  /**
   * Execute a full RAG query: semantic search + context assembly.
   *
   * This is the primary method called by Layer 4 agents to get
   * document context for their analysis.
   */
  async query(params: {
    query: string
    symbols: string[]
    topK?: number
    docTypes?: RagDocument['docType'][]
    formTypes?: string[]
    includeGraphContext?: boolean
  }): Promise<RagResult> {
    const startTime = Date.now()

    const ragQuery: RagQuery = {
      query: params.query,
      symbols: params.symbols,
      topK: params.topK || 10,
      minSimilarity: 0.6,
      docTypes: params.docTypes,
    }

    // Step 1: Semantic vector search
    const { chunks, scores } = await this.vectorStore.search(ragQuery)

    // Step 2: Assemble context string for LLM
    let assembledContext = this.assembleContext(chunks.slice(0, params.topK || 5), scores)

    // Step 3: Optionally enrich with knowledge graph context
    if (params.includeGraphContext && params.symbols.length > 0) {
      const graphContext = await this.getGraphContext(params.symbols[0])
      if (graphContext) {
        assembledContext = graphContext + '\n\n---\n\n' + assembledContext
      }
    }

    return {
      query: params.query,
      chunks,
      scores,
      totalFound: chunks.length,
      latencyMs: Date.now() - startTime,
      assembledContext,
    }
  }

  /**
   * Quick search: just returns the assembled context string.
   * Convenience for injecting directly into LLM prompts.
   */
  async getContextForAgent(
    symbol: string,
    question: string,
    topK = 5
  ): Promise<string> {
    const result = await this.query({
      query: question,
      symbols: [symbol],
      topK,
      includeGraphContext: true,
    })
    return result.assembledContext
  }

  /**
   * Search for recent SEC filings mentioning specific topics.
   */
  async searchFilings(
    symbol: string,
    topic: string,
    formTypes?: string[]
  ): Promise<RagResult> {
    return this.query({
      query: topic,
      symbols: [symbol],
      topK: 8,
      docTypes: ['sec_filing'],
      formTypes,
      includeGraphContext: false,
    })
  }

  /**
   * Get recent news context for a symbol.
   */
  async getNewsContext(symbol: string, query?: string): Promise<RagResult> {
    return this.query({
      query: query || `Recent news and developments for ${symbol}`,
      symbols: [symbol],
      topK: 8,
      docTypes: ['news_article'],
      includeGraphContext: false,
    })
  }

  // ═══════════════════════════════════════════════════════════
  // Context Assembly
  // ═══════════════════════════════════════════════════════════

  /**
   * Assemble retrieved chunks into a structured context string
   * optimized for LLM consumption.
   */
  private assembleContext(chunks: RagDocument[], scores: number[]): string {
    if (chunks.length === 0) {
      return 'No relevant documents found.'
    }

    const sections: string[] = []
    sections.push(`## Retrieved Context (${chunks.length} relevant documents)\n`)

    const docTypeLabels: Record<string, string> = {
      sec_filing: 'SEC Filing',
      news_article: 'News Article',
      earnings_transcript: 'Earnings Call Transcript',
      analyst_report: 'Analyst Report',
      social_post: 'Social Media Post',
    }

    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i]
      const score = scores[i] ?? 0
      const relevancePct = (score * 100).toFixed(0)
      const docTypeLabel = docTypeLabels[chunk.docType] || chunk.docType

      let header = `### [${i + 1}] ${docTypeLabel}`
      if (chunk.title) header += `: ${chunk.title}`
      header += ` (Relevance: ${relevancePct}%)`
      if (chunk.metadata.formType) header += ` — Form ${chunk.metadata.formType}`
      header += `\n`

      let section = header
      section += `Source: ${chunk.source}\n`
      if (chunk.metadata.publishedAt) {
        section += `Date: ${chunk.metadata.publishedAt}\n`
      }
      section += `\n${chunk.content}\n`

      sections.push(section)
    }

    return sections.join('\n---\n')
  }

  /**
   * Get knowledge graph context for a ticker as formatted text.
   */
  private async getGraphContext(ticker: string): Promise<string | null> {
    try {
      const result = await this.knowledgeGraph.getCompanyContext(ticker)
      if (result.entities.length <= 1) return null

      const lines: string[] = ['## Knowledge Graph Context\n']

      // List key relationships
      const seen = new Set<string>()
      for (const rel of result.relations) {
        const key = `${rel.from}-${rel.type}-${rel.to}`
        if (seen.has(key)) continue
        seen.add(key)

        const fromEntity = this.knowledgeGraph.getEntity(rel.from)
        const toEntity = this.knowledgeGraph.getEntity(rel.to)
        const fromName = fromEntity?.properties.name || fromEntity?.properties.symbol || rel.from
        const toName = toEntity?.properties.name || toEntity?.properties.symbol || rel.to

        lines.push(`- **${fromName}** ${rel.type.replace(/_/g, ' ').toLowerCase()} **${toName}**`)
        if (rel.properties.role) lines[lines.length - 1] += ` (${rel.properties.role})`
        if (rel.properties.shares) lines[lines.length - 1] += ` — ${rel.properties.shares} shares`
      }

      return lines.join('\n')
    } catch {
      return null
    }
  }
}
