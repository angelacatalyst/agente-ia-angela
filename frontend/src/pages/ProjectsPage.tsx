import { useEffect, useState } from 'react'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import type { QBOProject, QBODonor } from '@/lib/api'
import { cn } from '@/lib/utils'
import { FolderOpen, Users, RefreshCw, AlertCircle, Loader2, ChevronRight, DollarSign } from 'lucide-react'

const ALLAPATTAH_REALM = '9341454010854556'

type Tab = 'projects' | 'donors'

export function ProjectsPage() {
  const { selectedRealmId } = useAppStore()
  const [tab, setTab] = useState<Tab>('projects')
  const [projects, setProjects] = useState<QBOProject[]>([])
  const [donors, setDonors] = useState<QBODonor[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fetchedAt, setFetchedAt] = useState<string | null>(null)
  const [selectedDonor, setSelectedDonor] = useState<QBODonor | null>(null)
  const [plLoading, setPlLoading] = useState(false)
  const [plData, setPlData] = useState<any>(null)

  const isAllapattah = selectedRealmId === ALLAPATTAH_REALM

  const load = async () => {
    if (!selectedRealmId) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.qboData.projects(selectedRealmId)
      setProjects(data.projects)
      setDonors(data.donors)
      setFetchedAt(data.fetched_at)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Error loading projects')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedRealmId) load()
  }, [selectedRealmId])

  const loadDonorPL = async (donor: QBODonor) => {
    if (!selectedRealmId) return
    setSelectedDonor(donor)
    setPlLoading(true)
    setPlData(null)
    try {
      const now = new Date()
      const startDate = `${now.getFullYear()}-01-01`
      const endDate = now.toISOString().split('T')[0]
      const data = await api.qboData.projectPL(selectedRealmId, donor.id, startDate, endDate)
      setPlData(data)
    } catch (e) {
      setPlData(null)
    } finally {
      setPlLoading(false)
    }
  }

  if (!isAllapattah) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-50">
        <div className="text-center space-y-3 max-w-sm">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-50 ring-1 ring-amber-200">
            <FolderOpen size={24} className="text-amber-500" />
          </div>
          <h2 className="text-base font-semibold text-surface-900">Grant Projects — Allapattah CDC Only</h2>
          <p className="text-sm text-surface-500">
            Switch to <strong>Allapattah CDC</strong> in the sidebar to view grant projects and donors.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-surface-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 ring-1 ring-emerald-200">
            <FolderOpen size={14} className="text-emerald-600" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-surface-900 leading-none">Grant Projects</h1>
            <p className="text-[11px] text-surface-400 mt-0.5">Allapattah CDC · Live QBO data</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {fetchedAt && (
            <span className="text-[11px] text-surface-400">
              Updated {new Date(fetchedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-surface-200 bg-white px-3 py-1.5 text-xs font-medium text-surface-600 hover:bg-surface-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-surface-200 bg-white px-6">
        <div className="flex gap-1">
          {([['projects', 'Projects', FolderOpen], ['donors', 'Donors / Funders', Users]] as const).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-3 text-xs font-medium transition-colors',
                tab === key
                  ? 'border-primary-600 text-primary-700'
                  : 'border-transparent text-surface-500 hover:text-surface-700',
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 border border-red-200">
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex h-48 items-center justify-center gap-2 text-surface-400">
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Loading from QBO…</span>
          </div>
        ) : tab === 'projects' ? (
          <ProjectsTab projects={projects} />
        ) : (
          <DonorsTab
            donors={donors}
            selectedDonor={selectedDonor}
            onSelect={loadDonorPL}
            plLoading={plLoading}
            plData={plData}
          />
        )}
      </div>
    </div>
  )
}

function ProjectsTab({ projects }: { projects: QBOProject[] }) {
  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-surface-400 gap-2">
        <FolderOpen size={32} className="text-surface-300" />
        <p className="text-sm">No QBO Projects found. Projects are tracked via Donors/Customers.</p>
        <p className="text-xs text-surface-400">Switch to the <strong>Donors / Funders</strong> tab to see grant activity.</p>
      </div>
    )
  }

  return (
    <div className="grid gap-3 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
      {projects.map(p => (
        <div key={p.id} className="card rounded-xl p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-surface-900 leading-tight">{p.name}</h3>
            <span className={cn(
              'shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full',
              p.status === 'IN_PROGRESS' ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-100 text-surface-500',
            )}>
              {p.status === 'IN_PROGRESS' ? 'Active' : p.status}
            </span>
          </div>
          {p.customer_name && (
            <p className="text-xs text-surface-500">Funder: {p.customer_name}</p>
          )}
          {p.description && (
            <p className="text-xs text-surface-400 line-clamp-2">{p.description}</p>
          )}
        </div>
      ))}
    </div>
  )
}

function DonorsTab({
  donors, selectedDonor, onSelect, plLoading, plData,
}: {
  donors: QBODonor[]
  selectedDonor: QBODonor | null
  onSelect: (d: QBODonor) => void
  plLoading: boolean
  plData: any
}) {
  if (donors.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-surface-400 gap-2">
        <Users size={32} className="text-surface-300" />
        <p className="text-sm">No donors/customers found in QBO.</p>
      </div>
    )
  }

  return (
    <div className="flex gap-6 h-full">
      {/* Donor list */}
      <div className="w-72 shrink-0 space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-surface-400 mb-3">
          {donors.length} Donors / Funders
        </p>
        {donors.map(d => (
          <button
            key={d.id}
            onClick={() => onSelect(d)}
            className={cn(
              'w-full text-left rounded-xl border px-4 py-3 transition-all',
              selectedDonor?.id === d.id
                ? 'border-primary-300 bg-primary-50 shadow-sm'
                : 'border-surface-200 bg-white hover:border-surface-300 hover:shadow-sm',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-surface-900 truncate">{d.name}</span>
              <ChevronRight size={12} className="text-surface-400 shrink-0" />
            </div>
            {d.balance > 0 && (
              <div className="flex items-center gap-1 mt-1">
                <DollarSign size={10} className="text-emerald-500" />
                <span className="text-[11px] text-emerald-700 font-medium">{d.balance_formatted}</span>
              </div>
            )}
          </button>
        ))}
      </div>

      {/* P&L detail panel */}
      <div className="flex-1 min-w-0">
        {!selectedDonor && (
          <div className="flex h-full items-center justify-center text-surface-400">
            <p className="text-sm">Select a donor to see grant P&L</p>
          </div>
        )}
        {selectedDonor && (
          <div className="card rounded-xl p-5 h-full overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-bold text-surface-900">{selectedDonor.name}</h2>
                <p className="text-[11px] text-surface-400">YTD Grant Activity · {new Date().getFullYear()}</p>
              </div>
              {selectedDonor.balance > 0 && (
                <div className="text-right">
                  <p className="text-xs text-surface-400">Balance</p>
                  <p className="text-sm font-bold text-emerald-700">{selectedDonor.balance_formatted}</p>
                </div>
              )}
            </div>

            {plLoading && (
              <div className="flex items-center justify-center h-32 gap-2 text-surface-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm">Loading P&L from QBO…</span>
              </div>
            )}

            {!plLoading && plData && (
              <PLReport report={plData.report} />
            )}

            {!plLoading && !plData && selectedDonor && (
              <div className="text-center text-surface-400 py-8 text-sm">
                No P&L data available for this donor.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function PLReport({ report }: { report: any }) {
  const rows = report?.Rows?.Row || []
  if (!rows.length) {
    return <p className="text-sm text-surface-400">No transactions found for this donor in the selected period.</p>
  }

  const renderRows = (rows: any[], depth = 0): JSX.Element[] => {
    return rows.flatMap((row: any) => {
      const colData = row.ColData || row.Header?.ColData || []
      const label = colData[0]?.value || ''
      const value = colData[1]?.value || ''
      const subRows = row.Rows?.Row || []
      const summary = row.Summary?.ColData || []
      const summaryLabel = summary[0]?.value || ''
      const summaryValue = summary[1]?.value || ''

      const items: JSX.Element[] = []

      if (label && value) {
        items.push(
          <div key={`${label}-${depth}`} className={cn('flex justify-between py-1 text-xs', depth > 0 ? 'pl-4' : '')}>
            <span className="text-surface-600">{label}</span>
            <span className="font-medium text-surface-800">{value ? `$${parseFloat(value).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : ''}</span>
          </div>
        )
      }

      if (subRows.length) {
        items.push(...renderRows(subRows, depth + 1))
      }

      if (summaryLabel) {
        items.push(
          <div key={`sum-${summaryLabel}`} className={cn('flex justify-between py-1.5 text-xs font-semibold border-t border-surface-100 mt-1', depth > 0 ? 'pl-4' : '')}>
            <span className="text-surface-800">{summaryLabel}</span>
            <span className={cn(summaryValue && parseFloat(summaryValue) < 0 ? 'text-red-600' : 'text-emerald-700')}>
              {summaryValue ? `$${parseFloat(summaryValue).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : ''}
            </span>
          </div>
        )
      }

      return items
    })
  }

  return <div className="divide-y divide-surface-100">{renderRows(rows)}</div>
}
