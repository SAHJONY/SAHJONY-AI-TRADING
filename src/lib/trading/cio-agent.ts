// CIO Agent (Layer 6) — Chief Investment Officer meta-agent
// Oversees all Pod Managers, allocates capital across pods, manages risk budget,
// issues directives, and self-reflects to improve future decisions.
import type {
  PodConfig, PodState, PodPerformance, PodRiskLimits,
  PMDecision, CIODirective, CIODecision, CIOSelfReflection,
  PodCapitalAllocation, CIORiskAssessment, WorkforceState,
  RiskLevel,
} from '@/types/trading'
import { DEFAULT_CIO_CONFIG } from '@/types/trading'
import { PodManager } from './pod-manager'

// ========== CIO Scoring Helpers ==========

function scorePod(perf: PodPerformance): number {
  const winRateScore = perf.totalTrades > 0 ? Math.min(perf.winRate, 1) : 0.5
  const sharpeScore = perf.sharpeRatio > 0 ? Math.min(perf.sharpeRatio / 3, 1) : Math.max(perf.sharpeRatio / 3, 0)
  const drawdownPenalty = 1 - Math.min(perf.maxDrawdown, 1)
  const pnlScore = perf.totalPnlPct > 0 ? Math.min(perf.totalPnlPct / 0.20, 1) : Math.max(perf.totalPnlPct / -0.20, 0)

  return (
    winRateScore * 0.25 +
    sharpeScore * 0.25 +
    drawdownPenalty * 0.25 +
    pnlScore * 0.25
  )
}

function computeDrawdown(perf: PodPerformance): number {
  return Math.max(perf.currentDrawdown, perf.maxDrawdown)
}

// ========== CIO Agent ==========

export class CIOAgent {
  private pods: Map<string, PodManager> = new Map()
  private decisions: CIODecision[] = []
  private reflections: CIOSelfReflection[] = []
  private workforceLog: string[] = []
  private totalCapital: number
  private cycleCount: number = 0
  private activeDirectives: Map<string, CIODirective[]> = new Map() // podId → active directives
  private inactivityThresholdMs: number = 3600000 // 1 hour

  constructor(totalCapital: number = 100000) {
    this.totalCapital = totalCapital
    this.log(`[CIO] Initialized with $${totalCapital.toLocaleString()} total capital`)
  }

  // ========== Pod Management ==========

  /** Register a pod with the CIO */
  registerPod(pod: PodManager): void {
    this.pods.set(pod.podId, pod)
    this.log(`Registered pod: "${pod.name}" (${pod.podId}) with $${pod.allocatedCapital.toLocaleString()}`)
  }

  /** Remove a pod */
  removePod(podId: string): void {
    const pod = this.pods.get(podId)
    if (pod) {
      this.log(`Removing pod: "${pod.name}" — capital returned to pool`)
      this.pods.delete(podId)
      this.activeDirectives.delete(podId)
    }
  }

  /** Get all registered pods */
  getPods(): PodManager[] {
    return Array.from(this.pods.values())
  }

  // ========== Core CIO Cycle ==========

  /** Run a full CIO cycle: review pods → allocate → issue directives → reflect */
  async runCIOCycle(): Promise<CIODecision> {
    this.cycleCount++
    this.log(`[Cycle ${this.cycleCount}] CIO cycle starting`)

    // 1. Collect pod reports (run each pod's cycle)
    const podStates = await this.collectPodStates()

    // 2. Assess aggregate risk
    const riskAssessment = this.assessAggregateRisk(podStates)

    // 3. If aggregate risk is critical, halt everything
    if (riskAssessment.overallRisk === 'high' && riskAssessment.anyBreached) {
      this.log('⚠️ CRITICAL: Aggregate risk breached — issuing halt directives')
      const emergencyDecision = this.generateEmergencyDecision(podStates, riskAssessment)
      this.decisions.push(emergencyDecision)
      return emergencyDecision
    }

    // 4. Score pods and allocate capital
    const podAllocations = this.allocateCapital(podStates)

    // 5. Generate directives based on pod performance and risk
    const directives = this.generateDirectives(podStates, podAllocations, riskAssessment)

    // 6. Dispatch directives to pods (pass current allocations)
    this.dispatchDirectives(directives, podAllocations)

    // 7. Compute since-last-cycle performance
    const sinceLastCycle = this.computeCyclePerformance(podStates)

    // 8. Build CIO decision
    const decision: CIODecision = {
      id: `cio-${this.cycleCount}-${Date.now()}`,
      timestamp: new Date().toISOString(),
      podAllocations,
      directives,
      riskAssessment,
      macroOutlook: this.generateMacroOutlook(podStates),
      reasoning: this.buildCIOReasoning(podAllocations, directives, riskAssessment),
      sinceLastCycle,
    }

    this.decisions.push(decision)
    if (this.decisions.length > 500) this.decisions = this.decisions.slice(-500)

    // 9. Self-reflect periodically
    if (this.cycleCount % DEFAULT_CIO_CONFIG.reflectionInterval === 0 && this.decisions.length >= 2) {
      const reflection = this.selfReflect()
      this.reflections.push(reflection)
      this.log(`🧠 Self-reflection #${this.reflections.length}: ${reflection.impact.overall} (${reflection.adjustments.length} adjustments)`)
    }

    this.log(`CIO decision: ${podAllocations.length} pods allocated, ${directives.length} directives issued`)

    return decision
  }

  // ========== Pod State Collection ==========

  private async collectPodStates(): Promise<PodState[]> {
    const states: PodState[] = []

    for (const [, pod] of this.pods) {
      try {
        const decision = await pod.runPodCycle()
        const report = pod.getPodReport()
        report.latestDecision = decision
        states.push(report)
      } catch (error) {
        this.log(`⚠️ Pod "${pod.name}" cycle failed: ${error instanceof Error ? error.message : error}`)
        // Still include the pod state even if cycle failed
        states.push(pod.getPodReport())
      }
    }

    return states
  }

  // ========== Capital Allocation ==========

  private allocateCapital(podStates: PodState[]): PodCapitalAllocation[] {
    if (podStates.length === 0) return []

    // Score each pod
    const scored = podStates.map(state => ({
      state,
      score: scorePod(state.pod.performance),
    }))

    // Normalize scores to allocation percentages
    const totalScore = scored.reduce((sum, s) => sum + s.score, 0)
    const minAlloc = DEFAULT_CIO_CONFIG.minPodAllocationPct
    const maxAlloc = DEFAULT_CIO_CONFIG.maxPodAllocationPct

    const allocations: PodCapitalAllocation[] = scored.map(({ state, score }) => {
      let allocPct = totalScore > 0 ? score / totalScore : 1 / scored.length
      // Clamp between min and max
      allocPct = Math.max(minAlloc, Math.min(maxAlloc, allocPct))

      // Risk budget: higher-performing pods get more risk budget
      const riskBudget = Math.min(allocPct * 1.2, maxAlloc)

      // Assessment based on score
      let assessment: string
      if (score > 0.75) assessment = 'Strong performer — increase allocation'
      else if (score > 0.5) assessment = 'Performing adequately — maintain allocation'
      else if (score > 0.3) assessment = 'Underperforming — monitor closely, reduce allocation'
      else assessment = 'Weak performer — consider dissolution or capital withdrawal'

      return {
        podId: state.pod.podId,
        podName: state.pod.name,
        allocatedCapital: Math.round(this.totalCapital * allocPct),
        allocationPct: allocPct,
        riskBudget,
        performanceScore: score,
        assessment,
      }
    })

    // Normalize allocations to sum to 1.0, also recalculate riskBudget
    const totalAlloc = allocations.reduce((sum, a) => sum + a.allocationPct, 0)
    if (totalAlloc > 0) {
      for (const a of allocations) {
        a.allocationPct = a.allocationPct / totalAlloc
        a.allocatedCapital = Math.round(this.totalCapital * a.allocationPct)
        a.riskBudget = Math.min(a.allocationPct * 1.2, maxAlloc)
      }
    }

    return allocations
  }

  // ========== Directive Generation ==========

  private generateDirectives(
    podStates: PodState[],
    allocations: PodCapitalAllocation[],
    risk: CIORiskAssessment,
  ): CIODirective[] {
    const directives: CIODirective[] = []

    for (const state of podStates) {
      const alloc = allocations.find(a => a.podId === state.pod.podId)
      if (!alloc) continue

      // If allocation changed significantly, issue an allocation directive
      const currentAllocPct = state.pod.allocatedCapital / this.totalCapital
      const newAllocPct = alloc.allocationPct
      const drift = Math.abs(newAllocPct - currentAllocPct)

      if (drift > DEFAULT_CIO_CONFIG.rebalanceThreshold) {
        directives.push({
          id: `dir-alloc-${state.pod.podId}-${this.cycleCount}`,
          targetPodId: state.pod.podId,
          type: 'allocation',
          instruction: `Rebalance ${state.pod.name}: allocation from ${(currentAllocPct * 100).toFixed(1)}% to ${(newAllocPct * 100).toFixed(1)}%`,
          priority: drift > 0.15 ? 'high' : 'medium',
          reasoning: `Performance score: ${(alloc.performanceScore * 100).toFixed(0)}%. ${alloc.assessment}`,
          issuedAt: new Date().toISOString(),
        })
      }

      // Risk directives for high-risk pods
      if (state.riskBreached) {
        directives.push({
          id: `dir-risk-${state.pod.podId}-${this.cycleCount}`,
          targetPodId: state.pod.podId,
          type: 'risk',
          instruction: `Risk limits breached: ${state.breachedLimits.join(', ')}. Tighten risk controls immediately.`,
          riskLimitOverrides: {
            maxPositionSizePct: state.pod.riskLimits.maxPositionSizePct * 0.5,
          },
          priority: 'critical',
          reasoning: `Breached limits: ${state.breachedLimits.join(', ')}`,
          issuedAt: new Date().toISOString(),
        })
      }

      // Performance-based directives
      if (alloc.performanceScore < 0.3 && state.pod.performance.totalTrades > 5) {
        directives.push({
          id: `dir-review-${state.pod.podId}-${this.cycleCount}`,
          targetPodId: state.pod.podId,
          type: 'strategy',
          instruction: `Underperformance alert: ${state.pod.name} score ${(alloc.performanceScore * 100).toFixed(0)}%. Review strategy within 24h or face capital reduction.`,
          priority: 'high',
          reasoning: `Performance score ${(alloc.performanceScore * 100).toFixed(0)}% below threshold. ${alloc.assessment}`,
          issuedAt: new Date().toISOString(),
          expiresAt: new Date(Date.now() + 24 * 3600000).toISOString(),
        })
      }
    }

    // Global risk halt if overall risk is too high
    if (risk.overallRisk === 'high' && risk.anyBreached) {
      for (const state of podStates) {
        directives.push({
          id: `dir-halt-${state.pod.podId}-${this.cycleCount}`,
          targetPodId: state.pod.podId,
          type: 'halt',
          instruction: `GLOBAL HALT: Aggregate drawdown (${(risk.totalDrawdown * 100).toFixed(1)}%) exceeds CIO limit. All trading paused.`,
          priority: 'critical',
          reasoning: `Total drawdown: ${(risk.totalDrawdown * 100).toFixed(1)}% > limit ${(DEFAULT_CIO_CONFIG.maxDrawdownBeforeHalt * 100).toFixed(0)}%`,
          issuedAt: new Date().toISOString(),
        })
      }
    }

    return directives
  }

  private dispatchDirectives(directives: CIODirective[], podAllocations: PodCapitalAllocation[]): void {
    for (const directive of directives) {
      const pod = this.pods.get(directive.targetPodId)
      if (pod) {
        pod.receiveDirective(directive)

        // Apply allocation changes
        if (directive.type === 'allocation') {
          const podAlloc = podAllocations.find(a => a.podId === directive.targetPodId)
          if (podAlloc) {
            pod.adjustCapital(podAlloc.allocatedCapital)
          }
        }
      }
    }
  }

  // ========== Override / Veto ==========

  /** CIO veto: override a pod's decision entirely */
  overridePodDecision(podId: string, reason: string): boolean {
    const pod = this.pods.get(podId)
    if (!pod) return false

    pod.receiveDirective({
      id: `dir-veto-${podId}-${Date.now()}`,
      targetPodId: podId,
      type: 'halt',
      instruction: `CIO VETO: ${reason}. All pod trading halted until further review.`,
      priority: 'critical',
      reasoning: reason,
      issuedAt: new Date().toISOString(),
    })

    this.log(`🚫 CIO VETO on pod "${pod.name}": ${reason}`)
    return true
  }

  // ========== Risk Assessment ==========

  private assessAggregateRisk(podStates: PodState[]): CIORiskAssessment {
    const totalValue = podStates.reduce((sum, s) => sum + s.totalValue, 0)
    const totalDailyPnl = podStates.reduce((sum, s) => sum + s.pod.performance.dailyPnl, 0)
    const totalDrawdown = podStates.length > 0
      ? podStates.reduce((sum, s) => sum + computeDrawdown(s.pod.performance), 0) / podStates.length
      : 0

    // Simple VaR approximation
    const var95 = totalValue * 0.02 * 1.645 // 2% daily vol, 95% confidence
    const cvar95 = var95 * 1.4 // CVaR ≈ VaR * 1.4

    // Cross-pod correlations (simplified)
    const podCorrelations: { podA: string; podB: string; correlation: number }[] = []
    const podList = podStates.map(s => s.pod)
    for (let i = 0; i < podList.length; i++) {
      for (let j = i + 1; j < podList.length; j++) {
        // Simplified correlation based on asset type overlap
        const podAAssets = new Set(podList[i].assets.map(a => a.assetType))
        const podBAssets = new Set(podList[j].assets.map(a => a.assetType))
        const overlap = [...podAAssets].filter(a => podBAssets.has(a)).length
        const correlation = overlap / Math.max(podAAssets.size, podBAssets.size)

        podCorrelations.push({
          podA: podList[i].podId,
          podB: podList[j].podId,
          correlation: Math.round(correlation * 100) / 100,
        })
      }
    }

    // Warnings
    const warnings: string[] = []
    const anyBreached = podStates.some(s => s.riskBreached)
    const highCorr = podCorrelations.filter(c => c.correlation > 0.7)
    if (highCorr.length > 0) {
      warnings.push(`High inter-pod correlation detected: ${highCorr.map(c => `${c.podA}↔${c.podB}`).join(', ')}`)
    }

    let overallRisk: RiskLevel = 'low'
    if (totalDrawdown > 0.15 || anyBreached) overallRisk = 'high'
    else if (totalDrawdown > 0.08) overallRisk = 'medium'

    return {
      totalPortfolioValue: totalValue,
      totalDrawdown,
      totalDailyPnl,
      var95,
      cvar95,
      podCorrelations,
      overallRisk,
      anyBreached,
      warnings,
    }
  }

  private generateEmergencyDecision(podStates: PodState[], risk: CIORiskAssessment): CIODecision {
    return {
      id: `cio-emergency-${Date.now()}`,
      timestamp: new Date().toISOString(),
      podAllocations: podStates.map(s => ({
        podId: s.pod.podId,
        podName: s.pod.name,
        allocatedCapital: 0,
        allocationPct: 0,
        riskBudget: 0,
        performanceScore: 0,
        assessment: 'Emergency halt — capital frozen',
      })),
      directives: this.generateDirectives(podStates, [], risk),
      riskAssessment: risk,
      macroOutlook: 'Emergency: risk limits breached. All trading halted.',
      reasoning: `CRITICAL: Aggregate risk assessment shows ${risk.overallRisk} risk with breaches. All pods halted to preserve capital.`,
      sinceLastCycle: this.computeCyclePerformance(podStates),
    }
  }

  // ========== Self-Reflection ==========

  /** Analyze past CIO decisions to identify patterns and improve */
  selfReflect(): CIOSelfReflection {
    const recentDecisions = this.decisions.slice(-DEFAULT_CIO_CONFIG.reflectionInterval)
    if (recentDecisions.length < 2) {
      return this.emptyReflection('cio-empty')
    }

    const strengths: string[] = []
    const weaknesses: string[] = []
    const patterns: string[] = []
    const lessons: string[] = []
    const adjustments: CIOSelfReflection['adjustments'] = []

    // Analyze pod allocation accuracy — did we give more capital to winners?
    const podScoreSum = new Map<string, { sum: number; cycles: number }>()
    for (const decision of recentDecisions) {
      for (const alloc of decision.podAllocations) {
        const current = podScoreSum.get(alloc.podId) ?? { sum: 0, cycles: 0 }
        current.sum += alloc.performanceScore
        current.cycles++
        podScoreSum.set(alloc.podId, current)
      }
    }

    // Find the best and worst allocation decisions (using average score per cycle)
    const scoreEntries = [...podScoreSum.entries()].map(([podId, { sum, cycles }]) => ({
      podId,
      avgScore: cycles > 0 ? sum / cycles : 0,
    }))
    const sortedPods = scoreEntries.sort((a, b) => b.avgScore - a.avgScore)
    if (sortedPods.length >= 2) {
      const bestPod = sortedPods[0]
      const worstPod = sortedPods[sortedPods.length - 1]

      if (bestPod.avgScore > 0.6) {
        strengths.push(`Correctly allocated capital to high-performing pods like ${bestPod.podId}`)
        lessons.push('Continue allocating to pods with strong risk-adjusted returns')
      }

      if (worstPod.avgScore < 0.4) {
        weaknesses.push(`Continued allocating to underperforming pod ${worstPod.podId}`)
        adjustments.push({
          type: 'allocation',
          description: `Reduce or eliminate allocation to ${worstPod.podId} — consistently underperforms`,
          confidence: 0.8,
        })
      }
    }

    // Pattern: check if risk assessment was accurate
    const breaches = recentDecisions.filter(d => d.riskAssessment.anyBreached).length
    if (breaches > 0) {
      weaknesses.push(`Risk breaches occurred in ${breaches}/${recentDecisions.length} recent cycles`)
      patterns.push('Risk limits may be too loose — breaches occurring regularly')
      lessons.push('Tighten risk limits proactively before breaches occur')
      adjustments.push({
        type: 'risk',
        description: 'Reduce maxDrawdownPct from current levels to create earlier warning buffer',
        confidence: 0.85,
      })
    } else {
      strengths.push('Risk management effective — no breaches in recent cycles')
    }

    // Pattern: diversification check
    const podCount = this.pods.size
    if (podCount < 2) {
      weaknesses.push('Insufficient pod diversification — only 1 pod active')
      adjustments.push({
        type: 'pod_creation',
        description: 'Create additional pods with uncorrelated strategies',
        confidence: 0.9,
      })
    }

    // Impact estimation
    const totalPnl = recentDecisions.reduce(
      (sum, d) => sum + (d.sinceLastCycle?.totalPnl || 0), 0
    )

    return {
      id: `reflection-${this.reflections.length + 1}-${Date.now()}`,
      timestamp: new Date().toISOString(),
      decisionId: recentDecisions[recentDecisions.length - 1].id,
      reviewPeriod: {
        start: recentDecisions[0].timestamp,
        end: recentDecisions[recentDecisions.length - 1].timestamp,
      },
      strengths,
      weaknesses,
      patterns,
      lessons,
      adjustments,
      impact: {
        pnlAttributed: totalPnl,
        sharpeImpact: 0,
        drawdownImpact: breaches > 0 ? -0.1 : 0,
        overall: totalPnl > 0 ? 'positive' : totalPnl < 0 ? 'negative' : 'neutral',
      },
    }
  }

  private emptyReflection(decisionId: string): CIOSelfReflection {
    return {
      id: `reflection-empty-${Date.now()}`,
      timestamp: new Date().toISOString(),
      decisionId,
      reviewPeriod: { start: new Date().toISOString(), end: new Date().toISOString() },
      strengths: [],
      weaknesses: ['Insufficient data for meaningful reflection'],
      patterns: [],
      lessons: ['Need more decision cycles to identify patterns'],
      adjustments: [],
      impact: { pnlAttributed: 0, sharpeImpact: 0, drawdownImpact: 0, overall: 'neutral' },
    }
  }

  // ========== Reporting ==========

  private generateMacroOutlook(podStates: PodState[]): string {
    const totalPods = podStates.length
    const activePods = podStates.filter(s => s.pod.assets.some(a => a.active)).length
    const avgConviction = podStates.length > 0
      ? podStates.reduce((sum, s) => sum + s.pod.conviction, 0) / podStates.length
      : 0

    const totalValue = podStates.reduce((sum, s) => sum + s.totalValue, 0)
    const totalPnlPct = podStates.reduce((sum, s) => sum + s.pod.performance.totalPnlPct, 0)

    let outlook = 'Neutral'
    if (totalPnlPct > 0.05 && avgConviction > 0.6) outlook = 'Bullish — strong performance, high conviction'
    else if (totalPnlPct < -0.05 || avgConviction < 0.3) outlook = 'Bearish — underperformance, low conviction'
    else if (avgConviction > 0.5) outlook = 'Cautiously optimistic'

    return `${outlook}. ${activePods}/${totalPods} pods active. Portfolio value: $${totalValue.toLocaleString()}. Avg conviction: ${(avgConviction * 100).toFixed(0)}%.`
  }

  private buildCIOReasoning(
    allocations: PodCapitalAllocation[],
    directives: CIODirective[],
    risk: CIORiskAssessment,
  ): string {
    const parts: string[] = [
      `CIO Cycle ${this.cycleCount} — ${new Date().toISOString()}`,
      `Portfolio Value: $${risk.totalPortfolioValue.toLocaleString()}`,
    ]

    if (allocations.length > 0) {
      parts.push('Capital Allocations:')
      for (const a of allocations) {
        parts.push(`  ${a.podName}: ${(a.allocationPct * 100).toFixed(1)}% (score: ${(a.performanceScore * 100).toFixed(0)}%) — ${a.assessment}`)
      }
    }

    if (directives.length > 0) {
      parts.push(`Directives Issued (${directives.length}):`)
      for (const d of directives) {
        parts.push(`  [${d.priority}] ${d.type}: ${d.instruction}`)
      }
    }

    parts.push(`Risk: ${risk.overallRisk} | VaR(95%): $${risk.var95.toLocaleString()} | Drawdown: ${(risk.totalDrawdown * 100).toFixed(1)}%`)
    if (risk.warnings.length > 0) {
      parts.push(`Warnings: ${risk.warnings.join('; ')}`)
    }

    return parts.join('\n')
  }

  private computeCyclePerformance(podStates: PodState[]): {
    totalPnl: number
    totalPnlPct: number
    bestPod: string
    worstPod: string
  } {
    const totalPnl = podStates.reduce((sum, s) => sum + s.pod.performance.totalPnl, 0)
    const totalValue = podStates.reduce((sum, s) => sum + s.totalValue, 0)
    const totalPnlPct = totalValue > 0 ? totalPnl / totalValue : 0

    const sorted = [...podStates].sort((a, b) =>
      b.pod.performance.totalPnl - a.pod.performance.totalPnl
    )

    return {
      totalPnl,
      totalPnlPct,
      bestPod: sorted[0]?.pod.name || 'N/A',
      worstPod: sorted[sorted.length - 1]?.pod.name || 'N/A',
    }
  }

  /** Full workforce state for monitoring dashboard */
  getWorkforceState(): WorkforceState {
    const podStates = this.getPods().map(p => p.getPodReport())
    const totalValue = podStates.reduce((sum, s) => sum + s.totalValue, 0)
    const totalPnl = podStates.reduce((sum, s) => sum + s.pod.performance.totalPnl, 0)

    return {
      pods: podStates,
      latestCIODecision: this.decisions[this.decisions.length - 1] || null,
      recentReflections: this.reflections.slice(-5),
      aggregatePerformance: {
        totalCapital: this.totalCapital,
        totalValue,
        totalPnl,
        totalPnlPct: totalValue > 0 ? totalPnl / totalValue : 0,
        sharpeRatio: podStates.length > 0
          ? podStates.reduce((sum, s) => sum + s.pod.performance.sharpeRatio, 0) / podStates.length
          : 0,
        maxDrawdown: podStates.length > 0
          ? Math.max(...podStates.map(s => s.pod.performance.maxDrawdown))
          : 0,
        winRate: podStates.length > 0
          ? podStates.reduce((sum, s) => sum + s.pod.performance.winRate, 0) / podStates.length
          : 0,
        dailyPnl: podStates.reduce((sum, s) => sum + s.pod.performance.dailyPnl, 0),
        podCount: podStates.length,
        activeDebates: podStates.reduce((sum, s) => sum + s.pod.assets.filter(a => a.active).length, 0),
      },
      workforceLog: [...this.workforceLog.slice(-50)],
    }
  }

  // ========== Helpers ==========

  private log(message: string): void {
    const entry = `[CIO] ${message}`
    this.workforceLog.push(entry)
    if (this.workforceLog.length > 2000) {
      this.workforceLog = this.workforceLog.slice(-1000)
    }
    console.log(entry)
  }
}

// Singleton
export const cioAgent = new CIOAgent()
