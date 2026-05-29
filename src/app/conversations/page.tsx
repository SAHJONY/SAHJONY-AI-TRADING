'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { MessageSquare, Trash2, ArrowRight, Bot } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { Sidebar } from '@/components/layout/sidebar'
import { createClient } from '@/lib/supabase/client'
import { formatDate } from '@/lib/utils'
import { Modal } from '@/components/ui/modal'
import { Button } from '@/components/ui/button'
import type { Agent, Conversation } from '@/types/database'
import { cn } from '@/lib/utils'

interface ConversationWithAgent extends Conversation {
  agents?: { name: string } | null
}

export default function ConversationsPage() {
  const supabase = createClient()
  const [conversations, setConversations] = useState<ConversationWithAgent[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Load data on mount
  useEffect(() => {
    const loadData = async () => {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return

      const [agentsRes, convRes] = await Promise.all([
        supabase.from('agents').select('*').eq('user_id', user.id).order('updated_at', { ascending: false }),
        supabase.from('conversations').select('*, agents(name)').eq('user_id', user.id).order('updated_at', { ascending: false })
      ])

      setAgents(agentsRes.data || [])
      setConversations(convRes.data || [])
      setLoading(false)
    }
    loadData()
  }, [supabase])

  const handleDelete = async () => {
    if (!deleteId) return
    setDeleting(true)

    const { error } = await supabase
      .from('conversations')
      .delete()
      .eq('id', deleteId)

    if (!error) {
      setConversations(prev => prev.filter(c => c.id !== deleteId))
    }
    setDeleteId(null)
    setDeleting(false)
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <div className="flex">
        <Sidebar agents={agents} />
        <main className="flex-1 p-6 lg:p-8">
          <div className="mb-8 animate-slide-up">
            <h1 className="text-2xl font-bold text-white">Conversations</h1>
            <p className="text-zinc-500 mt-1">Your chat history with AI agents</p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            </div>
          ) : conversations.length > 0 ? (
            <div className="space-y-3">
              {conversations.map((conv, index) => (
                <div
                  key={conv.id}
                  className="card-elevated card-hover group flex items-center justify-between p-4 animate-slide-up"
                  style={{ animationDelay: `${50 + index * 30}ms` }}
                >
                  <Link
                    href={`/agents/${conv.agent_id}?conversation=${conv.id}`}
                    className="flex items-center gap-4 flex-1 min-w-0"
                  >
                    <div className="p-2.5 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                      <MessageSquare className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-white truncate">{conv.title}</h3>
                      <div className="flex items-center gap-2 mt-1">
                        <Bot className="h-3.5 w-3.5 text-zinc-500" />
                        <span className="text-xs text-zinc-500 truncate">{conv.agents?.name || 'Unknown Agent'}</span>
                        <span className="text-zinc-600">•</span>
                        <span className="text-xs text-zinc-500">{formatDate(conv.updated_at)}</span>
                      </div>
                    </div>
                    <ArrowRight className="h-5 w-5 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                  </Link>
                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      setDeleteId(conv.id)
                    }}
                    className="p-2.5 rounded-xl opacity-0 group-hover:opacity-100 hover:bg-error/20 text-zinc-400 hover:text-error transition-all flex-shrink-0 ml-2"
                    title="Delete conversation"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="card-elevated text-center py-20 animate-slide-up">
              <div className="w-20 h-20 rounded-2xl bg-surface mx-auto mb-6 flex items-center justify-center">
                <MessageSquare className="h-10 w-10 text-zinc-600" />
              </div>
              <h2 className="text-xl font-medium text-white mb-2">No conversations yet</h2>
              <p className="text-zinc-500 max-w-sm mx-auto">Start chatting with an agent to see your history here</p>
            </div>
          )}
        </main>
      </div>

      {/* Delete confirmation modal */}
      <Modal
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        title="Delete Conversation"
        description="This action cannot be undone. The conversation and all its messages will be permanently deleted."
        size="sm"
      >
        <div className="flex gap-3 mt-4">
          <Button variant="secondary" onClick={() => setDeleteId(null)} className="flex-1">
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDelete} disabled={deleting} className="flex-1">
            {deleting ? 'Deleting...' : 'Delete Conversation'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}