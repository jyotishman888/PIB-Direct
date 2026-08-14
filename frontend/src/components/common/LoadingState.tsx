import { Spin } from 'antd'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <Spin size="large" />
      <p className="text-sm text-muted">{label}</p>
    </div>
  )
}
