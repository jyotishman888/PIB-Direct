import { useQuery } from '@tanstack/react-query'

import { fetchMinistries } from '@/api/client'

export function useMinistries() {
  return useQuery({
    queryKey: ['ministries'],
    queryFn: fetchMinistries,
  })
}
