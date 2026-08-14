import { Typography } from 'antd'
import { Link } from 'react-router-dom'

import { MinistryBadge } from '@/components/articles/MinistryBadge'
import { formatDate } from '@/lib/formatDate'
import type { RelatedArticle } from '@/api/types'

const { Title } = Typography

export function RelatedArticles({ articles }: { articles: RelatedArticle[] }) {
  if (articles.length === 0) return null

  return (
    <section>
      <Title level={4} className="mb-0 font-serif text-foreground">
        Related past coverage
      </Title>
      <div className="mt-2 flex flex-col gap-2">
        {articles.map((related) => (
          <Link
            key={related.id}
            to={`/articles/${related.id}`}
            className="block rounded-lg border border-border bg-surface p-3 transition hover:border-accent/50"
          >
            <div className="flex items-center gap-2 text-xs text-muted">
              <MinistryBadge name={related.ministry.name} />
              <span aria-hidden="true">·</span>
              <time dateTime={related.release_datetime ?? undefined}>
                {formatDate(related.release_datetime)}
              </time>
            </div>
            <p className="mt-1 text-sm font-medium text-foreground">{related.title}</p>
            <p className="mt-1 text-sm text-muted">{related.relationship}</p>
          </Link>
        ))}
      </div>
    </section>
  )
}
