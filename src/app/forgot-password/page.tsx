'use client'

import { useState } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { ArrowLeft, Mail } from 'lucide-react'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const supabase = createClient()
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })

    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      setSent(true)
    }
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
          <h1 className="text-3xl font-display font-bold text-white tracking-tighter mb-2">Reset Password</h1>
          <p className="text-text-secondary text-sm font-light">We'll send you a reset link</p>
        </div>

        <div className="card-tesla p-8">
          {sent ? (
            <div className="text-center py-4">
              <div className="w-12 h-12 rounded-xl bg-primary/[0.08] flex items-center justify-center border border-primary/10 mx-auto mb-4">
                <Mail className="h-6 w-6 text-primary" />
              </div>
              <p className="text-white font-medium mb-2">Check your email</p>
              <p className="text-sm text-text-secondary mb-6">We sent a password reset link to {email}</p>
              <Link href="/login" className="text-sm text-primary hover:text-primary-hover transition-colors">
                Back to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
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
              {error && <p className="text-sm text-error">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full btn btn-primary py-3 text-sm"
              >
                {loading ? 'Sending...' : 'Send Reset Link'}
              </button>
            </form>
          )}
        </div>

        <div className="text-center mt-6">
          <Link href="/login" className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-white transition-colors">
            <ArrowLeft className="h-3 w-3" />
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  )
}
