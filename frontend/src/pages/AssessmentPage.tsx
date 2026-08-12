import { useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAppStore } from '@/stores/appStore'
import { apiClient } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  ClipboardCheck, Loader2, Download, AlertCircle, CheckCircle2,
  Building2, Calendar, FileSpreadsheet,
} from 'lucide-react'

export function AssessmentPage() {
  const { selectedRealmId, companies } = useAppStore()
  const companyName = companies.find(c => c.realm_id === selectedRealmId)?.company_name

  const today = new Date()
  const firstOfYear = `${today.getFullYear()}-01-01`
  const todayStr = today.toISOString().slice(0, 10)

  const [clientName, setClientName] = useState(companyName ?? '')
  const [periodFrom, setPeriodFrom] = useState(firstOfYear)
  const [periodTo, setPeriodTo] = useState(todayStr)
  const [accountingMethod, setAccountingMethod] = useState('Accrual')
  const [qboVersion, setQboVersion] = useState('Plus')
  const [taxOrgType, setTaxOrgType] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const handleRun = async () => {
    if (!selectedRealmId) return
    setLoading(true)
    setError(null)
    setDone(false)

    try {
      const resp = await apiClient.post(
        '/assessment/run',
        null,
        {
          params: {
            realm_id: selectedRealmId,
            period_from: periodFrom,
            period_to: periodTo,
            client_name: clientName || companyName || '',
            accounting_method: accountingMethod,
            qbo_version: qboVersion,
            tax_org_type: taxOrgType,
          },
          responseType: 'blob',
        },
      )

      // Trigger download
      const url = window.URL.createObjectURL(new Blob([resp.data]))
      const link = document.createElement('a')
      link.href = url
      const name = (clientName || companyName || 'Client').replace(/\s+/g, '_')
      link.download = `QBO_Assessment_${name}_${periodTo}.xlsx`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setDone(true)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error generating assessment'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={ClipboardCheck}
        title="QBO Diagnostic Assessment"
        subtitle={companyName
          ? `${companyName} · QuickBooks health check`
          : 'Run a full QuickBooks diagnostic for any connected company'}
        badge="AI"
      />

      <div className="flex-1 overflow-y-auto p-6">
        {!selectedRealmId ? (
          <div className="card p-10 flex flex-col items-center gap-3 text-center max-w-md mx-auto mt-10">
            <Building2 size={36} className="text-surface-300" />
            <p className="text-sm font-medium text-surface-600">No company selected</p>
            <p className="text-xs text-surface-400">
              Select a company from the sidebar to run a diagnostic assessment.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-6 max-w-5xl">
            {/* Config card */}
            <div className="card p-6 space-y-5">
              <div className="flex items-center gap-2">
                <FileSpreadsheet size={16} className="text-primary-600" />
                <h2 className="text-sm font-semibold text-surface-900">Assessment Setup</h2>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Client Name</label>
                <input
                  className="input"
                  placeholder={companyName ?? 'Enter client name'}
                  value={clientName}
                  onChange={e => setClientName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">
                    <Calendar size={11} className="inline mr-1" />Period From
                  </label>
                  <input
                    type="date"
                    className="input"
                    value={periodFrom}
                    onChange={e => setPeriodFrom(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">
                    <Calendar size={11} className="inline mr-1" />Period To
                  </label>
                  <input
                    type="date"
                    className="input"
                    value={periodTo}
                    onChange={e => setPeriodTo(e.target.value)}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Accounting Method</label>
                  <select
                    className="input"
                    value={accountingMethod}
                    onChange={e => setAccountingMethod(e.target.value)}
                  >
                    <option value="Accrual">Accrual</option>
                    <option value="Cash">Cash</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">QBO Version</label>
                  <select
                    className="input"
                    value={qboVersion}
                    onChange={e => setQboVersion(e.target.value)}
                  >
                    <option value="Simple Start">Simple Start</option>
                    <option value="Essentials">Essentials</option>
                    <option value="Plus">Plus</option>
                    <option value="Advanced">Advanced</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Tax Organization Type</label>
                <select
                  className="input"
                  value={taxOrgType}
                  onChange={e => setTaxOrgType(e.target.value)}
                >
                  <option value="">Select type…</option>
                  <option value="S-Corp (Form 1120-S)">S-Corp (Form 1120-S)</option>
                  <option value="Partnership (Form 1065)">Partnership (Form 1065)</option>
                  <option value="Sole Proprietor (Schedule C)">Sole Proprietor (Schedule C)</option>
                  <option value="C-Corp (Form 1120)">C-Corp (Form 1120)</option>
                  <option value="Nonprofit (Form 990)">Nonprofit (Form 990)</option>
                  <option value="LLC (Disregarded Entity)">LLC (Disregarded Entity)</option>
                </select>
              </div>

              <button
                onClick={handleRun}
                disabled={loading}
                className="btn-primary w-full justify-center mt-2"
              >
                {loading
                  ? <><Loader2 size={14} className="animate-spin" /> Running diagnostic…</>
                  : <><Download size={14} /> Generate Assessment (.xlsx)</>
                }
              </button>

              {error && (
                <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2.5">
                  <AlertCircle size={14} className="text-red-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-700">{error}</p>
                </div>
              )}

              {done && (
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2.5">
                  <CheckCircle2 size={14} className="text-emerald-600 shrink-0" />
                  <p className="text-xs text-emerald-700 font-medium">
                    Assessment downloaded successfully!
                  </p>
                </div>
              )}
            </div>

            {/* Info card */}
            <div className="space-y-4">
              <div className="card p-5">
                <h3 className="text-xs font-semibold text-surface-700 uppercase tracking-wide mb-3">
                  What the assessment covers
                </h3>
                <ul className="space-y-2.5 text-xs text-surface-600">
                  {[
                    { label: 'Banking', desc: 'Reconciliation status, uncleared items, bank feed health' },
                    { label: 'Profit & Loss', desc: 'Uncategorized income/expenses, unusual balances, miscategorized accounts' },
                    { label: 'Balance Sheet', desc: 'AR/AP balances, Opening Balance Equity, payroll liabilities, equity recording' },
                    { label: 'AR & AP Aging', desc: 'Items over 90 days, negative balances, unapplied credits' },
                    { label: 'Chart of Accounts', desc: 'Account count, types, numbering structure' },
                    { label: 'Payroll', desc: 'Payroll mapping, liabilities, expense recording' },
                    { label: 'Sales Tax', desc: 'Sales tax center setup and remittance' },
                    { label: 'Final Report', desc: 'Summary of all findings and recommendations' },
                  ].map(({ label, desc }) => (
                    <li key={label} className="flex items-start gap-2">
                      <CheckCircle2 size={12} className="text-primary-500 shrink-0 mt-0.5" />
                      <span><span className="font-semibold text-surface-800">{label}</span> — {desc}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="card p-5 bg-blue-50 border-blue-100">
                <p className="text-xs font-semibold text-blue-800 mb-1">Output</p>
                <p className="text-xs text-blue-700">
                  The agent pulls live data from QuickBooks, runs all diagnostic checks, and delivers
                  your completed <strong>TPC QuickBooks Diagnostic Template</strong> as a ready-to-send .xlsx file.
                  Each section is pre-filled with findings, comments, and amounts pulled directly from QBO.
                </p>
              </div>

              <div className="card p-5 bg-amber-50 border-amber-100">
                <p className="text-xs font-semibold text-amber-800 mb-1">Processing time</p>
                <p className="text-xs text-amber-700">
                  The assessment fetches multiple QBO reports simultaneously. Expect 15–45 seconds
                  depending on the size of the company's data.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
