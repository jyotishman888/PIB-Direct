import { Typography } from 'antd'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { SignInButtons } from '@/components/auth/SignInButtons'
import { useAuth } from '@/auth/authContext'

const { Title } = Typography

export function LoginPage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (user) navigate('/account', { replace: true })
  }, [user, navigate])

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-12 text-center">
      <div>
        <Title level={2} className="mb-1 font-serif text-foreground">
          Sign in
        </Title>
        <p className="text-sm text-muted">
          Keep your ministry subscriptions in one place, on every device — and get them on
          Telegram the moment PIB publishes.
        </p>
      </div>

      <SignInButtons onDone={() => navigate('/account')} />

      <p className="text-xs text-muted">
        Reading releases doesn't need an account. Signing in only saves what's yours.
      </p>
    </div>
  )
}
