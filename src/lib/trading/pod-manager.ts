// Pod Manager (Layer 5) — PM agent managing a strategy cluster
// Each pod runs debate squads on assigned assets, enforces hard stop-losses,
// allocates capital, and reports to the CIO (Layer 6).
import type {
  PodConfig, PodState, PodPerformance, PodRiskLimits,
  PMDecision, AssetDecision, CIODirective,
  AssetType, ConsensusAction, DebateState, Holding,
} from '@/types/trading'
import { DEFAULT_POD_RISK_LIMITS, DEFAULT_DEBATE_CONFIG, AGENT_ROLES } from '@/types/trading'
import { agentDebateOrchestrator } from './agent-debate'
import { metaLearning } from './meta-learning'

export class PodManager {
  private config: PodConfig
  private holdings: Holding[] = []
  private cashBalance: number
  private activityLog: string[] = []
  private pendingDirectives: CIODirective[] = []
  private originalRiskLimits: PodRiskLimits | null = null
  private activeRiskOverrides: { expiresAt?: string }[] = [] // track unexpired overrides
  private lastCycleTime: number = 0
  private cycleCount: number = 0
  private lastAssetDebates: Map<string, DebateState> = new Map() // persisted for reporting

  constructor(config: PodConfig, holdings: Holding[] = []) {
    this.config = config
    this.holdings = holdings
    this.cashBalance = config.allocatedCapital
    this.activityLog.push(`[${new Date().toISOString()}] Pod "${config.name}" initialized with $${config.allocatedCapital.toLocaleString()}`)
  }

  // ========== Core Pod Cycle ==========

  /** Run a full pod cycle: debate → aggregate → decide → execute */
  async runPodCycle(): Promise<PMDecision> {
    this.cycleCount++
    const startTime = Date.now()
    this.log(`[Cycle ${this.cycleCount}] Starting pod cycle`)

    // 1. Check for risk breaches first — if breached, liquidate
    if (this.isRiskBreached()) {
      this.log('⚠️ RISK BREACHED — forcing liquidation')
      return this.generateEmergencyDecision()
    }

    // 2. Run debates on all active assets
    this.lastAssetDebates = new Map()
    const activeAssets = this.config.assets.filter(a => a.active)

    for (const asset of activeAssets) {
      try {
        this.log(`  Running debate on ${asset.symbol}...`)
        const debate = await agentDebateOrchestrator.runDebate(asset.symbol, asset.assetType)
        this.lastAssetDebates.set(asset.symbol, debate)

        // Record debate in meta-learning
        if (debate.finalDecision) {
          metaLearning.recordDebate(
            asset.symbol,
            asset.assetType,
            debate.finalDecision,
            debate,
          )
        }

        this.log(`  ✓ ${asset.symbol}: ${debate.finalDecision?.action || 'HOLD'} (${((debate.finalDecision?.overallConfidence ?? 0) * 100).toFixed(0)}% confidence)`)
      } catch (error) {
        this.log(`  ✗ ${asset.symbol} debate failed: ${error instanceof Error ? error.message : error}`)
      }
    }

    // 3. Apply pending CIO directives (risk limit overrides, allocation shifts)
    this.applyCIODirectives()

    // 4. Build asset-level decisions from debates
    const assetDecisions = this.buildAssetDecisions(this.lastAssetDebates)

    // 5. Determine overall action
    const overallAction = this.determineOverallAction(assetDecisions)

    // 6. Calculate capital deployment
    const capitalToDeploy = this.calculateCapitalDeployment(assetDecisions, overallAction)

    // 7. Risk check on the proposed decisions
    const riskAssessment = this.assessRisk(assetDecisions, capitalToDeploy)

    // 8. Build the PM decision
    const decision: PMDecision = {
      podId: this.config.podId,
      timestamp: new Date().toISOString(),
      overallAction,
      assetDecisions,
      capitalToDeploy,
      reasoning: this.buildReasoning(assetDecisions, overallAction, riskAssessment),
      riskAssessment,
      cioDirectives: [...this.pendingDirectives],
      confidence: this.config.conviction,
    }

    this.log(`Decision: ${overallAction.toUpperCase()} | Deploy: $${capitalToDeploy.toLocaleString()} | Confidence: ${(this.config.conviction * 100).toFixed(0)}%`)

    this.lastCycleTime = Date.now() - startTime
    // Restore original risk limits only if ALL active overrides have expired
    const now = new Date()
    this.activeRiskOverrides = this.activeRiskOverrides.filter(
      o => !o.expiresAt || new Date(o.expiresAt) >= now // no expiresAt means permanent → keep
    )
    if (this.activeRiskOverrides.length === 0 && this.originalRiskLimits) {
      this.config.riskLimits = { ...this.originalRiskLimits }
      this.originalRiskLimits = null
      this.log('  Restored original risk limits (all overrides expired)')
    }
    this.pendingDirectives = [] // consumed

    return decision
  }

  // ========== Asset Decisions ==========

  private buildAssetDecisions(assetDebates: Map<string, DebateState>): AssetDecision[] {
    const decisions: AssetDecision[] = []

    for (const asset of this.config.assets) {
      if (!asset.active) continue

      const debate = assetDebates.get(asset.symbol)
      const defaultDecision: AssetDecision = {
        symbol: asset.symbol,
        assetType: asset.assetType,
        action: 'HOLD',
        allocationPct: 0,
        debate: debate || null,
        targetPrice: null,
        stopLoss: null,
        takeProfit: null,
        quantity: 0,
      }

      if (!debate || !debate.finalDecision) {
        decisions.push(defaultDecision)
        continue
      }

      const fd = debate.finalDecision
      let action = fd.action
      let overrideReason: string | undefined

      // PM override: if debate consensus is weak and PM conviction is high
      if (fd.overallConfidence < DEFAULT_DEBATE_CONFIG.minConfidenceForAuto) {
        // PM overrides: if conviction is high and there's signal, override to HOLD
        if (this.config.conviction > 0.7 && action !== 'HOLD') {
          overrideReason = `PM override: debate confidence (${(fd.overallConfidence * 100).toFixed(0)}%) below threshold (${(DEFAULT_DEBATE_CONFIG.minConfidenceForAuto * 100).toFixed(0)}%), PM overruling to HOLD`
          action = 'HOLD'
        }
      }

      // Apply conviction-based scaling to allocation
      const baseAllocation = asset.targetAllocationPct * fd.overallConfidence * this.config.conviction

      // Hard stop-loss enforcement: if any holding for this asset is at stop-loss, force SELL
      const assetHolding = this.holdings.find(h => h.symbol === asset.symbol)
      if (assetHolding && assetHolding.currentPrice) {
        const pnlPct = (assetHolding.currentPrice - assetHolding.averagePrice) / assetHolding.averagePrice
        if (pnlPct <= -this.config.riskLimits.hardStopLossPct) {
          action = 'SELL'
          overrideReason = `HARD STOP-LOSS TRIGGERED: position down ${(pnlPct * 100).toFixed(1)}% (limit: ${(this.config.riskLimits.hardStopLossPct * 100).toFixed(0)}%)`
        }
      }

      decisions.push({
        symbol: asset.symbol,
        assetType: asset.assetType,
        action,
        allocationPct: action === 'HOLD' ? 0 : baseAllocation,
        debate,
        overrideReason,
        targetPrice: fd.targetPrice,
        stopLoss: fd.stopLoss,
        takeProfit: fd.takeProfit,
        quantity: 0, // calculated by executeOrders
      })
    }

    return decisions
  }

  // ========== Risk Management ==========

  private isRiskBreached(): boolean {
    const perf = this.config.performance

    if (perf.currentDrawdown >= this.config.riskLimits.maxDrawdownPct) {
      this.log(`  Risk breach: drawdown ${(perf.currentDrawdown * 100).toFixed(1)}% >= limit ${(this.config.riskLimits.maxDrawdownPct * 100).toFixed(0)}%`)
      return true
    }

    if (Math.abs(perf.dailyPnl) >= this.config.riskLimits.dailyLossLimitPct * this.totalValue) {
      this.log(`  Risk breach: daily loss ${Math.abs(perf.dailyPnl)} >= limit ${this.config.riskLimits.dailyLossLimitPct * 100}%`)
      return true
    }

    return false
  }

  private assessRisk(decisions: AssetDecision[], capitalToDeploy: number): string {
    const warnings: string[] = []

    // Check single-asset concentration
    for (const d of decisions) {
      if (d.allocationPct > this.config.riskLimits.maxSingleAssetPct * this.totalValue) {
        warnings.push(`${d.symbol}: allocation ${(d.allocationPct * 100).toFixed(1)}% exceeds single-asset limit ${(this.config.riskLimits.maxSingleAssetPct * 100).toFixed(0)}%`)
      }
    }

    // Check total exposure
    const totalAllocation = decisions.reduce((sum, d) => sum + (d.action !== 'HOLD' ? d.allocationPct : 0), 0)
    if (totalAllocation > this.config.riskLimits.maxPositionSizePct) {
      warnings.push(`Total allocation ${(totalAllocation * 100).toFixed(1)}% exceeds limit ${(this.config.riskLimits.maxPositionSizePct * 100).toFixed(0)}%`)
    }

    return warnings.length > 0 ? warnings.join('; ') : 'All risk checks passed'
  }

  private generateEmergencyDecision(): PMDecision {
    return {
      podId: this.config.podId,
      timestamp: new Date().toISOString(),
      overallAction: 'liquidate',
      assetDecisions: this.config.assets.map(a => ({
        symbol: a.symbol,
        assetType: a.assetType,
        action: 'SELL' as ConsensusAction,
        allocationPct: 0,
        debate: null,
        quantity: 0,
        stopLoss: null,
        targetPrice: null,
        takeProfit: null,
        overrideReason: 'Risk limit breach — forced liquidation',
      })),
      capitalToDeploy: 0,
      reasoning: 'Emergency: risk limits breached. Liquidating all positions to preserve capital.',
      riskAssessment: 'CRITICAL: Risk limits breached',
      cioDirectives: [],
      confidence: 1.0,
    }
  }

  // ========== CIO Directives ==========

  receiveDirective(directive: CIODirective): void {
    this.pendingDirectives.push(directive)
    this.log(`Received CIO directive: [${directive.priority}] ${directive.type} — ${directive.instruction}`)
  }

  private applyCIODirectives(): void {
    for (const directive of this.pendingDirectives) {
      const now = new Date()
      // Skip expired directives
      if (directive.expiresAt && new Date(directive.expiresAt) < now) {
        this.log(`  Directive ${directive.id} expired — skipping`)
        continue
      }

      // Apply risk limit overrides (snapshot originals first for restoration)
      if (directive.riskLimitOverrides) {
        if (!this.originalRiskLimits) {
          this.originalRiskLimits = { ...this.config.riskLimits }
        }
        Object.assign(this.config.riskLimits, directive.riskLimitOverrides)
        this.activeRiskOverrides.push({ expiresAt: directive.expiresAt })
        this.log(`  Applied risk override: ${JSON.stringify(directive.riskLimitOverrides)}`)
      }

      // Critical directives force immediate action
      if (directive.priority === 'critical' && directive.type === 'liquidate') {
        this.config.assets.forEach(a => a.active = false)
        this.log(`  ⚠️ CIO critical directive: LIQUIDATE — all assets deactivated`)
      }

      if (directive.priority === 'critical' && directive.type === 'halt') {
        this.config.assets.forEach(a => a.active = false)
        this.log(`  ⚠️ CIO critical directive: HALT — all trading paused`)
      }
    }
  }

  // ========== Capital Allocation ==========

  private calculateCapitalDeployment(decisions: AssetDecision[], overallAction: string): number {
    if (overallAction === 'liquidate' || overallAction === 'hold') return 0

    const deployableCash = Math.min(this.cashBalance, this.config.allocatedCapital * 0.95)
    const targetDeploy = decisions
      .filter(d => d.action === 'BUY')
      .reduce((sum, d) => sum + this.totalValue * d.allocationPct, 0)

    // Don't deploy more than risk limits allow
    const maxDeploy = this.totalValue * this.config.riskLimits.maxPositionSizePct
    const currentExposure = this.holdings.reduce((sum, h) => sum + (h.currentPrice || h.averagePrice) * h.quantity, 0)

    return Math.min(
      targetDeploy,
      deployableCash,
      maxDeploy - currentExposure,
    )
  }

  // ========== Decision Helpers ==========

  private determineOverallAction(decisions: AssetDecision[]): PMDecision['overallAction'] {
    const buys = decisions.filter(d => d.action === 'BUY').length
    const sells = decisions.filter(d => d.action === 'SELL').length
    const total = decisions.length

    if (total === 0) return 'hold'
    if (sells === total) return 'liquidate'
    if (buys > sells && buys / total > 0.5) return 'deploy'
    if (sells > buys && sells / total > 0.5) return 'reduce'
    return 'hold'
  }

  private buildReasoning(decisions: AssetDecision[], overallAction: string, risk: string): string {
    const buyAssets = decisions.filter(d => d.action === 'BUY').map(d => d.symbol)
    const sellAssets = decisions.filter(d => d.action === 'SELL').map(d => d.symbol)
    const holdAssets = decisions.filter(d => d.action === 'HOLD').map(d => d.symbol)

    // Aggregate debate reasoning
    const debateReasoning = decisions
      .filter(d => d.debate?.finalDecision)
      .map(d =>
        `${d.symbol}: ${d.debate!.finalDecision!.action} ` +
        `(consensus confidence: ${(d.debate!.finalDecision!.overallConfidence * 100).toFixed(0)}%)` +
        `${d.overrideReason ? ' [OVERRIDDEN: ' + d.overrideReason + ']' : ''}`
      )
      .join('; ')

    return [
      `Pod "${this.config.name}" — Cycle ${this.cycleCount}`,
      `Action: ${overallAction.toUpperCase()}`,
      `Buy signals: ${buyAssets.length ? buyAssets.join(', ') : 'none'}`,
      `Sell signals: ${sellAssets.length ? sellAssets.join(', ') : 'none'}`,
      `Hold: ${holdAssets.length ? holdAssets.join(', ') : 'none'}`,
      `PM Conviction: ${(this.config.conviction * 100).toFixed(0)}%`,
      `Risk: ${risk}`,
      `Debates: ${debateReasoning}`,
    ].join('\n')
  }

  // ========== Pod Reporting ==========

  /** Generate a pod status report for the CIO */
  getPodReport(): PodState {
    // Convert Map<symbol, DebateState> to serializable Record
    const assetDebates: Record<string, DebateState> = {}
    for (const [symbol, debate] of this.lastAssetDebates) {
      assetDebates[symbol] = debate
    }

    return {
      pod: { ...this.config },
      assetDebates,
      holdings: [...this.holdings],
      cashBalance: this.cashBalance,
      totalValue: this.totalValue,
      riskBreached: this.isRiskBreached(),
      breachedLimits: this.getBreachedLimits(),
      latestDecision: null, // set by caller after cycle
      activityLog: [...this.activityLog.slice(-20)], // last 20 entries
    }
  }

  private getBreachedLimits(): string[] {
    const breached: string[] = []
    const perf = this.config.performance
    if (perf.currentDrawdown >= this.config.riskLimits.maxDrawdownPct) breached.push('maxDrawdown')
    if (Math.abs(perf.dailyPnl) >= this.config.riskLimits.dailyLossLimitPct * this.totalValue) breached.push('dailyLossLimit')
    return breached
  }

  // ========== State Updates ==========

  /** Update pod performance after a trade cycle */
  updatePerformance(metrics: Partial<PodPerformance>): void {
    Object.assign(this.config.performance, metrics)
  }

  /** Update pod's conviction based on recent performance */
  updateConviction(): void {
    const perf = this.config.performance
    // Conviction scales with win rate and recent P&L
    const winRateScore = perf.winRate || 0.5
    const pnlScore = perf.totalPnlPct > 0 ? Math.min(perf.totalPnlPct / 0.20, 1) : Math.max(perf.totalPnlPct / -0.20, 0)
    const sharpeBonus = perf.sharpeRatio > 0 ? Math.min(perf.sharpeRatio / 2, 0.3) : 0

    this.config.conviction = Math.min(
      Math.max(winRateScore * 0.4 + pnlScore * 0.4 + 0.2 + sharpeBonus, 0.1),
      1.0
    )
  }

  /** Accept CIO's capital allocation (may increase or decrease) */
  adjustCapital(newAllocation: number): void {
    const delta = newAllocation - this.config.allocatedCapital
    this.config.allocatedCapital = newAllocation
    this.cashBalance += delta
    this.log(`Capital adjusted by CIO: $${delta.toLocaleString()} → total: $${newAllocation.toLocaleString()}`)
  }

  // ========== Accessors ==========

  get podId(): string { return this.config.podId }
  get name(): string { return this.config.name }
  get allocatedCapital(): number { return this.config.allocatedCapital }
  get conviction(): number { return this.config.conviction }
  get performance(): PodPerformance { return this.config.performance }
  get riskLimits(): PodRiskLimits { return this.config.riskLimits }

  /** Total portfolio value: cash + holdings at market */
  get totalValue(): number {
    const holdingsValue = this.holdings.reduce(
      (sum, h) => sum + (h.currentPrice || h.averagePrice) * h.quantity, 0
    )
    return this.cashBalance + holdingsValue
  }

  // ========== Helpers ==========

  private log(message: string): void {
    const entry = `[${new Date().toISOString()}] ${message}`
    this.activityLog.push(entry)
    if (this.activityLog.length > 1000) {
      this.activityLog = this.activityLog.slice(-500)
    }
    console.log(`[Pod:${this.config.name}] ${message}`)
  }
}

// ========== Pod Factory ==========

export function createPod(
  podId: string,
  name: string,
  description: string,
  assets: { symbol: string; assetType: AssetType; targetAllocationPct: number }[],
  strategyIds: string[],
  allocatedCapital: number,
  riskLimits?: Partial<PodRiskLimits>,
): PodConfig {
  return {
    podId,
    name,
    description,
    assets: assets.map(a => ({ ...a, active: true })),
    strategyIds,
    riskLimits: { ...DEFAULT_POD_RISK_LIMITS, ...riskLimits },
    allocatedCapital,
    performance: {
      totalPnl: 0,
      totalPnlPct: 0,
      sharpeRatio: 0,
      maxDrawdown: 0,
      winRate: 0,
      totalTrades: 0,
      currentDrawdown: 0,
      dailyPnl: 0,
      weeklyPnl: 0,
      monthlyPnl: 0,
    },
    conviction: 0.5,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }
}
