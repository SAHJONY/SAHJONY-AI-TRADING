export type Desk = 'live' | 'crypto' | 'trainer' | 'stocks'
export type Posture = 'risk_on' | 'risk_off' | 'neutral'
export type ProvenanceKind = 'LIVE' | 'SIMULATED' | 'BACKTEST' | 'FALLBACK'

export interface AgentScore {
  name: string; shortName: string; focus: string; score: number; confidence: number
  rationale: string; alphaContribution: number; profitable: number; losing: number
}
export interface AssetCouncil { symbol: string; price: number; conviction: number; direction: string; agents: AgentScore[] }
export interface Position { symbol: string; strategy: string; shares: number; price: number; marketValue: number; unrealized: number }
export interface BlotterRow { ts: string; symbol: string; side: string; purpose: string; status: string; notional: number; agentDrivers: string[] }
export interface Trace { value: string | number; source: string; rationale: string; asOf: string }
export interface ParquetSnapshot {
  schemaVersion: 1; desk: Desk; cycle: number; ts: string; mode: string; broker: string
  provenance: { kind: ProvenanceKind; label: string; source: string; verified: boolean }
  account: { equity: number; equityStart: number; cash: number; deployed: number; nav: number }
  pnl: { returnPct: number; realized: number; benchmarkPct: number; alphaPct: number }
  health: { marketOpen: boolean; brokerOnline: boolean; liveArmed: boolean; halted: boolean; haltReason: string; dataIntegrity: number; reconciliation: string }
  brain: { posture: Posture; globalRiskMultiplier: number; commentary: string; model: string; used: boolean }
  throttle: { brainMultiplier: number; quantitativeMultiplier: number; effectiveMultiplier: number; targetVolatility: number; rationale: string }
  council: AssetCouncil[]; positions: Position[]; blotter: BlotterRow[]
  equityCurve: { cycle: number; nav: number; benchmark: number; expected: number }[]
  allocation: { name: string; value: number; color: string }[]
  attribution: AgentScore[]
  drift: { actualSharpe: number; expectedSharpe: number; deviation: number; alert: boolean; observations: number }
  incubation: { active: boolean; deployedCapital: number; capitalCeiling: number; qualifiedCycles: number; requiredCycles: number; scaleEligible: boolean; qualification: string }
  traces: Record<string, Trace>
}
