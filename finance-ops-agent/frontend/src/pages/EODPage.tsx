import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  ClipboardList, Loader2, CheckCircle2, Calendar, Download,
  TrendingUp, AlertTriangle, DollarSign,
} from 'lucide-react'

const CHECKLIST = [
  { label: 'All transactions posted and reviewed',       key: 'txn'   },
  { label: 'Bank feeds reconciled',                      key: 'bank'  },
  { label: 'Outstanding invoices reviewed',              key: 'inv'   },
  { label: 'AP aging reviewed',                          key: 'ap'    },
  { label: 'Payroll liabilities verified',               key: 'pay'   },
  { label: 'Grant expenditures within budget',           key: 'grant' },
  { label: 'All journal entries reviewed and approved',  key: 'je'    },
]

export function EODPage() {
  const { t } = useI18n()
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [notes, setNotes]     = useState('')
  const [date, setDate]       = useState(new Date().toISOString().slice(0, 10))
  const [result, setResult]   = useState<string | null>(null)

  const toggle = (key: string) => {
    setChecked(s => {
      const n = new Set(s)
      n.has(key) ? n.delete(key) : n.add(key)
      return n
    })
  }

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Generate EOD report for ${date}. Completed items: ${[...checked].join(', ')}. Additional notes: ${notes || 'None'}. Include summary, accomplishments, issues, and tomorrow's priorities.`,
      module: 'eod_report',
    }),
    onSuccess: (d) => setResult(d.content),
  })

  const completionPct = Math.round((checked.size / CHECKLIST.length) * 100)

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={ClipboardList}
        title={t('page.eod.title')}
        subtitle={t('page.eod.subtitle')}
        badge="AI"
        actions={result && (
          <button className="btn-primary text-[13px]">
            <Download size={14} /> {t('common.export')}
          </button>
        )}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Date + progress */}
        <div className="grid grid-cols-4 gap-4">
          <div className="card p-4 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-50">
              <Calendar size={16} className="text-primary-600" />
            </div>
            <div>
              <p className="text-[11px] text-surface-500">Report Date</p>
              <p className="text-sm font-bold text-surface-900">{date}</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <div className={cn(
              'flex h-9 w-9 items-center justify-center rounded-lg',
              completionPct === 100 ? 'bg-emerald-50' : 'bg-amber-50',
            )}>
              <CheckCircle2 size={16} className={completionPct === 100 ? 'text-emerald-600' : 'text-amber-600'} />
            </div>
            <div>
              <p className="text-[11px] text-surface-500">Checklist</p>
              <p className="text-sm font-bold text-surface-900">{checked.size}/{CHECKLIST.length} done</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50">
              <DollarSign size={16} className="text-blue-600" />
            </div>
            <div>
              <p className="text-[11px] text-surface-500">Today's Activity</p>
              <p className="text-sm font-bold text-surface-900">$47,200</p>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50">
              <AlertTriangle size={16} className="text-amber-600" />
            </div>
            <div>
              <p className="text-[11px] text-surface-500">Open Items</p>
              <p className="text-sm font-bold text-surface-900">2 pending</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-5">
          {/* Checklist */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-surface-900 mb-2">EOD Checklist</h2>

            {/* Progress bar */}
            <div className="mb-4 space-y-1">
              <div className="flex justify-between text-xs text-surface-500">
                <span>Progress</span>
                <span className="font-medium">{completionPct}%</span>
              </div>
              <div className="h-2 rounded-full bg-surface-100 overflow-hidden">
                <div
                  className={cn('h-full rounded-full transition-all', completionPct === 100 ? 'bg-emerald-500' : 'bg-primary-500')}
                  style={{ width: `${completionPct}%` }}
                />
              </div>
            </div>

            <div className="space-y-2 mb-4">
              {CHECKLIST.map(({ label, key }) => (
                <label key={key} className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-all',
                  checked.has(key) ? 'bg-emerald-50 border border-emerald-200' : 'bg-surface-50 border border-surface-100 hover:border-surface-200',
                )}>
                  <input
                    type="checkbox"
                    checked={checked.has(key)}
                    onChange={() => toggle(key)}
                    className="h-4 w-4 rounded border-surface-300 accent-emerald-600 cursor-pointer shrink-0"
                  />
                  <span className={cn('text-sm', checked.has(key) ? 'text-emerald-700 line-through' : 'text-surface-700')}>
                    {label}
                  </span>
                </label>
              ))}
            </div>

            {/* Date picker */}
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Report Date</label>
              <input type="date" className="input" value={date} onChange={e => setDate(e.target.value)} />
            </div>
          </div>

          {/* Notes + generate */}
          <div className="space-y-5">
            <div className="card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-surface-900">Notes & Issues</h2>
              <textarea
                rows={6}
                className="input resize-none"
                placeholder="Any issues encountered, pending items for tomorrow, special notes…"
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="btn-primary w-full justify-center"
              >
                {mutation.isPending
                  ? <><Loader2 size={14} className="animate-spin" /> Generating Report…</>
                  : <><ClipboardList size={14} /> Generate EOD Report</>
                }
              </button>
            </div>

            {result && (
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingUp size={16} className="text-primary-600" />
                  <h2 className="text-sm font-semibold text-surface-900">EOD Report</h2>
                </div>
                <div className="text-sm text-surface-800 whitespace-pre-wrap leading-relaxed overflow-y-auto max-h-64">
                  {result}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
