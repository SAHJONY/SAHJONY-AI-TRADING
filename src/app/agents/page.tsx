import Link from 'next/link'
import { Plus, Bot, ArrowRight } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { Sidebar } from '@/components/layout/sidebar'
import { AgentCard } from '@/components/agents/agent-card'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

export default async function AgentsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <div className="min-h-screen bg-background">
        <TopNav />
        <main className="container-custom py-32 text-center">
          <div className="w-20 h-20 rounded-2xl bg-primary/10 mx-auto mb-6 flex items-center justify-center">
            <Bot className="h-10 w-10 text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-3">Sign in to view your agents</h1>
          <p className="text-zinc-500 mb-6">Access your AI agents and start building</p>
          <Link 
            href="/login" 
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
          >
            Sign in
            <ArrowRight className="h-4 w-4" />
          </Link>
        </main>
      </div>
    )
  }

  const { data: agents } = await supabase
    .from('agents')
    .select('*')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false })

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <div className="flex">
        <Sidebar agents={agents || []} />
        <main className="flex-1 p-6 lg:p-8">
          {/* Header */}
          <div className="flex items-center justify-between mb-8 animate-slide-up">
            <div>
              <h1 className="text-2xl font-bold text-white">Agents</h1>
              <p className="text-zinc-500 mt-1">Manage your AI agents</p>
            </div>
            <Link
              href="/agents/new"
              className="inline-flex items-center gap-2 px-5 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all"
            >
              <Plus className="h-4 w-4" />
              New Agent
            </Link>
          </div>

          {/* Agents Grid */}
          {agents && agents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {agents.map((agent, index) => (
                <div key={agent.id} className="animate-slide-up" style={{ animationDelay: `${50 + index * 50}ms` }}>
                  <AgentCard agent={agent} />
                </div>
              ))}
            </div>
          ) : (
            <div className="card-elevated text-center py-20 animate-slide-up">
              <div className="w-20 h-20 rounded-2xl bg-surface mx-auto mb-6 flex items-center justify-center">
                <Bot className="h-10 w-10 text-zinc-600" />
              </div>
              <h2 className="text-xl font-semibold text-white mb-2">No agents yet</h2>
              <p className="text-zinc-500 mb-6 max-w-sm mx-auto">Create your first AI agent to get started with automated conversations</p>
              <Link
                href="/agents/new"
                className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
              >
                <Plus className="h-5 w-5" />
                Create Agent
              </Link>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}