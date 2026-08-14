import { useEffect, useState } from 'react'

type ColorScheme = 'light' | 'dark'

function resolveColorScheme(): ColorScheme {
  const override = document.documentElement.dataset.theme
  if (override === 'light' || override === 'dark') return override
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/**
 * Mirrors the precedence already encoded in index.css's CSS variables
 * (`data-theme` override, else `prefers-color-scheme`) so antd's theme
 * algorithm stays in sync with the existing Tailwind dark-mode mechanism
 * instead of tracking its own.
 */
export function useColorScheme(): ColorScheme {
  const [scheme, setScheme] = useState<ColorScheme>(() =>
    typeof window === 'undefined' ? 'light' : resolveColorScheme(),
  )

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setScheme(resolveColorScheme())

    media.addEventListener('change', update)

    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

    return () => {
      media.removeEventListener('change', update)
      observer.disconnect()
    }
  }, [])

  return scheme
}
