export function formatDate(isoString: string | null): string {
  if (!isoString) return 'Undated'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return 'Undated'
  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(isoString: string | null): string {
  if (!isoString) return 'Undated'
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return 'Undated'
  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** "12 minutes ago" / "3 hours ago" / "2 days ago".
 *
 * The static build serves a snapshot, and an absolute date ("Updated 20 Aug")
 * reads as current on the day it was built while saying nothing about whether
 * that was ten minutes or ten hours ago. Relative time is the honest signal,
 * and it is what makes the page feel alive rather than merely dated.
 */
export function formatRelative(isoString: string | null): string {
  if (!isoString) return 'Unknown'
  const then = new Date(isoString)
  if (Number.isNaN(then.getTime())) return 'Unknown'

  const seconds = Math.round((Date.now() - then.getTime()) / 1000)
  if (seconds < 0) return 'just now'
  if (seconds < 60) return 'just now'

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`

  const days = Math.round(hours / 24)
  // Past a week, "9 days ago" is less useful than the date itself.
  if (days <= 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return `on ${formatDate(isoString)}`
}
