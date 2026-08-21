import { ArrowLeftOutlined, ExportOutlined } from '@ant-design/icons'
import { Collapse, Typography } from 'antd'
import { Link, useParams } from 'react-router-dom'

import { MinistryBadge } from '@/components/articles/MinistryBadge'
import { UpscBadge } from '@/components/articles/UpscBadge'
import { ErrorState } from '@/components/common/ErrorState'
import { LoadingState } from '@/components/common/LoadingState'
import { EnrichmentSection } from '@/components/detail/EnrichmentSection'
import { RelatedArticles } from '@/components/detail/RelatedArticles'
import { useArticle } from '@/hooks/useArticle'
import { formatDateTime } from '@/lib/formatDate'

const { Title } = Typography

export function ArticleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const articleId = Number(id)
  const isValidId = Number.isFinite(articleId)

  const { data: article, isLoading, isError, refetch } = useArticle(articleId)

  if (!isValidId) {
    return <ErrorState message="This isn't a valid release." />
  }
  if (isLoading) return <LoadingState label="Loading release…" />
  if (isError || !article) {
    return <ErrorState message="Couldn't load this release." onRetry={() => refetch()} />
  }

  return (
    <article className="flex flex-col gap-[var(--spacing-block)]">
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
        >
          <ArrowLeftOutlined /> Back to releases
        </Link>
        <div className="mt-[var(--spacing-snug)] flex flex-wrap items-center gap-2 text-(length:--text-meta)/(--text-meta--line-height) text-muted">
          <MinistryBadge name={article.ministry.name} />
          {article.enrichment?.upsc_relevant && <UpscBadge />}
          <span aria-hidden="true">·</span>
          <time dateTime={article.release_datetime ?? undefined}>
            {formatDateTime(article.release_datetime)}
          </time>
          {article.pib_office && (
            <>
              <span aria-hidden="true">·</span>
              <span>{article.pib_office}</span>
            </>
          )}
        </div>
        <Title level={2} className="mt-[var(--spacing-tight)] mb-0 font-serif text-(length:--text-display)/(--text-display--line-height) text-balance text-foreground">
          {article.title}
        </Title>
        {article.subtitle && (
          <p className="mt-[var(--spacing-tight)] whitespace-pre-line text-(length:--text-body)/(--text-body--line-height) text-muted">
            {article.subtitle}
          </p>
        )}
        <a
          href={article.source_url}
          target="_blank"
          rel="noreferrer"
          className="mt-[var(--spacing-snug)] inline-flex items-center gap-1 text-(length:--text-meta)/(--text-meta--line-height) text-accent hover:underline"
        >
          View original PIB release
          <ExportOutlined className="text-xs" />
        </a>
      </div>

      {article.enrichment ? (
        <EnrichmentSection articleId={article.id} enrichment={article.enrichment} />
      ) : (
        <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
          This release hasn't been summarized yet — check back shortly.
        </p>
      )}

      <RelatedArticles articles={article.related_articles} />

      <Collapse
        ghost
        className="rounded-lg border border-border bg-surface"
        items={[
          {
            key: 'full-text',
            label: (
              <span className="text-sm font-medium text-foreground">Full original text</span>
            ),
            children: (
              <div className="whitespace-pre-line text-sm leading-relaxed text-muted">
                {article.body_text}
              </div>
            ),
          },
        ]}
      />
    </article>
  )
}
