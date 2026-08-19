import { Collapse, Tag, Tooltip, Typography } from 'antd'
import type { CSSProperties, ReactNode } from 'react'

import { accentTagStyle, examTagStyle, neutralTagStyle } from '@/lib/tagStyles'
import type { StudyClassification, StudyNotes } from '@/api/types'

const { Title } = Typography

// Syllabus and theme labels run long ("GS Paper 2 - Governance: Government
// Schemes for Export Promotion"), and antd Tags don't wrap — one such tag
// overflows a 375px viewport on its own.
const wrappingTagStyle: CSSProperties = {
  ...neutralTagStyle,
  whiteSpace: 'normal',
  maxWidth: '100%',
  height: 'auto',
}

const CLASSIFICATION_LABEL: Record<StudyClassification, string> = {
  PRELIMS: 'Prelims',
  MAINS: 'Mains',
  BOTH: 'Prelims + Mains',
  LOW_PRIORITY: 'Low priority',
}

/** Importance is the whole point of this layer, so it reads as a rating rather
 *  than a bare number — a reader scanning for what to study first shouldn't
 *  have to decode "4". */
function Importance({ score }: { score: number }) {
  const label = ['', 'Very low', 'Low', 'Moderate', 'High', 'Critical'][score] ?? String(score)
  const style: CSSProperties = score >= 4 ? examTagStyle : neutralTagStyle
  return (
    <Tooltip title={`Importance ${score}/5 — ${label}`}>
      <Tag className="m-0 shrink-0" style={style}>
        {'★'.repeat(score)}
        <span className="sr-only">{` importance ${score} of 5`}</span>
      </Tag>
    </Tooltip>
  )
}

function PointRow({
  importance,
  children,
  tag,
  note,
}: {
  importance: number
  children: ReactNode
  tag?: string
  note?: string
}) {
  return (
    <li className="flex flex-col gap-1 border-t border-border py-2.5 first:border-t-0">
      <div className="flex items-start gap-2">
        <Importance score={importance} />
        <span className="min-w-0 text-sm leading-relaxed text-foreground">{children}</span>
      </div>
      {(tag || note) && (
        <div className="flex min-w-0 flex-wrap items-center gap-2 ps-1 text-xs text-muted">
          {tag && (
            <Tag className="m-0" style={wrappingTagStyle}>
              {tag}
            </Tag>
          )}
          {note && <span className="min-w-0">{note}</span>}
        </div>
      )}
    </li>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <Title level={5} className="mb-1 font-serif text-foreground">
        {title}
      </Title>
      <ul className="m-0 list-none p-0">{children}</ul>
    </section>
  )
}

export function StudyNotesSection({ notes }: { notes: StudyNotes }) {
  const hasContent =
    notes.prelims.length > 0 || notes.mains.length > 0 || notes.both.length > 0
  if (!hasContent) return null

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-accent/30 bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Title level={4} className="mb-0 font-serif text-foreground">
          What to study
        </Title>
        <Tag className="m-0 font-semibold" style={accentTagStyle}>
          {CLASSIFICATION_LABEL[notes.classification]}
        </Tag>
      </div>
      <p className="m-0 text-sm leading-relaxed text-muted">{notes.reason}</p>

      {notes.both.length > 0 && (
        <Section title="Prelims + Mains">
          {notes.both.map((p) => (
            <PointRow
              key={p.concept}
              importance={p.importance}
              note={`Prelims: ${p.prelims_angle} · Mains: ${p.mains_angle}`}
            >
              {p.concept}
            </PointRow>
          ))}
        </Section>
      )}

      {notes.prelims.length > 0 && (
        <Section title="Prelims">
          {notes.prelims.map((p) => (
            <PointRow
              key={p.point}
              importance={p.importance}
              tag={p.syllabus}
              note={p.why_important}
            >
              {p.point}
            </PointRow>
          ))}
        </Section>
      )}

      {notes.mains.length > 0 && (
        <Section title="Mains">
          {notes.mains.map((p) => (
            <PointRow
              key={p.point}
              importance={p.importance}
              tag={`${p.gs_paper} · ${p.theme}`}
              note={p.analytical_use}
            >
              {p.point}
            </PointRow>
          ))}
        </Section>
      )}

      {notes.low_priority.length > 0 && (
        <Collapse
          ghost
          size="small"
          items={[
            {
              key: 'low',
              label: (
                <span className="text-xs text-muted">
                  Set aside as non-examinable ({notes.low_priority.length})
                </span>
              ),
              children: (
                <ul className="m-0 list-none p-0">
                  {notes.low_priority.map((p) => (
                    <li key={p.point} className="py-1 text-xs text-muted">
                      {p.point} — <span className="italic">{p.reason}</span>
                    </li>
                  ))}
                </ul>
              ),
            },
          ]}
        />
      )}
    </div>
  )
}
