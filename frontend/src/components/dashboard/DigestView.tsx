import { CalendarOutlined } from '@ant-design/icons'
import { Typography } from 'antd'
import { Link } from 'react-router-dom'

import { ArticleCard } from '@/components/articles/ArticleCard'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { useArticles } from '@/hooks/useArticles'
import { getTodayIST } from '@/lib/today'
import type { ArticleListItem } from '@/api/types'

const { Title } = Typography

// Mirrors the anchors written into the enrichment prompt
// (src/pib_agent/enrichment/prompts.py) — 4-5 is "substantive to landmark",
// 3 is "worth reading as background", below that is routine.
const TOP_PICK_THRESHOLD = 4
const WORTH_A_LOOK_THRESHOLD = 3

const DIGEST_LIMIT = 100

function scoreOf(article: ArticleListItem): number | null {
  return article.upsc_relevance
}

export function DigestView() {
  const today = getTodayIST()

  const { data, isLoading, isError, refetch } = useArticles({
    date_from: today,
    date_to: today,
    sort: 'relevance',
    limit: DIGEST_LIMIT,
  })

  if (isLoading) return <LoadingState label="Loading today's releases…" />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!data) return null

  if (data.total === 0) {
    return (
      <EmptyState
        title="Nothing published yet today"
        description="PIB releases usually start appearing mid-morning IST. Check back shortly, or browse past releases from the sidebar."
      />
    )
  }

  const topPicks = data.items.filter((a) => (scoreOf(a) ?? 0) >= TOP_PICK_THRESHOLD)
  const worthALook = data.items.filter((a) => {
    const score = scoreOf(a)
    return score !== null && score >= WORTH_A_LOOK_THRESHOLD && score < TOP_PICK_THRESHOLD
  })
  const pending = data.items.filter((a) => scoreOf(a) === null).length
  const shown = topPicks.length + worthALook.length + pending
  // Routine (score 1-2) plus anything beyond the 100-row cap — sorted by
  // relevance, so nothing a reader would want is hiding past the cutoff.
  const routineOrBeyondCap = data.total - shown

  const browseAllHref = `/?date_from=${today}&date_to=${today}`

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2 text-sm text-muted">
        <CalendarOutlined />
        <span>
          {data.total} release{data.total === 1 ? '' : 's'} so far today
        </span>
      </div>

      {topPicks.length === 0 && worthALook.length === 0 && (
        <EmptyState
          title="Nothing UPSC-relevant yet today"
          description="Today's releases so far are routine notices. Check back later, or browse everything from today below."
        />
      )}

      {topPicks.length > 0 && (
        <section className="flex flex-col gap-3">
          <Title level={4} className="mb-0 font-serif text-foreground">
            Top picks
          </Title>
          <div className="flex flex-col gap-3">
            {topPicks.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        </section>
      )}

      {worthALook.length > 0 && (
        <section className="flex flex-col gap-3">
          <Title level={4} className="mb-0 font-serif text-foreground">
            Worth a look
          </Title>
          <div className="flex flex-col gap-3">
            {worthALook.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        </section>
      )}

      {(routineOrBeyondCap > 0 || pending > 0) && (
        <p className="text-sm text-muted">
          {routineOrBeyondCap > 0 && (
            <>
              {routineOrBeyondCap} routine release{routineOrBeyondCap === 1 ? '' : 's'}
              {pending > 0 ? ', ' : ' '}
            </>
          )}
          {pending > 0 && (
            <>
              {pending} still being processed{routineOrBeyondCap > 0 ? '' : ' '}
            </>
          )}
          {' — '}
          <Link to={browseAllHref} className="text-accent hover:underline">
            browse all of today
          </Link>
        </p>
      )}
    </div>
  )
}
