import { Collapse, Tag, Typography } from 'antd'
import { useEffect } from 'react'
import type { ReactNode } from 'react'

import { MainsQuestionCard } from '@/components/detail/MainsQuestionCard'
import { PrelimsQuestionCard } from '@/components/detail/PrelimsQuestionCard'
import { StudyNotesSection } from '@/components/detail/StudyNotesSection'
import { recordQuestionTotal } from '@/lib/prelimsAttempts'
import { examTagStyle } from '@/lib/tagStyles'
import type { Enrichment } from '@/api/types'

const { Title } = Typography

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <Title
      level={4}
      className="mb-[var(--spacing-tight)] font-serif text-(length:--text-title)/(--text-title--line-height) text-foreground"
    >
      {children}
    </Title>
  )
}

export function EnrichmentSection({
  articleId,
  enrichment,
}: {
  articleId: number
  enrichment: Enrichment
}) {
  const questionCount = enrichment.prelims_questions.length

  useEffect(() => {
    if (questionCount > 0) recordQuestionTotal(articleId, questionCount)
  }, [articleId, questionCount])

  const hasPractice =
    enrichment.prelims_questions.length > 0 || enrichment.mains_questions.length > 0

  return (
    <div className="flex flex-col gap-[var(--spacing-block)]">
      {/* Order is deliberate: takeaways, then practice, then the source prose.
          Summary and context are the commodity half of this product — a nicer
          PIB reader — and leading with them buried "What to study" 1564px down
          on a phone, which is the half nothing else offers. */}
      {enrichment.study_notes && <StudyNotesSection notes={enrichment.study_notes} />}

      {enrichment.upsc_relevant && enrichment.syllabus_topics.length > 0 && (
        <section>
          <SectionHeading>Syllabus topics</SectionHeading>
          <div className="flex flex-wrap gap-[var(--spacing-tight)]">
            {enrichment.syllabus_topics.map((topic) => (
              // Topics run long ("GS Paper 2 - Governance: Government Schemes
              // for Export Promotion") and antd Tags don't wrap, so one can
              // overflow a 375px viewport on its own.
              <Tag
                key={topic}
                className="m-0"
                style={{ ...examTagStyle, whiteSpace: 'normal', maxWidth: '100%', height: 'auto' }}
              >
                {topic}
              </Tag>
            ))}
          </div>
        </section>
      )}

      {hasPractice && (
        <div className="flex flex-col gap-[var(--spacing-section)]">
          {enrichment.prelims_questions.length > 0 && (
            <section>
              <SectionHeading>Prelims practice</SectionHeading>
              <div className="flex flex-col gap-[var(--spacing-snug)]">
                {enrichment.prelims_questions.map((question, i) => (
                  <PrelimsQuestionCard
                    key={question.question}
                    articleId={articleId}
                    question={question}
                    index={i}
                  />
                ))}
              </div>
            </section>
          )}

          {enrichment.mains_questions.length > 0 && (
            <section>
              <SectionHeading>Mains practice</SectionHeading>
              <div className="flex flex-col gap-[var(--spacing-snug)]">
                {enrichment.mains_questions.map((question, i) => (
                  <MainsQuestionCard key={question.question} question={question} index={i} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <section>
        <SectionHeading>Summary</SectionHeading>
        <p className="text-(length:--text-body)/(--text-body--line-height) text-foreground">
          {enrichment.summary}
        </p>
      </section>

      {/* Background rather than takeaway: available, but not occupying a
          screen of scroll before the reader reaches anything actionable. */}
      <Collapse
        ghost
        className="rounded-lg border border-border bg-surface"
        items={[
          {
            key: 'context',
            label: (
              <span className="font-serif text-(length:--text-title)/(--text-title--line-height) text-foreground">
                Background &amp; context
              </span>
            ),
            children: (
              <p className="whitespace-pre-line text-(length:--text-body)/(--text-body--line-height) text-muted">
                {enrichment.context}
              </p>
            ),
          },
        ]}
      />
    </div>
  )
}
