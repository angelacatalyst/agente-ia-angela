import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Search, AlertTriangle, AlertCircle, CheckCircle2, Loader2,
  ChevronDown, ChevronUp, Download,
} from 'lucide-react'

const RISK_PRESETS = [
  'Full accounting audit',
  'Uncategorized transactions only',
  'Duplicate payment detection',
  'Sales tax compliance review',
  'Payroll liability reconciliation',
]

interface AuditItem {
  risk: 'high' | 'medium' | 'low'
  category: string
  description: string
  amount?: string
  recommendation: string
}

const riskBadge: Record<string, string> = {
  high:   'bg-red-50 text-red-700 ring-1 ring-red-200',
  medium: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  low:    'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
}

export function AuditPage() {
  const { t } = useI18n()
  const [scope, setScope] = useState('')
  const [realmId, setRealmId] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [result, setResult] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Run a QBO audit. Scope: ${scope || 'Full audit'}. Realm: ${realmId || 'N/A'}`,
      module: 'qbo_auditor',
    }),
    onSuccess: (data) => setResult(data.content),
  })

  const mockItems: AuditItem[] = [
    { risk: 'high',   category: 'Uncategorized',  description: '47 transactions uncategorized in Q1', amount: '$23,400', recommendation: 'Review and code all uncategorized items before month-end close.' },
    { risk: 'medium', category: 'Bank Rec',        description: 'March bank reconciliation not completed', amount: undefined,  recommendation: 'Complete reconciliation to ensure accurate cash position reporting.' },
    { risk: 'low',    category: 'Vendor 1099',     description: '3 vendors missing TINs for 1099 reporting', amount: '$8,200',  recommendation: 'Collect W-9 from affected vendors before filing deadline.' },
  ]

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
              <label className="block text-xs font-medium text-surface-600 mb-1.5">QBO Realm ID</label>
              <input
                className="input"
                placeholder="e.g. 123456789"
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
            <div className="ml-auto flex items-center gap-1.5">
              <span className="badge bg-red-50 text-red-600 ring-1 ring-red-200">1 High</span>
              <span className="badge bg-amber-50 text-amber-600 ring-1 ring-amber-200">1 Medium</span>
              <span className="badge bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200">1 Low</span>
            </div>
          </div>

          {result && (
            <div className="mb-4 p-4 rounded-xl bg-primary-50 border border-primary-200 text-sm text-surface-800 whitespace-pre-wrap">
              {result}
            </div>
          )}

          <div className="space-y-2">
            {mockItems.map((item, i) => (
              <div key={i} className="rounded-xl border border-surface-200 overflow-hidden">
                <button
                  className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-50 transition-colors"
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  <span className={`badge ${riskBadge[item.risk]} capitalize`}>{item.risk}</span>
                  <span className="text-sm font-medium text-surface-800 flex-1">{item.description}</span>
                  {item.amount && (
                    <span className="text-sm font-semibold text-surface-600">{item.amount}</span>
                  )}
                  {expanded === i
                    ? <ChevronUp size={14} className="text-surface-400 shrink-0" />
                    : <ChevronDown size={14} className="text-surface-400 shrink-0" />
                  }
                </button>
                {expanded === i && (
                  <div className="border-t border-surface-100 px-4 py-3 bg-surface-50 animate-fade-in">
                    <div className="flex items-start gap-2">
                      <CheckCircle2 size={14} className="text-primary-500 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-[11px] font-semibold text-surface-500 uppercase tracking-wider mb-1">Recommendation</p>
                        <p className="text-sm text-surface-700">{item.recommendation}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

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
