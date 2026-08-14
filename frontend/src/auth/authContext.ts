import { createContext, use } from 'react'

import type { CurrentUser } from '@/api/types'

export interface AuthContextValue {
  user: CurrentUser | null
  isLoading: boolean
  /** Re-read the session — call after a sign-in or a provider link. */
  refresh: () => Promise<void>
  setUser: (user: CurrentUser | null) => void
  signOut: () => Promise<void>
}

// Kept out of AuthProvider.tsx so that file exports only a component, which
// is what React Fast Refresh needs to hot-reload it cleanly.
export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = use(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used inside an AuthProvider.')
  }
  return context
}
