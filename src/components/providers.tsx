'use client'

import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { User } from '@supabase/supabase-js'
import { isOwnerEmail, getUserRole, hasUnrestrictedAccess } from '@/lib/access'

type AuthContextType = {
 user: User | null
 loading: boolean
 signOut: () => Promise<void>
 isOwner: boolean
 role: 'owner' | 'user' | 'anonymous'
 unrestricted: boolean
}

const AuthContext = createContext<AuthContextType>({
 user: null,
 loading: true,
 signOut: async () => {},
 isOwner: false,
 role: 'anonymous',
 unrestricted: false,
})

export function useAuth() {
 return useContext(AuthContext)
}

type ThemeContextType = {
 theme: 'dark' | 'light'
 toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextType>({
 theme: 'dark',
 toggleTheme: () => {},
})

export function useTheme() {
 return useContext(ThemeContext)
}

export function Providers({ children }: { children: React.ReactNode }) {
 const [user, setUser] = useState<User | null>(null)
 const [loading, setLoading] = useState(true)
 const [theme, setTheme] = useState<'dark' | 'light'>('dark')

 const ownerState = {
  isOwner: isOwnerEmail(user?.email ?? null),
  role: getUserRole(user?.email ?? null),
  unrestricted: hasUnrestrictedAccess(user?.email ?? null),
 }

 useEffect(() => {
  const supabase = createClient()

  supabase.auth.getUser().then(({ data: { user } }) => {
   setUser(user)
   setLoading(false)
  })

  const { data: { subscription } } = supabase.auth.onAuthStateChange(
   (_event, session) => {
    setUser(session?.user ?? null)
    setLoading(false)
   }
  )

  return () => subscription.unsubscribe()
 }, [])

 useEffect(() => {
  document.documentElement.classList.toggle('light', theme === 'light')
 }, [theme])

 const signOut = useCallback(async () => {
  const supabase = createClient()
  await supabase.auth.signOut()
  setUser(null)
 }, [])

 const toggleTheme = () => {
  setTheme(prev => prev === 'dark' ? 'light' : 'dark')
 }

 return (
  <AuthContext.Provider value={{ user, loading, signOut, ...ownerState }}>
   <ThemeContext.Provider value={{ theme, toggleTheme }}>
    {children}
   </ThemeContext.Provider>
  </AuthContext.Provider>
 )
}
