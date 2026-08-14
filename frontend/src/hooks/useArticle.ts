import { useQuery } from '@tanstack/react-query'

import { fetchArticle } from '@/api/client'

export function useArticle(id: number) {
  return useQuery({
    queryKey: ['article', id],
    queryFn: () => fetchArticle(id),
    enabled: Number.isFinite(id),
  })
}
