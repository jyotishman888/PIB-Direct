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
