import { CheckCircleFilled } from '@ant-design/icons'
import { Alert, Button, Card, Empty, Select, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchMySubscriptions, saveMySubscriptions } from '@/api/client'
import { useAuth } from '@/auth/authContext'
import { SignInButtons } from '@/components/auth/SignInButtons'
import { useMinistries } from '@/hooks/useMinistries'
import { accentTagStyle } from '@/lib/tagStyles'

const { Title } = Typography

const PROVIDER_LABELS: Record<string, string> = {
  google: 'Google',
  telegram: 'Telegram',
}

export function AccountPage() {
  const { user, isLoading } = useAuth()
  const navigate = useNavigate()
  const { data: ministries } = useMinistries()

  const [selected, setSelected] = useState<number[]>([])
  const [loadedSubs, setLoadedSubs] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoading && !user) navigate('/login', { replace: true })
  }, [isLoading, user, navigate])

  useEffect(() => {
    if (!user) return
    fetchMySubscriptions()
      .then((subs) => {
        setSelected(subs.map((s) => s.id))
        setLoadedSubs(true)
      })
      .catch(() => setError("Couldn't load your subscriptions."))
  }, [user])

  const options = useMemo(
    () => (ministries ?? []).map((m) => ({ label: m.name, value: m.id })),
    [ministries],
  )

  const missingProviders = useMemo(
    () => Object.keys(PROVIDER_LABELS).filter((p) => !user?.providers.includes(p)),
    [user],
  )

  if (!user) return null

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const updated = await saveMySubscriptions(selected)
      setSelected(updated.map((m) => m.id))
      message.success('Subscriptions saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save your subscriptions.')
    } finally {
      setSaving(false)
    }
  }

  const hasTelegram = user.providers.includes('telegram')

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Title level={2} className="mb-1 font-serif text-foreground">
          {user.display_name ?? 'Your account'}
        </Title>
        {user.email && <p className="text-sm text-muted">{user.email}</p>}
      </div>

      {error && <Alert type="error" title={error} showIcon />}

      <Card size="small" title="Sign-in methods">
        <div className="flex flex-wrap items-center gap-2">
          {user.providers.map((p) => (
            <Tag key={p} icon={<CheckCircleFilled />} style={accentTagStyle} className="m-0">
              {PROVIDER_LABELS[p] ?? p}
            </Tag>
          ))}
        </div>

        {missingProviders.length > 0 && (
          <div className="mt-4 flex flex-col gap-3">
            <p className="m-0 text-sm text-muted">
              Connect {missingProviders.map((p) => PROVIDER_LABELS[p]).join(' or ')} to sign in
              either way — it stays the same account.
            </p>
            <SignInButtons mode="link" />
          </div>
        )}
      </Card>

      <Card size="small" title="Ministries you follow">
        {!hasTelegram && (
          <Alert
            className="mb-3"
            type="info"
            showIcon
            title="Connect Telegram to get these as notifications"
            description="Subscriptions are saved either way, but releases are delivered through the Telegram bot."
          />
        )}

        {options.length === 0 ? (
          <Empty description="No ministries yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="flex flex-col gap-3">
            <Select
              mode="multiple"
              allowClear
              value={selected}
              onChange={setSelected}
              options={options}
              disabled={!loadedSubs}
              placeholder="Pick the ministries you want to follow"
              optionFilterProp="label"
              className="w-full"
              maxTagCount="responsive"
            />
            <div className="flex items-center gap-3">
              <Button type="primary" loading={saving} onClick={save} disabled={!loadedSubs}>
                Save subscriptions
              </Button>
              <Link to="/" className="text-sm text-accent hover:underline">
                Back to releases
              </Link>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
