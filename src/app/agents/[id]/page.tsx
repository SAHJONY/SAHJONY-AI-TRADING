'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/components/providers'
import { createClient } from '@/lib/supabase/client'
import { TopNav } from '@/components/layout/top-nav'
import { ArrowLeft, Send, Bot, User, Loader2 } from 'lucide-react'
import Link from 'next/link'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export default function AgentDetailPage() {
  const { user } = useAuth()
  const params = useParams()
  const router = useRouter()
  const agentId = params.id as string

  const [agent, setAgent] = useState<any>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!user) return
    const supabase = createClient()

    supabase.from('agents').select('*').eq('id', agentId).single().then(({ data }) => {
      setAgent(data)
    })

    supabase
      .from('messages')
      .select('*')
      .eq('agent_id', agentId)
      .order('created_at', { ascending: true })
      .then(({ data }) => {
        setMessages(data || [])
        setLoading(false)
      })
  }, [user, agentId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || sending) return

    const supabase = createClient()
    const userMessage = input.trim()
    setInput('')
    setSending(true)

    const { data: msg } = await supabase
      .from('messages')
      .insert({
        agent_id: agentId,
        user_id: user!.id,
        role: 'user',
        content: userMessage,
      })
      .select()
      .single()

    if (msg) setMessages(prev => [...prev, msg])

    // Call the chat API
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agentId, message: userMessage }),
      })
      const data = await res.json()

      if (data.content) {
        const { data: assistantMsg } = await supabase
          .from('messages')
          .insert({
            agent_id: agentId,
            user_id: user!.id,
            role: 'assistant',
            content: data.content,
          })
          .select()
          .single()
        if (assistantMsg) setMessages(prev => [...prev, assistantMsg])
      }
    } catch (err) {
      // Fallback: add error message
      setMessages(prev => [...prev, {
        id: 'error',
        role: 'assistant',
        content: 'Connection error. Please try again.',
        created_at: new Date().toISOString(),
      }])
    }

    setSending(false)
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-background noise-overlay">
        <TopNav />
        <main className="container-custom py-20 text-center">
          <p className="text-text-secondary mb-4">Sign in to chat with this agent.</p>
          <Link href="/login" className="btn btn-primary px-8 py-3">Sign In</Link>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <TopNav />
      <main className="flex-1 flex flex-col max-w-4xl mx-auto w-full">
        {/* Header */}
        <div className="border-b border-border/50 px-6 py-4 flex items-center gap-4">
          <Link href="/agents" className="text-text-muted hover:text-white transition-colors">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="flex items-center gap-3 flex-1">
            <div className="w-8 h-8 rounded-lg bg-primary/[0.08] flex items-center justify-center border border-primary/10">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white">{agent?.name || 'Agent'}</h1>
              <p className="text-xs text-text-muted">{agent?.model}</p>
            </div>
          </div>
          {agent && (
            <span className={`badge ${agent.status === 'active' ? 'badge-success' : 'bg-white/[0.04] text-text-muted border border-border'}`}>
              {agent.status}
            </span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 text-text-dim animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-20">
              <Bot className="h-8 w-8 text-text-dim mx-auto mb-4" />
              <p className="text-text-secondary text-sm">Start a conversation with this agent</p>
            </div>
          ) : (
            messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-lg bg-primary/[0.08] flex items-center justify-center border border-primary/10 flex-shrink-0">
                    <Bot className="h-3.5 w-3.5 text-primary" />
                  </div>
                )}
                <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-primary text-white'
                    : 'bg-surface border border-border text-text-secondary'
                }`}>
                  {msg.content}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-lg bg-white/[0.06] flex items-center justify-center border border-border flex-shrink-0">
                    <User className="h-3.5 w-3.5 text-text-secondary" />
                  </div>
                )}
              </div>
            ))
          )}
          {sending && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-lg bg-primary/[0.08] flex items-center justify-center border border-primary/10 flex-shrink-0">
                <Bot className="h-3.5 w-3.5 text-primary" />
              </div>
              <div className="bg-surface border border-border rounded-2xl px-4 py-3">
                <Loader2 className="h-4 w-4 text-text-dim animate-spin" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-border/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              className="input flex-1"
              placeholder="Send a message..."
              disabled={sending}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="btn btn-primary p-3"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
