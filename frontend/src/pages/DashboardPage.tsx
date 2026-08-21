import { useSearchParams } from 'react-router-dom'

import { ArticleCard } from '@/components/articles/ArticleCard'
import { FilterBar, type FilterBarValue } from '@/components/articles/FilterBar'
import { Pagination } from '@/components/articles/Pagination'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { DigestView } from '@/components/dashboard/DigestView'
import { StatsStrip } from '@/components/dashboard/StatsStrip'
import { useArticles } from '@/hooks/useArticles'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useDigestDate } from '@/hooks/useDigestDate'
import { useMinistries } from '@/hooks/useMinistries'
import { useTopics } from '@/hooks/useTopics'
import { formatDate } from '@/lib/formatDate'
import { getTodayIST } from '@/lib/today'

const PAGE_SIZE = 20

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const ministry = searchParams.get('ministry') ?? ''
  const topic = searchParams.get('topic') ?? ''
  const search = searchParams.get('search') ?? ''
  const upscOnly = searchParams.get('upsc_relevant') === 'true'
  const dateFrom = searchParams.get('date_from') ?? ''
  const dateTo = searchParams.get('date_to') ?? ''
  const offset = Number(searchParams.get('offset') ?? '0') || 0

  const debouncedSearch = useDebouncedValue(search, 350)
  const { data: ministries } = useMinistries()
  const { data: topics } = useTopics()

  function updateParams(patch: Record<string, string | null>, resetOffset = true) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === '') {
        next.delete(key)
      } else {
        next.set(key, value)
      }
    }
    if (resetOffset) next.delete('offset')
    setSearchParams(next, { replace: true })
  }

  function handleFilterChange(next: FilterBarValue) {
    updateParams({
      search: next.search || null,
      upsc_relevant: next.upscOnly ? 'true' : null,
      date_from: next.dateFrom || null,
      date_to: next.dateTo || null,
    })
  }

  function handleClearFilters() {
    updateParams({ search: null, upsc_relevant: null, date_from: null, date_to: null })
  }

  // topic joins the filter set: without it, picking a topic would leave the
  // digest rendering instead of the filtered list.
  const hasActiveFilters = Boolean(search || upscOnly || dateFrom || dateTo || topic)
  // The landing state — nothing selected, nothing searched, first page —
  // shows today's ranked digest instead of a flat, unranked list of
  // everything. Any ministry click, search, filter, or page turn falls
  // through to the browse view below.
  const isBareLanding = !ministry && !hasActiveFilters && offset === 0

  const { data, isLoading, isError, refetch, isPlaceholderData } = useArticles(
    {
      ministry: ministry || undefined,
      topic: topic || undefined,
      search: debouncedSearch || undefined,
      upsc_relevant: upscOnly || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: PAGE_SIZE,
      offset,
    },
    { enabled: !isBareLanding },
  )

  const activeMinistry = ministries?.find((m) => m.slug === ministry)
  const activeTopic = topics?.find((t) => t.slug === topic)
  const heading = topic
    ? (activeTopic?.name ?? 'Topic')
    : ministry
      ? (activeMinistry?.name ?? 'Ministry')
      : 'All ministries'

  // The static build serves a snapshot, so the digest's day can be older than
  // today — say which day it is rather than calling stale data "today's".
  const { data: digestDate } = useDigestDate()
  const digestIsToday = !digestDate || digestDate === getTodayIST()
  const digestHeading = digestIsToday ? "Today's digest" : `Digest — ${formatDate(digestDate)}`
  const digestSubtitle = digestIsToday
    ? "Today's releases, ranked by how much they're worth your study time."
    : 'The latest published releases, ranked by how much they’re worth your study time.'

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-serif text-2xl font-bold text-foreground">
          {isBareLanding ? digestHeading : heading}
        </h1>
        <p className="text-sm text-muted">
          {isBareLanding
            ? digestSubtitle
            : 'Daily PIB releases, summarized and mapped to UPSC syllabus topics.'}
        </p>
      </div>

      {!ministry && <StatsStrip />}

      <FilterBar
        value={{ search, upscOnly, dateFrom, dateTo }}
        onChange={handleFilterChange}
        onClear={handleClearFilters}
        hasActiveFilters={hasActiveFilters}
      />

      {isBareLanding && <DigestView />}

      {!isBareLanding && isLoading && <LoadingState label="Loading releases…" />}
      {!isBareLanding && isError && <ErrorState onRetry={() => refetch()} />}

      {!isBareLanding && data && (
        <div className={isPlaceholderData ? 'opacity-60 transition-opacity' : undefined}>
          {data.items.length === 0 ? (
            <EmptyState
              title="No releases match these filters"
              description="Try widening the date range or clearing filters."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {data.items.map((article) => (
                <ArticleCard key={article.id} article={article} />
              ))}
            </div>
          )}
          <div className="mt-4">
            <Pagination
              total={data.total}
              limit={data.limit}
              offset={data.offset}
              onOffsetChange={(next) => updateParams({ offset: String(next) }, false)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
