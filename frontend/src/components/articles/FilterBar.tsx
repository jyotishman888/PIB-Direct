import { Button, Checkbox, DatePicker, Input } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

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
  const rangeValue: [Dayjs | null, Dayjs | null] = [
    value.dateFrom ? dayjs(value.dateFrom) : null,
    value.dateTo ? dayjs(value.dateTo) : null,
  ]

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-3 sm:flex-row sm:flex-wrap sm:items-center">
      <Input.Search
        allowClear
        placeholder="Search title or summary…"
        value={value.search}
        onChange={(event) => onChange({ ...value, search: event.target.value })}
        className="flex-1 sm:min-w-[220px]"
      />

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
  )
}
