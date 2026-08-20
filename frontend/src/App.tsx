import { StyleProvider } from '@ant-design/cssinjs'
import { ConfigProvider, Drawer } from 'antd'
import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'

import { isStaticMode } from '@/api/client'
import { initAnalytics, trackPageView } from '@/lib/analytics'
import { AuthProvider } from '@/auth/AuthProvider'
import { LoadingState } from '@/components/common/LoadingState'
import { Header } from '@/components/layout/Header'
import { MinistrySidebar } from '@/components/layout/MinistrySidebar'
import { useColorScheme } from '@/hooks/useColorScheme'
import { DashboardPage } from '@/pages/DashboardPage'
import { antdThemes } from '@/theme/antdTheme'

// Split out of the landing bundle: none of these are needed for first paint,
// and together they pull in antd surface (DatePicker, Select, forms) a
// signed-out reader on mobile data never touches on the digest.
const ArticleDetailPage = lazy(() =>
  import('@/pages/ArticleDetailPage').then((m) => ({ default: m.ArticleDetailPage })),
)
const LoginPage = lazy(() =>
  import('@/pages/LoginPage').then((m) => ({ default: m.LoginPage })),
)
const AccountPage = lazy(() =>
  import('@/pages/AccountPage').then((m) => ({ default: m.AccountPage })),
)

/** GA4 counts the initial load only; a SPA has to report its own route
 *  changes or every page after the first is invisible. */
function usePageViews() {
  const { pathname, search } = useLocation()
  const lastTracked = useRef<string | null>(null)
  useEffect(() => {
    const path = pathname + search
    // StrictMode runs effects twice in development, which would double-count
    // every landing. Guarding on the last path tracked is also just correct:
    // re-rendering at the same URL is not a new page view.
    if (lastTracked.current === path) return
    lastTracked.current = path
    initAnalytics()
    trackPageView(path)
  }, [pathname, search])
}

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  usePageViews()
  const colorScheme = useColorScheme()

  return (
    <StyleProvider layer>
      <ConfigProvider theme={antdThemes[colorScheme]}>
        <AuthProvider>
        <div className="flex min-h-svh flex-col">
          <Header onMenuClick={() => setSidebarOpen((open) => !open)} />
          <div className="mx-auto flex w-full max-w-6xl flex-1 gap-6 px-4 py-6">
            <aside className="sticky top-20 hidden h-[calc(100svh-6rem)] w-64 shrink-0 lg:block">
              <MinistrySidebar />
            </aside>

            <Drawer
              placement="left"
              open={sidebarOpen}
              onClose={() => setSidebarOpen(false)}
              closable={false}
              size={280}
              styles={{ body: { padding: 12 } }}
              className="lg:hidden"
            >
              <MinistrySidebar onNavigate={() => setSidebarOpen(false)} />
            </Drawer>

            <main className="min-w-0 flex-1">
              <Suspense fallback={<LoadingState label="Loading…" />}>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/articles/:id" element={<ArticleDetailPage />} />
                  {/* No backend on the static build, so there is nothing to
                      sign into — these routes would only dead-end. */}
                  {!isStaticMode && <Route path="/login" element={<LoginPage />} />}
                  {!isStaticMode && <Route path="/account" element={<AccountPage />} />}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </main>
          </div>
        </div>
        </AuthProvider>
      </ConfigProvider>
    </StyleProvider>
  )
}

function NotFound() {
  return (
    <div className="py-16 text-center">
      <p className="text-lg font-semibold text-foreground">Page not found</p>
    </div>
  )
}
