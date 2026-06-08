'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/components/providers'
import { createClient } from '@/lib/supabase/client'
import { ArrowRight, Github, Mail } from 'lucide-react'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { user } = useAuth()

  if (user) {
    if (typeof window !== 'undefined') window.location.href = '/'
    return null
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const supabase = createClient()
    const { error } = await supabase.auth.signInWithPassword({ email, password })

    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      window.location.href = '/'
    }
  }

  const handleGithubLogin = async () => {
    const supabase = createClient()
    await supabase.auth.signInWithOAuth({
      provider: 'github',
      options: { redirectTo: `${window.location.origin}/` },
    })
  }

  return (
    <div className="min-h-screen bg-background noise-overlay flex items-center justify-center">
      <div className="absolute inset-0 tesla-hero-gradient" />
      <div className="relative z-10 w-full max-w-md px-6">
        <div className="text-center mb-10">
          <Link href="/" className="inline-flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
              <span className="text-white font-display font-bold text-lg">S</span>
            </div>
            <span className="font-display font-bold text-2xl text-white tracking-tesla">SAHJONY</span>
          </Link>
          <h1 className="text-3xl font-display font-bold text-white tracking-tighter mb-2">Sign in</h1>
          <p className="text-text-secondary text-sm font-light">Access your AI trading platform</p>
        </div>

        <div className="card-tesla p-8">
          <button
            onClick={handleGithubLogin}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white/[0.04] border border-white/[0.08] rounded-xl text-white font-medium text-sm hover:bg-white/[0.06] hover:border-white/[0.12] transition-all duration-300 mb-6"
          >
            <Github className="h-5 w-5" />
            Continue with GitHub
          </button>

          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-text-muted uppercase tracking-wider">or</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-wider">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="you@company.com"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-wider">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
                required
              />
            </div>

            {error && (
              <p className="text-sm text-error">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full btn btn-primary py-3 text-sm"
            >
              {loading ? 'Signing in...' : 'Sign in'}
              {!loading && <ArrowRight className="h-4 w-4" />}
            </button>
          </form>

          <div className="flex items-center justify-between mt-6 text-xs">
            <Link href="/forgot-password" className="text-text-muted hover:text-white transition-colors">
              Forgot password?
            </Link>
            <Link href="/pricing" className="text-primary hover:text-primary-hover transition-colors">
              Request access
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
