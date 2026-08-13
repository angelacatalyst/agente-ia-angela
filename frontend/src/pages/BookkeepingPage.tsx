import { useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { api } from '@/lib/api'
import type {
  BookkeepingTransaction, BookkeepingReviewResponse,
  AISuggestion, LineUpdate, QBOCompany,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Sparkles, Loader2, AlertCircle, CheckCircle2, ChevronDown,
  Building2, Search, RefreshCw, AlertTriangle, Tag,
  DollarSign, Info, X, ExternalLink,
} from 'lucide-react'

const fmt = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

type FilterType = 'all' | 'uncategorized' | 'bank_fee' | 'missing_class' | 'missing_grant'

const ISSUE_LABELS: Record<string, { label: string; color: string }> = {
  uncategorized: { label: 'Sin categoría', color: 'bg-red-100 text-red-700 border-red-200' },
  bank_fee:      { label: 'Bank Fee',      color: 'bg-amber-100 text-amber-700 border-amber-200' },
  missing_class: { label: 'Sin clase',     color: 'bg-blue-100 text-blue-700 border-blue-200' },
  missing_grant: { label: 'Sin grant',     color: 'bg-purple-100 text-purple-700 border-purple-200' },
}

const CONFIDENCE_STYLE: Record<string, string> = {
  high:   'bg-emerald-100 text-emerald-700',
  medium: 'bg-amber-100 text-amber-700',
  low:    'bg-red-100 text-red-700',
}

// ─────────────────────────────────────────────────────────────────────────────
export function BookkeepingPage() {
  // ── Config state ──────────────────────────────────────────────────────────
  const [companies, setCompanies]   = useState<QBOCompany[]>([])
  const [realm, setRealm]           = useState('')
  const [startDate, setStartDate]   = useState('2025-01-01')
  const [endDate, setEndDate]       = useState('2025-12-31')
  const [filter, setFilter]         = useState<FilterType>('all')
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [data, setData]             = useState<BookkeepingReviewResponse | null>(null)

  // ── Per-transaction state ─────────────────────────────────────────────────
  const [aiLoading, setAiLoading]   = useState<Record<string, boolean>>({})
  const [suggestions, setSuggestions] = useState<Record<string, AISuggestion>>({})
  const [saving, setSaving]         = useState<Record<string, boolean>>({})
  const [saved, setSaved]           = useState<Record<string, boolean>>({})
  const [txnError, setTxnError]     = useState<Record<string, string>>({})
  const [expanded, setExpanded]     = useState<Record<string, boolean>>({})

  // ── Inline edit state: {txnId: {lineId: {account_id, class_id, customer_id}}}
  const [edits, setEdits] = useState<Record<string, Record<string, Partial<LineUpdate>>>>({})

  const loadCompanies = async () => {
    if (companies.length > 0) return
    try {
      const c = await api.integrations.qboCompanies()
      setCompanies(c)
      if (c.length > 0 && !realm) setRealm(c[0].realm_id)
    } catch { /* silent */ }
  }

  // Auto-load companies on mount
  useState(() => { loadCompanies() })

  const runReview = async () => {
    if (!realm) return
    setLoading(true)
    setError(null)
    setData(null)
    setSuggestions({})
    setSaved({})
    setEdits({})
    try {
      const result = await api.bookkeeping.review(realm, startDate, endDate, filter)
      setData(result)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Error fetching transactions')
    } finally {
      setLoading(false)
    }
  }

  const runAISuggest = async (txn: BookkeepingTransaction) => {
    if (!data) return
    setAiLoading(p => ({ ...p, [txn.id]: true }))
    setTxnError(p => { const n = { ...p }; delete n[txn.id]; return n })
    try {
      const result = await api.bookkeeping.aiSuggest({
        realm_id:            realm,
        transaction_id:      txn.id,
        vendor:              txn.vendor ?? '',
        memo:                txn.memo,
        amount:              txn.total,
        date:                txn.date,
        current_account:     txn.lines[0]?.account ?? '',
        available_accounts:  data.reference.accounts,
        available_classes:   data.reference.classes,
        available_customers: data.reference.customers,
      })
      setSuggestions(p => ({ ...p, [txn.id]: result.suggestion }))
      // Pre-fill edits from suggestion
      const newEdits: Record<string, Partial<LineUpdate>> = {}
      txn.lines.forEach(line => {
        newEdits[line.id] = {
          line_id:     line.id,
          account_id:  result.suggestion.account_id ?? line.account_id ?? undefined,
          class_id:    result.suggestion.class_id   ?? line.class_id   ?? undefined,
          customer_id: result.suggestion.customer_id ?? line.customer_id ?? undefined,
        }
      })
      setEdits(p => ({ ...p, [txn.id]: newEdits }))
    } catch (e: any) {
      setTxnError(p => ({ ...p, [txn.id]: e?.response?.data?.detail ?? 'AI suggestion failed' }))
    } finally {
      setAiLoading(p => ({ ...p, [txn.id]: false }))
    }
  }

  const applyEdits = async (txn: BookkeepingTransaction) => {
    const txnEdits = edits[txn.id]
    if (!txnEdits) return
    setSaving(p => ({ ...p, [txn.id]: true }))
    setTxnError(p => { const n = { ...p }; delete n[txn.id]; return n })
    try {
      const lineUpdates: LineUpdate[] = Object.values(txnEdits).map(e => ({
        line_id:     e.line_id!,
        account_id:  e.account_id  ?? null,
        class_id:    e.class_id    ?? null,
        customer_id: e.customer_id ?? null,
      }))
      await api.bookkeeping.categorize({
        realm_id:       realm,
        transaction_id: txn.id,
        sync_token:     txn.sync_token,
        line_updates:   lineUpdates,
      })
      setSaved(p => ({ ...p, [txn.id]: true }))
      // Remove from list after save
      setTimeout(() => {
        setData(prev => prev
          ? { ...prev, transactions: prev.transactions.filter(t => t.id !== txn.id) }
          : prev
        )
      }, 1200)
    } catch (e: any) {
      setTxnError(p => ({ ...p, [txn.id]: e?.response?.data?.detail ?? 'Failed to save' }))
    } finally {
      setSaving(p => ({ ...p, [txn.id]: false }))
    }
  }

  const setLineEdit = (txnId: string, lineId: string, field: keyof LineUpdate, value: string) => {
    setEdits(p => ({
      ...p,
      [txnId]: {
        ...(p[txnId] ?? {}),
        [lineId]: {
          ...(p[txnId]?.[lineId] ?? { line_id: lineId }),
          [field]: value || null,
        },
      },
    }))
  }

  const ref = data?.reference

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Tag}
        title="Bookkeeping Cleanup"
        subtitle="Revisa y categoriza transacciones en QBO · Bank fees · Sin clase/grant"
        badge="AI"
      />

      {/* ── Controls ── */}
      <div className="border-b border-surface-200 bg-white px-6 py-3 flex flex-wrap items-end gap-3">
        {/* Company */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">Empresa QBO</label>
          <div className="relative">
            <select
              value={realm}
              onChange={e => setRealm(e.target.value)}
              className="appearance-none rounded-lg border border-surface-200 bg-white pl-3 pr-8 py-2 text-xs font-medium text-surface-800 focus:border-primary-400 focus:outline-none min-w-[200px]"
            >
              {companies.length === 0
                ? <option value="">Cargando…</option>
                : companies.map(c => <option key={c.realm_id} value={c.realm_id}>{c.company_name}</option>)
              }
            </select>
            <ChevronDown size={12} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
          </div>
        </div>

        {/* Date range */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">Desde</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            className="rounded-lg border border-surface-200 px-3 py-2 text-xs focus:border-primary-400 focus:outline-none" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">Hasta</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
            className="rounded-lg border border-surface-200 px-3 py-2 text-xs focus:border-primary-400 focus:outline-none" />
        </div>

        {/* Filter */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">Filtro</label>
          <div className="relative">
            <select
              value={filter}
              onChange={e => setFilter(e.target.value as FilterType)}
              className="appearance-none rounded-lg border border-surface-200 bg-white pl-3 pr-8 py-2 text-xs font-medium text-surface-800 focus:border-primary-400 focus:outline-none"
            >
              <option value="all">Todos los issues</option>
              <option value="uncategorized">Sin categoría</option>
              <option value="bank_fee">Bank Fees</option>
              <option value="missing_class">Sin clase</option>
              <option value="missing_grant">Sin grant</option>
            </select>
            <ChevronDown size={12} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
          </div>
        </div>

        {/* Run button */}
        <button
          onClick={runReview}
          disabled={loading || !realm}
          className="flex items-center gap-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-50 mt-auto"
        >
          {loading
            ? <><Loader2 size={13} className="animate-spin" /> Cargando…</>
            : <><Search size={13} /> Revisar transacciones</>
          }
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-red-50 border border-red-200 px-4 py-3">
            <AlertCircle size={14} className="text-red-500" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Summary counts */}
        {data && (
          <div className="grid grid-cols-5 gap-3">
            {[
              { key: 'total',         label: 'Total',          color: 'text-surface-700',  bg: 'bg-white' },
              { key: 'uncategorized', label: 'Sin categoría',  color: 'text-red-700',      bg: 'bg-red-50' },
              { key: 'bank_fee',      label: 'Bank Fees',      color: 'text-amber-700',    bg: 'bg-amber-50' },
              { key: 'missing_class', label: 'Sin clase',      color: 'text-blue-700',     bg: 'bg-blue-50' },
              { key: 'missing_grant', label: 'Sin grant',      color: 'text-purple-700',   bg: 'bg-purple-50' },
            ].map(({ key, label, color, bg }) => (
              <div key={key} className={cn('card p-4 text-center', bg)}>
                <p className={cn('text-2xl font-bold', color)}>
                  {data.counts[key as keyof typeof data.counts]}
                </p>
                <p className="text-[11px] text-surface-500 mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {data && data.transactions.length === 0 && (
          <div className="card p-12 flex flex-col items-center gap-3 text-center">
            <CheckCircle2 size={32} className="text-emerald-400" />
            <p className="text-sm font-semibold text-surface-700">¡Todo limpio!</p>
            <p className="text-xs text-surface-400">No hay transacciones que necesiten atención en este rango.</p>
          </div>
        )}

        {/* Transactions */}
        {data && data.transactions.map(txn => {
          const isExpanded = expanded[txn.id] ?? true
          const suggestion = suggestions[txn.id]
          const isSaved    = saved[txn.id]
          const isAiLoading = aiLoading[txn.id]
          const isSaving   = saving[txn.id]
          const txnEdits   = edits[txn.id] ?? {}
          const err        = txnError[txn.id]

          return (
            <div key={txn.id} className={cn(
              'card overflow-hidden transition-all',
              isSaved && 'opacity-50 scale-[0.99]',
            )}>
              {/* Header */}
              <div
                className="flex items-center gap-3 px-4 py-3 bg-surface-50 border-b border-surface-100 cursor-pointer hover:bg-surface-100 transition-colors"
                onClick={() => setExpanded(p => ({ ...p, [txn.id]: !isExpanded }))}
              >
                <div className="flex-1 flex items-center gap-3 min-w-0">
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-surface-900 truncate">
                      {txn.vendor || '(no vendor)'} · {txn.date}
                    </p>
                    {txn.doc_number && (
                      <p className="text-[10px] text-surface-400">{txn.doc_number}</p>
                    )}
                  </div>
                  {/* Issue badges */}
                  <div className="flex gap-1.5 flex-wrap shrink-0">
                    {txn.issues.map(issue => (
                      <span key={issue} className={cn(
                        'text-[10px] font-semibold px-2 py-0.5 rounded-full border',
                        ISSUE_LABELS[issue]?.color,
                      )}>
                        {ISSUE_LABELS[issue]?.label}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {isSaved && <CheckCircle2 size={14} className="text-emerald-500" />}
                  <p className="text-sm font-bold text-surface-900">{fmt(txn.total)}</p>
                  <ChevronDown size={13} className={cn('text-surface-400 transition-transform', isExpanded && 'rotate-180')} />
                </div>
              </div>

              {/* Body */}
              {isExpanded && (
                <div className="p-4 space-y-3">
                  {/* Memo */}
                  {txn.memo && (
                    <div className="flex items-start gap-2 text-[11px] text-surface-500">
                      <Info size={11} className="mt-0.5 shrink-0" />
                      <span>{txn.memo}</span>
                    </div>
                  )}

                  {/* AI Suggestion box */}
                  {suggestion && (
                    <div className={cn(
                      'rounded-lg border p-3 space-y-1.5',
                      suggestion.confidence === 'high'   ? 'bg-emerald-50 border-emerald-200' :
                      suggestion.confidence === 'medium' ? 'bg-amber-50 border-amber-200' :
                                                           'bg-surface-50 border-surface-200',
                    )}>
                      <div className="flex items-center gap-2">
                        <Sparkles size={12} className="text-primary-500" />
                        <p className="text-[11px] font-semibold text-surface-700">Sugerencia IA</p>
                        <span className={cn('text-[10px] font-bold px-1.5 py-0.5 rounded-full', CONFIDENCE_STYLE[suggestion.confidence])}>
                          {suggestion.confidence}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div><span className="text-surface-400">Cuenta: </span><span className="font-medium">{suggestion.account_name || '—'}</span></div>
                        <div><span className="text-surface-400">Clase: </span><span className="font-medium">{suggestion.class_name || '—'}</span></div>
                        <div><span className="text-surface-400">Grant: </span><span className="font-medium">{suggestion.customer_name || '—'}</span></div>
                      </div>
                      <p className="text-[10px] text-surface-500 italic">{suggestion.reasoning}</p>
                    </div>
                  )}

                  {/* Lines table */}
                  <div className="rounded-lg border border-surface-200 overflow-hidden">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="bg-surface-50 border-b border-surface-100 text-surface-400">
                          <th className="px-3 py-2 text-left font-medium w-8">#</th>
                          <th className="px-3 py-2 text-left font-medium">Descripción</th>
                          <th className="px-3 py-2 text-right font-medium w-20">Monto</th>
                          <th className="px-3 py-2 text-left font-medium w-48">Cuenta</th>
                          <th className="px-3 py-2 text-left font-medium w-36">Clase</th>
                          <th className="px-3 py-2 text-left font-medium w-36">Grant</th>
                        </tr>
                      </thead>
                      <tbody>
                        {txn.lines.map((line, li) => {
                          const lineEdit = txnEdits[line.id] ?? {}
                          return (
                            <tr key={line.id} className="border-b border-surface-50 last:border-0">
                              <td className="px-3 py-2 text-surface-400">{li + 1}</td>
                              <td className="px-3 py-2 text-surface-600 max-w-[200px] truncate">{line.description || '—'}</td>
                              <td className={cn('px-3 py-2 text-right font-semibold', line.amount < 0 ? 'text-red-600' : 'text-surface-900')}>
                                {fmt(line.amount)}
                              </td>
                              {/* Account dropdown */}
                              <td className="px-3 py-2">
                                <select
                                  value={lineEdit.account_id ?? line.account_id ?? ''}
                                  onChange={e => setLineEdit(txn.id, line.id, 'account_id', e.target.value)}
                                  className="w-full rounded border border-surface-200 px-1.5 py-1 text-[10px] focus:border-primary-400 focus:outline-none bg-white"
                                >
                                  <option value="">{line.account || '— seleccionar —'}</option>
                                  {ref?.accounts.map(a => (
                                    <option key={a.id} value={a.id}>{a.name}</option>
                                  ))}
                                </select>
                              </td>
                              {/* Class dropdown */}
                              <td className="px-3 py-2">
                                <select
                                  value={lineEdit.class_id ?? line.class_id ?? ''}
                                  onChange={e => setLineEdit(txn.id, line.id, 'class_id', e.target.value)}
                                  className="w-full rounded border border-surface-200 px-1.5 py-1 text-[10px] focus:border-primary-400 focus:outline-none bg-white"
                                >
                                  <option value="">{line.class || '— ninguna —'}</option>
                                  {ref?.classes.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                  ))}
                                </select>
                              </td>
                              {/* Grant/Customer dropdown */}
                              <td className="px-3 py-2">
                                <select
                                  value={lineEdit.customer_id ?? line.customer_id ?? ''}
                                  onChange={e => setLineEdit(txn.id, line.id, 'customer_id', e.target.value)}
                                  className="w-full rounded border border-surface-200 px-1.5 py-1 text-[10px] focus:border-primary-400 focus:outline-none bg-white"
                                >
                                  <option value="">{line.customer || '— ninguno —'}</option>
                                  {ref?.customers.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Error */}
                  {err && (
                    <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                      <AlertCircle size={12} className="text-red-500 shrink-0" />
                      <p className="text-[11px] text-red-700">{err}</p>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      onClick={() => runAISuggest(txn)}
                      disabled={isAiLoading}
                      className="flex items-center gap-1.5 rounded-lg border border-primary-200 bg-primary-50 hover:bg-primary-100 text-primary-700 px-3 py-1.5 text-[11px] font-semibold transition-colors disabled:opacity-50"
                    >
                      {isAiLoading
                        ? <><Loader2 size={11} className="animate-spin" /> Analizando…</>
                        : <><Sparkles size={11} /> Sugerir con IA</>
                      }
                    </button>
                    <button
                      onClick={() => applyEdits(txn)}
                      disabled={isSaving || Object.keys(txnEdits).length === 0}
                      className={cn(
                        'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-colors disabled:opacity-50',
                        isSaved
                          ? 'bg-emerald-600 text-white'
                          : 'bg-primary-600 hover:bg-primary-700 text-white',
                      )}
                    >
                      {isSaving
                        ? <><Loader2 size={11} className="animate-spin" /> Guardando…</>
                        : isSaved
                          ? <><CheckCircle2 size={11} /> Guardado</>
                          : <><RefreshCw size={11} /> Aplicar en QBO</>
                      }
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}

        {/* Initial empty state */}
        {!data && !loading && (
          <div className="card p-12 flex flex-col items-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-50 ring-1 ring-primary-200">
              <Tag size={24} className="text-primary-500" />
            </div>
            <div>
              <p className="text-sm font-semibold text-surface-800">Bookkeeping Cleanup</p>
              <p className="text-xs text-surface-400 mt-1 max-w-sm">
                Selecciona la empresa QBO y el rango de fechas, luego haz clic en "Revisar transacciones" para ver todo lo que necesita atención.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
