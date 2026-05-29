import { notFound } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Bot } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { AgentForm } from '@/components/agents/agent-form'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

export default async function EditAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params
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
          <h1 className="text-2xl font-bold text-white mb-3">Sign in to edit agents</h1>
          <p className="text-zinc-500 mb-6">Access your AI agents and make changes</p>
          <Link 
            href="/login" 
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover transition-all"
          >
            Sign in
          </Link>
        </main>
      </div>
    )
  }

  const { data: agent } = await supabase
    .from('agents')
    .select('*')
    .eq('id', resolvedParams.id)
    .eq('user_id', user.id)
    .single()

  if (!agent) {
    notFound()
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-8 max-w-2xl">
        {/* Back link */}
        <Link
          href="/agents"
          className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white transition-colors mb-6"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agents
        </Link>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2.5 rounded-xl bg-primary/10">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Edit Agent</h1>
              <p className="text-zinc-500 mt-0.5">Update your AI agent configuration</p>
            </div>
          </div>
        </div>

        {/* Form */}
        <div className="card-elevated">
          <AgentForm agent={agent} />
        </div>
      </main>
    </div>
  )
}