/**
 * Loading the two providers' browser SDKs.
 *
 * Both are loaded on demand rather than in index.html: a signed-out reader
 * browsing releases shouldn't pay for two third-party scripts, and neither
 * script is needed until someone actually opens the sign-in page.
 */

const GOOGLE_SRC = 'https://accounts.google.com/gsi/client'
const TELEGRAM_SRC = 'https://telegram.org/js/telegram-widget.js?22'

const loaded = new Map<string, Promise<void>>()

function loadScript(src: string): Promise<void> {
  const existing = loaded.get(src)
  if (existing) return existing

  const promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => {
      loaded.delete(src) // let a later attempt retry rather than fail forever
      reject(new Error(`Could not load ${src}`))
    }
    document.head.appendChild(script)
  })

  loaded.set(src, promise)
  return promise
}

export const GOOGLE_CLIENT_ID: string | undefined = import.meta.env.VITE_GOOGLE_CLIENT_ID
export const TELEGRAM_CLIENT_ID: string | undefined = import.meta.env.VITE_TELEGRAM_CLIENT_ID

interface GoogleCredentialResponse {
  credential: string
}

interface GoogleAccountsId {
  initialize: (options: {
    client_id: string
    callback: (response: GoogleCredentialResponse) => void
  }) => void
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void
}

interface TelegramLogin {
  init: (options: { client_id: string; scope?: string[] }, callback?: () => void) => void
  open: (callback: (result: { id_token?: string }) => void) => void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } }
    Telegram?: { Login?: TelegramLogin }
  }
}

/** Render Google's own button; resolves credentials through `onToken`. */
export async function renderGoogleButton(
  parent: HTMLElement,
  onToken: (idToken: string) => void,
): Promise<void> {
  if (!GOOGLE_CLIENT_ID) throw new Error('VITE_GOOGLE_CLIENT_ID is not set.')

  await loadScript(GOOGLE_SRC)
  const accounts = window.google?.accounts?.id
  if (!accounts) throw new Error('Google sign-in failed to initialise.')

  accounts.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: (response) => onToken(response.credential),
  })
  parent.replaceChildren()
  accounts.renderButton(parent, {
    theme: 'outline',
    size: 'large',
    text: 'signin_with',
    shape: 'rectangular',
    width: 280,
  })
}

// Long enough for someone to actually log in and approve, short enough that a
// silently-dead flow doesn't leave the button spinning indefinitely.
const TELEGRAM_TIMEOUT_MS = 90_000

/** Open Telegram's OIDC popup and hand back its id_token. */
export async function openTelegramLogin(): Promise<string> {
  if (!TELEGRAM_CLIENT_ID) throw new Error('VITE_TELEGRAM_CLIENT_ID is not set.')

  await loadScript(TELEGRAM_SRC)
  const login = window.Telegram?.Login
  if (!login) throw new Error('Telegram sign-in failed to initialise.')

  return new Promise<string>((resolve, reject) => {
    // Neither init's callback nor open's is guaranteed to fire — a blocked
    // popup or an unregistered domain can leave both hanging, which would
    // otherwise strand this promise forever with no feedback at all.
    const timer = window.setTimeout(() => {
      reject(
        new Error(
          "Telegram sign-in didn't complete. Check that pop-ups are allowed, and that this " +
            'domain is registered against the bot in BotFather (Login Widget).',
        ),
      )
    }, TELEGRAM_TIMEOUT_MS)

    const settle = (fn: () => void) => {
      window.clearTimeout(timer)
      fn()
    }

    try {
      login.init({ client_id: TELEGRAM_CLIENT_ID, scope: ['profile'] }, () => {
        login.open((result) => {
          if (result?.id_token) settle(() => resolve(result.id_token as string))
          else settle(() => reject(new Error('Telegram sign-in was cancelled.')))
        })
      })
    } catch (err) {
      settle(() => reject(err instanceof Error ? err : new Error('Telegram sign-in failed.')))
    }
  })
}
