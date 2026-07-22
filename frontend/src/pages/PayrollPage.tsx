import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Users, Loader2, CheckCircle2, AlertCircle, Download,
  Search, Calendar, DollarSign, BarChart2,
} from 'lucide-react'

const QUICK_PROMPTS = [
  { label: 'Full Payroll Analysis', desc: 'Analyze payroll for the current period including all allocations and tax liabilities' },
  { label: 'Grant Allocation Check', desc: 'Verify payroll allocations match approved FTE across all active grants' },
  { label: 'Payroll Desglose', desc: 'Provide a complete payroll breakdown: gross wages, taxes, benefits, and net pay by employee' },
  { label: 'Payroll Liability Review', desc: 'Check if all payroll tax and benefit liabilities are cleared in QBO' },
  { label: 'Functional Expense Split', desc: 'Analyze payroll split across Program, Management & General, and Fundraising for Form 990' },
]

export function PayrollPage() {
  const { selectedRealmId, companies } = useAppStore()
  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  const [selectedPrompt, setSelectedPrompt] = useState(0)
  const [startDate, setStartDate] = useState(() => {
    const d = new Date()
    d.setDate(1)
    return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10))
  const [customPrompt, setCustomPrompt] = useState('')
  const [result, setResult] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => {
      const base = QUICK_PROMPTS[selectedPrompt].desc
      const message = customPrompt || `${base}. Period: ${startDate} to ${endDate}.`
      return api.chat({
        message,
        module: 'payroll_allocation',
        qbo_realm_id: selectedRealmId ?? undefined,
      })
    },
    onSuccess: (d) => setResult(d.content),
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Users}
        title="Payroll Allocation"
        subtitle={companyName ? `${companyName} · Payroll analysis & compliance` : 'Analyze payroll, allocations, and compliance'}
        badge="AI"
        actions={
          result ? (
            <button className="btn-primary text-[13px]">
              <Download size={14} /> Export Report
            </button>
          ) : undefined
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {!selectedRealmId && (
          <div className="card p-8 flex flex-col items-center gap-3 text-center">
            <Users size={32} className="text-surface-300" />
            <p className="text-sm font-medium text-surface-600">No company selected</p>
            <p className="text-xs text-surface-400">Select a company from the sidebar to analyze payroll.</p>
          </div>
        )}

        {selectedRealmId && (
          <div className="grid grid-cols-2 gap-5">
            {/* Config */}
            <div className="space-y-5">
              {/* Analysis type */}
              <div className="card p-5">
                <h2 className="text-sm font-semibold text-surface-900 mb-3">Analysis Type</h2>
                <div className="space-y-2">
                  {QUICK_PROMPTS.map((p, i) => (
                    <button
                      key={i}
                      onClick={() => { setSelectedPrompt(i); setCustomPrompt('') }}
                      className={cn(
                        'w-full text-left rounded-xl border p-3 transition-all',
                        selectedPrompt === i && !customPrompt
                          ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                          : 'border-surface-200 hover:border-surface-300 hover:bg-surface-50',
                      )}
                    >
                      <p className={cn('text-xs font-semibold mb-0.5', selectedPrompt === i && !customPrompt ? 'text-primary-700' : 'text-surface-800')}>
                        {p.label}
                      </p>
                      <p className="text-[11px] text-surface-400 leading-relaxed">{p.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Period selector */}
              <div className="card p-5 space-y-4">
                <h2 className="text-sm font-semibold text-surface-900">Payroll Period</h2>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-surface-600 mb-1.5">Start Date</label>
                    <div className="relative">
                      <Calendar size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                      <input
                        type="date"
                        className="input pl-8"
                        value={startDate}
                        onChange={e => setStartDate(e.target.value)}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-surface-600 mb-1.5">End Date</label>
                    <div className="relative">
                      <Calendar size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                      <input
                        type="date"
                        className="input pl-8"
                        value={endDate}
                        onChange={e => setEndDate(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">
                    Custom Request (optional)
                  </label>
                  <textarea
                    rows={3}
                    className="input resize-none"
                    placeholder="e.g. Analyze payroll allocation for the Community Health grant for John Smith..."
                    value={customPrompt}
                    onChange={e => setCustomPrompt(e.target.value)}
                  />
                </div>

                <button
                  onClick={() => mutation.mutate()}
                  disabled={mutation.isPending}
                  className="btn-primary w-full justify-center"
                >
                  {mutation.isPending
                    ? <><Loader2 size={14} className="animate-spin" /> Analyzing payroll…</>
                    : <><BarChart2 size={14} /> Analyze Payroll</>
                  }
                </button>

                {mutation.isError && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                    <AlertCircle size={14} className="text-red-500" />
                    <p className="text-sm text-red-700">Failed to analyze payroll. Check QBO connection.</p>
                  </div>
                )}
              </div>

              {/* What AI checks */}
              <div className="card p-5 bg-emerald-50 border-emerald-100">
                <div className="flex items-start gap-3">
                  <CheckCircle2 size={16} className="text-emerald-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-emerald-800 mb-1">What the AI analyzes</p>
                    <ul className="text-xs text-emerald-700 space-y-1">
                      <li>• Gross wages, taxes, benefits, net pay</li>
                      <li>• Grant/program allocation vs approved FTE</li>
                      <li>• Payroll liability clearance (taxes payable)</li>
                      <li>• Functional expense split (Program/M&G/Fundraising)</li>
                      <li>• Time sheet support for grant-funded employees</li>
                      <li>• 2 CFR 200 compliance for federal grants</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Results */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <Users size={16} className="text-primary-600" />
                <h2 className="text-sm font-semibold text-surface-900">Payroll Analysis Report</h2>
              </div>

              {mutation.isPending && (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-surface-400">
                  <Loader2 size={28} className="animate-spin text-primary-500" />
                  <p className="text-sm">Fetching payroll data from QuickBooks…</p>
                  <p className="text-xs text-surface-300">This may take 20–40 seconds</p>
                </div>
              )}

              {!result && !mutation.isPending && (
                <div className="flex h-64 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                  <div className="text-center">
                    <Users size={28} className="mx-auto mb-2 text-surface-300" />
                    <p className="text-sm text-surface-400">Select analysis type and click Analyze Payroll</p>
                    <p className="text-xs text-surface-300 mt-1">AI fetches live payroll data from QuickBooks</p>
                  </div>
                </div>
              )}

              {result && (
                <div className="text-sm text-surface-800 whitespace-pre-wrap leading-relaxed max-h-[600px] overflow-y-auto">
                  {result}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
