import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchArticles } from '@/api/client'
import type { ArticleListParams } from '@/api/types'

export function useArticles(params: ArticleListParams, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['articles', params],
    queryFn: () => fetchArticles(params),
    placeholderData: keepPreviousData,
    enabled: options?.enabled,
  })
}
