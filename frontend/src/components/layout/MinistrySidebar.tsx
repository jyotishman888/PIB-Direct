import { SearchOutlined } from '@ant-design/icons'
import { Empty, Input, Menu, Segmented, Skeleton, Tooltip } from 'antd'
import type { MenuProps } from 'antd'
import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useMinistries } from '@/hooks/useMinistries'
import { useTopics } from '@/hooks/useTopics'

const ALL_KEY = '__all__'

type Mode = 'ministry' | 'topic'

/** One row shape for both modes: a truncating label with its count. */
function facetLabel(name: string, count: number) {
  return (
    <span className="flex items-center justify-between gap-2">
      <Tooltip title={name} placement="right" mouseEnterDelay={0.4}>
        <span className="truncate">{name}</span>
      </Tooltip>
      <span className="text-xs tabular-nums text-muted">{count}</span>
    </span>
  )
}

export function MinistrySidebar({ onNavigate }: { onNavigate?: () => void }) {
  const ministries = useMinistries()
  const topics = useTopics()
  const location = useLocation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  const params = location.pathname === '/' ? new URLSearchParams(location.search) : null
  const activeMinistry = params?.get('ministry') ?? null
  const activeTopic = params?.get('topic') ?? null

  // The URL decides the mode on load, so a shared ?topic= link opens in the
  // right tab rather than showing ministries over a topic-filtered list.
  const [mode, setMode] = useState<Mode>(activeTopic ? 'topic' : 'ministry')

  const source = mode === 'ministry' ? ministries : topics
  const { isLoading, isError } = source

  const rows = useMemo(() => {
    const all =
      mode === 'ministry'
        ? (ministries.data ?? []).map((m) => ({
            key: m.slug,
            name: m.name,
            count: m.article_count,
          }))
        : (topics.data ?? []).map((t) => ({
            key: t.slug,
            name: t.name,
            count: t.article_count,
          }))
    const q = query.trim().toLowerCase()
    return q ? all.filter((r) => r.name.toLowerCase().includes(q)) : all
  }, [mode, ministries.data, topics.data, query])

  const selectedKey = (mode === 'ministry' ? activeMinistry : activeTopic) ?? ALL_KEY
  const allLabel = mode === 'ministry' ? 'All ministries' : 'All topics'

  const items: MenuProps['items'] = [
    ...(query.trim() ? [] : [{ key: ALL_KEY, label: allLabel }]),
    ...rows.map((row) => ({ key: row.key, label: facetLabel(row.name, row.count) })),
  ]

  function handleClick({ key }: { key: string }) {
    navigate(key === ALL_KEY ? '/' : `/?${mode}=${encodeURIComponent(key)}`)
    onNavigate?.()
  }

  function handleModeChange(next: Mode) {
    setMode(next)
    setQuery('')
    // Switching tabs while a filter of the other kind is active would leave
    // the list contradicting the sidebar, so clear back to everything.
    if (activeMinistry || activeTopic) navigate('/')
  }

  return (
    <nav aria-label="Browse" className="flex h-full flex-col gap-2">
      <div className="px-1">
        <Segmented<Mode>
          block
          size="small"
          value={mode}
          onChange={handleModeChange}
          options={[
            { label: 'Ministries', value: 'ministry' },
            { label: 'Topics', value: 'topic' },
          ]}
        />
      </div>

      <div className="px-1 pb-1">
        <Input
          allowClear
          placeholder={mode === 'ministry' ? 'Filter ministries…' : 'Filter topics…'}
          prefix={<SearchOutlined className="text-muted" />}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={mode === 'ministry' ? 'Filter ministries' : 'Filter topics'}
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
        {isError && (
          <p className="px-3 py-2 text-sm text-danger">
            Couldn't load {mode === 'ministry' ? 'ministries' : 'topics'}.
          </p>
        )}
        {!isLoading && !isError && rows.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={`No ${mode === 'ministry' ? 'ministries' : 'topics'} match`}
            className="px-3 py-6"
          />
        )}
        {!isLoading && !isError && rows.length > 0 && (
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
