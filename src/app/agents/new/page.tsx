import { Bot, ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { TopNav } from '@/components/layout/top-nav'
import { AgentForm } from '@/components/agents/agent-form'

export const dynamic = 'force-dynamic'

export default function NewAgentPage() {
  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-8 max-w-2xl">
        {/* Back link */}
        <Link
          href="/agents"
          className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white transition-colors mb-6 animate-slide-up"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agents
        </Link>

        {/* Header */}
        <div className="mb-8 animate-slide-up" style={{ animationDelay: '50ms' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2.5 rounded-xl bg-primary/10">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <h1 className="text-2xl font-bold text-white">Create New Agent</h1>
          </div>
          <p className="text-zinc-500">Configure your AI agent with custom settings and capabilities</p>
        </div>

        {/* Form */}
        <div className="card-elevated animate-slide-up" style={{ animationDelay: '100ms' }}>
          <AgentForm />
        </div>
      </main>
    </div>
  )
}