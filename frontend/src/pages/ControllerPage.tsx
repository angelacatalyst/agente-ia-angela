import { useState, useEffect, useCallback } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api, type QBODashboard } from '@/lib/api'
import {
  LayoutDashboard, TrendingUp, AlertTriangle, CheckCircle2,
  ArrowUpRight, ArrowDownRight, RefreshCw, Download, Loader2,
  Building2,
} from 'lucide-react'

const levelStyle: Record<string, string> = {
  high:   'bg-red-50 text-red-700 ring-1 ring-red-200',
  medium: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  low:    'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
}

export function ControllerPage() {
  const { t } = useI18n()
  const { selectedRealmId, companies } = useAppStore()

  const [data, setData] = useState<QBODashboard | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [spinning, setSpinning] = useState(false)

  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  const fetchData = useCallback(async () => {
    if (!selectedRealmId) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.qboData.dashboard(selectedRealmId)
      setData(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [selectedRealmId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleRefresh = () => {
    setSpinning(true)
    fetchData().finally(() => setTimeout(() => setSpinning(false), 600))
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={LayoutDashboard}
        title={t('page.controller.title')}
        subtitle={companyName ? `${companyName} · Live QBO data` : t('page.controller.subtitle')}
        badge="AI"
        actions={
          <>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="btn-ghost text-[13px] gap-1.5"
            >
              <RefreshCw size={14} className={spinning || loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button className="btn-primary text-[13px]">
              <Download size={14} />
              {t('common.export')}
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">

        {/* No company selected */}
        {!selectedRealmId && (
          <div className="card p-8 flex flex-col items-center gap-3 text-center">
            <Building2 size={32} className="text-surface-300" />
            <p className="text-sm font-medium text-surface-600">No company selected</p>
            <p className="text-xs text-surface-400">Select a company from the sidebar to load live data.</p>
          </div>
        )}

        {/* Loading state */}
        {selectedRealmId && loading && !data && (
          <div className="card p-8 flex flex-col items-center gap-3 text-center">
            <Loader2 size={28} className="text-primary-500 animate-spin" />
            <p className="text-sm text-surface-500">Loading live data from QuickBooks…</p>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="card p-4 border-red-200 bg-red-50">
            <p className="text-sm text-red-700 font-medium">⚠️ {error}</p>
          </div>
        )}

        {/* Data loaded */}
        {data && (
          <>
            {/* KPIs */}
            <div className="grid grid-cols-4 gap-4">
              {data.kpis.map((k, i) => {
                const isPositive = i === 0
                const hasValue = k.raw !== null && k.raw !== undefined
                return (
                  <div key={k.label} className="card p-5 space-y-3">
                    <p className="text-[12px] font-medium text-surface-500">{k.label}</p>
                    <p className="text-2xl font-bold text-surface-900 tracking-tight">{k.value}</p>
                    <div className="flex items-center gap-1.5">
                      {hasValue && (
                        isPositive
                          ? <ArrowUpRight size={13} className="text-emerald-500" />
                          : <ArrowDownRight size={13} className="text-amber-500" />
                      )}
                      <span className="text-[11px] text-surface-400">{k.source}</span>
                    </div>
                  </div>
                )
              })}
            </div>

            <div className="grid grid-cols-3 gap-5">
              {/* Alerts */}
              <div className="col-span-2 card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <AlertTriangle size={16} className="text-amber-500" />
                  <h2 className="text-sm font-semibold text-surface-900">Priority Alerts</h2>
                  {data.alerts.filter(a => a.level === 'high').length > 0 && (
                    <span className="badge bg-red-50 text-red-600 ring-1 ring-red-200 ml-auto">
                      {data.alerts.filter(a => a.level === 'high').length} High
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  {data.alerts.map((a, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-surface-50 border border-surface-100">
                      <span className={`badge shrink-0 mt-px capitalize ${levelStyle[a.level]}`}>{a.level}</span>
                      <p className="text-sm text-surface-700">{a.text}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Today's Priorities */}
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle2 size={16} className="text-primary-600" />
                  <h2 className="text-sm font-semibold text-surface-900">Today's Priorities</h2>
                </div>
                <div className="space-y-3">
                  {data.priorities.map((p, i) => (
                    <label key={i} className="flex items-start gap-2.5 cursor-pointer group">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-4 w-4 rounded border-surface-300 accent-primary-600 cursor-pointer shrink-0"
                      />
                      <span className="text-sm text-surface-700 group-hover:text-surface-900 leading-snug">
                        {p}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            {/* Cash flow summary */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={16} className="text-primary-600" />
                <h2 className="text-sm font-semibold text-surface-900">Financial Summary</h2>
                <span className="ml-auto text-xs text-surface-400">
                  Updated {new Date(data.fetched_at).toLocaleTimeString()}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4">
                {data.kpis.slice(0, 3).map(k => (
                  <div key={k.label} className="rounded-xl bg-surface-50 border border-surface-100 p-4 text-center">
                    <p className="text-[11px] text-surface-400 mb-1">{k.label}</p>
                    <p className="text-lg font-bold text-surface-900">{k.value}</p>
                    <p className="text-[10px] text-surface-400 mt-1">{k.source}</p>
                  </div>
                ))}
              </div>
              {data.errors.length > 0 && (
                <p className="mt-3 text-[11px] text-amber-600">
                  ⚠️ Some data could not be loaded: {data.errors.join(', ')}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
