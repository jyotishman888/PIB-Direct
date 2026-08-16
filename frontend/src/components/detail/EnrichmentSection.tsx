import { Tag, Typography } from 'antd'
import { useEffect } from 'react'
import type { ReactNode } from 'react'

import { MainsQuestionCard } from '@/components/detail/MainsQuestionCard'
import { PrelimsQuestionCard } from '@/components/detail/PrelimsQuestionCard'
import { recordQuestionTotal } from '@/lib/prelimsAttempts'
import { examTagStyle } from '@/lib/tagStyles'
import type { Enrichment } from '@/api/types'

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
}: {
  articleId: number
  enrichment: Enrichment
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

      {enrichment.upsc_relevant && enrichment.syllabus_topics.length > 0 && (
        <section>
          <SectionHeading>Syllabus topics</SectionHeading>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {enrichment.syllabus_topics.map((topic) => (
              <Tag key={topic} className="m-0" style={examTagStyle}>
                {topic}
              </Tag>
            ))}
          </div>
        </section>
      )}

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
