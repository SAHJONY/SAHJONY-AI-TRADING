/**
 * Layer 3 — Financial Knowledge Graph
 *
 * In-memory typed graph with entity and relation management, Cypher-like
 * query interface, and persistence to disk. Designed for financial use cases:
 * corporate structure, insider relationships, competitive dynamics, and
 * event tracking.
 *
 * Key design principles:
 * - Typed entities with strong property typing (not free-form JSON)
 * - Weighted, directed relations with provenance tracking
 * - Graph traversal queries (N-hop neighborhood)
 * - Persistence for crash recovery (no external DB dependency)
 */

import * as fs from 'fs'
import * as path from 'path'
import {
  GraphEntity,
  GraphRelation,
  EntityType,
  RelationType,
  GraphQueryResult,
  GraphQueryPattern,
  KnowledgeGraphConfig,
} from './types'

// ═══════════════════════════════════════════════════════════════
// Default Configuration
// ═══════════════════════════════════════════════════════════════

export const DEFAULT_GRAPH_CONFIG: KnowledgeGraphConfig = {
  persist: true,
  persistDir: path.resolve(process.cwd(), 'data', 'knowledge-graph'),
  maxEntities: 50_000,
  maxRelations: 200_000,
}

// ═══════════════════════════════════════════════════════════════
// Knowledge Graph Implementation
// ═══════════════════════════════════════════════════════════════

export class KnowledgeGraph {
  private entities: Map<string, GraphEntity> = new Map()
  private relations: Map<string, GraphRelation> = new Map()

  // Adjacency indices for fast traversal
  private outgoingEdges: Map<string, GraphRelation[]> = new Map()   // from → relations
  private incomingEdges: Map<string, GraphRelation[]> = new Map()   // to → relations

  // Lookup indices
  private byType: Map<EntityType, Set<string>> = new Map()
  private byLabel: Map<string, Set<string>> = new Map()
  private bySymbol: Map<string, Set<string>> = new Map()            // ticker → entity IDs
  private byCik: Map<string, string> = new Map()                    // CIK → entity ID

  private config: KnowledgeGraphConfig
  private dirty = false
  private saveTimeout: NodeJS.Timeout | null = null

  constructor(config: Partial<KnowledgeGraphConfig> = {}) {
    this.config = { ...DEFAULT_GRAPH_CONFIG, ...config }

    if (this.config.persist) {
      fs.mkdirSync(this.config.persistDir, { recursive: true })
      this.loadFromDisk()
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Entity Management
  // ═══════════════════════════════════════════════════════════

  /**
   * Add or update an entity in the graph.
   */
  upsertEntity(entity: GraphEntity): GraphEntity {
    const isNew = !this.entities.has(entity.id)

    entity.updatedAt = new Date().toISOString()
    if (isNew) {
      entity.createdAt = entity.updatedAt
    } else {
      // Deindex old values before updating, in case type/labels/symbol changed
      const existing = this.entities.get(entity.id)!
      this.deindexEntity(existing)
    }

    this.entities.set(entity.id, entity)

    // Update indices
    this.indexEntity(entity)

    // Prune if over capacity
    if (this.entities.size > this.config.maxEntities) {
      this.pruneEntities()
    }

    this.markDirty()
    return entity
  }

  /**
   * Get an entity by ID.
   */
  getEntity(id: string): GraphEntity | null {
    return this.entities.get(id) || null
  }

  /**
   * Find entities by type and optional property filters.
   */
  findEntities(type?: EntityType, properties?: Record<string, unknown>): GraphEntity[] {
    let candidateIds: Set<string>

    if (type) {
      candidateIds = this.byType.get(type) || new Set()
    } else {
      candidateIds = new Set(this.entities.keys())
    }

    if (!properties) {
      return [...candidateIds].map(id => this.entities.get(id)!)
    }

    // Filter by property values
    return [...candidateIds]
      .map(id => this.entities.get(id)!)
      .filter(entity =>
        Object.entries(properties).every(
          ([key, value]) => entity.properties[key] === value
        )
      )
  }

  /**
   * Find the company entity for a given ticker symbol.
   */
  findCompanyByTicker(ticker: string): GraphEntity | null {
    const ids = this.bySymbol.get(ticker.toUpperCase())
    if (!ids || ids.size === 0) return null

    // Prefer Company type
    for (const id of ids) {
      const entity = this.entities.get(id)
      if (entity?.type === 'Company') return entity
    }

    // Fallback: return first match
    const firstId = [...ids][0]
    return this.entities.get(firstId) || null
  }

  /**
   * Find the company entity for a given CIK.
   */
  findCompanyByCik(cik: string): GraphEntity | null {
    const id = this.byCik.get(cik)
    return id ? this.entities.get(id) || null : null
  }

  /**
   * Delete an entity and all its relations.
   */
  deleteEntity(id: string): boolean {
    const entity = this.entities.get(id)
    if (!entity) return false

    // Remove outgoing relations
    const outEdges = this.outgoingEdges.get(id) || []
    for (const rel of outEdges) {
      this.deleteRelation(rel.id)
    }

    // Remove incoming relations
    const inEdges = this.incomingEdges.get(id) || []
    for (const rel of inEdges) {
      this.deleteRelation(rel.id)
    }

    // Remove from indices
    this.deindexEntity(entity)
    this.entities.delete(id)
    this.outgoingEdges.delete(id)
    this.incomingEdges.delete(id)

    this.markDirty()
    return true
  }

  // ═══════════════════════════════════════════════════════════
  // Relation Management
  // ═══════════════════════════════════════════════════════════

  /**
   * Add a directed relation between two entities.
   */
  addRelation(relation: GraphRelation): GraphRelation {
    // Validate entities exist
    if (!this.entities.has(relation.from)) {
      throw new Error(`Source entity ${relation.from} not found`)
    }
    if (!this.entities.has(relation.to)) {
      throw new Error(`Target entity ${relation.to} not found`)
    }

    this.relations.set(relation.id, relation)

    // Update adjacency indices
    const outList = this.outgoingEdges.get(relation.from) || []
    outList.push(relation)
    this.outgoingEdges.set(relation.from, outList)

    const inList = this.incomingEdges.get(relation.to) || []
    inList.push(relation)
    this.incomingEdges.set(relation.to, inList)

    // Prune if over capacity
    if (this.relations.size > this.config.maxRelations) {
      this.pruneRelations()
    }

    this.markDirty()
    return relation
  }

  /**
   * Delete a relation.
   */
  deleteRelation(id: string): boolean {
    const relation = this.relations.get(id)
    if (!relation) return false

    // Remove from adjacency
    this.removeFromAdjacency(this.outgoingEdges, relation.from, id)
    this.removeFromAdjacency(this.incomingEdges, relation.to, id)

    this.relations.delete(id)
    this.markDirty()
    return true
  }

  /**
   * Get all relations from an entity (outgoing edges).
   */
  getOutgoingRelations(fromId: string, type?: RelationType): GraphRelation[] {
    const edges = this.outgoingEdges.get(fromId) || []
    return type ? edges.filter(r => r.type === type) : edges
  }

  /**
   * Get all relations to an entity (incoming edges).
   */
  getIncomingRelations(toId: string, type?: RelationType): GraphRelation[] {
    const edges = this.incomingEdges.get(toId) || []
    return type ? edges.filter(r => r.type === type) : edges
  }

  // ═══════════════════════════════════════════════════════════
  // Graph Queries (Cypher-like)
  // ═══════════════════════════════════════════════════════════

  /**
   * Execute a graph query pattern.
   *
   * Finds entities matching the `match` criteria, then traverses outward
   * by `traverseDepth` hops, collecting related entities and relations.
   */
  async query(pattern: GraphQueryPattern): Promise<GraphQueryResult> {
    const startTime = Date.now()

    // Step 1: Find starting entities
    const startEntities = this.findEntities(
      pattern.match.type,
      pattern.match.properties
    ).slice(0, pattern.limit)

    // Step 2: BFS traversal
    const visitedEntities = new Set<string>()
    const visitedRelations = new Set<string>()

    const queue: Array<{ entityId: string; depth: number }> = startEntities.map(e => ({
      entityId: e.id,
      depth: 0,
    }))

    for (const e of startEntities) {
      visitedEntities.add(e.id)
    }

    while (queue.length > 0) {
      const current = queue.shift()!
      if (current.depth >= pattern.traverseDepth) continue

      // Explore outgoing
      const outEdges = this.outgoingEdges.get(current.entityId) || []
      for (const rel of outEdges) {
        if (pattern.traversRelations?.length && !pattern.traversRelations.includes(rel.type)) continue
        if (!visitedRelations.has(rel.id)) {
          visitedRelations.add(rel.id)
        }
        if (!visitedEntities.has(rel.to) && visitedEntities.size < pattern.limit) {
          visitedEntities.add(rel.to)
          queue.push({ entityId: rel.to, depth: current.depth + 1 })
        }
      }

      // Explore incoming
      const inEdges = this.incomingEdges.get(current.entityId) || []
      for (const rel of inEdges) {
        if (pattern.traversRelations?.length && !pattern.traversRelations.includes(rel.type)) continue
        if (!visitedRelations.has(rel.id)) {
          visitedRelations.add(rel.id)
        }
        if (!visitedEntities.has(rel.from) && visitedEntities.size < pattern.limit) {
          visitedEntities.add(rel.from)
          queue.push({ entityId: rel.from, depth: current.depth + 1 })
        }
      }
    }

    const entities = [...visitedEntities].map(id => this.entities.get(id)!).filter(Boolean)
    const relations = [...visitedRelations].map(id => this.relations.get(id)!).filter(Boolean)

    return {
      entities,
      relations,
      durationMs: Date.now() - startTime,
    }
  }

  /**
   * Get the full neighborhood context for a company ticker.
   * Traverses: executives, competitors, suppliers, filings, insider trades.
   */
  async getCompanyContext(ticker: string): Promise<GraphQueryResult> {
    const company = this.findCompanyByTicker(ticker)
    if (!company) {
      return { entities: [], relations: [], durationMs: 0 }
    }

    return this.query({
      match: { properties: { symbol: ticker.toUpperCase() } },
      traverseDepth: 3,
      traversRelations: [
        'CEO_OF', 'CFO_OF', 'DIRECTOR_OF', 'EXECUTIVE_OF',
        'COMPETES_WITH', 'SUPPLIES_TO', 'OPERATES_IN',
        'FILED', 'BOUGHT_SHARES', 'SOLD_SHARES',
      ],
      limit: 100,
    })
  }

  // ═══════════════════════════════════════════════════════════
  // Statistics
  // ═══════════════════════════════════════════════════════════

  getStats() {
    return {
      entityCount: this.entities.size,
      relationCount: this.relations.size,
      types: [...this.byType.entries()].reduce((acc, [type, ids]) => {
        acc[type] = ids.size
        return acc
      }, {} as Record<string, number>),
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Persistence
  // ═══════════════════════════════════════════════════════════

  /**
   * Save the entire graph to disk (JSON snapshot).
   */
  saveToDisk(): void {
    if (!this.config.persist || !this.dirty) return

    try {
      const data = {
        entities: [...this.entities.values()],
        relations: [...this.relations.values()],
        savedAt: new Date().toISOString(),
      }

      const filePath = path.join(this.config.persistDir, 'graph.json')
      fs.writeFileSync(filePath, JSON.stringify(data))

      this.dirty = false
    } catch (err) {
      console.error('[KnowledgeGraph] Failed to save:', err)
    }
  }

  /**
   * Load graph from disk (if persisted).
   */
  private loadFromDisk(): void {
    try {
      const filePath = path.join(this.config.persistDir, 'graph.json')
      if (!fs.existsSync(filePath)) return

      const raw = fs.readFileSync(filePath, 'utf-8')
      const data = JSON.parse(raw)

      for (const entity of data.entities || []) {
        this.entities.set(entity.id, entity)
        this.indexEntity(entity)
      }

      for (const relation of data.relations || []) {
        this.relations.set(relation.id, relation)
        const outList = this.outgoingEdges.get(relation.from) || []
        outList.push(relation)
        this.outgoingEdges.set(relation.from, outList)

        const inList = this.incomingEdges.get(relation.to) || []
        inList.push(relation)
        this.incomingEdges.set(relation.to, inList)
      }
    } catch (err) {
      console.error('[KnowledgeGraph] Failed to load from disk:', err)
    }
  }

  // ═══════════════════════════════════════════════════════════
  // Internal Helpers
  // ═══════════════════════════════════════════════════════════

  private indexEntity(entity: GraphEntity): void {
    // Type index
    if (!this.byType.has(entity.type)) {
      this.byType.set(entity.type, new Set())
    }
    this.byType.get(entity.type)!.add(entity.id)

    // Label indices
    for (const label of entity.labels) {
      if (!this.byLabel.has(label)) {
        this.byLabel.set(label, new Set())
      }
      this.byLabel.get(label)!.add(entity.id)
    }

    // Symbol index
    if (entity.properties.symbol) {
      const sym = String(entity.properties.symbol).toUpperCase()
      if (!this.bySymbol.has(sym)) {
        this.bySymbol.set(sym, new Set())
      }
      this.bySymbol.get(sym)!.add(entity.id)
    }

    // CIK index
    if (entity.properties.cik) {
      this.byCik.set(String(entity.properties.cik), entity.id)
    }
  }

  private deindexEntity(entity: GraphEntity): void {
    this.byType.get(entity.type)?.delete(entity.id)
    for (const label of entity.labels) {
      this.byLabel.get(label)?.delete(entity.id)
    }
    if (entity.properties.symbol) {
      this.bySymbol.get(String(entity.properties.symbol).toUpperCase())?.delete(entity.id)
    }
    if (entity.properties.cik) {
      this.byCik.delete(String(entity.properties.cik))
    }
  }

  private removeFromAdjacency(map: Map<string, GraphRelation[]>, key: string, relId: string): void {
    const list = map.get(key)
    if (!list) return

    const filtered = list.filter(r => r.id !== relId)
    if (filtered.length === 0) {
      map.delete(key)
    } else {
      map.set(key, filtered)
    }
  }

  private pruneEntities(): void {
    // Remove the oldest entities (by updatedAt)
    const sorted = [...this.entities.values()]
      .sort((a, b) => new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime())

    const toRemove = sorted.slice(0, Math.floor(sorted.length * 0.1))
    for (const entity of toRemove) {
      this.deleteEntity(entity.id)
    }
  }

  private pruneRelations(): void {
    // Remove lowest-weight relations
    const sorted = [...this.relations.values()]
      .sort((a, b) => a.weight - b.weight)

    const toRemove = sorted.slice(0, Math.floor(sorted.length * 0.1))
    for (const rel of toRemove) {
      this.deleteRelation(rel.id)
    }
  }

  private markDirty(): void {
    this.dirty = true
    if (this.saveTimeout) clearTimeout(this.saveTimeout)
    this.saveTimeout = setTimeout(() => this.saveToDisk(), 5000) // Debounce saves
  }

  /**
   * Force immediate save (call before process exit).
   */
  async shutdown(): Promise<void> {
    if (this.saveTimeout) clearTimeout(this.saveTimeout)
    this.saveToDisk()
  }
}
