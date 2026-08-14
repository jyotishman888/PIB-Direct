import { StyleProvider } from '@ant-design/cssinjs'
import { ConfigProvider, Drawer } from 'antd'
import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'

import { AuthProvider } from '@/auth/AuthProvider'
import { Header } from '@/components/layout/Header'
import { MinistrySidebar } from '@/components/layout/MinistrySidebar'
import { useColorScheme } from '@/hooks/useColorScheme'
import { AccountPage } from '@/pages/AccountPage'
import { ArticleDetailPage } from '@/pages/ArticleDetailPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { LoginPage } from '@/pages/LoginPage'
import { antdThemes } from '@/theme/antdTheme'

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
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
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/articles/:id" element={<ArticleDetailPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/account" element={<AccountPage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
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
