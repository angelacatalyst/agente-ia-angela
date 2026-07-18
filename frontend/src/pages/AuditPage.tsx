import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Search, AlertTriangle, AlertCircle, Loader2, Download,
} from 'lucide-react'

const RISK_PRESETS = [
  'Full accounting audit',
  'Uncategorized transactions only',
  'Duplicate payment detection',
  'Sales tax compliance review',
  'Payroll liability reconciliation',
]

export function AuditPage() {
  const { t } = useI18n()
  const { selectedRealmId, companies } = useAppStore()
  const [scope, setScope] = useState('')
  const [realmId, setRealmId] = useState('')
  const [result, setResult] = useState<string | null>(null)

  // Auto-populate from selected company
  useEffect(() => {
    if (selectedRealmId) setRealmId(selectedRealmId)
  }, [selectedRealmId])

  const companyName = companies.find(c => c.realm_id === realmId)?.company_name

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Run a QBO audit. Scope: ${scope || 'Full audit'}.`,
      module: 'qbo_auditor',
      qbo_realm_id: realmId || undefined,
    }),
    onSuccess: (data) => setResult(data.content),
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Search}
        title={t('page.audit.title')}
        subtitle={t('page.audit.subtitle')}
        badge="AI"
        actions={
          <button className="btn-primary text-[13px]">
            <Download size={14} /> {t('common.export')}
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Config card */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-surface-900 mb-4">Configure Audit</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">
                Company
                {companyName && <span className="ml-2 text-primary-600 font-normal">{companyName}</span>}
              </label>
              <input
                className="input font-mono text-xs"
                placeholder="e.g. 9341454010854556"
                value={realmId}
                onChange={e => setRealmId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Audit Scope</label>
              <select
                className="input"
                value={scope}
                onChange={e => setScope(e.target.value)}
              >
                <option value="">Full audit (recommended)</option>
                {RISK_PRESETS.slice(1).map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
          </div>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="btn-primary"
          >
            {mutation.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Running…</>
              : <><Search size={14} /> Run Audit</>
            }
          </button>
        </div>

        {/* Findings */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle size={16} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-surface-900">Audit Findings</h2>
          </div>

          {mutation.isPending && (
            <div className="flex items-center justify-center py-12 gap-2 text-surface-400">
              <Loader2 size={18} className="animate-spin" />
              <span className="text-sm">Running AI audit on your QBO data…</span>
            </div>
          )}

          {!result && !mutation.isPending && (
            <div className="flex h-40 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
              <div className="text-center">
                <Search size={24} className="mx-auto mb-2 text-surface-300" />
                <p className="text-sm text-surface-400">Configure and run an audit to see findings here.</p>
              </div>
            </div>
          )}

          {result && (
            <div className="p-4 rounded-xl bg-primary-50 border border-primary-200 text-sm text-surface-800 whitespace-pre-wrap leading-relaxed">
              {result}
            </div>
          )}

          {mutation.isError && (
            <div className="mt-3 p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
              <AlertCircle size={14} className="text-red-500" />
              <p className="text-sm text-red-700">Failed to run audit. Check your API key and QBO connection.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
