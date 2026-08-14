import { Alert, Button, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'

import { fetchAuthProviders, linkProvider, signIn } from '@/api/client'
import { useAuth } from '@/auth/authContext'
import {
  GOOGLE_CLIENT_ID,
  TELEGRAM_CLIENT_ID,
  openTelegramLogin,
  renderGoogleButton,
} from '@/auth/providerSdks'
import type { AuthProvider } from '@/api/types'

/**
 * @param mode  'signin' creates or resumes an account; 'link' attaches a
 *              provider to the account already signed in.
 */
export function SignInButtons({
  mode = 'signin',
  onDone,
}: {
  mode?: 'signin' | 'link'
  onDone?: () => void
}) {
  const { setUser, refresh } = useAuth()
  const googleSlot = useRef<HTMLDivElement>(null)
  const [providers, setProviders] = useState<AuthProvider[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetchAuthProviders()
      .then(setProviders)
      .catch(() => setError("Couldn't load sign-in options."))
  }, [])

  async function submit(provider: string, idToken: string) {
    setBusy(true)
    setError(null)
    try {
      const user = mode === 'link' ? await linkProvider(provider, idToken) : await signIn(provider, idToken)
      setUser(user)
      await refresh()
      onDone?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  const googleReady = providers?.some((p) => p.name === 'google' && p.configured) && GOOGLE_CLIENT_ID
  const telegramReady =
    providers?.some((p) => p.name === 'telegram' && p.configured) && TELEGRAM_CLIENT_ID

  useEffect(() => {
    if (!googleReady || !googleSlot.current) return
    renderGoogleButton(googleSlot.current, (token) => void submit('google', token)).catch(() =>
      setError('Google sign-in is unavailable right now.'),
    )
    // submit is stable enough for this one-shot render; re-running would
    // duplicate Google's button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleReady])

  if (providers === null && !error) {
    return <Spin />
  }

  const nothingConfigured = !googleReady && !telegramReady

  return (
    <div className="flex flex-col items-center gap-3">
      {error && <Alert type="error" title={error} showIcon className="w-full" />}

      {nothingConfigured && (
        <Alert
          type="warning"
          showIcon
          className="w-full"
          title="Sign-in isn't configured yet"
          description="Set VITE_GOOGLE_CLIENT_ID / VITE_TELEGRAM_CLIENT_ID and the matching server-side ids, then reload."
        />
      )}

      {googleReady && <div ref={googleSlot} />}

      {telegramReady && (
        <Button
          size="large"
          loading={busy}
          onClick={async () => {
            // busy has to be set here, not just inside submit(): waiting for
            // the Telegram popup is the slow part, and without this the button
            // looks inert for as long as it takes.
            setBusy(true)
            setError(null)
            try {
              const token = await openTelegramLogin()
              await submit('telegram', token)
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Telegram sign-in failed.')
            } finally {
              setBusy(false)
            }
          }}
          style={{ width: 280, background: '#229ED9', borderColor: '#229ED9', color: '#fff' }}
        >
          {mode === 'link' ? 'Connect Telegram' : 'Sign in with Telegram'}
        </Button>
      )}
    </div>
  )
}
