import { SearchOutlined } from '@ant-design/icons'
import { Empty, Input, Menu, Skeleton, Tooltip } from 'antd'
import type { MenuProps } from 'antd'
import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useMinistries } from '@/hooks/useMinistries'

const ALL_KEY = '__all__'

export function MinistrySidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data: ministries, isLoading, isError } = useMinistries()
  const location = useLocation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  const activeSlug =
    location.pathname === '/' ? new URLSearchParams(location.search).get('ministry') : null
  const selectedKey = activeSlug ?? ALL_KEY

  const filteredMinistries = useMemo(() => {
    if (!ministries) return []
    const q = query.trim().toLowerCase()
    if (!q) return ministries
    return ministries.filter((ministry) => ministry.name.toLowerCase().includes(q))
  }, [ministries, query])

  const items: MenuProps['items'] = [
    ...(query.trim() ? [] : [{ key: ALL_KEY, label: 'All ministries' }]),
    ...filteredMinistries.map((ministry) => ({
      key: ministry.slug,
      label: (
        <span className="flex items-center justify-between gap-2">
          <Tooltip title={ministry.name} placement="right" mouseEnterDelay={0.4}>
            <span className="truncate">{ministry.name}</span>
          </Tooltip>
          <span className="text-xs tabular-nums text-muted">{ministry.article_count}</span>
        </span>
      ),
    })),
  ]

  function handleClick({ key }: { key: string }) {
    navigate(key === ALL_KEY ? '/' : `/?ministry=${key}`)
    onNavigate?.()
  }

  return (
    <nav aria-label="Ministries" className="flex h-full flex-col gap-2">
      <div className="px-1 pb-1">
        <Input
          allowClear
          placeholder="Filter ministries…"
          prefix={<SearchOutlined className="text-muted" />}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter ministries"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex flex-col gap-2 px-3 py-2" aria-hidden="true">
            {[...Array(6)].map((_, i) => (
              <Skeleton.Input key={i} active size="small" block />
            ))}
          </div>
        )}
        {isError && <p className="px-3 py-2 text-sm text-danger">Couldn't load ministries.</p>}
        {!isLoading && !isError && filteredMinistries.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No ministries match"
            className="px-3 py-6"
          />
        )}
        {!isLoading && !isError && filteredMinistries.length > 0 && (
          <Menu
            mode="inline"
            items={items}
            selectedKeys={[selectedKey]}
            onClick={handleClick}
            style={{ background: 'transparent', border: 'none' }}
          />
        )}
      </div>
    </nav>
  )
}
