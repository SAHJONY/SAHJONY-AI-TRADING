// Force dynamic rendering — Supabase auth client references `location`
// during static generation, causing "ReferenceError: location is not defined"
export const dynamic = 'force-dynamic'

export default function AgentsNewLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
