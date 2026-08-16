import { CheckCircleOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import { Link } from 'react-router-dom'

import { MinistryBadge } from '@/components/articles/MinistryBadge'
import { UpscBadge } from '@/components/articles/UpscBadge'
import { formatDate } from '@/lib/formatDate'
import { getAttemptSummary } from '@/lib/prelimsAttempts'
import { accentTagStyle, neutralTagStyle } from '@/lib/tagStyles'
import type { ArticleListItem } from '@/api/types'

function AttemptBadge({ articleId }: { articleId: number }) {
  const summary = getAttemptSummary(articleId)
  if (!summary || summary.attempted === 0) return null

  const fullyAttempted = summary.attempted === summary.total
  const label = fullyAttempted
    ? `${summary.correct}/${summary.total} correct`
    : `${summary.attempted}/${summary.total} attempted`

  return (
    <Tag
      icon={<CheckCircleOutlined />}
      className="m-0"
      style={fullyAttempted ? accentTagStyle : neutralTagStyle}
    >
      {label}
    </Tag>
  )
}

export function ArticleCard({ article }: { article: ArticleListItem }) {
  return (
    <Link
      to={`/articles/${article.id}`}
      className="group block rounded-lg border border-border bg-surface p-4 transition duration-150 hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <MinistryBadge name={article.ministry.name} />
          <span aria-hidden="true">·</span>
          <time dateTime={article.release_datetime ?? undefined}>
            {formatDate(article.release_datetime)}
          </time>
        </div>
        <div className="flex items-center gap-1.5">
          <AttemptBadge articleId={article.id} />
          {article.upsc_relevant && <UpscBadge />}
        </div>
      </div>
      <h3 className="mt-2.5 text-base font-serif font-semibold leading-snug text-foreground group-hover:text-accent sm:text-lg">
        {article.title}
      </h3>
      {article.summary ? (
        <p className="mt-1.5 line-clamp-2 text-sm text-muted">{article.summary}</p>
      ) : (
        <p className="mt-1.5 text-sm italic text-muted/70">Summary pending…</p>
      )}
    </Link>
  )
}
