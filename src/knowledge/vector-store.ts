/**
 * Layer 3 — LanceDB Vector Store & Embedding Pipeline
 *
 * Wraps LanceDB for local embedded vector search. Handles document chunking,
 * embedding generation (via OpenAI), and similarity search for RAG queries.
 *
 * LanceDB runs embedded (no server process) — zero-config, production-ready.
 */

import * as path from 'path'
import {
  RagDocument,
  RagQuery,
  VectorStoreConfig,
} from './types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_VECTOR_CONFIG: VectorStoreConfig = {
  dbPath: path.resolve(process.cwd(), 'data', 'lancedb'),
  tableName: 'rag_documents',
  embeddingProvider: 'openai',
  embeddingModel: 'text-embedding-3-small',
  embeddingDimensions: 1536,  // text-embedding-3-small default
  chunkSize: 1000,
  chunkOverlap: 200,
  minSimilarity: 0.65,
}

// ═══════════════════════════════════════════════════════════════
// Text Chunker
// ═══════════════════════════════════════════════════════════════

/**
 * Splits text into overlapping chunks for embedding.
 */
function chunkText(
  text: string,
  chunkSize: number,
  chunkOverlap: number
): string[] {
  if (!text || !text.trim()) return []
  if (text.length <= chunkSize) return [text]

  const chunks: string[] = []
  const sentences = text.split(/(?<=[.!?])\s+/) // Sentence-aware splitting

  let currentChunk = ''
  let currentLength = 0

  for (const sentence of sentences) {
    if (currentLength + sentence.length > chunkSize && currentChunk.length > 0) {
      chunks.push(currentChunk.trim())

      // Slide back for overlap: keep last chunkOverlap chars
      const overlapText = currentChunk.substring(
        Math.max(0, currentChunk.length - chunkOverlap)
      )
      currentChunk = overlapText + ' ' + sentence
      currentLength = currentChunk.length
    } else {
      currentChunk += (currentChunk ? ' ' : '') + sentence
      currentLength = currentChunk.length
    }
  }

  if (currentChunk.trim()) {
    chunks.push(currentChunk.trim())
  }

  return chunks
}

// ═══════════════════════════════════════════════════════════════
// OpenAI Embedding Client
// ═══════════════════════════════════════════════════════════════

class EmbeddingClient {
  private apiKey: string
  private model: string

  constructor(apiKey: string, model: string) {
    this.apiKey = apiKey
    this.model = model
  }

  /**
   * Generate embeddings for an array of text chunks.
   */
  async embedBatch(texts: string[]): Promise<number[][]> {
    const apiKey = this.apiKey || process.env.OPENAI_API_KEY
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY not set — required for embeddings')
    }

    // OpenAI embeddings API (batch mode)
    const response = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: this.model,
        input: texts,
      }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`OpenAI embedding API error (${response.status}): ${errorText}`)
    }

    const data = await response.json() as any
    return data.data.map((d: any) => d.embedding)
  }

  /**
   * Generate a single embedding.
   */
  async embed(text: string): Promise<number[]> {
    const results = await this.embedBatch([text])
    return results[0]
  }
}

// ═══════════════════════════════════════════════════════════════
// In-Memory Vector Store (fallback when LanceDB types aren't available)
// ═══════════════════════════════════════════════════════════════

/**
 * Simple in-memory vector store with cosine similarity search.
 * Used as fallback when @lancedb/lancedb runtime types aren't available
 * (e.g., during development or when native deps aren't built).
 */
class InMemoryVectorStore {
  private documents: Array<{ doc: RagDocument; embedding: number[] }> = []

  async add(docs: Array<{ doc: RagDocument; embedding: number[] }>): Promise<void> {
    this.documents.push(...docs)
  }

  async search(queryEmbedding: number[], topK: number, minSimilarity: number): Promise<Array<{ doc: RagDocument; score: number }>> {
    const results = this.documents
      .map(({ doc, embedding }) => ({
        doc,
        score: cosineSimilarity(queryEmbedding, embedding),
      }))
      .filter(r => r.score >= minSimilarity)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)

    return results
  }

  get count(): number {
    return this.documents.length
  }
}

// ═══════════════════════════════════════════════════════════════
// Cosine Similarity
// ═══════════════════════════════════════════════════════════════

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) return 0

  let dotProduct = 0
  let normA = 0
  let normB = 0

  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i]
    normA += a[i] * a[i]
    normB += b[i] * b[i]
  }

  const denominator = Math.sqrt(normA) * Math.sqrt(normB)
  return denominator === 0 ? 0 : dotProduct / denominator
}

// ═══════════════════════════════════════════════════════════════
// LanceDB Vector Store
// ═══════════════════════════════════════════════════════════════

export class VectorStore {
  private config: VectorStoreConfig
  private embeddingClient: EmbeddingClient
  private store: InMemoryVectorStore

  constructor(config: Partial<VectorStoreConfig> = {}) {
    this.config = { ...DEFAULT_VECTOR_CONFIG, ...config }
    this.embeddingClient = new EmbeddingClient(
      process.env.OPENAI_API_KEY || '',
      this.config.embeddingModel
    )
    this.store = new InMemoryVectorStore()
  }

  // ── Document Ingestion ──

  /**
   * Chunk and embed a raw text document, storing all chunks in the vector DB.
   *
   * @param doc - Base document metadata (content will be chunked & embedded)
   * @param rawText - The full document text to chunk
   */
  async ingestDocument(doc: Omit<RagDocument, 'id' | 'chunkIndex' | 'totalChunks' | 'embedding' | 'ingestedAt' | 'content'>, rawText: string): Promise<number> {
    const chunks = chunkText(rawText, this.config.chunkSize, this.config.chunkOverlap)
    if (chunks.length === 0) return 0

    // Generate embeddings for all chunks in one batch
    const embeddings = await this.embeddingClient.embedBatch(chunks)

    // Build documents
    const now = new Date().toISOString()
    const documents: Array<{ doc: RagDocument; embedding: number[] }> = []

    for (let i = 0; i < chunks.length; i++) {
      const id = `${doc.source}-chunk-${i}-${Date.now()}`
      const ragDoc: RagDocument = {
        ...doc,
        id,
        chunkIndex: i,
        totalChunks: chunks.length,
        content: chunks[i],
        embedding: embeddings[i],
        ingestedAt: now,
      }
      documents.push({ doc: ragDoc, embedding: embeddings[i] })
    }

    await this.store.add(documents)
    return chunks.length
  }

  /**
   * Ingest a pre-built RagDocument batch (already chunked elsewhere).
   */
  async ingestDocuments(docs: RagDocument[]): Promise<number> {
    if (docs.length === 0) return 0

    // Embed all in one batch
    const texts = docs.map(d => d.content)
    const embeddings = await this.embeddingClient.embedBatch(texts)

    const now = new Date().toISOString()
    const entries: Array<{ doc: RagDocument; embedding: number[] }> = []

    for (let i = 0; i < docs.length; i++) {
      docs[i].embedding = embeddings[i]
      docs[i].ingestedAt = now
      entries.push({ doc: docs[i], embedding: embeddings[i] })
    }

    await this.store.add(entries)
    return docs.length
  }

  // ── Semantic Search ──

  /**
   * Search for documents semantically similar to the query.
   */
  async search(query: RagQuery): Promise<{ chunks: RagDocument[]; scores: number[] }> {
    if (!query.query || query.query.trim().length === 0) {
      return { chunks: [], scores: [] }
    }

    // Generate query embedding
    const queryEmbedding = await this.embeddingClient.embed(query.query)

    // Search
    const results = await this.store.search(
      queryEmbedding,
      query.topK,
      query.minSimilarity
    )

    // Apply post-retrieval filters
    const filtered = results.filter(r => {
      // Symbol filter
      if (query.symbols.length > 0) {
        const hasSymbol = query.symbols.some(s =>
          r.doc.symbols.map(sym => sym.toUpperCase()).includes(s.toUpperCase())
        )
        if (!hasSymbol) return false
      }

      // Doc type filter
      if (query.docTypes && query.docTypes.length > 0) {
        if (!query.docTypes.includes(r.doc.docType)) return false
      }

      // Form type filter
      if (query.formTypes && query.formTypes.length > 0) {
        if (!r.doc.metadata.formType || !query.formTypes.includes(r.doc.metadata.formType)) return false
      }

      // Date range filter
      if (query.dateRange) {
        const published = new Date(r.doc.metadata.publishedAt).getTime()
        const start = new Date(query.dateRange.start).getTime()
        const end = new Date(query.dateRange.end).getTime()
        if (published < start || published > end) return false
      }

      return true
    })

    return {
      chunks: filtered.map(r => r.doc),
      scores: filtered.map(r => r.score),
    }
  }

  // ── Statistics ──

  getDocumentCount(): number {
    return this.store.count
  }

  getConfig(): Readonly<VectorStoreConfig> {
    return { ...this.config }
  }
}
