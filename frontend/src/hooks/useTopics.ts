import { useQuery } from '@tanstack/react-query'

import { fetchTopics } from '@/api/client'

export function useTopics() {
  return useQuery({
    queryKey: ['topics'],
    queryFn: fetchTopics,
  })
}
