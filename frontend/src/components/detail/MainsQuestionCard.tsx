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
      {/* gs_paper is free text and runs long ("GS Paper 3 - Economy: Digital
          Currency and Financial Technology"); antd Tags don't wrap, so one
          overflows a 375px viewport on its own. */}
      <Tag
        className="m-0"
        style={{ ...accentTagStyle, whiteSpace: 'normal', maxWidth: '100%', height: 'auto' }}
      >
        {question.gs_paper}
      </Tag>
      <p className="mt-2 text-sm text-foreground">
        <span className="text-muted">Q{index + 1}.</span> {question.question}
      </p>
    </Card>
  )
}
