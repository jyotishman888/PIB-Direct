import { BankOutlined, FileTextOutlined, TrophyOutlined } from '@ant-design/icons'
import { Statistic } from 'antd'
import type { ReactNode } from 'react'

import { useArticles } from '@/hooks/useArticles'
import { useMinistries } from '@/hooks/useMinistries'

export function StatsStrip() {
  const { data: ministries } = useMinistries()
  const { data: totalData } = useArticles({ limit: 1 })
  const { data: upscData } = useArticles({ limit: 1, upsc_relevant: true })

  const ministriesCovered = ministries?.filter((m) => m.article_count > 0).length

  const stats: Array<{ key: string; title: string; value: number | undefined; icon: ReactNode }> = [
    { key: 'total', title: 'Releases tracked', value: totalData?.total, icon: <FileTextOutlined /> },
    { key: 'ministries', title: 'Ministries covered', value: ministriesCovered, icon: <BankOutlined /> },
    { key: 'upsc', title: 'UPSC-relevant', value: upscData?.total, icon: <TrophyOutlined /> },
  ]

  return (
    <div className="grid grid-cols-3 gap-3 rounded-lg border border-border bg-surface p-4 sm:gap-6 sm:p-5">
      {stats.map((stat) => (
        <Statistic
          key={stat.key}
          title={<span className="text-xs text-muted sm:text-sm">{stat.title}</span>}
          value={stat.value ?? '—'}
          prefix={<span className="text-accent">{stat.icon}</span>}
          styles={{
            content: { fontFamily: 'var(--font-serif)', fontWeight: 700, fontSize: '1.5rem' },
          }}
        />
      ))}
    </div>
  )
}
