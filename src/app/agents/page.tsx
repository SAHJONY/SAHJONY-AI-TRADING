'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { PROVIDERS } from '@/lib/providers/registry'
import { TRADING_AGENTS, type TradingAgent } from '@/lib/agents/registry'
import {
  Zap, Shield, TrendingUp, ArrowRight, Search, Filter,
  Check, Plus, Star, AlertTriangle, Clock, ChevronDown,
  Sparkles, Bot, Activity, Eye, Cpu, Globe, Lock, Gift,
  CircleDot, BadgeCheck, X
} from 'lucide-react'

const riskColors: Record<string, string> = {
  conservative: 'text-emerald-400 bg-emerald-500/[0.06] border-emerald-500/10',
  moderate: 'text-primary bg-primary/[0.06] border-primary/10',
  aggressive: 'text-accent bg-accent/[0.06] border-accent/10',
}

const horizonLabels: Record<string, string> = {
  scalp: 'Scalp (seconds–minutes)',
  intraday: 'Intraday (hours)',
  swing: 'Swing (days–weeks)',
  position: 'Position (weeks–months)',
}

export default function AgentsPage() {
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [filterProvider, setFilterProvider] = useState<string>('all')
  const [filterRisk, setFilterRisk] = useState<string>('all')
  const [filterHorizon, setFilterHorizon] = useState<string>('all')
  const [selectedAgent, setSelectedAgent] = useState<TradingAgent | null>(null)
  const [addedAgents, setAddedAgents] = useState<Set<string>>(new Set(['agent-hermes-oracle', 'agent-anthropic-sentinel', 'agent-groq-flash', 'agent-freebuff-zero']))

  const filteredAgents = TRADING_AGENTS.filter(agent => {
    if (search && !agent.name.toLowerCase().includes(search.toLowerCase()) && !agent.specialty.toLowerCase().includes(search.toLowerCase())) return false
    if (filterProvider !== 'all' && agent.providerId !== filterProvider) return false
    if (filterRisk !== 'all' && agent.riskLevel !== filterRisk) return false
    if (filterHorizon !== 'all' && agent.timeHorizon !== filterHorizon) return false
    return true
  })

  const handleAddAgent = (agentId: string) => {
    setAddedAgents(prev => {
      const next = new Set(prev)
      if (next.has(agentId)) next.delete(agentId)
      else next.add(agentId)
      return next
    })
  }

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-10 animate-slide-up">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-3xl font-display font-bold text-white tracking-tighter">AI Trading Agents</h1>
            </div>
            <p className="text-text-secondary text-sm font-light ml-[52px]">
              {TRADING_AGENTS.length} agents across {PROVIDERS.length} providers. Add any agent at your own initiative — all models auto-update to their latest version daily.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="badge badge-primary">{addedAgents.size} active</span>
          </div>
        </div>

        {/* Search + Filters */}
        <div className="flex flex-col md:flex-row gap-4 mb-8 animate-slide-up" style={{ animationDelay: '50ms' }}>
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-dim" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agents by name or specialty..."
              className="input pl-11"
            />
          </div>
          <select
            value={filterProvider}
            onChange={(e) => setFilterProvider(e.target.value)}
            className="input w-auto min-w-[160px] appearance-none cursor-pointer"
          >
            <option value="all">All Providers</option>
            {PROVIDERS.filter(p => p.status === 'active').map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select
            value={filterRisk}
            onChange={(e) => setFilterRisk(e.target.value)}
            className="input w-auto min-w-[140px] appearance-none cursor-pointer"
          >
            <option value="all">All Risk Levels</option>
            <option value="conservative">Conservative</option>
            <option value="moderate">Moderate</option>
            <option value="aggressive">Aggressive</option>
          </select>
          <select
            value={filterHorizon}
            onChange={(e) => setFilterHorizon(e.target.value)}
            className="input w-auto min-w-[140px] appearance-none cursor-pointer"
          >
            <option value="all">All Time Horizons</option>
            <option value="scalp">Scalp</option>
            <option value="intraday">Intraday</option>
            <option value="swing">Swing</option>
            <option value="position">Position</option>
          </select>
        </div>

        {/* Agent Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-12">
          {filteredAgents.map((agent, idx) => {
            const isAdded = addedAgents.has(agent.id)
            const provider = PROVIDERS.find(p => p.id === agent.providerId)

            return (
              <div
                key={agent.id}
                className={`card-tesla p-6 animate-slide-up cursor-pointer transition-all duration-400 ${
                  isAdded ? 'border-primary/20' : ''
                }`}
                style={{ animationDelay: `${80 + idx * 40}ms` }}
                onClick={() => setSelectedAgent(agent)}
              >
                {/* Provider Badge */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{agent.icon}</span>
                    <span className={`text-[11px] font-medium ${provider?.color || 'text-text-muted'}`}>
                      {provider?.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {agent.isDefault && <span className="badge badge-primary text-[9px]">Default</span>}
                    {agent.isPremium && <span className="badge badge-accent text-[9px]">Premium</span>}
                  </div>
                </div>

                {/* Name & Specialty */}
                <h3 className="text-lg font-display font-semibold text-white tracking-tight mb-1">{agent.name}</h3>
                <p className="text-[12px] text-primary font-medium mb-2">{agent.specialty}</p>
                <p className="text-[11px] text-text-dim leading-relaxed mb-4 line-clamp-2">{agent.description}</p>

                {/* Risk & Horizon */}
                <div className="flex items-center gap-2 mb-4">
                  <span className={`badge border text-[9px] ${riskColors[agent.riskLevel]}`}>
                    {agent.riskLevel}
                  </span>
                  <span className="badge bg-white/[0.03] border-white/[0.06] text-[9px] text-text-muted">
                    {agent.timeHorizon}
                  </span>
                </div>

                {/* Add/Remove Button */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleAddAgent(agent.id) }}
                  className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-full text-sm font-medium transition-all duration-400 ${
                    isAdded
                      ? 'bg-primary/[0.08] border border-primary/20 text-primary hover:bg-red-500/[0.06] hover:border-red-500/20 hover:text-red-400'
                      : 'bg-gradient-to-r from-primary-deep to-primary text-white shadow-primary hover:shadow-primary-lg'
                  }`}
                >
                  {isAdded ? (
                    <>
                      <Check className="h-3.5 w-3.5" />
                      Active — Click to Remove
                    </>
                  ) : (
                    <>
                      <Plus className="h-3.5 w-3.5" />
                      Add Agent
                    </>
                  )}
                </button>
              </div>
            )
          })}
        </div>

        {/* Auto-Update Notice */}
        <div className="max-w-3xl mx-auto animate-slide-up" style={{ animationDelay: '600ms' }}>
          <div className="p-5 rounded-2xl bg-primary/[0.03] border border-primary/10">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10 flex-shrink-0">
                <Sparkles className="h-4.5 w-4.5 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium text-white mb-1">Auto-Update to Latest Models — Daily</p>
                <p className="text-[11px] text-text-dim leading-relaxed">
                  Every agent automatically resolves to its provider's most advanced model each day. When OpenAI releases a new GPT, 
                  when Anthropic ships a new Claude, when NVIDIA drops a faster NIM — your agents upgrade instantly. Zero config, zero downtime.
                  The platform polls all provider APIs at midnight UTC and updates the model registry autonomously.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ═══ AGENT DETAIL MODAL ═══ */}
        {selectedAgent && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedAgent(null)}>
            <div className="w-full max-w-lg card-tesla p-8 animate-slide-up" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{selectedAgent.icon}</span>
                  <div>
                    <h2 className="text-xl font-display font-semibold text-white tracking-tight">{selectedAgent.name}</h2>
                    <p className="text-[12px] text-primary font-medium">{selectedAgent.specialty}</p>
                  </div>
                </div>
                <button onClick={() => setSelectedAgent(null)} className="text-text-dim hover:text-white transition-colors text-xl">
                  <X className="h-5 w-5" />
                </button>
              </div>

              <p className="text-sm text-text-secondary font-light leading-relaxed mb-6">{selectedAgent.description}</p>

              {/* Specs Grid */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                  <p className="text-[10px] text-text-dim tracking-tesla uppercase mb-1">Provider</p>
                  <p className="text-sm font-medium text-white">{PROVIDERS.find(p => p.id === selectedAgent.providerId)?.name}</p>
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                  <p className="text-[10px] text-text-dim tracking-tesla uppercase mb-1">Model</p>
                  <p className="text-sm font-medium text-white">Latest (Auto-Update)</p>
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                  <p className="text-[10px] text-text-dim tracking-tesla uppercase mb-1">Risk Level</p>
                  <span className={`badge border text-[10px] ${riskColors[selectedAgent.riskLevel]}`}>{selectedAgent.riskLevel}</span>
                </div>
                <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                  <p className="text-[10px] text-text-dim tracking-tesla uppercase mb-1">Time Horizon</p>
                  <p className="text-sm font-medium text-white">{horizonLabels[selectedAgent.timeHorizon]}</p>
                </div>
              </div>

              {/* Model Auto-Update */}
              <div className="p-4 rounded-2xl bg-primary/[0.03] border border-primary/10 mb-6">
                <div className="flex items-center gap-3">
                  <Sparkles className="h-4 w-4 text-primary flex-shrink-0" />
                  <p className="text-[11px] text-text-secondary">
                    This agent's model auto-updates daily to the latest version from {PROVIDERS.find(p => p.id === selectedAgent.providerId)?.name}. Always running the most advanced model available.
                  </p>
                </div>
              </div>

              <button
                onClick={() => { handleAddAgent(selectedAgent.id); setSelectedAgent(null) }}
                className={`w-full flex items-center justify-center gap-2 px-6 py-4 rounded-full font-semibold text-sm transition-all duration-500 ${
                  addedAgents.has(selectedAgent.id)
                    ? 'glass border border-red-500/20 text-red-400 hover:bg-red-500/[0.06]'
                    : 'bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.2)]'
                }`}
              >
                {addedAgents.has(selectedAgent.id) ? (
                  <><X className="h-4 w-4" /> Remove Agent</>
                ) : (
                  <><Plus className="h-4 w-4" /> Add to My Agents</>
                )}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
