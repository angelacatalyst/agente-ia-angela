import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { ChatPage } from '@/pages/ChatPage'
import { ControllerPage } from '@/pages/ControllerPage'
import { TransactionsPage } from '@/pages/TransactionsPage'
import { EODPage } from '@/pages/EODPage'
import { AuditPage } from '@/pages/AuditPage'
import { GrantsPage } from '@/pages/GrantsPage'
import { PaymentsPage } from '@/pages/PaymentsPage'
import { VendorsPage } from '@/pages/VendorsPage'
import { SOPsPage } from '@/pages/SOPsPage'
import { SettingsPage } from '@/pages/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 1000 * 60 * 5, retry: 1 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen overflow-hidden bg-surface-50">
          <Sidebar />
          <main className="flex-1 overflow-hidden min-w-0">
            <Routes>
              <Route path="/"             element={<ChatPage />} />
              <Route path="/controller"   element={<ControllerPage />} />
              <Route path="/audit"        element={<AuditPage />} />
              <Route path="/transactions" element={<TransactionsPage />} />
              <Route path="/grants"       element={<GrantsPage />} />
              <Route path="/payments"     element={<PaymentsPage />} />
              <Route path="/vendors"      element={<VendorsPage />} />
              <Route path="/sops"         element={<SOPsPage />} />
              <Route path="/eod"          element={<EODPage />} />
              <Route path="/settings"     element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
