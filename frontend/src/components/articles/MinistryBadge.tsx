import { Tag } from 'antd'

import { neutralTagStyle } from '@/lib/tagStyles'

export function MinistryBadge({ name }: { name: string }) {
  return (
    <Tag className="m-0" style={neutralTagStyle}>
      {name}
    </Tag>
  )
}
