import Link from 'next/link'
import { Bot, MessageSquare, Plus, ArrowRight, Zap, Shield, Code, Globe, TrendingUp, BarChart3, Brain, Lock, Cpu, Radio, ChevronRight, Sparkles, Diamond, CircleDot } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

const features = [
  {
    icon: Brain,
    title: 'Autonomous Intelligence',
    description: 'Self-directed agents that reason, plan, and execute complex multi-step workflows without human intervention.',
    tag: 'Core',
    color: 'sapphire',
  },
  {
    icon: BarChart3,
    title: 'Real-Time Market Cognition',
    description: 'Continuous analysis of market signals, sentiment, and regime shifts — processed in milliseconds.',
    tag: 'Trading',
    color: 'gold',
  },
  {
    icon: Lock,
    title: 'Zero-Trust Architecture',
    description: 'End-to-end encryption, role-based access, and immutable audit trails for every decision and action.',
    tag: 'Security',
    color: 'sapphire',
  },
  {
    icon: Cpu,
    title: 'Institutional-Grade Infrastructure',
    description: 'Built for hedge funds and trading desks. 99.99% uptime. Sub-100ms execution latency.',
    tag: 'Platform',
    color: 'gold',
  },
]

const stats = [
  { value: '99.99%', label: 'Uptime SLA' },
  { value: '<80ms', label: 'Execution Latency' },
  { value: '24/7', label: 'Autonomous Operation' },
  { value: '$100K+', label: 'Starting Capital Managed' },
]

export default async function HomePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <div className="min-h-screen bg-background noise-overlay grid-lines">
        <TopNav />
        <main className="relative">
          {/* ═══ HERO — Cinematic 8K Tesla ═══ */}
          <section className="relative overflow-hidden min-h-[92vh] flex items-center">
            <div className="absolute inset-0 tesla-hero-gradient" />
            
            {/* Cinematic Orbs — Ambient Light */}
            <div className="cinematic-orb cinematic-orb-blue animate-orb-drift" style={{ width: 600, height: 600, top: '-15%', left: '30%' }} />
            <div className="cinematic-orb cinematic-orb-gold animate-orb-drift" style={{ width: 400, height: 400, bottom: '5%', right: '10%', animationDelay: '-7s' }} />
            <div className="cinematic-orb cinematic-orb-purple animate-orb-drift" style={{ width: 300, height: 300, top: '40%', left: '5%', animationDelay: '-14s' }} />
            <div className="cinematic-orb cinematic-orb-emerald animate-orb-drift" style={{ width: 250, height: 250, bottom: '20%', left: '40%', animationDelay: '-10s' }} />
            
            {/* Tesla horizontal accent line */}
            <div className="absolute top-1/2 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/[0.03] to-transparent" />

            <div className="container-custom relative z-10 py-32 lg:py-44">
              <div className="max-w-4xl mx-auto text-center">
                {/* Live status indicator */}
                <div className="inline-flex items-center gap-3 px-5 py-2 rounded-full glass border border-white/[0.04] mb-10 animate-slide-up">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-primary"></span>
                  </span>
                  <span className="text-[11px] text-text-secondary font-medium tracking-tesla uppercase">Systems Operational</span>
                  <CircleDot className="h-3 w-3 text-primary/40" />
                </div>

                {/* Hero Headline */}
                <h1 className="text-5xl md:text-7xl lg:text-[5.5rem] font-display font-bold text-white mb-7 leading-[0.88] tracking-tighter animate-slide-up" style={{ animationDelay: '80ms' }}>
                  AI That{' '}
                  <span className="sapphire-shimmer">Trades</span>
                  <br />
                  <span className="text-text-muted font-light text-[0.65em]">While You Sleep</span>
                </h1>

                {/* Tesla accent bar under headline */}
                <div className="flex justify-center mb-8 animate-slide-up" style={{ animationDelay: '160ms' }}>
                  <div className="h-[2px] w-20 bg-gradient-to-r from-primary via-accent to-transparent rounded-full" />
                </div>

                <p className="text-lg md:text-xl text-text-secondary mb-12 max-w-xl mx-auto leading-relaxed font-light animate-slide-up" style={{ animationDelay: '200ms' }}>
                  Autonomous AI agents that research, analyze, and execute — 24/7.
                  <br />
                  <span className="text-text-muted">Built for institutional precision.</span>
                </p>

                {/* CTA Buttons */}
                <div className="flex flex-col sm:flex-row gap-4 justify-center animate-slide-up" style={{ animationDelay: '280ms' }}>
                  <Link
                    href="/login"
                    className="group inline-flex items-center justify-center gap-2.5 px-9 py-4 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-semibold hover:from-primary hover:to-primary-hover shadow-primary-lg transition-all duration-500 text-sm tracking-tight"
                  >
                    Request Access
                    <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform duration-300" />
                  </Link>
                  <Link
                    href="/pricing"
                    className="inline-flex items-center justify-center gap-2.5 px-9 py-4 glass border border-white/[0.06] text-text-secondary rounded-full font-medium hover:text-white hover:border-white/[0.12] hover:bg-white/[0.03] transition-all duration-500 text-sm tracking-tight"
                  >
                    <Diamond className="h-3.5 w-3.5 text-accent/60" />
                    View Pricing
                  </Link>
                </div>

                <p className="mt-10 text-[11px] text-text-dim tracking-tesla uppercase animate-fade-in" style={{ animationDelay: '500ms' }}>
                  Institutional clients only &bull; NDA required &bull; $2,999/mo
                </p>
              </div>
            </div>
          </section>

          <div className="tesla-divider" />

          {/* ═══ FEATURES — Tesla Precision Grid ═══ */}
          <section className="py-28 lg:py-40 relative">
            <div className="absolute inset-0">
              <div className="cinematic-orb cinematic-orb-blue animate-orb-drift" style={{ width: 500, height: 500, top: '20%', right: '-10%', animationDelay: '-5s' }} />
            </div>
            
            <div className="container-custom relative z-10">
              <div className="max-w-2xl mb-20 animate-slide-up">
                <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full glass border border-white/[0.04] mb-7">
                  <Cpu className="h-3.5 w-3.5 text-primary" />
                  <span className="text-[11px] text-text-secondary font-medium tracking-tesla uppercase">Platform</span>
                </div>
                <h2 className="text-4xl md:text-5xl lg:text-[3.5rem] font-display font-bold text-white mb-5 tracking-tighter leading-[0.92]">
                  Engineered for
                  <br />
                  <span className="text-text-muted font-light">performance</span>
                </h2>
                <p className="text-text-secondary text-lg font-light leading-relaxed max-w-md">
                  Every component designed for institutional-grade reliability and speed.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {features.map((feature, index) => (
                  <div
                    key={index}
                    className={`card-tesla tesla-sweep-light p-9 group animate-slide-up ${
                      feature.color === 'gold' ? 'card-tesla-premium' : ''
                    }`}
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex items-start justify-between mb-7">
                      <div className={`w-12 h-12 rounded-[16px] flex items-center justify-center border transition-all duration-500 ${
                        feature.color === 'gold'
                          ? 'bg-accent/[0.06] border-accent/10 group-hover:border-accent/25 group-hover:bg-accent/[0.1]'
                          : 'bg-primary/[0.06] border-primary/10 group-hover:border-primary/25 group-hover:bg-primary/[0.1]'
                      }`}>
                        <feature.icon className={`h-5 w-5 transition-colors duration-500 ${
                          feature.color === 'gold'
                            ? 'text-text-muted group-hover:text-accent'
                            : 'text-text-muted group-hover:text-primary'
                        }`} />
                      </div>
                      <span className="text-[10px] text-text-dim tracking-tesla uppercase font-medium px-3 py-1 rounded-full border border-white/[0.04] bg-white/[0.02]">
                        {feature.tag}
                      </span>
                    </div>

                    <h3 className="text-xl font-display font-semibold text-white mb-3 tracking-tight group-hover:gradient-text transition-all duration-500">
                      {feature.title}
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed font-light">
                      {feature.description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <div className="tesla-divider" />

          {/* ═══ STATS — Tesla Monumental Numbers ═══ */}
          <section className="py-24 lg:py-36 relative">
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/[0.008] to-transparent" />
            <div className="container-custom relative z-10">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 lg:gap-20">
                {stats.map((stat, index) => (
                  <div key={index} className="tesla-stat text-center py-6 animate-slide-up" style={{ animationDelay: `${index * 100}ms` }}>
                    <div className="text-4xl md:text-5xl lg:text-[4rem] font-display font-bold text-white mb-3 tracking-tighter leading-none">
                      {stat.value}
                    </div>
                    <div className="text-[11px] text-text-dim tracking-tesla uppercase font-medium">
                      {stat.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <div className="tesla-divider" />

          {/* ═══ CTA — Cinematic Close ═══ */}
          <section className="py-28 lg:py-40 relative overflow-hidden">
            <div className="absolute inset-0">
              <div className="cinematic-orb cinematic-orb-blue animate-orb-drift" style={{ width: 700, height: 700, top: '0%', left: '20%', animationDelay: '-3s' }} />
              <div className="cinematic-orb cinematic-orb-gold animate-orb-drift" style={{ width: 400, height: 400, bottom: '0%', right: '20%', animationDelay: '-9s' }} />
            </div>
            
            <div className="container-custom relative z-10">
              <div className="max-w-3xl mx-auto text-center">
                <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass border border-white/[0.04] mb-7">
                  <Sparkles className="h-3.5 w-3.5 text-accent/60" />
                  <span className="text-[11px] text-text-secondary font-medium tracking-tesla uppercase">The Future</span>
                </div>
                
                <h2 className="text-4xl md:text-5xl lg:text-[4.5rem] font-display font-bold text-white mb-7 tracking-tighter leading-[0.9]">
                  The future of trading
                  <br />
                  <span className="gradient-text-hero font-light">is autonomous</span>
                </h2>
                
                <p className="text-text-secondary text-lg font-light mb-12 max-w-lg mx-auto leading-relaxed">
                  Deploy your AI workforce today. No management overhead. No downtime. Pure alpha generation.
                </p>
                
                <Link
                  href="/login"
                  className="group inline-flex items-center gap-2.5 px-9 py-4 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-semibold hover:from-primary hover:to-primary-hover shadow-primary-lg transition-all duration-500 text-sm"
                >
                  Start Building Now
                  <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform duration-300" />
                </Link>
              </div>
            </div>
          </section>

          {/* ═══ FOOTER — Tesla Precision ═══ */}
          <footer className="border-t border-white/[0.03] py-14">
            <div className="container-custom">
              <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary-deep to-primary flex items-center justify-center shadow-primary">
                    <span className="text-white font-display font-bold text-xs">S</span>
                  </div>
                  <span className="font-display font-bold text-sm text-white tracking-tesla">SAHJONY</span>
                  <span className="text-[10px] text-text-dim tracking-tesla uppercase">Capital LLC</span>
                </div>
                <div className="flex items-center gap-10 text-[11px] text-text-muted tracking-wide">
                  <Link href="/pricing" className="hover:text-white transition-colors duration-400">Pricing</Link>
                  <Link href="/agents" className="hover:text-white transition-colors duration-400">Agents</Link>
                  <Link href="/trading" className="hover:text-white transition-colors duration-400">Trading</Link>
                  <Link href="/login" className="hover:text-white transition-colors duration-400">Sign in</Link>
                </div>
                <p className="text-[11px] text-text-dim tracking-wide">&copy; 2026 Sahjony Capital LLC. All rights reserved.</p>
              </div>
            </div>
          </footer>
        </main>
      </div>
    )
  }

  // ═══ AUTHENTICATED DASHBOARD ═══
  const { data: agents } = await supabase
    .from('agents')
    .select('*')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false })
    .limit(5)

  const { data: conversations } = await supabase
    .from('conversations')
    .select('*, agents(name)')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false })
    .limit(5)

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        {/* Dashboard Header */}
        <div className="flex items-center justify-between mb-10 animate-slide-up">
          <div>
            <h1 className="text-3xl font-display font-bold text-white tracking-tighter">Dashboard</h1>
            <p className="text-text-secondary mt-1.5 text-sm font-light">Welcome back. Your AI workforce is standing by.</p>
          </div>
          <Link
            href="/agents/new"
            className="group inline-flex items-center gap-2.5 px-6 py-3 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-medium text-sm shadow-primary hover:from-primary hover:to-primary-hover hover:shadow-primary-lg transition-all duration-500"
          >
            <Plus className="h-4 w-4" />
            Deploy Agent
          </Link>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-12">
          <div className="card-tesla tesla-sweep-light p-7 animate-slide-up" style={{ animationDelay: '50ms' }}>
            <div className="flex items-center gap-5">
              <div className="w-14 h-14 rounded-[18px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                <Bot className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-4xl font-display font-bold text-white tracking-tight leading-none">{agents?.length || 0}</p>
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mt-1.5">Active Agents</p>
              </div>
            </div>
          </div>
          <div className="card-tesla tesla-sweep-light p-7 animate-slide-up" style={{ animationDelay: '100ms' }}>
            <div className="flex items-center gap-5">
              <div className="w-14 h-14 rounded-[18px] bg-accent/[0.06] flex items-center justify-center border border-accent/10">
                <MessageSquare className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-4xl font-display font-bold text-white tracking-tight leading-none">{conversations?.length || 0}</p>
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mt-1.5">Conversations</p>
              </div>
            </div>
          </div>
          <div className="card-tesla tesla-sweep-light p-7 animate-slide-up" style={{ animationDelay: '150ms' }}>
            <div className="flex items-center gap-5">
              <div className="w-14 h-14 rounded-[18px] bg-emerald-500/[0.06] flex items-center justify-center border border-emerald-500/10">
                <TrendingUp className="h-6 w-6 text-emerald-400" />
              </div>
              <div>
                <p className="text-4xl font-display font-bold text-white tracking-tight leading-none">0</p>
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mt-1.5">Executions Today</p>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Agents */}
        <div className="mb-12 animate-slide-up" style={{ animationDelay: '200ms' }}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-display font-semibold text-white tracking-tight">Recent Agents</h2>
            <Link
              href="/agents"
              className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-white transition-colors duration-400 tracking-wide"
            >
              View all
              <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          {agents && agents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {agents.map((agent, index) => (
                <Link
                  key={agent.id}
                  href={`/agents/${agent.id}`}
                  className="card-tesla tesla-sweep-light p-6 group"
                  style={{ animationDelay: `${250 + index * 60}ms` }}
                >
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-[16px] bg-primary/[0.06] flex items-center justify-center border border-primary/10 group-hover:border-primary/25 group-hover:bg-primary/[0.1] transition-all duration-500">
                      <Bot className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-white text-sm truncate">{agent.name}</h3>
                      <p className="text-[11px] text-text-dim mt-0.5 font-mono-display">{agent.model}</p>
                    </div>
                    <span className={`badge ${agent.status === 'active' ? 'badge-success' : 'bg-white/[0.03] text-text-muted border border-white/[0.04]'}`}>
                      {agent.status}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card-tesla text-center py-24">
              <div className="w-16 h-16 rounded-[20px] bg-surface mx-auto mb-5 flex items-center justify-center border border-white/[0.04]">
                <Bot className="h-7 w-7 text-text-dim" />
              </div>
              <p className="text-text-secondary mb-6 text-sm">No agents deployed yet</p>
              <Link
                href="/agents/new"
                className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-medium text-sm shadow-primary hover:shadow-primary-lg transition-all duration-500"
              >
                <Plus className="h-4 w-4" />
                Deploy your first agent
              </Link>
            </div>
          )}
        </div>

        {/* Recent Conversations */}
        <div className="animate-slide-up" style={{ animationDelay: '300ms' }}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-display font-semibold text-white tracking-tight">Recent Conversations</h2>
            <Link
              href="/conversations"
              className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-white transition-colors duration-400 tracking-wide"
            >
              View all
              <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
          {conversations && conversations.length > 0 ? (
            <div className="space-y-2">
              {conversations.map((conv, index) => (
                <Link
                  key={conv.id}
                  href={`/agents/${conv.agent_id}?conversation=${conv.id}`}
                  className="card-tesla group flex items-center justify-between p-5"
                  style={{ animationDelay: `${350 + index * 50}ms` }}
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-[14px] bg-white/[0.02] flex items-center justify-center border border-white/[0.04] group-hover:border-white/[0.08] transition-all duration-400">
                      <MessageSquare className="h-4.5 w-4.5 text-text-muted" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-medium text-white text-sm truncate">{conv.title}</h3>
                      <p className="text-[11px] text-text-dim mt-0.5">{conv.agents?.name}</p>
                    </div>
                  </div>
                  <span className="text-[11px] text-text-dim flex-shrink-0 font-mono-display">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card-tesla text-center py-24">
              <div className="w-16 h-16 rounded-[20px] bg-surface mx-auto mb-5 flex items-center justify-center border border-white/[0.04]">
                <MessageSquare className="h-7 w-7 text-text-dim" />
              </div>
              <p className="text-text-secondary text-sm">No conversations yet</p>
              <p className="text-[11px] text-text-dim mt-1.5">Deploy an agent and start interacting</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
