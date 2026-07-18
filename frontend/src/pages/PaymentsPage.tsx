import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api, type QBOBill } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  CreditCard, UploadCloud, FileText, Loader2, Plus,
  CheckCircle2, Clock, X, Download, RefreshCw, AlertCircle,
} from 'lucide-react'

const statusStyle: Record<string, string> = {
  pending:  'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  overdue:  'bg-red-50 text-red-700 ring-1 ring-red-200',
  approved: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
}

export function PaymentsPage() {
  const { t } = useI18n()
  const { selectedRealmId } = useAppStore()

  const [bills, setBills] = useState<QBOBill[]>([])
  const [loadingBills, setLoadingBills] = useState(false)
  const [billsError, setBillsError] = useState<string | null>(null)

  const [vendor, setVendor] = useState('')
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<string | null>(null)

  const fetchBills = useCallback(async () => {
    if (!selectedRealmId) return
    setLoadingBills(true)
    setBillsError(null)
    try {
      const data = await api.qboData.bills(selectedRealmId, true)
      setBills(data.bills)
    } catch (e: any) {
      setBillsError(e?.response?.data?.detail || 'Failed to load bills')
    } finally {
      setLoadingBills(false)
    }
  }, [selectedRealmId])

  useEffect(() => { fetchBills() }, [fetchBills])

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Generate payment request: Vendor=${vendor}, Amount=${amount}, Category=${category}, Notes=${notes}`,
      module: 'payment_request',
      qbo_realm_id: selectedRealmId ?? undefined,
    }),
    onSuccess: (d) => setResult(d.content),
  })

  const onDrop = useCallback((files: File[]) => {
    if (files[0]) setFile(files[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'image/*': ['.png', '.jpg', '.jpeg'] },
    maxFiles: 1,
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={CreditCard}
        title={t('page.payments.title')}
        subtitle={t('page.payments.subtitle')}
        badge="AI"
        actions={
          <>
            <button onClick={fetchBills} disabled={loadingBills} className="btn-ghost text-[13px] gap-1.5">
              <RefreshCw size={14} className={loadingBills ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button className="btn-primary text-[13px]">
              <Plus size={14} /> New Request
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-2 gap-5">
          {/* Form */}
          <div className="card p-5 space-y-4">
            <h2 className="text-sm font-semibold text-surface-900">New Payment Request</h2>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Vendor Name</label>
                <input className="input" placeholder="e.g. Office Depot" value={vendor} onChange={e => setVendor(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Amount</label>
                <input className="input" placeholder="$0.00" value={amount} onChange={e => setAmount(e.target.value)} />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">GL Category</label>
              <input className="input" placeholder="e.g. Professional Services" value={category} onChange={e => setCategory(e.target.value)} />
            </div>

            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Business Purpose / Notes</label>
              <textarea
                rows={3}
                className="input resize-none"
                placeholder="Describe the business purpose of this payment…"
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
            </div>

            {/* Invoice upload */}
            <div>
              <label className="block text-xs font-medium text-surface-600 mb-1.5">Attach Invoice (PDF / Image)</label>
              <div
                {...getRootProps()}
                className={cn(
                  'cursor-pointer rounded-xl border-2 border-dashed p-4 text-center transition-all',
                  isDragActive
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-surface-200 hover:border-primary-300 hover:bg-primary-50/50',
                )}
              >
                <input {...getInputProps()} />
                {file ? (
                  <div className="flex items-center justify-center gap-2">
                    <FileText size={15} className="text-primary-500" />
                    <span className="text-sm font-medium text-surface-700">{file.name}</span>
                    <button onClick={e => { e.stopPropagation(); setFile(null) }} className="text-surface-400 hover:text-red-500">
                      <X size={13} />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-center gap-2 text-surface-400">
                    <UploadCloud size={16} />
                    <span className="text-sm">Drop invoice or click to browse</span>
                  </div>
                )}
              </div>
            </div>

            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || !vendor || !amount}
              className="btn-primary w-full justify-center"
            >
              {mutation.isPending
                ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
                : <><CreditCard size={14} /> Generate Request</>
              }
            </button>

            {result && (
              <div className="p-4 rounded-xl bg-primary-50 border border-primary-200 text-sm text-surface-800 whitespace-pre-wrap leading-relaxed">
                {result}
              </div>
            )}
          </div>

          {/* QBO Bills Queue */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-surface-900">
                Unpaid Bills — QBO
                {bills.length > 0 && (
                  <span className="ml-2 text-[11px] font-normal text-surface-400">({bills.length})</span>
                )}
              </h2>
              <button className="btn-ghost text-[13px]">
                <Download size={13} /> {t('common.export')}
              </button>
            </div>

            {!selectedRealmId && (
              <p className="text-sm text-surface-400 text-center py-6">Select a company to load bills.</p>
            )}

            {loadingBills && (
              <div className="flex items-center justify-center py-8 gap-2 text-surface-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm">Loading from QuickBooks…</span>
              </div>
            )}

            {billsError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-500" />
                <p className="text-sm text-red-700">{billsError}</p>
              </div>
            )}

            {!loadingBills && bills.length === 0 && selectedRealmId && !billsError && (
              <p className="text-sm text-surface-400 text-center py-6">No unpaid bills found.</p>
            )}

            <div className="space-y-2 max-h-[420px] overflow-y-auto">
              {bills.map(b => (
                <div key={b.id} className="rounded-xl border border-surface-200 p-4 hover:border-surface-300 transition-all">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-surface-900">{b.vendor}</p>
                      <p className="text-xs text-surface-500">
                        #{b.doc_number} · Due: {b.due_date || b.txn_date}
                      </p>
                    </div>
                    <div className="text-right space-y-1">
                      <p className="text-sm font-bold text-surface-900">{b.balance_formatted}</p>
                      <span className={`badge ${statusStyle[b.status] ?? statusStyle.pending}`}>{b.status}</span>
                    </div>
                  </div>
                  {b.status === 'pending' || b.status === 'overdue' ? (
                    <div className="flex gap-2 mt-3">
                      <button className="flex-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 transition-colors flex items-center justify-center gap-1">
                        <CheckCircle2 size={12} /> Approve
                      </button>
                      <button className="flex-1 rounded-lg bg-surface-100 px-3 py-1.5 text-xs font-medium text-surface-600 hover:bg-surface-200 transition-colors flex items-center justify-center gap-1">
                        <Clock size={12} /> Hold
                      </button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
