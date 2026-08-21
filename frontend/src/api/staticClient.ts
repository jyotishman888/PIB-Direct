/**
 * Reads the pre-built JSON bundle instead of calling the API.
 *
 * GitHub Pages serves files, not Python, so the deployed site has no backend
 * behind it. The bundle is produced by `pib-agent export-static`
 * (src/pib_agent/export_static.py) using the same mapping functions the API
 * uses, so the payload shapes here are identical to the live ones and
 * `types.ts` covers both.
 *
 * Filtering, sorting and pagination therefore have to be reimplemented in the
 * browser. Everything below mirrors src/pib_agent/api/routers/articles.py
 * deliberately and exactly — where the two diverge, the deployed site behaves
 * differently from the app, which is the whole failure mode this file exists
 * to avoid.
 */

import { ApiError } from './errors'
import type {
  ArticleDetail,
  ArticleListItem,
  ArticleListParams,
  AuthProvider,
  CurrentUser,
  MinistryListItem,
  MinistryRef,
  PaginatedArticles,
  TopicListItem,
} from './types'

// Vite's BASE_URL carries the deploy subpath ("/PIB-Direct/" on Pages, "/" in
// dev) and always ends in a slash.
const DATA_BASE = `${import.meta.env.BASE_URL}data`

export interface StaticMeta {
  generated_at: string
  latest_date: string | null
  article_count: number
  ministry_count: number
  window_days: number
}

/** Mirrors area_slug in src/pib_agent/syllabus.py — the two must agree or a
 *  topic link built by one is unreadable by the other. */
function areaSlug(area: string): string {
  return area
    .replace(/&/g, 'and')
    .replace(/-/g, ' ')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .join('-')
}

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(`${DATA_BASE}${path}`)
  if (!response.ok) {
    throw new ApiError(response.statusText || 'Request failed', response.status)
  }
  return (await response.json()) as T
}

// index.json and meta.json are fetched once and reused: the entire list
// surface is computed from them, so every interaction after the first costs no
// network at all.
let indexPromise: Promise<ArticleListItem[]> | null = null
let metaPromise: Promise<StaticMeta> | null = null

function loadIndex(): Promise<ArticleListItem[]> {
  indexPromise ??= loadJson<ArticleListItem[]>('/index.json')
  return indexPromise
}

/** Freshness of the bundle. The digest keys its day off `latest_date`. */
export function fetchMeta(): Promise<StaticMeta> {
  metaPromise ??= loadJson<StaticMeta>('/meta.json')
  return metaPromise
}

/**
 * `release_datetime` is stored and serialised without a timezone, and the
 * backend compares it against naive day boundaries. Slicing the date component
 * off the ISO string reproduces that; `new Date(...)` would apply the
 * visitor's UTC offset and shift releases across the day boundary.
 */
function dayOf(iso: string | null): string | null {
  return iso ? iso.slice(0, 10) : null
}

/**
 * Mirrors SQLAlchemy's `nullslast(col.desc())` — non-null values descending,
 * nulls after all of them. ISO-8601 strings sort lexicographically in
 * chronological order, so the same comparator serves dates and scores.
 */
function descNullsLast(a: string | number | null, b: string | number | null): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1
  return a > b ? -1 : 1
}

function matches(article: ArticleListItem, params: ArticleListParams): boolean {
  const { ministry, topic, upsc_relevant, search, date_from, date_to } = params

  if (ministry !== undefined && article.ministry.slug !== ministry) return false

  // Slug comparison, matching the backend's area_from_slug lookup. An
  // unrecognised slug matches nothing, so a stale bookmark lands on an
  // empty list rather than an error.
  if (topic !== undefined && !article.syllabus_topics.some((t) => areaSlug(t) === topic)) {
    return false
  }

  // `Enrichment.upsc_relevant == value` in SQL: an article with no enrichment
  // holds NULL and is excluded whichever way the filter points.
  if (upsc_relevant !== undefined && article.upsc_relevant !== upsc_relevant) return false

  // The API rejects a one-character search with a 422 (`min_length=2`).
  // Ignoring it is the graceful equivalent — the debounced input would
  // otherwise flash an error state on the way to a real query.
  if (search !== undefined && search.length >= 2) {
    const needle = search.toLowerCase()
    const inTitle = article.title.toLowerCase().includes(needle)
    // A NULL summary never matches ilike, so an unenriched article is
    // title-only here too.
    const inSummary = (article.summary ?? '').toLowerCase().includes(needle)
    if (!inTitle && !inSummary) return false
  }

  // Undated articles drop out once a date filter applies, exactly as a NULL
  // comparison does in SQL.
  const day = dayOf(article.release_datetime)
  if (date_from !== undefined && (day === null || day < date_from)) return false
  if (date_to !== undefined && (day === null || day > date_to)) return false

  return true
}

export async function fetchArticles(params: ArticleListParams): Promise<PaginatedArticles> {
  const all = await loadIndex()
  const limit = params.limit ?? 20
  const offset = params.offset ?? 0
  const sort = params.sort ?? 'newest'

  const filtered = all.filter((article) => matches(article, params))

  const sorted = filtered.sort((a, b) => {
    if (sort === 'relevance') {
      const byScore = descNullsLast(a.upsc_relevance, b.upsc_relevance)
      if (byScore !== 0) return byScore
    }
    const byDate = descNullsLast(a.release_datetime, b.release_datetime)
    if (byDate !== 0) return byDate
    return b.id - a.id
  })

  return {
    items: sorted.slice(offset, offset + limit),
    total: filtered.length,
    limit,
    offset,
  }
}

export function fetchArticle(id: number): Promise<ArticleDetail> {
  return loadJson<ArticleDetail>(`/articles/${id}.json`)
}

export function fetchMinistries(): Promise<MinistryListItem[]> {
  return loadJson<MinistryListItem[]>('/ministries.json')
}

export function fetchTopics(): Promise<TopicListItem[]> {
  return loadJson<TopicListItem[]>('/topics.json')
}

// --- auth -----------------------------------------------------------------
// There is no server to authenticate against. These resolve to a signed-out
// state rather than throwing, so nothing on the page has to special-case it;
// the static build also omits the sign-in UI and the /login and /account
// routes entirely.

export function fetchAuthProviders(): Promise<AuthProvider[]> {
  return Promise.resolve([])
}

export function fetchSession(): Promise<CurrentUser | null> {
  return Promise.resolve(null)
}

function unavailable<T>(): Promise<T> {
  return Promise.reject(new ApiError('Not available on the static site.', 501))
}

export function signIn(): Promise<CurrentUser> {
  return unavailable()
}

export function linkProvider(): Promise<CurrentUser> {
  return unavailable()
}

export function signOut(): Promise<void> {
  return Promise.resolve()
}

export function fetchMySubscriptions(): Promise<MinistryRef[]> {
  return Promise.resolve([])
}

export function saveMySubscriptions(): Promise<MinistryRef[]> {
  return unavailable()
}
