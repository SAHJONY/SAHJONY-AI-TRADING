'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

// Dummy data for AI agents – replace with real data from your backend
const dummyAgents = [
  { id: '1', name: 'Market Scout', status: 'active', description: 'Scans market data in real‑time' },
  { id: '2', name: 'Risk Manager', status: 'idle', description: 'Monitors portfolio risk limits' },
  { id: '3', name: 'Trade Executor', status: 'active', description: 'Places orders on Alpaca' },
]

export default function AdminDashboard() {
  const [agents, setAgents] = useState(dummyAgents)
  const [loading, setLoading] = useState(false)

  // Example Supabase fetch – currently a stub because no table is defined
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      const supabase = createClient()
      // const { data, error } = await supabase.from('agents').select('*')
      // if (!error) setAgents(data)
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div className="min-h-screen bg-background py-8">
      <div className="container mx-auto px-4">
        <h1 className="text-3xl font-bold mb-6 text-white">Ultra‑Premium AI Agentic Dashboard</h1>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <div key={agent.id} className="bg-card/30 backdrop-blur-sm border border-primary/20 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-lg font-semibold text-white">{agent.name}</h2>
                <span className={`px-2 py-0.5 rounded text-xs ${agent.status === 'active' ? 'bg-green-600' : 'bg-gray-600'}`}>{agent.status}</span>
              </div>
              <p className="text-sm text-muted-foreground">{agent.description}</p>
            </div>
          ))}
        </div>
        {loading && <p className="mt-4 text-center text-muted-foreground">Loading…</p>}
      </div>
    </div>
  )
}
