import { useState, useEffect } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Search, AlertTriangle, AlertCircle, Loader2, CheckCircle2,
  ShieldCheck, Calendar, ChevronDown, ChevronUp,
} from 'lucide-react'

interface Finding {
  severity: 'high' | 'medium' | 'low'
  message: string
}

interface AuditResult {
  realm_id: string
  period_from: string
  period_to: string
  audited_at: string
  status: 'clean' | 'needs_attention' | 'critical'
  total_findings: number
  high: Finding[]
  medium: Finding[]
  low: Finding[]
  data_fetched: Record<string, boolean>
}

function SeverityBadge({ sev }: { sev: 'high' | 'medium' | 'low' }) {
  const cfg = {
    high:   { cls: 'bg-red-100 text-red-700 border-red-200',    label: 'High' },
    medium: { cls: 'bg-amber-100 text-amber-700 border-amber-200', label: 'Medium' },
    low:    { cls: 'bg-blue-100 text-blue-700 border-blue-200',  label: 'Low' },
  }[sev]
  return (
    <span className={cn('text-[10px] font-bold px-2 py-0.5 rounded-full border', cfg.cls)}>
      {cfg.label}
    </span>
  )
}

function FindingGroup({ title, findings, defaultOpen = true }: {
  title: string
  findings: Finding[]
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  if (!findings.length) return null
  return (
    <div className="border border-surface-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface-50 hover:bg-surface-100 transition-colors"
      >
        <span className="text-xs font-semibold text-surface-700">{title} ({findings.length})</span>
        {open ? <ChevronUp size={14} className="text-surface-400" /> : <ChevronDown size={14} className="text-surface-400" />}
      </button>
      {open && (
        <div className="divide-y divide-surface-100">
          {findings.map((f, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-3">
              <SeverityBadge sev={f.severity} />
              <p className="text-xs text-surface-700 leading-relaxed flex-1">{f.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function AuditPage() {
  const { t } = useI18n()
  const { selectedRealmId, companies } = useAppStore()

  const today = new Date()
  const firstOfYear = `${today.getFullYear()}-01-01`
  const todayStr = today.toISOString().slice(0, 10)

  const [periodFrom, setPeriodFrom] = useState(firstOfYear)
  const [periodTo, setPeriodTo] = useState(todayStr)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AuditResult | null>(null)

  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  // Auto-run when company changes
  useEffect(() => {
    setResult(null)
    setError(null)
  }, [selectedRealmId])

  const handleRun = async () => {
    if (!selectedRealmId) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await apiClient.get<AuditResult>('/audit/run', {
        params: { realm_id: selectedRealmId, period_from: periodFrom, period_to: periodTo },
      })
      setResult(resp.data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error running audit'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const statusCfg = result ? {
    clean:           { icon: CheckCircle2, cls: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200', label: 'No critical issues found' },
    needs_attention: { icon: AlertTriangle, cls: 'text-amber-600', bg: 'bg-amber-50 border-amber-200', label: 'Issues found — review recommended' },
    critical:        { icon: AlertCircle,  cls: 'text-red-600',    bg: 'bg-red-50 border-red-200',    label: 'Critical issues require immediate attention' },
  }[result.status] : null

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Search}
        title={t('page.audit.title')}
        subtitle={companyName ? `${companyName} · Automated QBO health check` : t('page.audit.subtitle')}
        badge="AI"
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Config card */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-surface-900 mb-4">Configure Audit</h2>
          <div className="flex items-end gap-4 flex-wrap">
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">
                <Calendar size={11} className="inline mr-1" />Period From
              </label>
              <input type="date" className="input" value={periodFrom} onChange={e => setPeriodFrom(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">
                <Calendar size={11} className="inline mr-1" />Period To
              </label>
              <input type="date" className="input" value={periodTo} onChange={e => setPeriodTo(e.target.value)} />
            </div>
            <button
              onClick={handleRun}
              disabled={loading || !selectedRealmId}
              className="btn-primary"
            >
              {loading
                ? <><Loader2 size={14} className="animate-spin" /> Running audit…</>
                : <><Search size={14} /> Run Audit</>
              }
            </button>
          </div>

          {!selectedRealmId && (
            <p className="mt-3 text-xs text-amber-600">Select a company from the sidebar first.</p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="card p-4 bg-red-50 border-red-200 flex items-start gap-2">
            <AlertCircle size={14} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="card p-10 flex flex-col items-center gap-3 text-surface-400">
            <Loader2 size={28} className="animate-spin text-primary-500" />
            <p className="text-sm">Fetching QBO data and running diagnostic checks…</p>
            <p className="text-xs text-surface-300">This may take 15–30 seconds</p>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <>
            {/* Status banner */}
            {statusCfg && (
              <div className={cn('card p-4 flex items-center gap-3 border', statusCfg.bg)}>
                <statusCfg.icon size={20} className={statusCfg.cls} />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-surface-900">{statusCfg.label}</p>
                  <p className="text-xs text-surface-500 mt-0.5">
                    {result.total_findings} finding{result.total_findings !== 1 ? 's' : ''} —
                    {result.high.length} high · {result.medium.length} medium · {result.low.length} low
                    · Period: {result.period_from} to {result.period_to}
                  </p>
                </div>
                <div className="flex gap-1.5 shrink-0 text-[10px]">
                  {Object.entries(result.data_fetched).map(([k, v]) => (
                    <span key={k} className={cn('px-1.5 py-0.5 rounded font-medium', v ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600')}>
                      {k.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* No findings */}
            {result.total_findings === 0 && (
              <div className="card p-10 flex flex-col items-center gap-3 text-center">
                <ShieldCheck size={36} className="text-emerald-500" />
                <p className="text-sm font-semibold text-surface-800">Books look clean!</p>
                <p className="text-xs text-surface-400">No issues detected in the reviewed period.</p>
              </div>
            )}

            {/* Findings grouped by severity */}
            <div className="space-y-3">
              <FindingGroup
                title="🔴 High Priority"
                findings={result.high}
                defaultOpen={true}
              />
              <FindingGroup
                title="🟡 Medium Priority"
                findings={result.medium}
                defaultOpen={true}
              />
              <FindingGroup
                title="🔵 Low Priority"
                findings={result.low}
                defaultOpen={false}
              />
            </div>
          </>
        )}

        {/* Empty state */}
        {!result && !loading && !error && (
          <div className="card p-10 flex flex-col items-center gap-3 text-center">
            <Search size={28} className="text-surface-300" />
            <p className="text-sm text-surface-400">Configure the period and click Run Audit to see findings.</p>
            <p className="text-xs text-surface-300">Checks P&L, Balance Sheet, Banking, Chart of Accounts, and Undeposited Funds.</p>
          </div>
        )}
      </div>
    </div>
  )
}
