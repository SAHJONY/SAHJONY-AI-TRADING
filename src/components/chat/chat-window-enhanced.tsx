'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, Copy, RefreshCw, Check, Bot, Wifi, WifiOff, Settings2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/utils'
import { BrainStatus } from '@/components/agents/brain-status'
import { ConversationSettings, ConversationSettings as ConversationSettingsType } from '@/components/chat/conversation-settings'
import { QuickActions } from '@/components/chat/quick-actions'
import type { Message } from '@/types/database'

interface EnhancedChatWindowProps {
  messages: Message[]
  onSend: (content: string, settings?: ConversationSettingsType) => void
  onRetry?: () => void
  onClear?: () => void
  onExport?: () => void
  onShare?: () => void
  streaming?: boolean
  brainStatus?: boolean
}

export function EnhancedChatWindow({ 
  messages, 
  onSend, 
  onRetry, 
  onClear,
  onExport,
  onShare,
  streaming = false,
  brainStatus = true 
}: EnhancedChatWindowProps) {
  const [input, setInput] = useState('')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [conversationSettings, setConversationSettings] = useState<ConversationSettingsType>()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streaming])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || streaming) return
    onSend(input.trim(), conversationSettings)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const copyMessage = async (id: string, content: string) => {
    await navigator.clipboard.writeText(content)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const handleSettingsChange = (settings: ConversationSettingsType) => {
    setConversationSettings(settings)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with Brain Status */}
      {brainStatus && (
        <div className="border-b border-border px-4 py-3">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-primary/10">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">SAHJONY Agent</h3>
                <p className="text-xs text-zinc-500">Powered by Unified Brain</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ConversationSettings onSettingsChange={handleSettingsChange} />
              <QuickActions
                onClear={onClear}
                onExport={onExport}
                onShare={onShare}
                onCopy={() => messages.length > 0 && copyMessage(messages[0].id, messages[0].content)}
                onRegenerate={onRetry}
              />
            </div>
          </div>
          <BrainStatus showDetails={true} />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center animate-fade-in">
            <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
              <Bot className="h-10 w-10 text-primary" />
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">Start a conversation</h3>
            <p className="text-zinc-500 max-w-sm leading-relaxed">
              Send a message to begin chatting with your AI agent powered by Hermes and Freebuff.
            </p>
            
            {/* Quick Start Suggestions */}
            <div className="flex flex-wrap justify-center gap-2 mt-6 max-w-md">
              {[
                'Help me write a Python function',
                'Explain how async/await works',
                'Debug my React component',
                'Create a REST API endpoint',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="text-xs px-3 py-1.5 bg-surface-elevated border border-border rounded-full text-zinc-400 hover:text-white hover:border-primary/30 transition-all"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <div
              key={message.id}
              className={cn(
                'flex animate-slide-up',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-5 py-4',
                  message.role === 'user'
                    ? 'bg-primary text-white rounded-tr-md'
                    : 'bg-surface-elevated border border-border rounded-tl-md'
                )}
              >
                <div className="text-sm leading-relaxed whitespace-pre-wrap">
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>

                <div className="flex items-center justify-between mt-3 pt-2 border-t border-border/50">
                  <span className="text-xs opacity-50">
                    {message.role === 'user' ? 'You' : 'SAHJONY'} • {formatDate(message.created_at)}
                  </span>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => copyMessage(message.id, message.content)}
                      className="p-1.5 rounded-lg hover:bg-white/10 transition-colors opacity-50 hover:opacity-100"
                      title="Copy message"
                    >
                      {copiedId === message.id ? (
                        <Check className="h-3.5 w-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                    {message.role === 'assistant' && onRetry && (
                      <button
                        onClick={onRetry}
                        className="p-1.5 rounded-lg hover:bg-white/10 transition-colors opacity-50 hover:opacity-100"
                        title="Regenerate response"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}

        {/* Streaming indicator */}
        {streaming && (
          <div className="flex justify-start animate-slide-up">
            <div className="bg-surface-elevated border border-border rounded-2xl rounded-tl-md px-5 py-4">
              <div className="flex items-center gap-3 text-zinc-400">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '100ms' }} />
                  <span className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '200ms' }} />
                </div>
                <span className="text-sm">Thinking...</span>
                <span className="text-xs text-zinc-600">Powered by Unified Brain</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-4 bg-surface/50">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (Shift+Enter for new line)"
            className="flex-1 bg-surface-elevated border border-border rounded-xl px-4 py-3.5 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:border-primary focus:ring-primary/30 resize-none"
            rows={1}
            disabled={streaming}
          />
          <button
            type="submit"
            disabled={!input.trim() || streaming}
            className="px-5 py-3.5 bg-primary text-white rounded-xl hover:bg-primary-hover hover:shadow-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
          >
            <Send className="h-5 w-5" />
          </button>
        </form>
        <div className="flex items-center justify-between mt-2.5">
          <p className="text-xs text-zinc-600">
            Press Enter to send, Shift+Enter for new line
          </p>
          {conversationSettings && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span>Model: {conversationSettings.model}</span>
              <span>•</span>
              <span>Temp: {conversationSettings.temperature}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}