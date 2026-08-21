import { CheckCircleOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import { Link } from 'react-router-dom'

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

export function ArticleCard({
  article,
  featured = false,
}: {
  article: ArticleListItem
  /** Top picks carry more weight so the digest's ranking is legible without
   *  reading the section headings. */
  featured?: boolean
}) {
  return (
    <Link
      to={`/articles/${article.id}`}
      className={`group block rounded-xl border bg-surface transition duration-150 hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-md ${
        featured
          ? 'border-accent/30 p-[var(--spacing-section)] shadow-sm'
          : 'border-border p-[var(--spacing-snug)] sm:p-[var(--spacing-section)]'
      }`}
    >
      {/* Title first and dominant. Previously four chips of equal weight sat
          above every headline, which is most of what read as clutter. */}
      {/* Featured and regular titles share a size. The weight difference
          comes from the card treatment — accent border, padding, a longer
          summary — because a display-size headline ran six lines on a phone
          and one card filled the screen, which is the problem this pass
          exists to fix. */}
      <h3 className="font-serif text-(length:--text-title)/(--text-title--line-height) font-semibold text-foreground group-hover:text-accent">
        {article.title}
      </h3>

      {article.summary ? (
        <p
          className={`mt-[var(--spacing-tight)] text-(length:--text-body)/(--text-body--line-height) text-muted ${
            featured ? 'line-clamp-3' : 'line-clamp-2'
          }`}
        >
          {article.summary}
        </p>
      ) : (
        <p className="mt-[var(--spacing-tight)] text-(length:--text-body)/(--text-body--line-height) italic text-muted/70">
          Summary pending…
        </p>
      )}

      {/* Metadata recedes to a single muted line beneath the content it
          describes, rather than competing with the headline above it. */}
      <div className="mt-[var(--spacing-snug)] flex flex-wrap items-center gap-x-2 gap-y-1 text-(length:--text-meta)/(--text-meta--line-height) text-muted">
        <span className="truncate">{article.ministry.name}</span>
        <span aria-hidden="true">·</span>
        <time dateTime={article.release_datetime ?? undefined}>
          {formatDate(article.release_datetime)}
        </time>
        {article.upsc_relevant && (
          <>
            <span aria-hidden="true">·</span>
            {/* Recessed to text rather than a coloured chip: 77% of the corpus
                carries this, so as a badge it was decoration, not signal. */}
            <span className="text-exam">UPSC</span>
          </>
        )}
        <AttemptBadge articleId={article.id} />
      </div>
    </Link>
  )
}
