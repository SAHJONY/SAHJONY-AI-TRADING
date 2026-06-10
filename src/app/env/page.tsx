'use client'
import { useState } from 'react'
import Link from 'next/link'
import { TopNav } from '@/components/layout/top-nav'

export const dynamic = 'force-dynamic'

export default function EnvPage() {
  const [variables, setVariables] = useState([{ key: '', value: '' }])

  const handleChange = (index: number, field: 'key' | 'value', val: string) => {
    const newVars = [...variables]
    newVars[index][field] = val
    setVariables(newVars)
  }

  const addRow = () => setVariables([...variables, { key: '', value: '' }])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const filtered = variables.filter(v => v.key.trim() !== '')
    const res = await fetch('/api/env', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filtered),
    })
    if (res.ok) {
      alert('Environment variables saved')
      setVariables([{ key: '', value: '' }])
    } else {
      const txt = await res.text()
      alert('Error: ' + txt)
    }
  }

  return (
    <main className="min-h-screen bg-background text-white">
      <TopNav />
      <div className="container-custom mx-auto py-12">
        <h1 className="text-3xl font-bold mb-6">Add Environment Variables</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          {variables.map((v, i) => (
            <div key={i} className="flex gap-2">
              <input
                type="text"
                placeholder="KEY"
                value={v.key}
                onChange={e => handleChange(i, 'key', e.target.value)}
                className="flex-1 px-3 py-2 bg-surface-glass rounded text-white placeholder:text-gray-400"
                required
              />
              <input
                type="text"
                placeholder="VALUE"
                value={v.value}
                onChange={e => handleChange(i, 'value', e.target.value)}
                className="flex-1 px-3 py-2 bg-surface-glass rounded text-white placeholder:text-gray-400"
                required
              />
            </div>
          ))}
          <button
            type="button"
            onClick={addRow}
            className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90"
          >
            Add another
          </button>
          <br />
          <button
            type="submit"
            className="px-6 py-3 bg-primary text-white rounded hover:bg-primary/90"
          >
            Save Variables
          </button>
        </form>
        <p className="mt-8 text-sm text-gray-400">
          Variables are appended to the project <code>.env</code> file in the repo root.
        </p>
        <Link href="/" className="mt-4 inline-block text-primary underline">
          ← Back to Home
        </Link>
      </div>
    </main>
  )
}
