import Link from 'next/link'
import { MessageSquare, Clock } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

export default async function ConversationsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <div className="min-h-screen bg-background noise-overlay">
        <TopNav />
        <main className="container-custom py-20">
          <div className="max-w-lg mx-auto text-center">
            <h1 className="text-3xl font-display font-bold text-white mb-4">Conversations</h1>
            <p className="text-text-secondary mb-8">Sign in to view your conversations.</p>
            <Link href="/login" className="btn btn-primary px-8 py-3">Sign In</Link>
          </div>
        </main>
      </div>
    )
  }

  const { data: conversations } = await supabase
    .from('conversations')
    .select('*, agents(id, name)')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false })

  return (
    <div className="min-h-screen bg-background noise-overlay">
      <TopNav />
      <main className="container-custom py-8">
        <div className="mb-8 animate-slide-up">
          <h1 className="text-3xl font-display font-bold text-white tracking-tighter">Conversations</h1>
          <p className="text-text-secondary mt-1 text-sm font-light">Your chat history with AI agents</p>
        </div>

        {conversations && conversations.length > 0 ? (
          <div className="space-y-2">
            {conversations.map((conv, index) => (
              <Link
                key={conv.id}
                href={`/agents/${conv.agent_id}?conversation=${conv.id}`}
                className="card-tesla flex items-center justify-between p-5 group animate-slide-up"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.03] flex items-center justify-center border border-border group-hover:border-border-hover transition-colors duration-300 flex-shrink-0">
                    <MessageSquare className="h-5 w-5 text-text-muted" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-medium text-white text-sm truncate">{conv.title || 'Untitled'}</h3>
                    <p className="text-xs text-text-muted mt-0.5">{conv.agents?.name || 'Unknown Agent'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-text-dim flex-shrink-0">
                  <Clock className="h-3 w-3" />
                  {new Date(conv.updated_at).toLocaleDateString()}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="card-tesla text-center py-24 animate-scale-in">
            <div className="w-16 h-16 rounded-2xl bg-surface mx-auto mb-5 flex items-center justify-center border border-border">
              <MessageSquare className="h-7 w-7 text-text-dim" />
            </div>
            <h2 className="text-xl font-display font-semibold text-white mb-2">No conversations yet</h2>
            <p className="text-text-secondary text-sm mb-8">Deploy an agent and start chatting.</p>
            <Link
              href="/agents"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-full font-medium text-sm hover:bg-primary-hover transition-all duration-300"
            >
              View Agents
            </Link>
          </div>
        )}
      </main>
    </div>
  )
}
