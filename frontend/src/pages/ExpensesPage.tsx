import { useState, useEffect, useCallback } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAppStore } from '@/stores/appStore'
import { api, type QBOExpense, type QBOCustomerOption } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Loader2, Search, CheckSquare, Square, Tag, AlertCircle,
  CheckCircle2, RefreshCw, Filter, DollarSign,
} from 'lucide-react'

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonth(): string {
  const d = new Date()
  d.setDate(1)
  return d.toISOString().slice(0, 10)
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function ExpensesPage() {
  const { selectedRealmId } = useAppStore()

  // Filters
  const [dateFrom, setDateFrom]     = useState(firstOfMonth())
  const [dateTo, setDateTo]         = useState(today())
  const [noGrantOnly, setNoGrantOnly] = useState(false)

  // Data
  const [expenses, setExpenses]       = useState<QBOExpense[]>([])
  const [customers, setCustomers]     = useState<QBOCustomerOption[]>([])
  const [loading, setLoading]         = useState(false)
  const [loadingCustomers, setLoadingCustomers] = useState(false)
  const [error, setError]             = useState<string | null>(null)

  // Selection + grant assignment
  const [selected, setSelected]       = useState<Set<string>>(new Set())
  const [grantId, setGrantId]         = useState('')
  const [saving, setSaving]           = useState(false)
  const [result, setResult]           = useState<{ success: number; failed: number; errors: string[] } | null>(null)

  // Load customers once
  useEffect(() => {
    if (!selectedRealmId) return
    setLoadingCustomers(true)
    api.expenses.customers(selectedRealmId)
      .then(d => setCustomers(d.customers))
      .catch(() => {})
      .finally(() => setLoadingCustomers(false))
  }, [selectedRealmId])

  const fetchExpenses = useCallback(async () => {
    if (!selectedRealmId || !dateFrom || !dateTo) return
    setLoading(true)
    setError(null)
    setSelected(new Set())
    setResult(null)
    try {
      const data = await api.expenses.list(selectedRealmId, dateFrom, dateTo, noGrantOnly)
      setExpenses(data.expenses)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Error al cargar gastos')
    } finally {
      setLoading(false)
    }
  }, [selectedRealmId, dateFrom, dateTo, noGrantOnly])

  // Toggle row selection
  const toggleRow = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleAll = () => {
    if (selected.size === expenses.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(expenses.map(e => e.id)))
    }
  }

  // Bulk assign grant
  const handleAssign = async () => {
    if (!selectedRealmId || !grantId || selected.size === 0) return
    const grantName = customers.find(c => c.id === grantId)?.name ?? ''
    setSaving(true)
    setResult(null)
    try {
      const updates = [...selected].map(id => ({
        expense_id:    id,
        customer_id:   grantId,
        customer_name: grantName,
      }))
      const res: any = await api.expenses.bulkUpdateGrant(selectedRealmId, updates)
      setResult({
        success: res.summary.success,
        failed:  res.summary.failed,
        errors:  res.errors ?? [],
      })
      // Refresh list after update
      await fetchExpenses()
    } catch (e: any) {
      setResult({
        success: 0,
        failed:  selected.size,
        errors:  [e?.response?.data?.detail || 'Error al actualizar'],
      })
    } finally {
      setSaving(false)
    }
  }

  const allSelected = expenses.length > 0 && selected.size === expenses.length
  const someSelected = selected.size > 0 && !allSelected
  const selectedGrant = customers.find(c => c.id === grantId)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Gastos"
        subtitle="Asigna o modifica el grant en tus gastos de QBO"
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">

        {/* ── Filters ── */}
        <div className="rounded-xl border border-surface-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Desde</label>
              <input
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                className="rounded-lg border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Hasta</label>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                className="rounded-lg border border-surface-200 bg-surface-50 px-3 py-1.5 text-sm text-surface-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={noGrantOnly}
                onChange={e => setNoGrantOnly(e.target.checked)}
                className="rounded accent-primary-600"
              />
              <span className="text-sm font-medium text-surface-700">Solo sin grant</span>
            </label>
            <button
              onClick={fetchExpenses}
              disabled={loading || !selectedRealmId}
              className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50 transition-colors ml-auto"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
              Buscar gastos
            </button>
          </div>
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle size={14} className="shrink-0" />
            {error}
          </div>
        )}

        {/* ── Result banner ── */}
        {result && (
          <div className={cn(
            'flex items-start gap-2 rounded-lg border px-4 py-3 text-sm',
            result.failed === 0
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-amber-200 bg-amber-50 text-amber-800',
          )}>
            <CheckCircle2 size={14} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">
                {result.success} actualizado{result.success !== 1 ? 's' : ''}
                {result.failed > 0 && ` · ${result.failed} con error`}
              </p>
              {result.errors.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-xs opacity-80">
                  {result.errors.map((e, i) => <li key={i}>• {e}</li>)}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* ── Bulk assign bar (visible when rows selected) ── */}
        {selected.size > 0 && (
          <div className="flex items-center gap-3 rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 shadow-sm">
            <Tag size={15} className="shrink-0 text-primary-600" />
            <span className="text-sm font-semibold text-primary-800">
              {selected.size} gasto{selected.size !== 1 ? 's' : ''} seleccionado{selected.size !== 1 ? 's' : ''}
            </span>

            <select
              value={grantId}
              onChange={e => setGrantId(e.target.value)}
              disabled={loadingCustomers}
              className="ml-2 flex-1 max-w-xs rounded-lg border border-surface-200 bg-white px-3 py-1.5 text-sm text-surface-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">— Selecciona un grant —</option>
              {customers.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>

            <button
              onClick={handleAssign}
              disabled={!grantId || saving}
              className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
              Asignar grant
            </button>
          </div>
        )}

        {/* ── Table ── */}
        {expenses.length > 0 && (
          <div className="rounded-xl border border-surface-200 bg-white shadow-sm overflow-hidden">
            {/* Table header with count */}
            <div className="flex items-center justify-between border-b border-surface-100 px-4 py-2.5 bg-surface-50">
              <span className="text-xs font-semibold text-surface-500 uppercase tracking-wide">
                {expenses.length} gasto{expenses.length !== 1 ? 's' : ''}
              </span>
              <button
                onClick={fetchExpenses}
                className="flex items-center gap-1 text-xs text-surface-500 hover:text-surface-700 transition-colors"
              >
                <RefreshCw size={11} />
                Actualizar
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-100 bg-surface-50/50">
                    <th className="w-10 px-4 py-2.5 text-left">
                      <button onClick={toggleAll} className="text-surface-400 hover:text-surface-700 transition-colors">
                        {allSelected
                          ? <CheckSquare size={15} className="text-primary-600" />
                          : someSelected
                            ? <CheckSquare size={15} className="text-primary-400" />
                            : <Square size={15} />}
                      </button>
                    </th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Fecha</th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Proveedor</th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Clase</th>
                    <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Monto</th>
                    <th className="px-3 py-2.5 text-left text-[11px] font-semibold text-surface-500 uppercase tracking-wide">Grant actual</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-50">
                  {expenses.map(exp => {
                    const isSelected = selected.has(exp.id)
                    return (
                      <tr
                        key={exp.id}
                        onClick={() => toggleRow(exp.id)}
                        className={cn(
                          'cursor-pointer transition-colors',
                          isSelected
                            ? 'bg-primary-50/60'
                            : 'hover:bg-surface-50',
                        )}
                      >
                        <td className="px-4 py-2.5">
                          {isSelected
                            ? <CheckSquare size={15} className="text-primary-600" />
                            : <Square size={15} className="text-surface-300" />}
                        </td>
                        <td className="px-3 py-2.5 text-surface-700 whitespace-nowrap">{exp.date}</td>
                        <td className="px-3 py-2.5 text-surface-800 font-medium max-w-[200px] truncate">
                          {exp.vendor || <span className="text-surface-400 italic">Sin proveedor</span>}
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex flex-wrap gap-1">
                            {exp.classes.length > 0
                              ? exp.classes.map(cls => (
                                  <span key={cls} className="inline-flex items-center rounded-md bg-surface-100 px-1.5 py-0.5 text-[11px] font-medium text-surface-600">
                                    {cls}
                                  </span>
                                ))
                              : <span className="text-[11px] text-surface-400">—</span>
                            }
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-sm text-surface-800">
                          {fmt(exp.amount)}
                        </td>
                        <td className="px-3 py-2.5">
                          {exp.grant
                            ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                                <Tag size={9} />
                                {exp.grant}
                              </span>
                            )
                            : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                                <Filter size={9} />
                                Sin grant
                              </span>
                            )
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Footer summary */}
            <div className="border-t border-surface-100 px-4 py-2 bg-surface-50 flex items-center justify-between">
              <span className="text-xs text-surface-500">
                Total: <span className="font-semibold text-surface-700">
                  {fmt(expenses.reduce((s, e) => s + e.amount, 0))}
                </span>
              </span>
              <span className="text-xs text-surface-500">
                Sin grant: <span className="font-semibold text-amber-600">
                  {expenses.filter(e => !e.grant).length}
                </span>
              </span>
            </div>
          </div>
        )}

        {/* ── Empty state ── */}
        {!loading && expenses.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-16 text-center text-surface-400">
            <DollarSign size={32} className="mb-3 opacity-30" />
            <p className="text-sm font-medium">Busca gastos para comenzar</p>
            <p className="text-xs mt-1 opacity-70">Selecciona un rango de fechas y presiona "Buscar gastos"</p>
          </div>
        )}

      </div>
    </div>
  )
}
