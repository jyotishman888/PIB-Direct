import { LogoutOutlined, MenuOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons'
import { Avatar, Button, Dropdown, Skeleton } from 'antd'
import type { MenuProps } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '@/auth/authContext'

const TODAY = new Date().toLocaleDateString('en-IN', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-20 border-b border-accent/20 bg-surface/95 shadow-sm backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-4">
        <Button
          type="text"
          onClick={onMenuClick}
          aria-label="Toggle ministry menu"
          icon={<MenuOutlined />}
          className="lg:hidden"
        />
        <span className="hidden h-8 w-1.5 shrink-0 rounded-full bg-accent sm:block" />
        <Link to="/" className="flex flex-1 items-baseline gap-2">
          <span className="font-serif text-xl font-bold tracking-tight text-foreground">
            PIB Direct
          </span>
          <span className="hidden text-xs text-muted sm:inline">
            Daily press releases, annotated for UPSC prep
          </span>
        </Link>
        <span className="hidden shrink-0 text-xs text-muted sm:block">{TODAY}</span>
        <AccountMenu />
      </div>
    </header>
  )
}

function AccountMenu() {
  const { user, isLoading, signOut } = useAuth()
  const navigate = useNavigate()

  if (isLoading) {
    return <Skeleton.Avatar active size="small" />
  }

  if (!user) {
    return (
      <Button size="small" icon={<UserOutlined />} onClick={() => navigate('/login')}>
        Sign in
      </Button>
    )
  }

  const items: MenuProps['items'] = [
    { key: 'account', icon: <SettingOutlined />, label: 'My ministries' },
    { type: 'divider' },
    { key: 'signout', icon: <LogoutOutlined />, label: 'Sign out' },
  ]

  async function handleClick({ key }: { key: string }) {
    if (key === 'account') navigate('/account')
    if (key === 'signout') {
      await signOut()
      navigate('/')
    }
  }

  return (
    <Dropdown menu={{ items, onClick: handleClick }} trigger={['click']} placement="bottomRight">
      <button
        type="button"
        aria-label="Account menu"
        className="flex shrink-0 cursor-pointer items-center gap-2 rounded-full border-0 bg-transparent p-0"
      >
        <Avatar
          size="small"
          src={user.avatar_url ?? undefined}
          icon={<UserOutlined />}
          style={{ backgroundColor: 'var(--color-accent-value)' }}
        />
      </button>
    </Dropdown>
  )
}
