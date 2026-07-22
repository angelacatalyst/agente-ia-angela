import { useState, useCallback, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Landmark, Loader2, CheckCircle2, AlertCircle, RefreshCw,
  Download, Search, AlertTriangle, DollarSign,
} from 'lucide-react'

const QUICK_PROMPTS = [
  'Run a full bank reconciliation review for all accounts',
  'Review undeposited funds and identify stale items',
  'Find all uncleared checks older than 30 days',
  'Reconcile checking account for this month',
  'Identify any duplicate deposits or payments',
]

export function BankRecPage() {
  const { t } = useI18n()
  const { selectedRealmId, companies } = useAppStore()

  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  const [prompt, setPrompt] = useState('')
  const [statementBalance, setStatementBalance] = useState('')
  const [statementDate, setStatementDate] = useState(
    new Date().toISOString().slice(0, 10)
  )
  const [accountName, setAccountName] = useState('')
  const [result, setResult] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => {
      const message = accountName && statementBalance
        ? `Reconcile bank account "${accountName}" as of ${statementDate}. Bank statement ending balance: $${statementBalance}. Perform complete reconciliation.`
        : prompt || 'Run a complete bank reconciliation review for all accounts. List all uncleared items, any stale undeposited funds, and reconciliation status for each account.'

      return api.chat({
        message,
        module: 'bank_reconciliation',
        qbo_realm_id: selectedRealmId ?? undefined,
      })
    },
    onSuccess: (d) => setResult(d.content),
  })

  const handleQuickPrompt = (p: string) => {
    setPrompt(p)
    setAccountName('')
    setStatementBalance('')
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Landmark}
        title="Bank Reconciliation"
        subtitle={companyName ? `${companyName} · AI-powered bank rec` : 'Reconcile bank and credit card accounts'}
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
            <Landmark size={32} className="text-surface-300" />
            <p className="text-sm font-medium text-surface-600">No company selected</p>
            <p className="text-xs text-surface-400">Select a company from the sidebar to run bank reconciliation.</p>
          </div>
        )}

        {selectedRealmId && (
          <div className="grid grid-cols-2 gap-5">
            {/* Config panel */}
            <div className="space-y-5">
              {/* Quick prompts */}
              <div className="card p-5">
                <h2 className="text-sm font-semibold text-surface-900 mb-3">Quick Actions</h2>
                <div className="space-y-2">
                  {QUICK_PROMPTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => handleQuickPrompt(p)}
                      className={cn(
                        'w-full text-left rounded-lg border px-3 py-2.5 text-xs transition-all hover:border-primary-300 hover:bg-primary-50',
                        prompt === p
                          ? 'border-primary-400 bg-primary-50 text-primary-700 font-medium'
                          : 'border-surface-200 text-surface-700',
                      )}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              {/* Manual account rec */}
              <div className="card p-5 space-y-4">
                <h2 className="text-sm font-semibold text-surface-900">Reconcile Specific Account</h2>
                <p className="text-xs text-surface-400">
                  Enter your bank statement details to run a precise reconciliation.
                </p>

                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Account Name</label>
                  <input
                    className="input"
                    placeholder="e.g. Checking, Savings, Chase Bank"
                    value={accountName}
                    onChange={e => setAccountName(e.target.value)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-surface-600 mb-1.5">Statement Date</label>
                    <input
                      type="date"
                      className="input"
                      value={statementDate}
                      onChange={e => setStatementDate(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-surface-600 mb-1.5">Statement Balance</label>
                    <div className="relative">
                      <DollarSign size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                      <input
                        className="input pl-7"
                        placeholder="0.00"
                        value={statementBalance}
                        onChange={e => setStatementBalance(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                {!accountName && !prompt && (
                  <div>
                    <label className="block text-xs font-medium text-surface-600 mb-1.5">Or Custom Request</label>
                    <textarea
                      rows={3}
                      className="input resize-none"
                      placeholder="Describe what you need to reconcile…"
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                    />
                  </div>
                )}

                <button
                  onClick={() => mutation.mutate()}
                  disabled={mutation.isPending || (!prompt && !accountName)}
                  className="btn-primary w-full justify-center"
                >
                  {mutation.isPending
                    ? <><Loader2 size={14} className="animate-spin" /> Running reconciliation…</>
                    : <><Search size={14} /> Run Bank Reconciliation</>
                  }
                </button>

                {mutation.isError && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                    <AlertCircle size={14} className="text-red-500" />
                    <p className="text-sm text-red-700">Failed to run reconciliation. Check your QBO connection.</p>
                  </div>
                )}
              </div>

              {/* Info card */}
              <div className="card p-5 bg-blue-50 border-blue-100">
                <div className="flex items-start gap-3">
                  <AlertTriangle size={16} className="text-blue-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs font-semibold text-blue-800 mb-1">What the AI checks</p>
                    <ul className="text-xs text-blue-700 space-y-1">
                      <li>• Outstanding checks &amp; uncleared payments</li>
                      <li>• Deposits in transit</li>
                      <li>• Undeposited Funds account (stale items)</li>
                      <li>• Bank charges not in QBO</li>
                      <li>• Reconciling differences</li>
                      <li>• Accounts overdue for reconciliation</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Results panel */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={16} className="text-primary-600" />
                <h2 className="text-sm font-semibold text-surface-900">Reconciliation Report</h2>
              </div>

              {mutation.isPending && (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-surface-400">
                  <Loader2 size={28} className="animate-spin text-primary-500" />
                  <p className="text-sm">Fetching bank data and running reconciliation…</p>
                  <p className="text-xs text-surface-300">This may take 15–30 seconds</p>
                </div>
              )}

              {!result && !mutation.isPending && (
                <div className="flex h-64 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                  <div className="text-center">
                    <Landmark size={28} className="mx-auto mb-2 text-surface-300" />
                    <p className="text-sm text-surface-400">Select an action and run reconciliation</p>
                    <p className="text-xs text-surface-300 mt-1">AI will pull live data from QuickBooks</p>
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
