'use client'

import { useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import type { SupabaseClient } from '@supabase/supabase-js'

/**
 * Hook that safely initializes a Supabase browser client.
 * - Guarantees client is created only in the browser (after mount)
 * - Avoids SSR crashes from missing NEXT_PUBLIC_* env vars
 * - Returns { client, ready } so components can gate renders
 */
export function useSupabaseClient() {
  const clientRef = useRef<SupabaseClient | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    try {
      clientRef.current = createClient()
    } catch {
      clientRef.current = null
    }
    setReady(true)
  }, [])

  return { client: clientRef.current, ready }
}
