import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchSession, signOut as signOutRequest } from '@/api/client'
import { AuthContext } from '@/auth/authContext'
import type { CurrentUser } from '@/api/types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setUser(await fetchSession())
    } catch {
      // A failed session check means signed-out, not broken. Reading the
      // dashboard doesn't require an account, so this must never surface
      // as an error to someone just browsing.
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const signOut = useCallback(async () => {
    await signOutRequest()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, isLoading, refresh, setUser, signOut }),
    [user, isLoading, refresh, signOut],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
