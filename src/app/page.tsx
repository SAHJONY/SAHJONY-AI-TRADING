import Link from 'next/link'
import { Bot, MessageSquare, Plus, ArrowRight, Zap, Shield, Code, Globe, TrendingUp } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { UsageAnalytics } from '@/components/dashboard/usage-analytics'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

const features = [
  {
    icon: Bot,
    title: 'Intelligent Agents',
    description: 'Deploy AI agents that understand context and learn from interactions',
  },
  {
    icon: Zap,
    title: 'Lightning Fast',
    description: 'Optimized for speed with response times under 100ms',
  },
  {
    icon: Shield,
    title: 'Enterprise Security',
    description: 'Bank-grade encryption and privacy-first architecture',
  },
  {
    icon: Code,
    title: 'Easy Integration',
    description: 'REST API and SDKs for seamless integration into your workflow',
  },
]

export default async function HomePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <div className="min-h-screen bg-background">
        <TopNav />
        <main>
          {/* Hero Section */}
          <section className="relative overflow-hidden py-24 lg:py-32">
            {/* Background decoration */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              <div className="absolute top-20 -left-40 w-80 h-80 bg-primary/10 rounded-full blur-3xl" />
              <div className="absolute bottom-20 -right-40 w-96 h-96 bg-accent/10 rounded-full blur-3xl" />
            </div>

            <div className="container-custom relative">
              <div className="max-w-3xl mx-auto text-center">
                <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 mb-6">
                  <span className="w-2 h-2 bg-success rounded-full animate-pulse" />
                  <span className="text-sm text-primary font-medium">Now with Unified Brain Architecture</span>
                </div>

                <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-6 leading-tight">
                  Build, Deploy & Manage{' '}
                  <span className="gradient-text">AI Agents</span>{' '}
                  That Think
                </h1>
                <p className="text-lg md:text-xl text-zinc-400 mb-10 max-w-2xl mx-auto">
                  Create intelligent agents powered by Hermes Agent and Freebuff. 
                  From customer support to code generation — automate it all.
                </p>

                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                  <Link
                    href="/login"
                    className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all text-lg"
                  >
                    Get Started Free
                    <ArrowRight className="h-5 w-5" />
                  </Link>
                  <Link
                    href="/pricing"
                    className="inline-flex items-center justify-center gap-2 px-8 py-4 border border-border text-zinc-300 rounded-xl font-semibold hover:bg-surface hover:border-border-hover transition-all text-lg"
                  >
                    View Pricing
                  </Link>
                </div>

                <p className="mt-6 text-sm text-zinc-500">No credit card required • 14-day free trial</p>
              </div>
            </div>
          </section>

          {/* Features Section */}
          <section className="py-20 border-t border-border">
            <div className="container-custom">
              <div className="text-center mb-14">
                <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
                  Everything you need to build AI agents
                </h2>
                <p className="text-zinc-400 max-w-2xl mx-auto">
                  Powerful features designed to help you create and deploy intelligent agents in minutes
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {features.map((feature, index) => (
                  <div
                    key={index}
                    className="p-6 rounded-2xl border border-border bg-surface hover:border-primary/30 hover:bg-surface-elevated transition-all group"
                  >
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                      <feature.icon className="h-6 w-6 text-primary" />
                    </div>
                    <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                    <p className="text-sm text-zinc-400 leading-relaxed">{feature.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Stats Section */}
          <section className="py-20 bg-surface border-y border-border">
            <div className="container-custom">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
                {[
                  { value: '10K+', label: 'Active Agents' },
                  { value: '1M+', label: 'Conversations' },
                  { value: '99.9%', label: 'Uptime' },
                  { value: '<100ms', label: 'Avg Response' },
                ].map((stat, index) => (
                  <div key={index} className="text-center">
                    <div className="text-3xl md:text-4xl font-bold gradient-text mb-2">{stat.value}</div>
                    <div className="text-sm text-zinc-500">{stat.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* CTA Section */}
          <section className="py-24">
            <div className="container-custom">
              <div className="relative overflow-hidden rounded-3xl bg-surface-elevated border border-border p-8 md:p-16 text-center">
                <div className="absolute inset-0 overflow-hidden pointer-events-none">
                  <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
                </div>
                <div className="relative">
                  <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
                    Ready to build your first AI agent?
                  </h2>
                  <p className="text-zinc-400 max-w-xl mx-auto mb-8">
                    Start building for free. No credit card required, cancel anytime.
                  </p>
                  <Link
                    href="/login"
                    className="inline-flex items-center gap-2 px-8 py-4 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all"
                  >
                    Start Building Now
                    <ArrowRight className="h-5 w-5" />
                  </Link>
                </div>
              </div>
            </div>
          </section>

          {/* Footer */}
          <footer className="border-t border-border py-12">
            <div className="container-custom">
              <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-primary/10">
                    <Bot className="h-5 w-5 text-primary" />
                  </div>
                  <span className="font-bold text-lg gradient-text">SAHJONY</span>
                </div>
                <div className="flex items-center gap-8 text-sm text-zinc-500">
                  <Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link>
                  <Link href="/agents" className="hover:text-white transition-colors">Agents</Link>
                  <Link href="/login" className="hover:text-white transition-colors">Sign in</Link>
                </div>
                <p className="text-sm text-zinc-600">© 2025 SAHJONY. All rights reserved.</p>
              </div>
            </div>
          </footer>
        </main>
      </div>
    )
  }

  // Get user's agents and recent conversations
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
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8 animate-slide-up">
          <div>
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-zinc-400 mt-1">Welcome back! Here's your AI overview.</p>
          </div>
          <Link
            href="/agents/new"
            className="inline-flex items-center gap-2 px-5 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all"
          >
            <Plus className="h-4 w-4" />
            Create Agent
          </Link>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-10">
          <div className="card-elevated animate-slide-up" style={{ animationDelay: '50ms' }}>
            <div className="flex items-center gap-4">
              <div className="p-4 rounded-xl bg-primary/10">
                <Bot className="h-7 w-7 text-primary" />
              </div>
              <div>
                <p className="text-3xl font-bold text-white">{agents?.length || 0}</p>
                <p className="text-sm text-zinc-500">Active Agents</p>
              </div>
            </div>
          </div>
          <div className="card-elevated animate-slide-up" style={{ animationDelay: '100ms' }}>
            <div className="flex items-center gap-4">
              <div className="p-4 rounded-xl bg-accent/10">
                <MessageSquare className="h-7 w-7 text-accent" />
              </div>
              <div>
                <p className="text-3xl font-bold text-white">{conversations?.length || 0}</p>
                <p className="text-sm text-zinc-500">Conversations</p>
              </div>
            </div>
          </div>
          <div className="card-elevated animate-slide-up" style={{ animationDelay: '150ms' }}>
            <div className="flex items-center gap-4">
              <div className="p-4 rounded-xl bg-emerald-500/10">
                <TrendingUp className="h-7 w-7 text-emerald-400" />
              </div>
              <div>
                <p className="text-3xl font-bold text-white">
                  {conversations?.reduce((acc, c) => acc + 0, 0) || 0}
                </p>
                <p className="text-sm text-zinc-500">Total Messages</p>
              </div>
            </div>
          </div>
        </div>

        {/* Usage Analytics */}
        <div className="mb-10 animate-slide-up" style={{ animationDelay: '175ms' }}>
          <h2 className="text-xl font-semibold text-white mb-5">Usage Analytics</h2>
          <UsageAnalytics />
        </div>

        {/* Recent Agents */}
        <div className="mb-10 animate-slide-up" style={{ animationDelay: '200ms' }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-semibold text-white">Recent Agents</h2>
            <Link
              href="/agents"
              className="flex items-center gap-1 text-sm text-zinc-400 hover:text-primary transition-colors"
            >
              View all
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          {agents && agents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {agents.map((agent, index) => (
                <Link
                  key={agent.id}
                  href={`/agents/${agent.id}`}
                  className="card-elevated card-hover group"
                  style={{ animationDelay: `${250 + index * 50}ms` }}
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                      <Bot className="h-6 w-6 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-white truncate">{agent.name}</h3>
                      <p className="text-xs text-zinc-500 mt-0.5">{agent.model}</p>
                    </div>
                    <span className={`badge ${agent.status === 'active' ? 'badge-success' : 'bg-zinc-700 text-zinc-400'}`}>
                      {agent.status}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card-elevated text-center py-16">
              <div className="w-16 h-16 rounded-2xl bg-surface mx-auto mb-4 flex items-center justify-center">
                <Bot className="h-8 w-8 text-zinc-600" />
              </div>
              <p className="text-zinc-500 mb-5">No agents yet</p>
              <Link
                href="/agents/new"
                className="inline-flex items-center gap-2 px-5 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
              >
                <Plus className="h-4 w-4" />
                Create your first agent
              </Link>
            </div>
          )}
        </div>

        {/* Recent Conversations */}
        <div className="animate-slide-up" style={{ animationDelay: '300ms' }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-semibold text-white">Recent Conversations</h2>
            <Link
              href="/conversations"
              className="flex items-center gap-1 text-sm text-zinc-400 hover:text-primary transition-colors"
            >
              View all
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          {conversations && conversations.length > 0 ? (
            <div className="space-y-3">
              {conversations.map((conv, index) => (
                <Link
                  key={conv.id}
                  href={`/agents/${conv.agent_id}?conversation=${conv.id}`}
                  className="card-elevated card-hover group flex items-center justify-between p-4"
                  style={{ animationDelay: `${350 + index * 50}ms` }}
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded-lg bg-surface group-hover:bg-border transition-colors">
                      <MessageSquare className="h-5 w-5 text-zinc-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-white truncate">{conv.title}</h3>
                      <p className="text-xs text-zinc-500 mt-0.5">{conv.agents?.name}</p>
                    </div>
                  </div>
                  <span className="text-xs text-zinc-500 flex-shrink-0">
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="card-elevated text-center py-16">
              <div className="w-16 h-16 rounded-2xl bg-surface mx-auto mb-4 flex items-center justify-center">
                <MessageSquare className="h-8 w-8 text-zinc-600" />
              </div>
              <p className="text-zinc-500">No conversations yet</p>
              <p className="text-sm text-zinc-600 mt-1">Start a chat with an agent to see history here</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}