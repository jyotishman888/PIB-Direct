import type { CSSProperties } from 'react'

// Shared antd Tag styles pulling from the theme's CSS variables (index.css)
// so tag colors stay in sync with light/dark mode without JS-side lookups.
export const examTagStyle: CSSProperties = {
  borderRadius: 9999,
  color: 'var(--color-exam-value)',
  background: 'var(--color-exam-soft-value)',
  borderColor: 'var(--color-exam-soft-value)',
}

export const accentTagStyle: CSSProperties = {
  borderRadius: 9999,
  color: 'var(--color-accent-value)',
  background: 'var(--color-accent-soft-value)',
  borderColor: 'var(--color-accent-soft-value)',
}

export const neutralTagStyle: CSSProperties = {
  borderRadius: 9999,
}
