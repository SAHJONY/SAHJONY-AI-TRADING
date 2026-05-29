'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Bot, ArrowLeft, Settings } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { TopNav } from '@/components/layout/top-nav'
import { Sidebar } from '@/components/layout/sidebar'
import { ChatWindow } from '@/components/chat/chat-window'
import { cn } from '@/lib/utils'
import type { Agent, Conversation, Message } from '@/types/database'

export default function AgentChatPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const supabase = createClient()

  const [agent, setAgent] = useState<Agent | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [streaming, setStreaming] = useState(false)

  const agentId = params.id as string
  const conversationId = searchParams.get('conversation')

  const loadAgent = useCallback(async () => {
    const { data: agent } = await supabase
      .from('agents')
      .select('*')
      .eq('id', agentId)
      .single()
    setAgent(agent)
  }, [supabase, agentId])

  const loadAgents = useCallback(async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return
    const { data } = await supabase
      .from('agents')
      .select('*')
      .eq('user_id', user.id)
      .order('updated_at', { ascending: false })
    setAgents(data || [])
  }, [supabase])

  const loadConversation = useCallback(async () => {
    if (!conversationId) {
      // Create new conversation
      const { data: { user } } = await supabase.auth.getUser()
      if (!user || !agent) return

      const { data: conv } = await supabase
        .from('conversations')
        .insert({
          agent_id: agentId,
          user_id: user.id,
          title: 'New Conversation',
        })
        .select()
        .single()

      if (conv) {
        setConversation(conv)
        // Update URL without refresh
        window.history.replaceState({}, '', `/agents/${agentId}?conversation=${conv.id}`)
      }
      return
    }

    const { data: conv } = await supabase
      .from('conversations')
      .select('*')
      .eq('id', conversationId)
      .single()
    setConversation(conv)
  }, [supabase, agentId, conversationId, agent])

  const loadMessages = useCallback(async () => {
    if (!conversation) return

    const { data } = await supabase
      .from('messages')
      .select('*')
      .eq('conversation_id', conversation.id)
      .order('created_at', { ascending: true })
    setMessages(data || [])
  }, [supabase, conversation])

  useEffect(() => {
    Promise.all([loadAgent(), loadAgents()])
  }, [loadAgent, loadAgents])

  useEffect(() => {
    if (agent) {
      loadConversation()
    }
  }, [agent, loadConversation])

  useEffect(() => {
    if (conversation) {
      loadMessages()
    }
  }, [conversation, loadMessages])

  const handleSend = async (content: string) => {
    if (!conversation || !agent) return

    // Add user message
    const { data: userMsg } = await supabase
      .from('messages')
      .insert({
        conversation_id: conversation.id,
        role: 'user',
        content,
      })
      .select()
      .single()

    if (userMsg) {
      setMessages((prev) => [...prev, userMsg])
    }

    setStreaming(true)

    try {
      // Call chat API
      const response = await fetch(`/api/chat/${conversation.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: content,
          agentId,
        }),
      })

      if (!response.ok) throw new Error('Failed to get response')

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      let assistantContent = ''

      // Read streaming response
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const text = new TextDecoder().decode(value)
        assistantContent += text

        // Update messages with streaming content
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant') {
            return [...prev.slice(0, -1), { ...last, content: assistantContent }]
          }
          // Create new assistant message placeholder
          return [...prev, {
            id: 'temp-' + Date.now(),
            conversation_id: conversation.id,
            role: 'assistant' as const,
            content: assistantContent,
            metadata: {},
            created_at: new Date().toISOString()
          }]
        })
      }

      // Save assistant message to database
      if (assistantContent) {
        await supabase.from('messages').insert({
          conversation_id: conversation.id,
          role: 'assistant',
          content: assistantContent,
        })
      }

      // Update conversation title with first user message
      if (messages.length === 0) {
        await supabase
          .from('conversations')
          .update({ title: content.slice(0, 50) + (content.length > 50 ? '...' : '') })
          .eq('id', conversation.id)
      }
    } catch (error) {
      console.error('Chat error:', error)
      // Remove the streaming placeholder on error
      setMessages((prev) => prev.filter(m => !m.id.startsWith('temp-')))
    } finally {
      setStreaming(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <TopNav />
        <div className="flex">
          <Sidebar agents={agents} />
          <main className="flex-1 flex items-center justify-center">
            <div className="flex items-center gap-3 text-zinc-500">
              <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              Loading agent...
            </div>
          </main>
        </div>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="min-h-screen bg-background">
        <TopNav />
        <div className="flex">
          <Sidebar agents={agents} />
          <main className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-surface mx-auto mb-4 flex items-center justify-center">
                <Bot className="h-8 w-8 text-zinc-600" />
              </div>
              <h2 className="text-xl font-medium text-white mb-2">Agent not found</h2>
              <p className="text-zinc-500">This agent doesn't exist or you don't have access.</p>
              <Link
                href="/agents"
                className="inline-flex items-center gap-2 mt-4 text-primary hover:text-primary-hover transition-colors"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to agents
              </Link>
            </div>
          </main>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <div className="flex h-[calc(100vh-4rem)]">
        <Sidebar agents={agents} />
        <main className="flex-1 flex flex-col">
          {/* Chat header */}
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href="/agents"
                className="p-2 rounded-xl hover:bg-surface text-zinc-400 hover:text-white transition-all"
                title="Back to agents"
              >
                <ArrowLeft className="h-5 w-5" />
              </Link>
              <div className="p-2.5 rounded-xl bg-primary/10">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="font-semibold text-white">{agent.name}</h2>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    agent.status === 'active' ? 'bg-success' : 'bg-zinc-600'
                  )} />
                  <span className="text-xs text-zinc-500">{agent.model}</span>
                </div>
              </div>
            </div>
            <Link
              href={`/agents/${agent.id}/edit`}
              className="p-2.5 rounded-xl hover:bg-surface text-zinc-400 hover:text-white transition-all"
              title="Agent settings"
            >
              <Settings className="h-5 w-5" />
            </Link>
          </div>

          {/* Chat window */}
          <div className="flex-1 overflow-hidden">
            <ChatWindow
              messages={messages}
              onSend={handleSend}
              streaming={streaming}
            />
          </div>
        </main>
      </div>
    </div>
  )
}