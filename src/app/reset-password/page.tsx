'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Bot, Lock, ArrowLeft, Check, X } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'

export default function ResetPasswordPage() {
  const router = useRouter()
  const supabase = createClient()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [validating, setValidating] = useState(true)
  const [tokenValid, setTokenValid] = useState(false)

  // Check if we have a valid token from the URL
  useEffect(() => {
    const checkToken = async () => {
      // Supabase sends the token as query parameters (access_token, refresh_token)
      // when the user clicks the password reset link
      const hash = window.location.hash
      const search = window.location.search
      
      // Try to get tokens from hash first (Supabase sometimes uses fragment)
      let accessToken: string | null = null
      let refreshToken: string | null = null
      
      if (hash) {
        const hashParams = new URLSearchParams(hash.substring(1))
        accessToken = hashParams.get('access_token')
        refreshToken = hashParams.get('refresh_token')
      }
      
      // Also check search params
      if (!accessToken && search) {
        const searchParams = new URLSearchParams(search)
        accessToken = searchParams.get('access_token')
        refreshToken = searchParams.get('refresh_token')
        // Also check for 'token' parameter which some providers use
        if (!accessToken) {
          accessToken = searchParams.get('token')
        }
      }
      
      if (accessToken) {
        // Exchange the tokens for a session
        const { data, error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken || '',
        })
        
        if (error) {
          setError('Invalid or expired reset link')
          setTokenValid(false)
        } else if (data.session) {
          setTokenValid(true)
        }
      } else {
        // No token in URL - check if user is already logged in
        const { data: { session } } = await supabase.auth.getSession()
        if (session) {
          // User is logged in - they can reset password from settings
          setTokenValid(true)
        } else {
          setError('Invalid reset link. Please request a new one.')
          setTokenValid(false)
        }
      }
      setValidating(false)
    }
    
    checkToken()
  }, [supabase])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      setLoading(false)
      return
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      setLoading(false)
      return
    }

    try {
      const { error } = await supabase.auth.updateUser({
        password: password,
      })
      
      if (error) throw error
      
      setSuccess(true)
      // Redirect to login after 3 seconds
      setTimeout(() => {
        router.push('/login')
      }, 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  if (validating) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="text-zinc-400">Validating reset link...</div>
      </div>
    )
  }

  if (!tokenValid) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <Link href="/" className="flex items-center justify-center gap-2 mb-8">
            <div className="p-2 rounded-lg bg-primary/10">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <span className="text-2xl font-bold gradient-text">Convo</span>
          </Link>
          
          <div className="bg-surface border border-error/30 rounded-lg p-6">
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-error/10 mx-auto mb-4">
              <X className="h-6 w-6 text-error" />
            </div>
            <h2 className="text-xl font-semibold text-white text-center mb-2">
              Invalid Reset Link
            </h2>
            <p className="text-zinc-400 text-center mb-6">
              {error || 'This password reset link is invalid or has expired.'}
            </p>
            <div className="space-y-3">
              <Link
                href="/forgot-password"
                className="block w-full py-2.5 bg-primary text-white rounded-md font-medium text-center hover:bg-primary-hover transition-colors"
              >
                Request new reset link
              </Link>
              <Link
                href="/login"
                className="block w-full py-2.5 border border-border text-zinc-300 rounded-md font-medium text-center hover:bg-border transition-colors"
              >
                Back to login
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <Link href="/" className="flex items-center justify-center gap-2 mb-8">
            <div className="p-2 rounded-lg bg-primary/10">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <span className="text-2xl font-bold gradient-text">Convo</span>
          </Link>
          
          <div className="bg-surface border border-success/30 rounded-lg p-6">
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-success/10 mx-auto mb-4">
              <Check className="h-6 w-6 text-success" />
            </div>
            <h2 className="text-xl font-semibold text-white text-center mb-2">
              Password Reset Complete
            </h2>
            <p className="text-zinc-400 text-center mb-6">
              Your password has been successfully reset. Redirecting to login...
            </p>
            <div className="text-center">
              <div className="animate-pulse text-primary text-sm">Redirecting in 3 seconds...</div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <Link href="/" className="flex items-center justify-center gap-2 mb-8">
          <div className="p-2 rounded-lg bg-primary/10">
            <Bot className="h-8 w-8 text-primary" />
          </div>
          <span className="text-2xl font-bold gradient-text">Convo</span>
        </Link>

        {/* Back to login */}
        <Link 
          href="/login" 
          className="flex items-center gap-2 text-sm text-zinc-400 hover:text-white mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to login
        </Link>

        {/* Form */}
        <div className="bg-surface border border-border rounded-lg p-6">
          <h1 className="text-xl font-semibold text-white text-center mb-2">
            Set new password
          </h1>
          <p className="text-zinc-400 text-sm text-center mb-6">
            Enter your new password below
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-md bg-error/10 border border-error/30 text-error text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                type="password"
                placeholder="New password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-background border border-border rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-1 focus:border-primary"
                required
                minLength={6}
              />
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                type="password"
                placeholder="Confirm new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-background border border-border rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-1 focus:border-primary"
                required
                minLength={6}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-primary text-white rounded-md font-medium hover:bg-primary-hover transition-colors disabled:opacity-50"
            >
              {loading ? 'Resetting...' : 'Reset password'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}