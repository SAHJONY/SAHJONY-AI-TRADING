// Lazy load Supabase to avoid initialization errors during build
let supabaseClient: any = null

function createDummyClient() {
  return {
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      getUser: async () => ({ data: { user: null }, error: null }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithOAuth: async () => ({ data: null, error: null }),
      signOut: async () => ({ error: null }),
    },
    from: () => ({
      select: () => ({
        eq: () => ({
          order: () => ({
            then: (resolve: Function) => resolve({ data: [], error: null }),
            catch: () => {}
          })
        })
      }),
      insert: async () => ({ data: null, error: null }),
      update: async () => ({ data: null, error: null }),
      delete: async () => ({ data: null, error: null }),
    }),
    channel: () => ({
      on: () => ({ subscribe: () => ({}) }),
      subscribe: () => ({}),
    }),
  }
}

export function createClient() {
  if (supabaseClient) return supabaseClient
  
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  
  // Check if credentials are missing or placeholders
  const hasCredentials = supabaseUrl && 
                          supabaseAnonKey && 
                          !supabaseUrl.includes('placeholder') && 
                          !supabaseAnonKey.includes('placeholder') &&
                          supabaseUrl !== ''
  
  if (!hasCredentials) {
    console.warn('Supabase credentials not configured - using placeholder client for build')
    supabaseClient = createDummyClient()
    return supabaseClient
  }
  
  try {
    // Lazy import to avoid initialization errors
    const { createBrowserClient } = require('@supabase/ssr')
    supabaseClient = createBrowserClient(supabaseUrl, supabaseAnonKey)
    return supabaseClient
  } catch (error) {
    console.warn('Failed to create Supabase client:', error)
    supabaseClient = createDummyClient()
    return supabaseClient
  }
}