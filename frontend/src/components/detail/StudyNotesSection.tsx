import { Collapse, Tag, Tooltip, Typography } from 'antd'
import type { CSSProperties, ReactNode } from 'react'

import { accentTagStyle, examTagStyle, neutralTagStyle } from '@/lib/tagStyles'
import type { Importance, StudyClassification, StudyNotes } from '@/api/types'

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

/** Two buckets, not a rating. The reader makes one decision here — what to
 *  study first — so the label says exactly that instead of asking them to
 *  decode a number. */
function ImportanceTag({ importance }: { importance: Importance }) {
  const important = importance === 'IMPORTANT'
  return (
    <Tooltip title={important ? 'Know this one' : 'Worth reading once'}>
      <Tag
        className="m-0 shrink-0"
        style={important ? examTagStyle : neutralTagStyle}
      >
        {important ? 'Important' : 'Worth a look'}
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
  importance: Importance
  children: ReactNode
  tag?: string
  note?: string
}) {
  return (
    <li className="flex flex-col gap-1 border-t border-border py-2.5 first:border-t-0">
      <div className="flex items-start gap-2">
        <ImportanceTag importance={importance} />
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

/** Important first: the label is only useful if it also drives the order. */
function byImportance<T extends { importance: Importance }>(points: T[]): T[] {
  return [...points].sort((a, b) =>
    a.importance === b.importance ? 0 : a.importance === 'IMPORTANT' ? -1 : 1,
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
          {byImportance(notes.both).map((p) => (
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
          {byImportance(notes.prelims).map((p) => (
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
          {byImportance(notes.mains).map((p) => (
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
