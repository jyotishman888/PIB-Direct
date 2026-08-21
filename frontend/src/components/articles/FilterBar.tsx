import { FilterOutlined, SearchOutlined } from '@ant-design/icons'
import { Badge, Button, Checkbox, DatePicker, Input } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

const { RangePicker } = DatePicker

export interface FilterBarValue {
  search: string
  upscOnly: boolean
  dateFrom: string
  dateTo: string
}

export function FilterBar({
  value,
  onChange,
  onClear,
  hasActiveFilters,
}: {
  value: FilterBarValue
  onChange: (value: FilterBarValue) => void
  onClear: () => void
  hasActiveFilters: boolean
}) {
  // Collapsed by default on phones, where the full control set costs ~150px of
  // the first screen to a reader who has nothing to filter yet. Opens
  // automatically when a filter is already applied, so an arriving link never
  // hides why the list is narrowed.
  const [open, setOpen] = useState(false)
  const showControls = open || hasActiveFilters

  const rangeValue: [Dayjs | null, Dayjs | null] = [
    value.dateFrom ? dayjs(value.dateFrom) : null,
    value.dateTo ? dayjs(value.dateTo) : null,
  ]

  const activeCount =
    (value.upscOnly ? 1 : 0) + (value.dateFrom || value.dateTo ? 1 : 0)

  return (
    <div className="flex flex-col gap-[var(--spacing-snug)]">
      {/* Search stays visible at all widths: it is the one control a reader
          reaches for without being prompted. */}
      <div className="flex items-center gap-[var(--spacing-tight)]">
        <Input
          allowClear
          prefix={<SearchOutlined className="text-muted" />}
          placeholder="Search releases…"
          value={value.search}
          onChange={(event) => onChange({ ...value, search: event.target.value })}
          className="flex-1"
          aria-label="Search releases"
        />
        <Badge count={activeCount} size="small" offset={[-2, 2]}>
          <Button
            icon={<FilterOutlined />}
            onClick={() => setOpen((v) => !v)}
            aria-expanded={showControls}
            aria-label="Filters"
            className="sm:hidden"
          />
        </Badge>
      </div>

      <div
        className={`${showControls ? 'flex' : 'hidden'} flex-col gap-[var(--spacing-snug)] sm:flex sm:flex-row sm:flex-wrap sm:items-center`}
      >
        <Checkbox
          checked={value.upscOnly}
          onChange={(event) => onChange({ ...value, upscOnly: event.target.checked })}
        >
          UPSC-relevant only
        </Checkbox>

        <RangePicker
          value={rangeValue}
          allowEmpty={[true, true]}
          onChange={(dates) => {
            onChange({
              ...value,
              dateFrom: dates?.[0] ? dates[0].format('YYYY-MM-DD') : '',
              dateTo: dates?.[1] ? dates[1].format('YYYY-MM-DD') : '',
            })
          }}
        />

        {hasActiveFilters && (
          <Button type="link" onClick={onClear} className="px-0">
            Clear filters
          </Button>
        )}
      </div>
    </div>
  )
}
