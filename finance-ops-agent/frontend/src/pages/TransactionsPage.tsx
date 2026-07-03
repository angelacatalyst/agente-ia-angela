import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Tag, UploadCloud, FileText, Loader2, CheckCircle2,
  ChevronDown, Download, X,
} from 'lucide-react'

const ENTITY_TYPES = [
  { value: 'nonprofit',  label: 'Nonprofit (GAAP + Fund Accounting)' },
  { value: 'forprofit',  label: 'For-Profit (GAAP Standard)' },
  { value: 'government', label: 'Government (Modified Accrual)' },
]

interface TxRow {
  date: string; payee: string; amount: string; type: string; coded: string; confidence: number
}

const SAMPLE: TxRow[] = [
  { date: '2024-04-01', payee: 'Amazon Web Services', amount: '-$420.00', type: 'Expense', coded: '6100 · Software Subscriptions', confidence: 97 },
  { date: '2024-04-02', payee: 'ACH Deposit — GRANT-2024', amount: '+$15,000', type: 'Income', coded: '4200 · Grant Revenue', confidence: 94 },
  { date: '2024-04-03', payee: 'Office Depot #1138', amount: '-$89.50', type: 'Expense', coded: '6300 · Office Supplies', confidence: 88 },
]

export function TransactionsPage() {
  const { t } = useI18n()
  const [entityType, setEntityType] = useState('nonprofit')
  const [manualText, setManualText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<TxRow[] | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const data = await api.chat({
        message: `Code these transactions for ${entityType}. ${manualText || (file ? `File: ${file.name}` : '')}`,
        module: 'transaction_coder',
      })
      return data
    },
    onSuccess: () => setResult(SAMPLE),
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
        actions={result && (
          <button className="btn-primary text-[13px]">
            <Download size={14} /> {t('common.export')}
          </button>
        )}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
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

            {/* Drop zone */}
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
                    <button
                      onClick={e => { e.stopPropagation(); setFile(null) }}
                      className="text-surface-400 hover:text-red-500 transition-colors"
                    >
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
              <h2 className="text-sm font-semibold text-surface-900">Coded Results</h2>
              {result && (
                <span className="badge bg-primary-50 text-primary-700 ring-1 ring-primary-200 ml-auto">
                  {result.length} transactions
                </span>
              )}
            </div>

            {!result && (
              <div className="flex h-48 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                <div className="text-center">
                  <Tag size={24} className="mx-auto mb-2 text-surface-300" />
                  <p className="text-sm text-surface-400">Coded transactions will appear here</p>
                </div>
              </div>
            )}

            {result && (
              <div className="overflow-auto rounded-xl border border-surface-200">
                <table className="min-w-full text-xs">
                  <thead className="bg-surface-50 border-b border-surface-200">
                    <tr>
                      {['Date', 'Payee', 'Amount', 'Account', 'Conf.'].map(h => (
                        <th key={h} className="px-3 py-2 text-left font-semibold text-surface-600">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-100">
                    {result.map((row, i) => (
                      <tr key={i} className="hover:bg-surface-50 transition-colors">
                        <td className="px-3 py-2 text-surface-600 font-mono">{row.date}</td>
                        <td className="px-3 py-2 text-surface-800 font-medium">{row.payee}</td>
                        <td className={cn('px-3 py-2 font-semibold font-mono', row.amount.startsWith('+') ? 'text-emerald-600' : 'text-surface-800')}>
                          {row.amount}
                        </td>
                        <td className="px-3 py-2 text-surface-700">{row.coded}</td>
                        <td className="px-3 py-2">
                          <span className={cn('badge', row.confidence > 90 ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-amber-50 text-amber-700 ring-1 ring-amber-200')}>
                            {row.confidence}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
