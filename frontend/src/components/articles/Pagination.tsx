import { Pagination as AntPagination } from 'antd'

export function Pagination({
  total,
  limit,
  offset,
  onOffsetChange,
}: {
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
}) {
  if (total === 0) return null

  const current = Math.floor(offset / limit) + 1

  return (
    <div className="flex justify-end pt-2">
      <AntPagination
        current={current}
        pageSize={limit}
        total={total}
        showSizeChanger={false}
        onChange={(page, pageSize) => onOffsetChange((page - 1) * pageSize)}
        showTotal={(count, range) => `Showing ${range[0]}–${range[1]} of ${count}`}
      />
    </div>
  )
}
