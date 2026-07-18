import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api, type QBOTransaction } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Tag, UploadCloud, FileText, Loader2, CheckCircle2,
  ChevronDown, Download, X, RefreshCw, AlertCircle,
} from 'lucide-react'

const ENTITY_TYPES = [
  { value: 'nonprofit',  label: 'Nonprofit (GAAP + Fund Accounting)' },
  { value: 'forprofit',  label: 'For-Profit (GAAP Standard)' },
  { value: 'government', label: 'Government (Modified Accrual)' },
]

interface TxRow {
  date: string; payee: string; amount: string; type: string; coded: string; confidence: number
}

export function TransactionsPage() {
  const { t } = useI18n()
  const { selectedRealmId } = useAppStore()

  const [tab, setTab] = useState<'live' | 'code'>('live')
  const [entityType, setEntityType] = useState('nonprofit')
  const [manualText, setManualText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<TxRow[] | null>(null)

  // Live QBO transactions
  const [qboTxns, setQboTxns] = useState<QBOTransaction[]>([])
  const [loadingTxns, setLoadingTxns] = useState(false)
  const [txnError, setTxnError] = useState<string | null>(null)

  const fetchTxns = useCallback(async () => {
    if (!selectedRealmId) return
    setLoadingTxns(true)
    setTxnError(null)
    try {
      const data = await api.qboData.transactions(selectedRealmId)
      setQboTxns(data.transactions)
    } catch (e: any) {
      setTxnError(e?.response?.data?.detail || 'Failed to load transactions')
    } finally {
      setLoadingTxns(false)
    }
  }, [selectedRealmId])

  useEffect(() => {
    if (tab === 'live') fetchTxns()
  }, [fetchTxns, tab])

  const mutation = useMutation({
    mutationFn: async () => {
      const data = await api.chat({
        message: `Code these transactions for ${entityType}. ${manualText || (file ? `File: ${file.name}` : '')}`,
        module: 'transaction_coder',
        qbo_realm_id: selectedRealmId ?? undefined,
      })
      return data
    },
    onSuccess: () => setResult([]),
  })

  const onDrop = useCallback((files: File[]) => {
    if (files[0]) setFile(files[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
    maxFiles: 1,
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Tag}
        title={t('page.transactions.title')}
        subtitle={t('page.transactions.subtitle')}
        badge="AI"
        actions={
          <>
            {tab === 'live' && (
              <button onClick={fetchTxns} disabled={loadingTxns} className="btn-ghost text-[13px] gap-1.5">
                <RefreshCw size={14} className={loadingTxns ? 'animate-spin' : ''} />
                Refresh
              </button>
            )}
            <button className="btn-primary text-[13px]">
              <Download size={14} /> {t('common.export')}
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Tabs */}
        <div className="flex gap-1 rounded-xl bg-surface-100 p-1 w-fit">
          <button
            onClick={() => setTab('live')}
            className={cn(
              'rounded-lg px-4 py-1.5 text-xs font-medium transition-all',
              tab === 'live' ? 'bg-white shadow-sm text-surface-900' : 'text-surface-500 hover:text-surface-700',
            )}
          >
            Live QBO Data
          </button>
          <button
            onClick={() => setTab('code')}
            className={cn(
              'rounded-lg px-4 py-1.5 text-xs font-medium transition-all',
              tab === 'code' ? 'bg-white shadow-sm text-surface-900' : 'text-surface-500 hover:text-surface-700',
            )}
          >
            AI Transaction Coder
          </button>
        </div>

        {/* Live QBO tab */}
        {tab === 'live' && (
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <h2 className="text-sm font-semibold text-surface-900">
                Invoices &amp; Bills
                {qboTxns.length > 0 && (
                  <span className="ml-2 text-[11px] font-normal text-surface-400">({qboTxns.length} records from QBO)</span>
                )}
              </h2>
            </div>

            {!selectedRealmId && (
              <div className="flex h-48 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                <p className="text-sm text-surface-400">Select a company from the sidebar to view transactions.</p>
              </div>
            )}

            {loadingTxns && (
              <div className="flex items-center justify-center py-12 gap-2 text-surface-400">
                <Loader2 size={18} className="animate-spin" />
                <span className="text-sm">Loading from QuickBooks…</span>
              </div>
            )}

            {txnError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-500" />
                <p className="text-sm text-red-700">{txnError}</p>
              </div>
            )}

            {!loadingTxns && qboTxns.length === 0 && selectedRealmId && !txnError && (
              <div className="flex h-48 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                <p className="text-sm text-surface-400">No transactions found in QuickBooks.</p>
              </div>
            )}

            {qboTxns.length > 0 && (
              <div className="overflow-auto rounded-xl border border-surface-200">
                <table className="min-w-full text-xs">
                  <thead className="bg-surface-50 border-b border-surface-200">
                    <tr>
                      {['Date', 'Payee / Customer', 'Amount', 'Type', 'Status', 'Doc #'].map(h => (
                        <th key={h} className="px-3 py-2 text-left font-semibold text-surface-600">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-100">
                    {qboTxns.map((row, i) => (
                      <tr key={i} className="hover:bg-surface-50 transition-colors">
                        <td className="px-3 py-2 text-surface-600 font-mono">{row.date}</td>
                        <td className="px-3 py-2 text-surface-800 font-medium">{row.payee}</td>
                        <td className={cn('px-3 py-2 font-semibold font-mono', row.amount.startsWith('+') ? 'text-emerald-600' : 'text-surface-800')}>
                          {row.amount}
                        </td>
                        <td className="px-3 py-2 text-surface-600">{row.type}</td>
                        <td className="px-3 py-2">
                          <span className={cn('badge', {
                            'bg-amber-50 text-amber-700 ring-1 ring-amber-200': row.status === 'Open' || row.status === 'Unpaid',
                            'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200': row.status === 'Paid',
                          })}>
                            {row.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-surface-500">#{row.doc_number}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* AI Coder tab */}
        {tab === 'code' && (
          <div className="grid grid-cols-2 gap-5">
            {/* Config */}
            <div className="card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-surface-900">Transaction Settings</h2>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Entity Type</label>
                <div className="relative">
                  <select
                    className="input appearance-none pr-8"
                    value={entityType}
                    onChange={e => setEntityType(e.target.value)}
                  >
                    {ENTITY_TYPES.map(e => (
                      <option key={e.value} value={e.value}>{e.label}</option>
                    ))}
                  </select>
                  <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Upload File (CSV / Excel)</label>
                <div
                  {...getRootProps()}
                  className={cn(
                    'cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-all',
                    isDragActive
                      ? 'border-primary-400 bg-primary-50'
                      : 'border-surface-200 hover:border-primary-300 hover:bg-primary-50/50',
                  )}
                >
                  <input {...getInputProps()} />
                  {file ? (
                    <div className="flex items-center justify-center gap-2">
                      <FileText size={16} className="text-primary-500" />
                      <span className="text-sm font-medium text-surface-700">{file.name}</span>
                      <button onClick={e => { e.stopPropagation(); setFile(null) }} className="text-surface-400 hover:text-red-500 transition-colors">
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <UploadCloud size={24} className="mx-auto mb-2 text-surface-300" />
                      <p className="text-sm text-surface-500">Drop CSV or Excel file here</p>
                      <p className="text-xs text-surface-400 mt-1">or click to browse</p>
                    </>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Or Paste Transactions</label>
                <textarea
                  rows={4}
                  className="input resize-none font-mono text-xs"
                  placeholder={'Date, Payee, Amount\n2024-04-01, Amazon, -420.00\n...'}
                  value={manualText}
                  onChange={e => setManualText(e.target.value)}
                />
              </div>

              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending || (!file && !manualText)}
                className="btn-primary w-full justify-center"
              >
                {mutation.isPending
                  ? <><Loader2 size={14} className="animate-spin" /> Coding…</>
                  : <><Tag size={14} /> Code Transactions</>
                }
              </button>
            </div>

            {/* Results */}
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 size={16} className="text-primary-600" />
                <h2 className="text-sm font-semibold text-surface-900">AI Response</h2>
              </div>

              {!result && !mutation.data && (
                <div className="flex h-48 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                  <div className="text-center">
                    <Tag size={24} className="mx-auto mb-2 text-surface-300" />
                    <p className="text-sm text-surface-400">Upload or paste transactions to code them</p>
                  </div>
                </div>
              )}

              {mutation.data && (
                <div className="text-sm text-surface-800 whitespace-pre-wrap leading-relaxed">
                  {mutation.data.content}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
