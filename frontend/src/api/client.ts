import type {
  ArticleDetail,
  ArticleListParams,
  AuthProvider,
  CurrentUser,
  MinistryListItem,
  MinistryRef,
  PaginatedArticles,
} from './types'

// Defaults to the /api path on the page's own origin, which the Vite dev
// server proxies to the backend (see vite.config.ts). Going through the page
// origin rather than straight to 127.0.0.1:8000 is what makes tunnelled hosts
// work — and it keeps the session cookie first-party.
//
// Resolved against the current origin so a relative value like "/api" becomes
// absolute; an absolute VITE_API_BASE_URL is still honoured as-is.
const API_BASE_URL: string = new URL(
  import.meta.env.VITE_API_BASE_URL ?? '/api',
  window.location.origin,
).toString().replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  // Concatenated, not `new URL(path, base)` — an absolute path would discard
  // the base's own path segment and drop the /api prefix.
  const url = new URL(API_BASE_URL + path)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }

  // The session lives in an httpOnly cookie, so every call has to send
  // credentials for the API to know who's asking.
  const response = await fetch(url, { credentials: 'include' })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

export function fetchMinistries(): Promise<MinistryListItem[]> {
  return request<MinistryListItem[]>('/ministries')
}

export function fetchArticles(params: ArticleListParams): Promise<PaginatedArticles> {
  return request<PaginatedArticles>('/articles', { ...params })
}

export function fetchArticle(id: number): Promise<ArticleDetail> {
  return request<ArticleDetail>(`/articles/${id}`)
}

// --- auth -----------------------------------------------------------------

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(new URL(API_BASE_URL + path), {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const parsed = (await response.json()) as { detail?: string }
      detail = parsed.detail ?? detail
    } catch {
      // not JSON; keep statusText
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function fetchAuthProviders(): Promise<AuthProvider[]> {
  return request<AuthProvider[]>('/auth/providers')
}

/** Current user, or null when signed out. Never throws on 401. */
export function fetchSession(): Promise<CurrentUser | null> {
  return request<CurrentUser | null>('/auth/session')
}

export function signIn(provider: string, idToken: string): Promise<CurrentUser> {
  return send<CurrentUser>(`/auth/${provider}`, 'POST', { id_token: idToken })
}

export function linkProvider(provider: string, idToken: string): Promise<CurrentUser> {
  return send<CurrentUser>(`/auth/${provider}/link`, 'POST', { id_token: idToken })
}

export function signOut(): Promise<void> {
  return send<void>('/auth/logout', 'POST')
}

export function fetchMySubscriptions(): Promise<MinistryRef[]> {
  return request<MinistryRef[]>('/auth/subscriptions')
}

export function saveMySubscriptions(ministryIds: number[]): Promise<MinistryRef[]> {
  return send<MinistryRef[]>('/auth/subscriptions', 'PUT', { ministry_ids: ministryIds })
}
