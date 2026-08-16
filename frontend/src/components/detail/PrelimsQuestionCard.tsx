import { Card, Radio } from 'antd'
import { useState } from 'react'
import type { CSSProperties } from 'react'

import { getAnswer, recordAnswer } from '@/lib/prelimsAttempts'
import type { PrelimsQuestion } from '@/api/types'

export function PrelimsQuestionCard({
  articleId,
  question,
  index,
}: {
  articleId: number
  question: PrelimsQuestion
  index: number
}) {
  const [selected, setSelected] = useState<number | null>(
    () => getAnswer(articleId, index)?.selected ?? null,
  )
  const revealed = selected !== null

  function handleChange(value: number) {
    setSelected(value)
    recordAnswer(articleId, index, value, value === question.correct_option_index)
  }

  return (
    <Card size="small">
      <p className="text-sm font-medium text-foreground">
        <span className="text-muted">Q{index + 1}.</span> {question.question}
      </p>
      <Radio.Group
        value={selected}
        disabled={revealed}
        onChange={(event) => handleChange(event.target.value)}
        className="mt-3 flex flex-col gap-1.5"
      >
        {question.options.map((option, i) => {
          const isSelected = selected === i
          const isCorrect = i === question.correct_option_index

          let style: CSSProperties = {}
          if (revealed && isCorrect) {
            style = {
              borderColor: 'var(--color-accent-value)',
              color: 'var(--color-accent-value)',
              background: 'var(--color-accent-soft-value)',
            }
          } else if (revealed && isSelected && !isCorrect) {
            style = {
              borderColor: 'var(--color-danger-value)',
              color: 'var(--color-danger-value)',
            }
          }

          return (
            <Radio.Button
              key={option}
              value={i}
              style={style}
              className="ms-0 flex h-auto items-center justify-start gap-2 rounded-md px-3 py-1.5 text-left text-sm"
            >
              <span className="mr-1 inline-flex h-5 w-5 items-center justify-center rounded-full border border-current align-middle text-xs">
                {String.fromCharCode(65 + i)}
              </span>
              {option}
            </Radio.Button>
          )
        })}
      </Radio.Group>
      {revealed && (
        <p className="mt-3 rounded-md bg-background px-3 py-2 text-sm text-muted">
          <span className="font-medium text-foreground">
            {selected === question.correct_option_index ? 'Correct. ' : 'Not quite. '}
          </span>
          {question.explanation}
        </p>
      )}
    </Card>
  )
}
