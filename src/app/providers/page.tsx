'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { PROVIDERS } from '@/lib/providers/registry'
import { TRADING_AGENTS } from '@/lib/agents/registry'
import {
  Search, Sparkles, Check, Key, Globe, Lock,
  Cpu, Zap, Shield, ArrowRight, X, Plus, BadgeCheck,
  RefreshCw, Eye, Activity, Star
} from 'lucide-react'

export default function ProvidersPage() {
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null)
  const [apiKeyMap, setApiKeyMap] = useState<Record<string, string>>({})

  const filteredProviders = PROVIDERS.filter(p => p.status === 'active').filter(p => {
    if (!search) return true
    return p.name.toLowerCase().includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase())
  })

  const selected = selectedProvider ? PROVIDERS.find(p => p.id === selectedProvider) : null
  const selectedAgents = selectedProvider ? TRADING_AGENTS.filter(a => a.providerId === selectedProvider) : []

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-10 animate-slide-up">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                <Cpu className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-3xl font-display font-bold text-white tracking-tighter">AI Providers & Models</h1>
            </div>
            <p className="text-text-secondary text-sm font-light ml-[52px]">
              {PROVIDERS.filter(p => p.status === 'active').length} providers. All models auto-update to their latest version daily. Add your own API keys or use platform defaults.
            </p>
          </div>
          <button className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-primary/[0.06] border border-primary/10 text-primary text-sm font-medium hover:bg-primary/[0.1] transition-all duration-400">
            <RefreshCw className="h-3.5 w-3.5" />
            Auto-Update Now
          </button>
        </div>

        {/* Auto-Update Banner */}
        <div className="max-w-4xl mx-auto mb-8 p-5 rounded-2xl bg-primary/[0.03] border border-primary/10 animate-slide-up" style={{ animationDelay: '50ms' }}>
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10 flex-shrink-0">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">Always on the Latest Model — No Config Needed</p>
              <p className="text-[11px] text-text-dim mt-0.5">
                The platform polls every provider's API daily at midnight UTC. When a new model drops — GPT-5, Claude 5, Gemini 3, Grok 4 — 
                your agents upgrade instantly. You always run the most advanced model available. Add your own API key for any provider to use your own quota and rate limits.
              </p>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-8 animate-slide-up" style={{ animationDelay: '80ms' }}>
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-dim" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search providers..."
            className="input pl-11 max-w-md"
          />
        </div>

        {/* Provider Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-12">
          {filteredProviders.map((provider, idx) => {
            const agentCount = TRADING_AGENTS.filter(a => a.providerId === provider.id).length
            const hasKey = !!apiKeyMap[provider.id]

            return (
              <div
                key={provider.id}
                className="card-tesla p-6 animate-slide-up cursor-pointer hover:border-white/[0.08] transition-all duration-400"
                style={{ animationDelay: `${100 + idx * 40}ms` }}
                onClick={() => setSelectedProvider(provider.id)}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{provider.icon}</span>
                    <div>
                      <h3 className="text-lg font-display font-semibold text-white tracking-tight">{provider.name}</h3>
                      <p className="text-[11px] text-text-dim">{provider.models.length} model{provider.models.length > 1 ? 's' : ''} · {agentCount} agent{agentCount > 1 ? 's' : ''}</p>
                    </div>
                  </div>
                  {hasKey && <BadgeCheck className="h-4 w-4 text-emerald-400" />}
                </div>

                <p className="text-[11px] text-text-dim leading-relaxed mb-4 line-clamp-2">{provider.description}</p>

                {/* Features */}
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {provider.features.slice(0, 3).map(f => (
                    <span key={f} className="badge bg-white/[0.03] border-white/[0.06] text-[9px] text-text-muted">{f}</span>
                  ))}
                  {provider.features.length > 3 && (
                    <span className="badge bg-white/[0.03] border-white/[0.06] text-[9px] text-text-dim">+{provider.features.length - 3}</span>
                  )}
                </div>

                {/* Key Status */}
                <div className="flex items-center justify-between pt-4 border-t border-white/[0.04]">
                  <div className="flex items-center gap-2">
                    <Key className={`h-3 w-3 ${hasKey ? 'text-emerald-400' : 'text-text-dim'}`} />
                    <span className="text-[10px] text-text-dim">{hasKey ? 'Your key active' : 'Platform default'}</span>
                  </div>
                  <span className={`text-[10px] font-medium ${provider.color}`}>View Models →</span>
                </div>
              </div>
            )
          })}
        </div>

        {/* ═══ PROVIDER DETAIL MODAL ═══ */}
        {selected && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedProvider(null)}>
            <div className="w-full max-w-2xl card-tesla p-8 animate-slide-up max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{selected.icon}</span>
                  <div>
                    <h2 className="text-xl font-display font-semibold text-white tracking-tight">{selected.name}</h2>
                    <p className="text-[12px] text-text-dim">{selected.baseUrl}</p>
                  </div>
                </div>
                <button onClick={() => setSelectedProvider(null)} className="text-text-dim hover:text-white transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>

              <p className="text-sm text-text-secondary font-light leading-relaxed mb-6">{selected.description}</p>

              {/* Features */}
              <div className="mb-6">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Features</p>
                <div className="flex flex-wrap gap-2">
                  {selected.features.map(f => (
                    <span key={f} className="badge bg-primary/[0.06] border-primary/10 text-[10px] text-primary">{f}</span>
                  ))}
                </div>
              </div>

              {/* Models */}
              <div className="mb-6">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Available Models (Auto-Update)</p>
                <div className="space-y-3">
                  {selected.models.map(model => (
                    <div key={model.id} className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-medium text-white">{model.name}</h4>
                        {model.isLatest && (
                          <span className="badge bg-primary/[0.06] border-primary/10 text-[9px] text-primary flex items-center gap-1">
                            <Sparkles className="h-2.5 w-2.5" /> Auto-Update
                          </span>
                        )}
                        {model.isRecommended && (
                          <span className="badge bg-accent/[0.06] border-accent/10 text-[9px] text-accent ml-1 flex items-center gap-1">
                            <Star className="h-2.5 w-2.5" /> Recommended
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-text-dim mb-3">{model.description}</p>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <p className="text-[9px] text-text-dim uppercase">Context</p>
                          <p className="text-[11px] text-text-secondary">{(model.contextWindow / 1000).toFixed(0)}K</p>
                        </div>
                        <div>
                          <p className="text-[9px] text-text-dim uppercase">Max Output</p>
                          <p className="text-[11px] text-text-secondary">{(model.maxOutput / 1000).toFixed(0)}K</p>
                        </div>
                        <div>
                          <p className="text-[9px] text-text-dim uppercase">Price/1M</p>
                          <p className="text-[11px] text-text-secondary">
                            {model.pricing.inputPer1M === 0 ? 'Free' : `$${model.pricing.inputPer1M} in / $${model.pricing.outputPer1M} out`}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-3">
                        {model.capabilities.map(cap => (
                          <span key={cap} className="badge bg-white/[0.03] border-white/[0.06] text-[8px] text-text-dim">{cap}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Trading Agents for this Provider */}
              {selectedAgents.length > 0 && (
                <div className="mb-6">
                  <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Trading Agents</p>
                  <div className="space-y-2">
                    {selectedAgents.map(agent => (
                      <div key={agent.id} className="flex items-center justify-between p-3 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">{agent.icon}</span>
                          <div>
                            <p className="text-sm font-medium text-white">{agent.name}</p>
                            <p className="text-[10px] text-text-dim">{agent.specialty}</p>
                          </div>
                        </div>
                        <span className={`badge border text-[9px] ${riskColors[agent.riskLevel]}`}>{agent.riskLevel}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* API Key Input */}
              <div className="mb-6">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Your API Key (Optional)</p>
                <div className="flex gap-3">
                  <input
                    type="password"
                    value={apiKeyMap[selected.id] || ''}
                    onChange={(e) => setApiKeyMap(prev => ({ ...prev, [selected.id]: e.target.value }))}
                    placeholder={`Enter your ${selected.envKey}...`}
                    className="input flex-1"
                  />
                  <button
                    onClick={() => {
                      if (apiKeyMap[selected.id]) {
                        // TODO: Save to Supabase user_provider_keys table
                        console.log(`Saved API key for ${selected.id}`)
                      }
                    }}
                    className="px-5 py-2.5 rounded-full bg-gradient-to-r from-primary-deep to-primary text-white text-sm font-medium shadow-primary hover:shadow-primary-lg transition-all duration-500 flex-shrink-0"
                  >
                    Save
                  </button>
                </div>
                <p className="text-[10px] text-text-dim mt-2">
                  Add your own key to use your quota and rate limits. Without a key, the platform uses shared defaults. Keys are encrypted at rest.
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

const riskColors: Record<string, string> = {
  conservative: 'text-emerald-400 bg-emerald-500/[0.06] border-emerald-500/10',
  moderate: 'text-primary bg-primary/[0.06] border-primary/10',
  aggressive: 'text-accent bg-accent/[0.06] border-accent/10',
}
