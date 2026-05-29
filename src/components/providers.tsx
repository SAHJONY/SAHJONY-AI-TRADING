'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { createBrowserClient } from '@supabase/ssr'
import type { User, Session } from '@supabase/supabase-js'
import { ThemeProvider } from './theme-provider'

interface AuthContextType {
  user: User | null
  session: Session | null
  loading: boolean
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  session: null,
  loading: true,
  signOut: async () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}

export { useTheme } from './theme-provider'

export function Providers({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [supabase, setSupabase] = useState<ReturnType<typeof createBrowserClient> | null>(null)

  useEffect(() => {
    // Only create client on the client side after mount
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
    
    if (url && key) {
      const client = createBrowserClient(url, key)
      setSupabase(client)
      
      const getSession = async () => {
        const { data: { session } } = await client.auth.getSession()
        setSession(session)
        setUser(session?.user ?? null)
        setLoading(false)
      }

      getSession()

      const { data: { subscription } } = client.auth.onAuthStateChange((_event, session) => {
        setSession(session)
        setUser(session?.user ?? null)
        setLoading(false)
      })

      return () => subscription.unsubscribe()
    } else {
      // No Supabase config - stay in loading state but show app
      setLoading(false)
    }
  }, [])

  const signOut = async () => {
    if (supabase) {
      await supabase.auth.signOut()
    }
  }

  return (
    <ThemeProvider>
      <AuthContext.Provider value={{ user, session, loading, signOut }}>
        {children}
      </AuthContext.Provider>
    </ThemeProvider>
  )
}