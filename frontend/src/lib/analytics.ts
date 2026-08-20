/**
 * Google Analytics 4, for measuring whether anyone actually reads this.
 *
 * Client-side only: gtag.js collects, and reporting happens in the GA console.
 * Deliberately not a live-visitor widget — realtime counts come from the
 * server-side Analytics Data API, which the static build has no server to call,
 * and a "1 person reading now" badge is negative social proof anyway.
 *
 * No-ops entirely when VITE_GA_MEASUREMENT_ID is unset, which is the case in
 * local dev and in any fork, so development traffic never reaches the property.
 */

const MEASUREMENT_ID: string | undefined = import.meta.env.VITE_GA_MEASUREMENT_ID

declare global {
  interface Window {
    dataLayer?: unknown[]
    gtag?: (...args: unknown[]) => void
  }
}

let started = false

export function initAnalytics(): void {
  if (!MEASUREMENT_ID || started) return
  started = true

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`
  document.head.appendChild(script)

  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag(...args: unknown[]) {
    window.dataLayer!.push(args)
  }
  window.gtag('js', new Date())
  // send_page_view off, because this is a SPA: gtag would count the initial
  // load and then miss every client-side route change. trackPageView owns all
  // of them instead, so first paint isn't double-counted.
  window.gtag('config', MEASUREMENT_ID, { send_page_view: false })
}

export function trackPageView(path: string): void {
  if (!MEASUREMENT_ID) return
  window.gtag?.('event', 'page_view', { page_path: path })
}
