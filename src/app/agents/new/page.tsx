'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/providers'
import { createClient } from '@/lib/supabase/client'
import { ArrowLeft, Bot, Cpu, Brain, Zap, Shield } from 'lucide-react'
import Link from 'next/link'

const agentTemplates = [
  { name: 'Alpha Scout', description: 'Scans for alpha opportunities across markets using technical and fundamental signals', model: 'meta-llama/llama-3.3-70b-instruct', icon: Brain },
  { name: 'Risk Monitor', description: 'Continuously monitors portfolio risk, margin levels, and correlation drift', model: 'nvidia/llama-3.1-nemotron-70b-instruct', icon: Shield },
  { name: 'Sentiment Engine', description: 'Parses news, filings, and social sentiment for directional signals', model: 'meta-llama/llama-3.3-70b-instruct', icon: Zap },
  { name: 'Custom Agent', description: 'Build your own agent from scratch with custom configuration', model: 'meta-llama/llama-3.3-70b-instruct', icon: Cpu },
]

export default function NewAgentPage() {
  const { user } = useAuth()
  const router = useRouter()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [model, setModel] = useState('meta-llama/llama-3.3-70b-instruct')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  if (!user) {
    router.push('/login')
    return null
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const supabase = createClient()
    const { data, error } = await supabase
      .from('agents')
      .insert({
        user_id: user.id,
        name,
        description,
        model,
        status: 'active',
      })
      .select()
      .single()

    if (error) {
      setError(error.message)
      setLoading(false)
    } else if (data) {
      router.push(`/agents/${data.id}`)
    }
  }

  const selectTemplate = (template: typeof agentTemplates[0]) => {
    setName(template.name)
    setDescription(template.description)
    setModel(template.model)
  }

  return (
    <div className="min-h-screen bg-background noise-overlay">
      <main className="container-custom py-8 max-w-3xl mx-auto">
        <Link
          href="/agents"
          className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-white transition-colors mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agents
        </Link>

        <h1 className="text-3xl font-display font-bold text-white tracking-tighter mb-2 animate-slide-up">Deploy New Agent</h1>
        <p className="text-text-secondary text-sm font-light mb-10 animate-slide-up">Choose a template or configure a custom agent</p>

        {/* Templates */}
        <div className="grid grid-cols-2 gap-3 mb-10">
          {agentTemplates.map((template) => (
            <button
              key={template.name}
              onClick={() => selectTemplate(template)}
              className={`card-tesla p-5 text-left group transition-all duration-300 ${
                name === template.name ? 'border-primary/30 ring-1 ring-primary/10' : ''
              }`}
            >
              <template.icon className={`h-5 w-5 mb-3 ${name === template.name ? 'text-primary' : 'text-text-secondary group-hover:text-primary'} transition-colors duration-300`} />
              <h3 className="text-sm font-semibold text-white mb-1">{template.name}</h3>
              <p className="text-xs text-text-muted leading-relaxed line-clamp-2">{template.description}</p>
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleCreate} className="card-tesla p-8 space-y-5">
          <div>
            <label className="block text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-wider">Agent Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
              placeholder="e.g. Alpha Scout"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-wider">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="input min-h-[80px] resize-none"
              placeholder="What does this agent do?"
            />
          </div>
          <div>
            <label className="block text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-wider">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="input"
            >
              <option value="meta-llama/llama-3.3-70b-instruct">Llama 3.3 70B</option>
              <option value="nvidia/llama-3.1-nemotron-70b-instruct">Nemotron 70B</option>
              <option value="deepseek-ai/deepseek-r1">DeepSeek R1</option>
            </select>
          </div>

          {error && <p className="text-sm text-error">{error}</p>}

          <button
            type="submit"
            disabled={loading || !name}
            className="w-full btn btn-primary py-3 text-sm"
          >
            {loading ? 'Deploying...' : 'Deploy Agent'}
          </button>
        </form>
      </main>
    </div>
  )
}
