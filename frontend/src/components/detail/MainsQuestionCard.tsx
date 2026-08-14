import { Card, Tag } from 'antd'

import { accentTagStyle } from '@/lib/tagStyles'
import type { MainsQuestion } from '@/api/types'

export function MainsQuestionCard({
  question,
  index,
}: {
  question: MainsQuestion
  index: number
}) {
  return (
    <Card size="small">
      <Tag className="m-0" style={accentTagStyle}>
        {question.gs_paper}
      </Tag>
      <p className="mt-2 text-sm text-foreground">
        <span className="text-muted">Q{index + 1}.</span> {question.question}
      </p>
    </Card>
  )
}
