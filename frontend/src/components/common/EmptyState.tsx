import { Empty } from 'antd'

export function EmptyState({
  title = 'Nothing here yet',
  description,
}: {
  title?: string
  description?: string
}) {
  return (
    <div className="rounded-lg border border-dashed border-border px-6 py-16">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            <span className="block text-sm font-medium text-foreground">{title}</span>
            {description && <span className="mt-1 block text-sm text-muted">{description}</span>}
          </span>
        }
      />
    </div>
  )
}
