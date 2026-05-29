'use client'

import React, { useState } from 'react'
import { Brain, Zap, Shield, TrendingUp, BarChart3, MessageSquare, ArrowUpRight, ArrowDownRight, Minus, Play, RotateCw, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { DebateState, AgentAnalysis, AgentTradingRole, FinalDecision, ConsensusAction } from '@/types/trading'
import { AGENT_ROLES } from '@/types/trading'

interface AgentDebatePanelProps {
  className?: string
  onDebateComplete?: (debate: DebateState) => void
}

export function AgentDebatePanel({ className, onDebateComplete }: AgentDebatePanelProps) {
  const [symbol, setSymbol] = useState('AAPL')
  const [assetType, setAssetType] = useState<string>('stock')
  const [running, setRunning] = useState(false)
  const [debate, setDebate] = useState<DebateState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedLog, setExpandedLog] = useState(false)

  const handleRunDebate = async () => {
    setRunning(true)
    setError(null)
    setDebate(null)
    try {
      const res = await fetch('/api/trading/debate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: symbol.toUpperCase(), assetType }),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setDebate(data.debate)
        onDebateComplete?.(data.debate)
      }
    } catch (err) {
      setError('Failed to run debate')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={cn('card-elevated', className)}>
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-2 mb-1">
          <Brain className="h-5 w-5 text-primary" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Agent Debate</h3>
        </div>
        <p className="text-xs text-zinc-500">6 specialized agents analyze and debate market conditions</p>
      </div>

      <div className="p-5 space-y-4">
        {/* Input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol"
            className="flex-1 bg-zinc-800 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary"
          />
          <select
            value={assetType}
            onChange={e => setAssetType(e.target.value)}
            className="bg-zinc-800 border border-border rounded-lg px-2 py-2 text-sm text-white"
          >
            <option value="stock">Stock</option>
            <option value="crypto">Crypto</option>
            <option value="forex">Forex</option>
          </select>
          <button
            onClick={handleRunDebate}
            disabled={running || !symbol}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white text-sm font-semibold rounded-lg hover:bg-primary-hover disabled:opacity-50 transition-all"
          >
            {running ? (
              <RotateCw className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {running ? 'Debating...' : 'Run'}
          </button>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Results */}
        {debate && (
          <div className="space-y-4">
            {/* Final Decision */}
            {debate.finalDecision && <DecisionBanner decision={debate.finalDecision} vetoTriggered={debate.vetoTriggered} />}

            {/* Agent Analyses */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Agent Analyses ({debate.agentAnalyses.length})
              </h4>
              <div className="grid gap-2">
                {debate.agentAnalyses.map(analysis => (
                  <AgentAnalysisCard key={analysis.role} analysis={analysis} />
                ))}
              </div>
            </div>

            {/* Voting Breakdown */}
            {debate.votingBreakdown.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">Voting</h4>
                <div className="flex h-2 rounded-full overflow-hidden bg-zinc-800">
                  <VotingBar breakdown={debate.votingBreakdown} />
                </div>
                <div className="flex flex-wrap gap-3 mt-2">
                  {debate.votingBreakdown.map(vb => {
                    const config = AGENT_ROLES[vb.role]
                    return (
                      <div key={vb.role} className="flex items-center gap-1.5 text-xs text-zinc-400">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: getRoleColor(vb.role) }} />
                        {config.label} ({(vb.contribution > 0 ? '+' : '')}{vb.contribution.toFixed(2)})
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Debate Log */}
            <div>
              <button
                onClick={() => setExpandedLog(!expandedLog)}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-white transition-colors"
              >
                {expandedLog ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                Debate Log ({debate.debateLog.length} entries)
              </button>
              {expandedLog && (
                <div className="mt-2 p-3 bg-zinc-800/50 rounded-lg text-xs text-zinc-400 font-mono max-h-48 overflow-y-auto space-y-1">
                  {debate.debateLog.map((line, i) => (
                    <div key={i} className={line.includes('VETO') ? 'text-red-400' : line.includes('Consensus') ? 'text-emerald-400' : ''}>
                      {line}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Debate Metadata */}
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span>Rounds: {debate.currentRound}/{debate.maxRounds}</span>
              <span>•</span>
              <span>Consensus: {debate.consensusReached ? '✓' : '✗'}</span>
              <span>•</span>
              <span>Threshold: {debate.consensusThreshold}</span>
              {debate.vetoTriggered && (
                <>
                  <span>•</span>
                  <span className="text-red-400">⚠ VETO</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Agent roster */}
        {!debate && (
          <div className="grid grid-cols-2 gap-2 pt-2">
            {(Object.entries(AGENT_ROLES) as [AgentTradingRole, typeof AGENT_ROLES['macro_strategist']][]).map(([role, config]) => (
              <div key={role} className="flex items-center gap-2 p-2 rounded-lg bg-zinc-800/50">
                <RoleIcon role={role} />
                <div className="text-xs">
                  <div className="text-white font-medium">{config.label}</div>
                  <div className="text-zinc-500">Weight: {(config.weight * 100).toFixed(0)}%</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DecisionBanner({ decision, vetoTriggered }: { decision: FinalDecision; vetoTriggered: boolean }) {
  const actionColors: Record<ConsensusAction, string> = {
    BUY: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
    SELL: 'bg-red-500/10 border-red-500/30 text-red-400',
    HOLD: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
  }

  const actionIcons: Record<ConsensusAction, React.ReactNode> = {
    BUY: <ArrowUpRight className="h-6 w-6" />,
    SELL: <ArrowDownRight className="h-6 w-6" />,
    HOLD: <Minus className="h-6 w-6" />,
  }

  const vetoColor = 'bg-red-600/20 border-red-500/40 text-red-300'

  return (
    <div className={cn(
      'p-4 rounded-xl border',
      vetoTriggered ? vetoColor : actionColors[decision.action]
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            'p-2 rounded-lg',
            decision.action === 'BUY' ? 'bg-emerald-500/20' :
            decision.action === 'SELL' ? 'bg-red-500/20' :
            'bg-amber-500/20'
          )}>
            {actionIcons[decision.action]}
          </div>
          <div>
            <div className="text-lg font-bold text-white">
              {vetoTriggered ? '⚠ VETO — FORCED SELL' : decision.action}
            </div>
            <div className="text-sm text-zinc-300 mt-0.5">
              Confidence: {(decision.overallConfidence * 100).toFixed(0)}% • Position: {(decision.positionSizePct * 100).toFixed(0)}%
            </div>
          </div>
        </div>
        <div className="text-right text-sm">
          {decision.targetPrice && (
            <div className="text-zinc-300">Target: ${decision.targetPrice.toFixed(2)}</div>
          )}
          {decision.stopLoss && (
            <div className="text-zinc-500">Stop: ${decision.stopLoss.toFixed(2)}</div>
          )}
          {decision.takeProfit && (
            <div className="text-emerald-400">TP: ${decision.takeProfit.toFixed(2)}</div>
          )}
        </div>
      </div>
      <p className="text-sm mt-3 text-zinc-300">{decision.reasoningSummary}</p>
      <div className="flex items-center gap-3 mt-2 text-xs text-zinc-500">
        <span>Risk Manager: {decision.riskManagerApproval ? '✓ Approved' : '✗ Rejected'}</span>
        <span>•</span>
        <span>{decision.debateRounds} round(s)</span>
      </div>
    </div>
  )
}

function AgentAnalysisCard({ analysis }: { analysis: AgentAnalysis }) {
  const [expanded, setExpanded] = useState(false)
  const config = AGENT_ROLES[analysis.role]

  const recColors: Record<string, string> = {
    STRONG_BUY: 'border-l-emerald-400 bg-emerald-500/5',
    BUY: 'border-l-emerald-400/70 bg-emerald-500/5',
    HOLD: 'border-l-amber-400 bg-amber-500/5',
    SELL: 'border-l-red-400/70 bg-red-500/5',
    STRONG_SELL: 'border-l-red-400 bg-red-500/5',
  }

  return (
    <div
      className={cn('border-l-4 rounded-r-lg p-3 cursor-pointer transition-colors hover:bg-zinc-800/30', recColors[analysis.recommendation])}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <RoleIcon role={analysis.role} />
          <div className="text-sm font-medium text-white truncate">{config.label}</div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={cn(
            'text-xs font-bold px-1.5 py-0.5 rounded',
            analysis.recommendation.startsWith('STRONG_BUY') ? 'text-emerald-400 bg-emerald-500/10' :
            analysis.recommendation === 'BUY' ? 'text-emerald-300 bg-emerald-500/10' :
            analysis.recommendation === 'HOLD' ? 'text-amber-400 bg-amber-500/10' :
            analysis.recommendation === 'SELL' ? 'text-red-300 bg-red-500/10' :
            'text-red-400 bg-red-500/10'
          )}>
            {analysis.recommendation}
          </span>
          <span className="text-xs text-zinc-500">{(analysis.confidence * 100).toFixed(0)}%</span>
          <ChevronDown className={cn('h-3 w-3 text-zinc-600 transition-transform', expanded && 'rotate-180')} />
        </div>
      </div>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-border space-y-2">
          <p className="text-xs text-zinc-400">{analysis.reasoning}</p>
          {Object.keys(analysis.keyMetrics).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(analysis.keyMetrics).map(([key, value]) => (
                <span key={key} className="px-2 py-0.5 bg-zinc-800 rounded text-xs text-zinc-300">
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          )}
          {analysis.riskFlags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {analysis.riskFlags.map(flag => (
                <span key={flag} className="px-2 py-0.5 bg-red-500/10 text-red-400 rounded text-xs">⚠ {flag}</span>
              ))}
            </div>
          )}
          <div className="text-xs text-zinc-600">{analysis.latencyMs}ms</div>
        </div>
      )}
    </div>
  )
}

function VotingBar({ breakdown }: { breakdown: { role: AgentTradingRole; contribution: number }[] }) {
  const maxContribution = Math.max(...breakdown.map(b => Math.abs(b.contribution)), 0.01)
  return (
    <>
      {breakdown.map(vb => {
        const pct = Math.abs(vb.contribution) / maxContribution * 100
        return (
          <div
            key={vb.role}
            className="transition-all duration-300"
            style={{
              width: `${Math.max(pct, 3)}%`,
              backgroundColor: getRoleColor(vb.role),
              opacity: vb.contribution > 0 ? 1 : 0.4,
            }}
          />
        )
      })}
    </>
  )
}

function RoleIcon({ role }: { role: AgentTradingRole }) {
  const iconClass = 'h-4 w-4'
  switch (role) {
    case 'macro_strategist': return <Shield className={cn(iconClass, 'text-blue-400')} />
    case 'sector_analyst': return <TrendingUp className={cn(iconClass, 'text-purple-400')} />
    case 'sentiment_agent': return <MessageSquare className={cn(iconClass, 'text-amber-400')} />
    case 'technical_analyst': return <BarChart3 className={cn(iconClass, 'text-emerald-400')} />
    case 'risk_manager': return <Shield className={cn(iconClass, 'text-red-400')} />
    case 'execution_optimizer': return <Zap className={cn(iconClass, 'text-accent')} />
    default: return <Brain className={cn(iconClass, 'text-zinc-400')} />
  }
}

function getRoleColor(role: AgentTradingRole): string {
  switch (role) {
    case 'macro_strategist': return '#60a5fa'
    case 'sector_analyst': return '#a78bfa'
    case 'sentiment_agent': return '#fbbf24'
    case 'technical_analyst': return '#34d399'
    case 'risk_manager': return '#f87171'
    case 'execution_optimizer': return '#22d3ee'
    default: return '#71717a'
  }
}
