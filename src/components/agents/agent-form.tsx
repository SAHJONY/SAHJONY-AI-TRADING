'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Input, Textarea } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/client'
import { MODELS } from '@/lib/constants'
import type { Agent } from '@/types/database'

interface AgentFormProps {
  agent?: Agent
  onSuccess?: () => void
}

export function AgentForm({ agent, onSuccess }: AgentFormProps) {
  const router = useRouter()
  const supabase = createClient()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [name, setName] = useState(agent?.name || '')
  const [description, setDescription] = useState(agent?.description || '')
  const [systemPrompt, setSystemPrompt] = useState(
    agent?.system_prompt || 'You are a helpful AI assistant.'
  )
  const [model, setModel] = useState(agent?.model || 'gpt-4')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      if (agent) {
        // Update existing agent
        const { error } = await supabase
          .from('agents')
          .update({
            name,
            description,
            system_prompt: systemPrompt,
            model,
          })
          .eq('id', agent.id)

        if (error) throw error
      } else {
        // Create new agent
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) throw new Error('Not authenticated')

        const { error } = await supabase.from('agents').insert({
          user_id: user.id,
          name,
          description,
          system_prompt: systemPrompt,
          model,
        })

        if (error) throw error
      }

      onSuccess?.()
      router.push('/agents')
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="p-3 rounded-md bg-error/10 border border-error/30 text-error text-sm">
          {error}
        </div>
      )}

      <Input
        label="Agent Name"
        placeholder="My AI Assistant"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />

      <Textarea
        label="Description"
        placeholder="Describe what your agent does..."
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />

      <Textarea
        label="System Prompt"
        placeholder="You are a helpful AI assistant that..."
        value={systemPrompt}
        onChange={(e) => setSystemPrompt(e.target.value)}
        className="min-h-[150px]"
      />

      <Select
        label="Model"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        options={MODELS.map((m) => ({ value: m.id, label: `${m.name} (${m.provider})` }))}
      />

      <div className="flex gap-3 pt-4">
        <Button type="submit" disabled={loading}>
          {loading ? 'Saving...' : agent ? 'Update Agent' : 'Create Agent'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => router.back()}
        >
          Cancel
        </Button>
      </div>
    </form>
  )
}