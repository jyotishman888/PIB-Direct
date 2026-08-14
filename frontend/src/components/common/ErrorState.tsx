import { Button, Result } from 'antd'

export function ErrorState({
  message = 'Something went wrong while loading this.',
  onRetry,
}: {
  message?: string
  onRetry?: () => void
}) {
  return (
    <Result
      status="error"
      title={message}
      extra={
        onRetry && (
          <Button onClick={onRetry} className="border-border">
            Try again
          </Button>
        )
      }
    />
  )
}
