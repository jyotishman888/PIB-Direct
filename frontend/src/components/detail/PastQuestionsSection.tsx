import { Tag, Typography } from 'antd'

import { examTagStyle } from '@/lib/tagStyles'
import type { PastQuestion } from '@/api/types'

const { Title } = Typography

/** Real questions from past papers that share this release's syllabus areas.
 *
 *  This is the difference between an opinion and a fact: "worth studying" is a
 *  claim, "this area was examined in 2023 and 2019" is evidence. Nothing here
 *  is generated — the corpus is operator-imported only, so an empty corpus
 *  renders nothing at all rather than an empty promise.
 */
export function PastQuestionsSection({ questions }: { questions: PastQuestion[] }) {
  if (questions.length === 0) return null

  const years = [...new Set(questions.map((q) => q.year))].sort((a, b) => b - a)

  return (
    <section>
      <Title level={4} className="mb-1 font-serif text-foreground">
        Asked before
      </Title>
      <p className="mb-3 text-sm text-muted">
        These syllabus areas were examined in {years.join(', ')}.
      </p>

      <ol className="flex flex-col gap-3">
        {questions.map((q) => (
          <li
            key={`${q.year}-${q.paper}-${q.question}`}
            className="rounded-lg border border-border bg-surface p-3"
          >
            <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="font-medium text-foreground">{q.year}</span>
              <span aria-hidden="true">·</span>
              <span className="capitalize">{q.paper}</span>
              {q.syllabus_area && (
                <Tag
                  className="m-0"
                  style={{ ...examTagStyle, whiteSpace: 'normal', maxWidth: '100%', height: 'auto' }}
                >
                  {q.syllabus_area}
                </Tag>
              )}
            </div>
            <p className="text-sm text-foreground">{q.question}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
