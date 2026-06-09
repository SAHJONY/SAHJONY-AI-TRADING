/**
 * Owner/Role access utilities for SAHJONY platform.
 * Owner emails have unrestricted access to all features, routes, and data.
 */

// Owner emails — full unrestricted access, no limits
const OWNER_EMAILS: string[] = [
  'sahjonycapitalllc@outlook.com',
  'juan@example.com', // added for full access
]

export function isOwnerEmail(email: string | null | undefined): boolean {
  if (!email) return false
  return OWNER_EMAILS.includes(email.toLowerCase())
}

export function getUserRole(email: string | null | undefined): 'owner' | 'user' | 'anonymous' {
  if (!email) return 'anonymous'
  if (isOwnerEmail(email)) return 'owner'
  return 'user'
}

export function hasUnrestrictedAccess(email: string | null | undefined): boolean {
  return isOwnerEmail(email)
}
