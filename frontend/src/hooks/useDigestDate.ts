import { useQuery } from '@tanstack/react-query'

import { isStaticMode } from '@/api/client'
import { fetchMeta } from '@/api/staticClient'
import { getTodayIST } from '@/lib/today'

/**
 * The day the digest covers.
 *
 * Live, that's today in IST — PIB publishes on IST, not the visitor's clock.
 *
 * On the static build the bundle is a snapshot that may be hours or days
 * behind, so the digest follows the newest day actually present in it.
 * Keying a snapshot to the visitor's clock lands almost every visitor on the
 * "nothing published yet today" empty state, which is the single way this
 * deployment could look broken while working exactly as built.
 */
export function useDigestDate() {
  return useQuery({
    queryKey: ['digest-date'],
    queryFn: async (): Promise<string> => {
      if (!isStaticMode) return getTodayIST()
      const meta = await fetchMeta()
      return meta.latest_date ?? getTodayIST()
    },
    staleTime: Infinity,
    // Live mode knows the answer without a round trip, so the digest renders
    // on first paint instead of flashing a loading state.
    initialData: isStaticMode ? undefined : getTodayIST(),
  })
}
