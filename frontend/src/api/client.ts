import { ApiError } from './errors'
import * as staticApi from './staticClient'
import type {
  ArticleDetail,
  ArticleListParams,
  AuthProvider,
  CurrentUser,
  MinistryListItem,
  MinistryRef,
  PaginatedArticles,
  TopicListItem,
} from './types'

export { ApiError }

// Set at build time for the GitHub Pages bundle, which has no backend behind
// it. Resolved once here rather than branched per call, so the live path is
// exactly what it was before static mode existed.
const STATIC_MODE = import.meta.env.VITE_STATIC_MODE === 'true'

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

function liveFetchMinistries(): Promise<MinistryListItem[]> {
  return request<MinistryListItem[]>('/ministries')
}

function liveFetchTopics(): Promise<TopicListItem[]> {
  return request<TopicListItem[]>('/topics')
}

function liveFetchArticles(params: ArticleListParams): Promise<PaginatedArticles> {
  return request<PaginatedArticles>('/articles', { ...params })
}

function liveFetchArticle(id: number): Promise<ArticleDetail> {
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

function liveFetchAuthProviders(): Promise<AuthProvider[]> {
  return request<AuthProvider[]>('/auth/providers')
}

/** Current user, or null when signed out. Never throws on 401. */
function liveFetchSession(): Promise<CurrentUser | null> {
  return request<CurrentUser | null>('/auth/session')
}

function liveSignIn(provider: string, idToken: string): Promise<CurrentUser> {
  return send<CurrentUser>(`/auth/${provider}`, 'POST', { id_token: idToken })
}

function liveLinkProvider(provider: string, idToken: string): Promise<CurrentUser> {
  return send<CurrentUser>(`/auth/${provider}/link`, 'POST', { id_token: idToken })
}

function liveSignOut(): Promise<void> {
  return send<void>('/auth/logout', 'POST')
}

function liveFetchMySubscriptions(): Promise<MinistryRef[]> {
  return request<MinistryRef[]>('/auth/subscriptions')
}

function liveSaveMySubscriptions(ministryIds: number[]): Promise<MinistryRef[]> {
  return send<MinistryRef[]>('/auth/subscriptions', 'PUT', { ministry_ids: ministryIds })
}

// --- the surface the app actually imports ---------------------------------

export const fetchMinistries = STATIC_MODE ? staticApi.fetchMinistries : liveFetchMinistries
export const fetchTopics = STATIC_MODE ? staticApi.fetchTopics : liveFetchTopics
export const fetchArticles = STATIC_MODE ? staticApi.fetchArticles : liveFetchArticles
export const fetchArticle = STATIC_MODE ? staticApi.fetchArticle : liveFetchArticle

export const fetchAuthProviders = STATIC_MODE
  ? staticApi.fetchAuthProviders
  : liveFetchAuthProviders
export const fetchSession = STATIC_MODE ? staticApi.fetchSession : liveFetchSession
export const signIn: (provider: string, idToken: string) => Promise<CurrentUser> = STATIC_MODE
  ? staticApi.signIn
  : liveSignIn
export const linkProvider: (provider: string, idToken: string) => Promise<CurrentUser> = STATIC_MODE
  ? staticApi.linkProvider
  : liveLinkProvider
export const signOut = STATIC_MODE ? staticApi.signOut : liveSignOut
export const fetchMySubscriptions = STATIC_MODE
  ? staticApi.fetchMySubscriptions
  : liveFetchMySubscriptions
export const saveMySubscriptions: (ministryIds: number[]) => Promise<MinistryRef[]> = STATIC_MODE
  ? staticApi.saveMySubscriptions
  : liveSaveMySubscriptions

/** True when the app is running against a pre-built JSON bundle. */
export const isStaticMode = STATIC_MODE
