import { Tag, Typography } from 'antd'
import { useEffect } from 'react'
import type { ReactNode } from 'react'

import { MainsQuestionCard } from '@/components/detail/MainsQuestionCard'
import { PastQuestionsSection } from '@/components/detail/PastQuestionsSection'
import { PrelimsQuestionCard } from '@/components/detail/PrelimsQuestionCard'
import { StudyNotesSection } from '@/components/detail/StudyNotesSection'
import { recordQuestionTotal } from '@/lib/prelimsAttempts'
import { examTagStyle } from '@/lib/tagStyles'
import type { Enrichment, PastQuestion } from '@/api/types'

const { Title } = Typography

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <Title level={4} className="mb-0 font-serif text-foreground">
      {children}
    </Title>
  )
}

export function EnrichmentSection({
  articleId,
  enrichment,
  pastQuestions = [],
}: {
  articleId: number
  enrichment: Enrichment
  pastQuestions?: PastQuestion[]
}) {
  const questionCount = enrichment.prelims_questions.length

  useEffect(() => {
    if (questionCount > 0) recordQuestionTotal(articleId, questionCount)
  }, [articleId, questionCount])

  return (
    <div className="flex flex-col gap-6">
      <section>
        <SectionHeading>Summary</SectionHeading>
        <p className="mt-2 text-sm leading-relaxed text-foreground">{enrichment.summary}</p>
      </section>

      <section>
        <SectionHeading>Context</SectionHeading>
        <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-muted">
          {enrichment.context}
        </p>
      </section>

      {/* Above the questions: this is the "what should I take away" layer,
          and the questions below are practice on it. */}
      {enrichment.study_notes && <StudyNotesSection notes={enrichment.study_notes} />}

      {enrichment.upsc_relevant && enrichment.syllabus_topics.length > 0 && (
        <section>
          <SectionHeading>Syllabus topics</SectionHeading>
          <div className="mt-2 flex flex-wrap gap-1.5">
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

      {/* Placed against the topics rather than the practice questions: it is
          evidence for the tags above, not another exercise. */}
      <PastQuestionsSection questions={pastQuestions} />

      {enrichment.prelims_questions.length > 0 && (
        <section>
          <SectionHeading>Prelims practice</SectionHeading>
          <div className="mt-2 flex flex-col gap-3">
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
          <div className="mt-2 flex flex-col gap-3">
            {enrichment.mains_questions.map((question, i) => (
              <MainsQuestionCard key={question.question} question={question} index={i} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
