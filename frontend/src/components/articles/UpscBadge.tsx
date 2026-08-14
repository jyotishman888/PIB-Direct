import { TrophyOutlined } from '@ant-design/icons'
import { Tag } from 'antd'

import { examTagStyle } from '@/lib/tagStyles'

export function UpscBadge() {
  return (
    <Tag icon={<TrophyOutlined />} className="m-0 font-semibold" style={examTagStyle}>
      UPSC
    </Tag>
  )
}
