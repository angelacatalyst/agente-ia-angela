import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import type { QBOBankAccount, QBOLastReconciliationAccount } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Landmark, Loader2, CheckCircle2, AlertCircle, RefreshCw,
  Download, Search, AlertTriangle, DollarSign, ChevronDown, FileText,
} from 'lucide-react'

const QUICK_PROMPTS = [
  'Run a full bank reconciliation review for all accounts',
  'Review undeposited funds and identify stale items',
  'Find all uncleared checks older than 30 days',
  'Reconcile checking account for this month',
  'Identify any duplicate deposits or payments',
]

function formatLastRecReport(accounts: QBOLastReconciliationAccount[], focused: QBOLastReconciliationAccount | null): string {
  const list = focused ? [focused] : accounts
  if (!list.length) return 'No bank or credit card accounts found in QBO.'

  const lines: string[] = [
    '## Last Bank Reconciliation & Statement Status',
    '',
    `Fetched from QuickBooks · ${new Date().toLocaleString()}`,
    '',
  ]

  for (const a of list) {
    lines.push(`### ${a.full_name}`)
    lines.push(`- Type: ${a.account_type}`)
    lines.push(`- Current QBO Balance: ${a.balance_fmt}`)
    if (a.last_reconcile_date) {
      lines.push(`- Last Reconciliation: ${a.last_reconcile_date}`)
      if (a.statement_period_start) {
        lines.push(`- Open Statement Period Start: ${a.statement_period_start}`)
      }
      if (a.next_statement_date) {
        lines.push(`- Suggested Next Statement Date: ${a.next_statement_date}`)
      }
      lines.push(`- Status: Reconciled through ${a.last_reconcile_date}`)
    } else {
      lines.push('- Last Reconciliation: Never reconciled in QBO')
      lines.push('- Status: Needs first reconciliation')
    }
    if (a.report_error) {
      lines.push(`- Reconciliation report: unavailable (${a.report_error})`)
    } else if (a.reconciliation_report) {
      lines.push('- Reconciliation report: loaded from QBO (see statement ending balance in QBO Reconciliation Detail)')
      try {
        const raw = JSON.stringify(a.reconciliation_report, null, 2)
        // Keep report readable but capped
        lines.push('```')
        lines.push(raw.length > 4000 ? raw.slice(0, 4000) + '\n… (truncated)' : raw)
        lines.push('```')
      } catch {
        lines.push('- (Could not serialize reconciliation report)')
      }
    }
    lines.push('')
  }

  lines.push('---')
  lines.push('Tip: Select an account, enter the bank statement ending balance, then click **Run Bank Reconciliation** for a full AI review.')
  return lines.join('\n')
}

export function BankRecPage() {
  const { selectedRealmId, companies } = useAppStore()

  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  const [prompt, setPrompt] = useState('')
  const [statementBalance, setStatementBalance] = useState('')
  const [statementDate, setStatementDate] = useState(
    new Date().toISOString().slice(0, 10)
  )
  const [accountName, setAccountName] = useState('')
  const [result, setResult] = useState<string | null>(null)

  // Bank accounts dropdown
  const [bankAccounts, setBankAccounts] = useState<QBOBankAccount[]>([])
  const [loadingAccounts, setLoadingAccounts] = useState(false)
  const [selectedAccount, setSelectedAccount] = useState<QBOBankAccount | null>(null)
  const [loadingLastRec, setLoadingLastRec] = useState(false)
  const [lastRecError, setLastRecError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedRealmId) return
    setLoadingAccounts(true)
    setBankAccounts([])
    setSelectedAccount(null)
    setAccountName('')
    setLastRecError(null)
    api.qboData.bankAccounts(selectedRealmId)
      .then(d => setBankAccounts(d.accounts))
      .catch(() => setBankAccounts([]))
      .finally(() => setLoadingAccounts(false))
  }, [selectedRealmId])

  // When account is selected from dropdown, pre-fill statement date and show last rec info
  const handleAccountSelect = (fullName: string) => {
    setAccountName(fullName)
    const acct = bankAccounts.find(a => a.full_name === fullName) ?? null
    setSelectedAccount(acct)
    setLastRecError(null)
    if (acct?.next_statement_date) {
      setStatementDate(acct.next_statement_date)
    }
  }

  // Format date for display: YYYY-MM-DD → MM/DD/YYYY
  const fmtDate = (d: string) => {
    if (!d) return '—'
    const [y, m, day] = d.split('-')
    return `${m}/${day}/${y}`
  }

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

  const handleLoadLastReconciliation = async () => {
    if (!selectedRealmId) return
    setLoadingLastRec(true)
    setLastRecError(null)
    try {
      // Refresh dropdown metadata first (last rec dates / next statement)
      const banks = await api.qboData.bankAccounts(selectedRealmId)
      setBankAccounts(banks.accounts)
      const refreshed = accountName
        ? banks.accounts.find(a => a.full_name === accountName) ?? null
        : selectedAccount
          ? banks.accounts.find(a => a.id === selectedAccount.id) ?? null
          : null
      if (refreshed) {
        setSelectedAccount(refreshed)
        if (refreshed.next_statement_date) {
          setStatementDate(refreshed.next_statement_date)
        }
      }

      const data = await api.qboData.lastReconciliation(
        selectedRealmId,
        refreshed?.id || selectedAccount?.id,
      )
      setResult(formatLastRecReport(data.accounts, data.focused))
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setLastRecError(typeof msg === 'string' ? msg : 'Could not load last reconciliation from QBO.')
    } finally {
      setLoadingLastRec(false)
    }
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
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">
                    Account Name
                    {loadingAccounts && <Loader2 size={10} className="inline ml-1.5 animate-spin text-surface-400" />}
                  </label>
                  {bankAccounts.length > 0 ? (
                    <div className="relative">
                      <select
                        className="input appearance-none pr-8"
                        value={accountName}
                        onChange={e => handleAccountSelect(e.target.value)}
                      >
                        <option value="">— Select bank account —</option>
                        {bankAccounts.map(acct => (
                          <option key={acct.id} value={acct.full_name}>
                            {acct.full_name}
                            {acct.account_type === 'Credit Card' ? ' (CC)' : ''}
                            {' · '}
                            {acct.balance_fmt}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={13} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-surface-400" />
                    </div>
                  ) : (
                    <input
                      className="input"
                      placeholder={loadingAccounts ? 'Loading accounts…' : 'e.g. Checking, Savings, Chase Bank'}
                      value={accountName}
                      onChange={e => setAccountName(e.target.value)}
                      disabled={loadingAccounts}
                    />
                  )}
                </div>

                {/* Last reconciliation info */}
                {selectedAccount && (
                  <div className={cn(
                    'rounded-xl border px-4 py-3 text-xs space-y-2',
                    selectedAccount.last_reconcile_date
                      ? 'bg-emerald-50 border-emerald-200'
                      : 'bg-amber-50 border-amber-200',
                  )}>
                    {selectedAccount.last_reconcile_date ? (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-emerald-800">Last Reconciliation</span>
                          <span className="font-bold text-emerald-700">{fmtDate(selectedAccount.last_reconcile_date)}</span>
                        </div>
                        <div className="flex items-center justify-between text-emerald-700">
                          <span>Current QBO Balance</span>
                          <span className="font-semibold">{selectedAccount.balance_fmt}</span>
                        </div>
                        <div className="flex items-center justify-between text-emerald-600">
                          <span>Next period suggested</span>
                          <span className="font-semibold">{fmtDate(selectedAccount.next_statement_date)}</span>
                        </div>
                        <p className="text-[11px] text-emerald-600 pt-1 border-t border-emerald-200">
                          Statement date pre-filled to next period. Enter the ending balance from your bank statement below.
                        </p>
                      </>
                    ) : (
                      <div className="flex items-center gap-2 text-amber-700">
                        <AlertTriangle size={13} className="shrink-0" />
                        <span>This account has never been reconciled in QBO.</span>
                      </div>
                    )}
                  </div>
                )}

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
                  type="button"
                  onClick={handleLoadLastReconciliation}
                  disabled={loadingLastRec || mutation.isPending}
                  className="w-full justify-center inline-flex items-center gap-2 rounded-lg border border-surface-300 bg-white px-4 py-2.5 text-sm font-medium text-surface-800 hover:bg-surface-50 disabled:opacity-50"
                >
                  {loadingLastRec
                    ? <><Loader2 size={14} className="animate-spin" /> Loading last reconciliation…</>
                    : <><FileText size={14} /> Load Last Reconciliation & Statements</>
                  }
                </button>

                <button
                  onClick={() => mutation.mutate()}
                  disabled={mutation.isPending || loadingLastRec || (!prompt && !accountName)}
                  className="btn-primary w-full justify-center"
                >
                  {mutation.isPending
                    ? <><Loader2 size={14} className="animate-spin" /> Running reconciliation…</>
                    : <><Search size={14} /> Run Bank Reconciliation</>
                  }
                </button>

                {(mutation.isError || lastRecError) && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                    <AlertCircle size={14} className="text-red-500" />
                    <p className="text-sm text-red-700">
                      {lastRecError || 'Failed to run reconciliation. Check your QBO connection.'}
                    </p>
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
                {(mutation.isPending || loadingLastRec) ? null : result ? (
                  <button
                    type="button"
                    onClick={handleLoadLastReconciliation}
                    className="ml-auto text-xs text-surface-500 hover:text-primary-600 inline-flex items-center gap-1"
                    title="Refresh last reconciliation"
                  >
                    <RefreshCw size={12} /> Refresh
                  </button>
                ) : null}
              </div>

              {(mutation.isPending || loadingLastRec) && (
                <div className="flex flex-col items-center justify-center py-16 gap-3 text-surface-400">
                  <Loader2 size={28} className="animate-spin text-primary-500" />
                  <p className="text-sm">
                    {loadingLastRec
                      ? 'Fetching last reconciliation and statements from QBO…'
                      : 'Fetching bank data and running reconciliation…'}
                  </p>
                  <p className="text-xs text-surface-300">This may take 15–30 seconds</p>
                </div>
              )}

              {!result && !mutation.isPending && !loadingLastRec && (
                <div className="flex h-64 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                  <div className="text-center">
                    <Landmark size={28} className="mx-auto mb-2 text-surface-300" />
                    <p className="text-sm text-surface-400">Select an action and run reconciliation</p>
                    <p className="text-xs text-surface-300 mt-1">AI will pull live data from QuickBooks</p>
                  </div>
                </div>
              )}

              {result && !mutation.isPending && !loadingLastRec && (
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
