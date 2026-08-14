import { Link } from 'react-router-dom'

import { MinistryBadge } from '@/components/articles/MinistryBadge'
import { UpscBadge } from '@/components/articles/UpscBadge'
import { formatDate } from '@/lib/formatDate'
import type { ArticleListItem } from '@/api/types'

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
        {article.upsc_relevant && <UpscBadge />}
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
