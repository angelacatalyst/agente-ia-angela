/**
 * Global app store — sidebar, preferences, selected QBO company.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { QBOCompany } from '@/lib/api'

interface AppState {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  setSidebar: (v: boolean) => void

  // QBO company selection
  companies: QBOCompany[]
  selectedRealmId: string | null
  setCompanies: (companies: QBOCompany[]) => void
  setSelectedRealmId: (realmId: string | null) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebar: (v) => set({ sidebarCollapsed: v }),

      companies: [],
      selectedRealmId: null,
      setCompanies: (companies) => set({ companies }),
      setSelectedRealmId: (realmId) => set({ selectedRealmId: realmId }),
    }),
    {
      name: 'finance-ops-app',
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        selectedRealmId: s.selectedRealmId,
      }),
    },
  ),
)
