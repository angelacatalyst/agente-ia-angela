import { useRef, useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { api } from '@/lib/api'
import type {
  PayrollPeriod, PayrollMatrixResponse,
  PayrollJournalEntry, PayrollBudgetInfo,
  PayrollQBOPreviewResponse, PayrollQBOPostResult,
  PayrollQBOLookup,
  QBOCompany,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Users, Loader2, Upload, AlertCircle, ChevronDown,
  DollarSign, FileText, BarChart2, CheckCircle2, Info,
  Building2, BookOpen, AlertTriangle, TrendingUp,
  Send, X, ExternalLink, ShieldCheck, Eye,
} from 'lucide-react'

type Tab = 'calculator' | 'budget' | 'matrix' | 'journal'

// ── Colour coding per grant ───────────────────────────────────────────────────
const GRANT_COLORS: Record<string, string> = {
  'B3':             'bg-violet-50 text-violet-700 border-violet-200',
  'FIRST CITIZEN':  'bg-sky-50 text-sky-700 border-sky-200',
  'WELLS FARGO':    'bg-amber-50 text-amber-700 border-amber-200',
  'MHFA (1)':       'bg-emerald-50 text-emerald-700 border-emerald-200',
  'MHFA (2)':       'bg-emerald-100 text-emerald-800 border-emerald-300',
  'MHFA (3)':       'bg-teal-50 text-teal-700 border-teal-200',
  'CITI':           'bg-blue-50 text-blue-700 border-blue-200',
  'CITY OF MIAMI':  'bg-orange-50 text-orange-700 border-orange-200',
  'TRUIST':         'bg-teal-50 text-teal-700 border-teal-200',
  'JPM CHASE':      'bg-indigo-50 text-indigo-700 border-indigo-200',
  'LATINOS':        'bg-rose-50 text-rose-700 border-rose-200',
  'ROBERT WOOD':    'bg-lime-50 text-lime-700 border-lime-200',
  'PENDING':        'bg-red-50 text-red-700 border-red-300',
}
const grantStyle = (name: string) =>
  GRANT_COLORS[name] ?? 'bg-surface-100 text-surface-600 border-surface-200'

const fmt = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

// ─────────────────────────────────────────────────────────────────────────────
export function PayrollPage() {
  const [tab, setTab] = useState<Tab>('calculator')

  // ── Calculator state ──────────────────────────────────────────────────────
  const fileRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [periods, setPeriods] = useState<PayrollPeriod[]>([])
  const [totalPeriods, setTotalPeriods] = useState(0)
  const [selectedPeriodIdx, setSelectedPeriodIdx] = useState(0)
  const [journalEntries, setJournalEntries] = useState<PayrollJournalEntry[]>([])
  const [budgetStatus, setBudgetStatus] = useState<
    Record<string, Record<string, PayrollBudgetInfo>>
  >({})

  // ── Matrix state ──────────────────────────────────────────────────────────
  const [matrix, setMatrix] = useState<PayrollMatrixResponse | null>(null)
  const [matrixLoading, setMatrixLoading] = useState(false)

  // ── QBO post state ────────────────────────────────────────────────────────
  const [qboModalOpen, setQboModalOpen] = useState(false)
  const [qboCompanies, setQboCompanies] = useState<QBOCompany[]>([])
  const [qboRealm, setQboRealm] = useState('')
  const [qboVendor, setQboVendor] = useState('Gusto')
  const [qboAccount, setQboAccount] = useState('Salaries & Wages')
  const [qboBankAccount, setQboBankAccount] = useState('Payroll')
  const [qboTaxAccount, setQboTaxAccount] = useState('Payroll Tax')
  const [qboHealthAccount, setQboHealthAccount] = useState('Payroll Health')
  const [qboTaxExpenseAccount, setQboTaxExpenseAccount] = useState('Payroll Taxes')
  const [qboHealthExpenseAccount, setQboHealthExpenseAccount] = useState('Health Benefits')
  const [qboDentalExpenseAccount, setQboDentalExpenseAccount] = useState('Vision and Dental')
  const [qboDentalVendor, setQboDentalVendor] = useState('The Guardian')
  const [qboPreview, setQboPreview] = useState<PayrollQBOPreviewResponse | null>(null)
  const [qboPreviewLoading, setQboPreviewLoading] = useState(false)
  const [qboPosting, setQboPosting] = useState(false)
  const [qboPostResult, setQboPostResult] = useState<PayrollQBOPostResult | null>(null)
  const [qboError, setQboError] = useState<string | null>(null)

  const openQboModal = async () => {
    setQboModalOpen(true)
    setQboPreview(null)
    setQboPostResult(null)
    setQboError(null)
    if (qboCompanies.length === 0) {
      try {
        const companies = await api.integrations.qboCompanies()
        setQboCompanies(companies)
        if (companies.length > 0 && !qboRealm) setQboRealm(companies[0].realm_id)
      } catch { /* silent */ }
    }
  }

  const qboOpts = () => ({
    expenseAccount: qboAccount,
    payrollVendor: qboVendor,
    bankAccount: qboBankAccount,
    taxLiabilityAccount: qboTaxAccount,
    healthLiabilityAccount: qboHealthAccount,
    taxExpenseAccount: qboTaxExpenseAccount,
    healthExpenseAccount: qboHealthExpenseAccount,
    dentalExpenseAccount: qboDentalExpenseAccount,
    dentalVendor: qboDentalVendor,
  })

  const runQboPreview = async () => {
    if (!fileRef.current?.files?.[0] || !qboRealm) return
    setQboPreviewLoading(true)
    setQboPreview(null)
    setQboError(null)
    try {
      const preview = await api.payroll.previewQBO(
        fileRef.current.files[0], qboRealm, selectedPeriodIdx, qboOpts(),
      )
      setQboPreview(preview)
    } catch (err: any) {
      setQboError(err?.response?.data?.detail ?? 'Error connecting to QBO')
    } finally {
      setQboPreviewLoading(false)
    }
  }

  const confirmQboPost = async () => {
    if (!fileRef.current?.files?.[0] || !qboRealm) return
    setQboPosting(true)
    setQboError(null)
    try {
      const result = await api.payroll.postToQBO(
        fileRef.current.files[0], qboRealm, selectedPeriodIdx, qboOpts(),
      )
      setQboPostResult(result)
    } catch (err: any) {
      setQboError(err?.response?.data?.detail ?? 'Error posting to QBO')
    } finally {
      setQboPosting(false)
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFileName(f.name)
    setError(null)
    setLoading(true)
    setPeriods([])
    try {
      const result = await api.payroll.process(f, undefined, true)
      setPeriods(result.periods)
      setTotalPeriods(result.total_periods)
      setJournalEntries(result.journal_entries ?? [])
      setBudgetStatus(result.budget_status ?? {})
      setSelectedPeriodIdx(result.periods.length - 1)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Error processing payroll file')
    } finally {
      setLoading(false)
    }
  }

  const loadMatrix = async () => {
    if (matrix) return
    setMatrixLoading(true)
    try { setMatrix(await api.payroll.matrix()) }
    catch { /* silent */ }
    finally { setMatrixLoading(false) }
  }

  const selectedPeriod = periods[selectedPeriodIdx] ?? null
  const selectedJE     = journalEntries[selectedPeriodIdx] ?? null

  const hasBudget = Object.keys(budgetStatus).length > 0

  const TABS: [Tab, string, any][] = [
    ['calculator', 'Allocation Calculator', BarChart2],
    ['budget',     'Grant Budget Tracker',  TrendingUp],
    ['matrix',     'Allocation Matrix',     BookOpen],
    ['journal',    'Journal Entry',         FileText],
  ]

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={Users}
        title="Payroll Allocation"
        subtitle="Allapattah CDC · Gusto → Class → Grant (waterfall)"
        badge="AI"
      />

      {/* Tabs */}
      <div className="border-b border-surface-200 bg-white px-6">
        <div className="flex gap-1">
          {TABS.map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => { setTab(key); if (key === 'matrix') loadMatrix() }}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-3 text-xs font-medium transition-colors',
                tab === key
                  ? 'border-primary-600 text-primary-700'
                  : 'border-transparent text-surface-500 hover:text-surface-700',
              )}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">

        {/* ══ TAB: Allocation Calculator ══════════════════════════════════ */}
        {tab === 'calculator' && (
          <div className="space-y-5">
            {/* Upload + period selector */}
            <div className="flex items-start gap-4">
              <div className="card p-5 flex-1">
                <h2 className="text-sm font-semibold text-surface-900 mb-3">
                  1. Upload Gusto Payroll Export
                </h2>
                <div
                  onClick={() => fileRef.current?.click()}
                  className={cn(
                    'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed py-6 transition-colors',
                    fileName
                      ? 'border-emerald-300 bg-emerald-50'
                      : 'border-surface-200 hover:border-primary-300 hover:bg-primary-50/30',
                  )}
                >
                  {loading
                    ? <><Loader2 size={22} className="animate-spin text-primary-500" /><p className="text-xs text-surface-500">Processing…</p></>
                    : fileName
                      ? <><CheckCircle2 size={22} className="text-emerald-500" /><p className="text-xs font-medium text-emerald-700">{fileName}</p></>
                      : <><Upload size={22} className="text-surface-400" /><p className="text-xs text-surface-500">Click to upload Gusto .xlsx</p></>
                  }
                </div>
                <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={handleFileChange} />
                {error && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                    <AlertCircle size={13} className="text-red-500" />
                    <p className="text-xs text-red-700">{error}</p>
                  </div>
                )}
              </div>

              {periods.length > 0 && (
                <div className="card p-5 w-72 shrink-0">
                  <h2 className="text-sm font-semibold text-surface-900 mb-3">
                    2. Select Pay Period
                    <span className="ml-2 text-[11px] font-normal text-surface-400">({totalPeriods} found)</span>
                  </h2>
                  <div className="relative">
                    <select
                      value={selectedPeriodIdx}
                      onChange={e => setSelectedPeriodIdx(Number(e.target.value))}
                      className="w-full appearance-none rounded-lg border border-surface-200 bg-white px-3 py-2.5 pr-8 text-xs font-medium text-surface-800 focus:border-primary-400 focus:outline-none"
                    >
                      {periods.map((p, i) => (
                        <option key={i} value={i}>{p.period} (pay {p.payday})</option>
                      ))}
                    </select>
                    <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
                  </div>

                  {selectedPeriod && (
                    <div className="mt-3 rounded-xl bg-surface-50 border border-surface-100 p-3 space-y-1">
                      <div className="flex justify-between text-xs">
                        <span className="text-surface-500">Employees</span>
                        <span className="font-semibold">{selectedPeriod.employees.length}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-surface-500">Total Cost</span>
                        <span className="font-bold text-surface-900">{fmt(selectedPeriod.period_total_cost)}</span>
                      </div>
                      {selectedPeriod.unmatched_employees.length > 0 && (
                        <div className="flex items-center gap-1 text-[11px] text-amber-600 mt-1">
                          <Info size={11} />
                          Unmatched: {selectedPeriod.unmatched_employees.join(', ')}
                        </div>
                      )}
                      {/* PENDING alert */}
                      {(selectedPeriod.period_grant_totals['PENDING'] ?? 0) > 0 && (
                        <div className="flex items-center gap-1 text-[11px] text-red-600 mt-1 font-semibold">
                          <AlertTriangle size={11} />
                          PENDING: {fmt(selectedPeriod.period_grant_totals['PENDING'])}
                        </div>
                      )}
                      {/* Post to QBO button */}
                      <div className="pt-2">
                        <button
                          onClick={openQboModal}
                          className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white px-3 py-2 text-xs font-semibold transition-colors"
                        >
                          <Send size={12} /> Post to QBO
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Employee breakdown */}
            {selectedPeriod && (
              <>
                <div className="card p-5">
                  <h2 className="text-sm font-semibold text-surface-900 mb-4">
                    Employee Cost Allocation — {selectedPeriod.period}
                  </h2>
                  <div className="space-y-4">
                    {selectedPeriod.employees.map((emp) => {
                      const name = emp.full_name ?? `${emp.first} ${emp.last}`
                      if (!emp.allocation) {
                        return (
                          <div key={name} className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                            <p className="text-xs font-semibold text-amber-700">{name}</p>
                            <p className="text-[11px] text-amber-600 mt-0.5">Not found in allocation matrix.</p>
                          </div>
                        )
                      }

                      const hasPending = (emp.allocation.pending ?? 0) > 0.01

                      return (
                        <div key={name} className={cn('rounded-xl border overflow-hidden', hasPending ? 'border-red-200' : 'border-surface-200')}>
                          {/* Header */}
                          <div className={cn('flex items-center justify-between px-4 py-3 border-b', hasPending ? 'bg-red-50 border-red-100' : 'bg-surface-50 border-surface-100')}>
                            <div>
                              <p className="text-xs font-bold text-surface-900">{name}</p>
                              {emp.title && <p className="text-[11px] text-surface-400">{emp.title}</p>}
                            </div>
                            <div className="flex items-center gap-3">
                              {hasPending && (
                                <div className="flex items-center gap-1 rounded-full bg-red-100 border border-red-300 px-2.5 py-1">
                                  <AlertTriangle size={11} className="text-red-600" />
                                  <span className="text-[11px] font-bold text-red-700">
                                    PENDING {fmt(emp.allocation.pending)}
                                  </span>
                                </div>
                              )}
                              <div className="text-right">
                                <p className="text-xs font-bold text-surface-900">{fmt(emp.total_cost ?? 0)}</p>
                                <p className="text-[11px] text-surface-400">total cost</p>
                              </div>
                            </div>
                          </div>

                          {/* Cost components */}
                          <div className="grid grid-cols-5 border-b border-surface-100 text-[11px]">
                            {[
                              ['Gross Salary', emp.gross],
                              ['Employer FICA', emp.employer_taxes],
                              ['Health Allow.', emp.health_allowance],
                              ['Dental/Vision', emp.dental_vision_employer ?? 0],
                              ['Total Cost', emp.total_cost ?? 0],
                            ].map(([label, val], idx) => (
                              <div key={label as string} className={cn(
                                'px-4 py-2 border-r border-surface-100 last:border-r-0',
                                idx === 4 && 'bg-surface-50 font-bold',
                              )}>
                                <p className="text-surface-400">{label}</p>
                                <p className={cn('font-semibold text-surface-700', idx === 4 && 'text-surface-900')}>{fmt(val as number)}</p>
                              </div>
                            ))}
                          </div>

                          {/* Grant charges summary */}
                          <div className="flex flex-wrap gap-2 px-4 py-2.5 border-b border-surface-100 bg-surface-50/50">
                            {Object.entries(emp.allocation.grant_charges).map(([gname, amt]) => (
                              <span key={gname} className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold', grantStyle(gname))}>
                                {gname === 'PENDING' && <AlertTriangle size={10} />}
                                {gname}: {fmt(amt)}
                              </span>
                            ))}
                          </div>

                          {/* Class table */}
                          <table className="w-full text-[11px]">
                            <thead>
                              <tr className="border-b border-surface-100 text-surface-400">
                                <th className="px-4 py-2 text-left font-medium">Class</th>
                                <th className="px-3 py-2 text-right font-medium">%</th>
                                <th className="px-3 py-2 text-right font-medium">Salary</th>
                                <th className="px-3 py-2 text-right font-medium">FICA</th>
                                <th className="px-3 py-2 text-right font-medium">Health</th>
                                <th className="px-3 py-2 text-right font-medium">Dental/Vis.</th>
                                <th className="px-3 py-2 text-right font-medium">Total</th>
                                <th className="px-3 py-2 text-left font-medium">Grant</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(emp.allocation.classes).map(([cls, data]) => (
                                <tr key={cls} className="border-b border-surface-50 hover:bg-surface-50/40">
                                  <td className="px-4 py-1.5 font-medium text-surface-800">{cls}</td>
                                  <td className="px-3 py-1.5 text-right text-surface-500">{(data.pct * 100).toFixed(0)}%</td>
                                  <td className="px-3 py-1.5 text-right text-surface-600">{fmt(data.salary_portion)}</td>
                                  <td className="px-3 py-1.5 text-right text-surface-600">{fmt(data.taxes_portion)}</td>
                                  <td className="px-3 py-1.5 text-right text-surface-600">{fmt(data.health_portion ?? 0)}</td>
                                  <td className="px-3 py-1.5 text-right text-surface-600">{fmt(data.dental_portion ?? 0)}</td>
                                  <td className="px-3 py-1.5 text-right font-semibold text-surface-900">{fmt(data.amount)}</td>
                                  <td className="px-3 py-1.5">
                                    <span className={cn('inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold', grantStyle(data.grant))}>
                                      {data.grant}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>

                          {emp.note && (
                            <div className="px-4 py-2 bg-amber-50 border-t border-amber-100">
                              <p className="text-[11px] text-amber-700"><Info size={10} className="inline mr-1" />{emp.note}</p>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Period summary */}
                <div className="grid grid-cols-2 gap-5">
                  <div className="card p-5">
                    <h3 className="text-sm font-semibold text-surface-900 mb-3 flex items-center gap-2">
                      <BarChart2 size={14} className="text-primary-500" /> Total by Class
                    </h3>
                    <div className="space-y-2">
                      {Object.entries(selectedPeriod.period_class_totals)
                        .sort((a, b) => b[1] - a[1])
                        .map(([cls, amt]) => {
                          const pct = (amt / selectedPeriod.period_total_cost) * 100
                          return (
                            <div key={cls}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="font-medium text-surface-700">{cls}</span>
                                <span className="font-semibold text-surface-900">{fmt(amt)}</span>
                              </div>
                              <div className="h-1.5 rounded-full bg-surface-100">
                                <div className="h-1.5 rounded-full bg-primary-400" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          )
                        })}
                    </div>
                  </div>

                  <div className="card p-5">
                    <h3 className="text-sm font-semibold text-surface-900 mb-3 flex items-center gap-2">
                      <DollarSign size={14} className="text-emerald-500" /> Total by Grant
                    </h3>
                    <div className="space-y-2">
                      {Object.entries(selectedPeriod.period_grant_totals)
                        .sort((a, b) => b[1] - a[1])
                        .map(([grant, amt]) => (
                          <div key={grant} className="flex items-center justify-between rounded-lg border px-3 py-2">
                            <span className={cn('text-[11px] font-semibold rounded-full border px-2 py-0.5 flex items-center gap-1', grantStyle(grant))}>
                              {grant === 'PENDING' && <AlertTriangle size={10} />}
                              {grant}
                            </span>
                            <span className="text-xs font-bold text-surface-900">{fmt(amt)}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                </div>
              </>
            )}

            {!periods.length && !loading && (
              <div className="card p-12 flex flex-col items-center gap-4 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-50 ring-1 ring-primary-200">
                  <Upload size={24} className="text-primary-500" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-surface-800">Upload your Gusto payroll export</p>
                  <p className="text-xs text-surface-400 mt-1 max-w-sm">
                    Descarga el resumen de nómina de Gusto como Excel y súbelo aquí. El sistema aplica la matriz de asignación y muestra el costo por clase y grant, con lógica waterfall (B3 → FIRST CITIZEN → PENDING, etc.).
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══ TAB: Grant Budget Tracker ════════════════════════════════════ */}
        {tab === 'budget' && (
          <div className="space-y-5">
            {!hasBudget ? (
              <div className="card p-10 flex flex-col items-center gap-3 text-center">
                <TrendingUp size={28} className="text-surface-300" />
                <p className="text-sm font-medium text-surface-600">No data yet</p>
                <p className="text-xs text-surface-400">Upload a Gusto file in the Allocation Calculator tab first.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 rounded-xl bg-blue-50 border border-blue-200 px-4 py-3">
                  <Info size={14} className="text-blue-500 shrink-0" />
                  <p className="text-xs text-blue-700">
                    Muestra el presupuesto acumulado de todos los {totalPeriods} períodos procesados. Los grants se van agotando en orden: cuando uno se termina, el siguiente toma el relevo.
                  </p>
                </div>

                <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
                  {Object.entries(budgetStatus).map(([empKey, grants]) => {
                    const empName = Object.values(grants).length > 0
                      ? empKey === 'Santander' ? 'Santander Arguelles'
                      : empKey === 'Mileyka' ? 'Mileyka Burgos-Flores'
                      : empKey === 'Meysa' ? 'Meysa Arguelles'
                      : empKey === 'Drelly' ? 'Drelly Rios'
                      : empKey === 'Maricarmen' ? 'Maricarmen Buraschi'
                      : empKey === 'Fernando' ? 'Fernando Ortiz'
                      : empKey
                      : empKey
                    const hasExhausted = Object.values(grants).some(g => g.exhausted)
                    const hasPending   = Object.values(grants).some(g => g.remaining <= 0 && g.original > 0)

                    return (
                      <div key={empKey} className={cn('card overflow-hidden', hasExhausted && 'ring-1 ring-amber-200')}>
                        <div className={cn('flex items-center justify-between px-4 py-3 border-b', hasExhausted ? 'bg-amber-50 border-amber-100' : 'bg-surface-50 border-surface-100')}>
                          <div className="flex items-center gap-2">
                            <Users size={14} className="text-surface-500" />
                            <p className="text-xs font-bold text-surface-900">{empName}</p>
                          </div>
                          {hasExhausted && (
                            <span className="text-[10px] font-semibold bg-amber-100 text-amber-700 border border-amber-300 rounded-full px-2 py-0.5">
                              Grant exhausted
                            </span>
                          )}
                        </div>

                        <div className="p-4 space-y-3">
                          {Object.entries(grants).map(([gname, info]) => {
                            const usedPct = info.original > 0 ? (info.used / info.original) * 100 : 0
                            const isExhausted = info.exhausted
                            return (
                              <div key={gname}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className={cn('text-[11px] font-semibold rounded-full border px-2 py-0.5', grantStyle(gname))}>
                                    {gname}
                                  </span>
                                  <div className="text-right">
                                    {isExhausted ? (
                                      <span className="text-[11px] font-bold text-red-600">EXHAUSTED</span>
                                    ) : (
                                      <span className="text-[11px] font-semibold text-emerald-700">
                                        {fmt(info.remaining)} left
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <div className="h-2 rounded-full bg-surface-100">
                                  <div
                                    className={cn('h-2 rounded-full transition-all', isExhausted ? 'bg-red-400' : 'bg-emerald-400')}
                                    style={{ width: `${Math.min(usedPct, 100)}%` }}
                                  />
                                </div>
                                <div className="flex justify-between mt-0.5">
                                  <span className="text-[10px] text-surface-400">Used: {fmt(info.used)}</span>
                                  <span className="text-[10px] text-surface-400">Budget: {fmt(info.original)}</span>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {/* ══ TAB: Allocation Matrix ══════════════════════════════════════ */}
        {tab === 'matrix' && (
          <div className="space-y-4">
            {matrixLoading && (
              <div className="flex items-center justify-center h-48 gap-2 text-surface-400">
                <Loader2 size={18} className="animate-spin" /><span className="text-sm">Loading matrix…</span>
              </div>
            )}
            {matrix && Object.entries(matrix.matrix).map(([key, emp]) => (
              <div key={key} className="card overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 bg-surface-50 border-b border-surface-100">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-100">
                      <Users size={14} className="text-primary-600" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-surface-900">{emp.full_name}</p>
                      <p className="text-[11px] text-surface-400">{emp.title}</p>
                    </div>
                  </div>
                  {emp.note && (
                    <div className="flex items-center gap-1 text-[11px] text-amber-600 max-w-xs text-right">
                      <Info size={11} className="shrink-0" />{emp.note}
                    </div>
                  )}
                </div>

                <div className="flex divide-x divide-surface-100">
                  {/* Classes */}
                  <div className="flex-1 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-surface-400 mb-2">
                      Classes — Empleado/a
                    </p>
                    <div className="space-y-1.5">
                      {Object.entries(emp.classes).map(([cls, pct]) => (
                        <div key={cls} className="flex items-center justify-between">
                          <span className="text-xs text-surface-700">{cls}</span>
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-20 rounded-full bg-surface-100">
                              <div className="h-1.5 rounded-full bg-primary-400" style={{ width: `${(pct as number) * 100}%` }} />
                            </div>
                            <span className="text-[11px] font-semibold text-surface-600 w-8 text-right">
                              {((pct as number) * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Contractor classes (Meysa) */}
                    {(emp as any).contractor && (
                      <div className="mt-3 pt-3 border-t border-surface-100">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-500 mb-2">
                          Classes — Contratista ({(emp as any).contractor.start_date} · ${(emp as any).contractor.monthly_amount.toLocaleString()}/mes)
                        </p>
                        <div className="space-y-1.5">
                          {Object.entries((emp as any).contractor.classes).map(([cls, pct]) => (
                            <div key={cls} className="flex items-center justify-between">
                              <span className="text-xs text-surface-700">{cls}</span>
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-20 rounded-full bg-amber-100">
                                  <div className="h-1.5 rounded-full bg-amber-400" style={{ width: `${(pct as number) * 100}%` }} />
                                </div>
                                <span className="text-[11px] font-semibold text-amber-700 w-8 text-right">
                                  {((pct as number) * 100).toFixed(0)}%
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Grant rules */}
                  <div className="flex-1 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-surface-400 mb-2">Grant Waterfall</p>
                    <div className="space-y-2">
                      {/* Employee grant rules */}
                      {(emp as any).grant_rules?.map((pool: any, pi: number) => (
                        <div key={pi} className="rounded-lg border border-surface-100 p-2.5">
                          <p className="text-[10px] text-surface-400 mb-1.5">
                            Covers: <span className="font-medium text-surface-600">{pool.pool_classes.join(', ')}</span>
                          </p>
                          <div className="space-y-1">
                            {pool.waterfall.map((g: any, gi: number) => (
                              <div key={g.name} className="flex items-center gap-2">
                                <span className="text-[10px] text-surface-400 w-3">{gi + 1}.</span>
                                <span className={cn('text-[11px] font-semibold rounded-full border px-2 py-0.5', grantStyle(g.name))}>
                                  {g.name}
                                </span>
                                <span className="text-[10px] text-surface-500 ml-auto">{fmt(g.annual_budget)}/yr</span>
                              </div>
                            ))}
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[10px] text-surface-400 w-3">↓</span>
                              <span className={cn('text-[11px] font-semibold rounded-full border px-2 py-0.5', grantStyle('PENDING'))}>
                                PENDING
                              </span>
                              <span className="text-[10px] text-surface-400 ml-auto">if all exhausted</span>
                            </div>
                          </div>
                        </div>
                      ))}

                      {/* Contractor grant rules (Meysa) */}
                      {(emp as any).contractor?.grant_rules?.map((pool: any, pi: number) => (
                        <div key={`c-${pi}`} className="rounded-lg border border-amber-200 bg-amber-50 p-2.5">
                          <p className="text-[10px] text-amber-600 font-semibold mb-1">CONTRATISTA</p>
                          <p className="text-[10px] text-surface-400 mb-1.5">
                            Covers: <span className="font-medium text-surface-600">{pool.pool_classes.join(', ')}</span>
                          </p>
                          <div className="space-y-1">
                            {pool.waterfall.map((g: any, gi: number) => (
                              <div key={g.name} className="flex items-center gap-2">
                                <span className="text-[10px] text-amber-400 w-3">{gi + 1}.</span>
                                <span className={cn('text-[11px] font-semibold rounded-full border px-2 py-0.5', grantStyle(g.name))}>
                                  {g.name}
                                </span>
                                <span className="text-[10px] text-surface-500 ml-auto">{fmt(g.annual_budget)}/yr</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ══ TAB: Journal Entry ══════════════════════════════════════════ */}
        {tab === 'journal' && (
          <div className="space-y-4">
            {!journalEntries.length ? (
              <div className="card p-10 flex flex-col items-center gap-3 text-center">
                <FileText size={28} className="text-surface-300" />
                <p className="text-sm font-medium text-surface-600">No journal entries yet</p>
                <p className="text-xs text-surface-400">Upload a Gusto file in the Allocation Calculator tab first.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <label className="text-xs font-medium text-surface-600">Pay Period:</label>
                  <div className="relative">
                    <select
                      value={selectedPeriodIdx}
                      onChange={e => setSelectedPeriodIdx(Number(e.target.value))}
                      className="appearance-none rounded-lg border border-surface-200 bg-white px-3 py-2 pr-8 text-xs font-medium text-surface-800 focus:border-primary-400 focus:outline-none"
                    >
                      {periods.map((p, i) => (
                        <option key={i} value={i}>{p.period} · Pay {p.payday}</option>
                      ))}
                    </select>
                    <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
                  </div>
                </div>

                {selectedJE && (
                  <div className="card overflow-hidden">
                    <div className="px-5 py-3 bg-surface-50 border-b border-surface-100 flex items-center justify-between">
                      <div>
                        <p className="text-sm font-bold text-surface-900">{selectedJE.memo}</p>
                        <p className="text-[11px] text-surface-400">Date: {selectedJE.date}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-surface-400">Total</p>
                        <p className="text-sm font-bold text-surface-900">{fmt(selectedJE.total)}</p>
                      </div>
                    </div>

                    <div className="px-5 py-3 bg-blue-50 border-b border-blue-100 flex items-start gap-2">
                      <Building2 size={13} className="text-blue-500 shrink-0 mt-0.5" />
                      <p className="text-[11px] text-blue-700">
                        En QBO: <strong>+New → Journal Entry</strong>. Fecha: {selectedJE.date}. Agrega cada línea de débito con Account, Class y Customer/Project. Una línea de crédito a Wages Payable.
                      </p>
                    </div>

                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-surface-100 text-surface-400 text-[11px]">
                          <th className="px-4 py-2.5 text-left font-medium w-8">#</th>
                          <th className="px-3 py-2.5 text-left font-medium">Account</th>
                          <th className="px-3 py-2.5 text-left font-medium">Class</th>
                          <th className="px-3 py-2.5 text-left font-medium">Customer / Grant</th>
                          <th className="px-3 py-2.5 text-left font-medium">Employee</th>
                          <th className="px-3 py-2.5 text-right font-medium">Debit</th>
                          <th className="px-3 py-2.5 text-right font-medium">Credit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedJE.debit_lines.map((line, i) => (
                          <tr key={i} className="border-b border-surface-50 hover:bg-surface-50/50">
                            <td className="px-4 py-1.5 text-surface-400">{i + 1}</td>
                            <td className="px-3 py-1.5 font-medium text-surface-800">{line.account}</td>
                            <td className="px-3 py-1.5 text-surface-600">{line.class}</td>
                            <td className="px-3 py-1.5">
                              <span className={cn('rounded-full border px-1.5 py-0.5 text-[10px] font-semibold', grantStyle(line.customer ?? ''))}>
                                {line.customer}
                              </span>
                            </td>
                            <td className="px-3 py-1.5 text-surface-400 text-[10px]">{line.employee}</td>
                            <td className="px-3 py-1.5 text-right font-semibold text-surface-900">{fmt(line.amount)}</td>
                            <td className="px-3 py-1.5 text-right text-surface-300">—</td>
                          </tr>
                        ))}
                        <tr className="border-b-2 border-surface-200 bg-surface-50">
                          <td colSpan={5} className="px-4 py-2 text-xs font-semibold text-surface-700 text-right">Total Debits</td>
                          <td className="px-3 py-2 text-right font-bold text-surface-900">{fmt(selectedJE.total)}</td>
                          <td />
                        </tr>
                        <tr className="bg-emerald-50/30">
                          <td className="px-4 py-1.5 text-surface-400">{selectedJE.debit_lines.length + 1}</td>
                          <td className="px-3 py-1.5 font-medium text-surface-800">{selectedJE.credit_line.account}</td>
                          <td className="px-3 py-1.5 text-surface-400">—</td>
                          <td className="px-3 py-1.5 text-surface-400">—</td>
                          <td className="px-3 py-1.5 text-surface-400 text-[10px]">—</td>
                          <td className="px-3 py-1.5 text-right text-surface-300">—</td>
                          <td className="px-3 py-1.5 text-right font-bold text-emerald-700">{fmt(selectedJE.credit_line.amount)}</td>
                        </tr>
                      </tbody>
                    </table>

                    <div className="px-5 py-3 border-t border-surface-100 flex items-center justify-between bg-surface-50">
                      <p className="text-[11px] text-surface-400">
                        {selectedJE.debit_lines.length} lines · Debit = Credit = {fmt(selectedJE.total)}
                      </p>
                      <span className={cn(
                        'text-[11px] font-semibold px-2.5 py-1 rounded-full',
                        Math.abs(selectedJE.total - selectedJE.credit_line.amount) < 0.02
                          ? 'bg-emerald-100 text-emerald-700'
                          : 'bg-red-100 text-red-700',
                      )}>
                        {Math.abs(selectedJE.total - selectedJE.credit_line.amount) < 0.02 ? '✓ Balanced' : '⚠ Out of balance'}
                      </span>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* ══ QBO Post Modal ══════════════════════════════════════════════════ */}
      {qboModalOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setQboModalOpen(false)}
          />
          {/* Panel */}
          <div className="relative z-10 h-full w-[520px] overflow-y-auto bg-white shadow-2xl border-l border-surface-200 flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-surface-100 bg-surface-50 shrink-0">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-100">
                  <Send size={13} className="text-primary-600" />
                </div>
                <div>
                  <p className="text-sm font-bold text-surface-900">Post Allocations to QBO</p>
                  {selectedPeriod && (
                    <p className="text-[11px] text-surface-400">{selectedPeriod.period}</p>
                  )}
                </div>
              </div>
              <button onClick={() => setQboModalOpen(false)} className="p-1.5 rounded-lg hover:bg-surface-100 text-surface-400">
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 p-5 space-y-4">
              {/* Success state */}
              {qboPostResult && (
                <div className="space-y-3">
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 size={16} className="text-emerald-600" />
                      <p className="text-sm font-bold text-emerald-800">
                        {qboPostResult.expenses_created.length} Expenses created in QBO
                      </p>
                    </div>
                    <p className="text-sm font-bold text-emerald-900">{fmt(qboPostResult.total_posted)}</p>
                  </div>

                  <div className="space-y-2">
                    {qboPostResult.expenses_created.map((exp) => (
                      <div key={exp.expense_id} className="rounded-lg border border-surface-200 px-3 py-2 flex items-center justify-between">
                        <div>
                          <p className="text-xs font-semibold text-surface-800">{exp.employee_name}</p>
                          <p className="text-[11px] text-surface-400">{exp.doc_number} · {exp.line_count} lines</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-bold text-surface-900">{fmt(exp.total ?? 0)}</p>
                          <a href={exp.qbo_link} target="_blank" rel="noopener noreferrer"
                            className="text-primary-600 hover:text-primary-700">
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>

                  {qboPostResult.errors.length > 0 && (
                    <div className="rounded-lg bg-red-50 border border-red-200 p-3 space-y-1">
                      <p className="text-[11px] font-semibold text-red-700">Errors</p>
                      {qboPostResult.errors.map((e, i) => (
                        <p key={i} className="text-[11px] text-red-700">✕ {e}</p>
                      ))}
                    </div>
                  )}
                  {qboPostResult.warnings.length > 0 && (
                    <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-1">
                      {qboPostResult.warnings.slice(0, 4).map((w, i) => (
                        <p key={i} className="text-[11px] text-amber-700">⚠ {w}</p>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={() => { setQboPostResult(null); setQboPreview(null) }}
                    className="w-full rounded-lg border border-surface-200 px-3 py-2 text-xs font-medium text-surface-600 hover:bg-surface-50"
                  >
                    Post another period
                  </button>
                </div>
              )}

              {!qboPostResult && (
                <>
                  {/* Step 1: QBO Company */}
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-surface-700 flex items-center gap-1">
                      <Building2 size={12} className="text-surface-400" /> QBO Company
                    </p>
                    {qboCompanies.length === 0 ? (
                      <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
                        <AlertCircle size={13} className="text-amber-500" />
                        <p className="text-xs text-amber-700">No QBO companies connected. Connect QBO in Integrations first.</p>
                      </div>
                    ) : (
                      <div className="relative">
                        <select
                          value={qboRealm}
                          onChange={e => { setQboRealm(e.target.value); setQboPreview(null) }}
                          className="w-full appearance-none rounded-lg border border-surface-200 bg-white px-3 py-2.5 pr-8 text-xs font-medium text-surface-800 focus:border-primary-400 focus:outline-none"
                        >
                          {qboCompanies.map(c => (
                            <option key={c.realm_id} value={c.realm_id}>{c.company_name}</option>
                          ))}
                        </select>
                        <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-surface-400" />
                      </div>
                    )}
                  </div>

                  {/* Step 2: Account settings */}
                  <div className="rounded-xl border border-surface-200 p-3 space-y-2.5">
                    <p className="text-[11px] font-semibold text-surface-500 uppercase tracking-wider">QBO Account Names</p>
                    <div className="grid grid-cols-2 gap-2.5">
                      {[
                        { label: 'Vendor (Payee)',    val: qboVendor,              set: setQboVendor,              ph: 'Gusto' },
                        { label: 'Bank Account',      val: qboBankAccount,         set: setQboBankAccount,         ph: '1112 Cash:Payroll' },
                        { label: 'Expense Account',   val: qboAccount,             set: setQboAccount,             ph: '6110 Personnel:Salaries' },
                        { label: 'Tax Liability',     val: qboTaxAccount,          set: setQboTaxAccount,          ph: '2131 Payroll Tax' },
                        { label: 'Health Liability',  val: qboHealthAccount,       set: setQboHealthAccount,       ph: '2136 Health Benefits' },
                        { label: 'Tax Expense Acct',  val: qboTaxExpenseAccount,   set: setQboTaxExpenseAccount,   ph: '6130 Payroll Taxes' },
                        { label: 'Health Expense Acct',val: qboHealthExpenseAccount,set: setQboHealthExpenseAccount,ph: '6155 Health Benefits' },
                        { label: 'Dental Expense Acct',val: qboDentalExpenseAccount,set: setQboDentalExpenseAccount,ph: '6152 Vision and Dental' },
                        { label: 'Dental Vendor',     val: qboDentalVendor,        set: setQboDentalVendor,        ph: 'The Guardian' },
                      ].map(({ label, val, set, ph }) => (
                        <div key={label} className="space-y-1">
                          <label className="text-[10px] font-semibold text-surface-500">{label}</label>
                          <input
                            value={val}
                            onChange={e => { set(e.target.value); setQboPreview(null) }}
                            className="w-full rounded-lg border border-surface-200 px-2.5 py-1.5 text-[11px] focus:border-primary-400 focus:outline-none"
                            placeholder={ph}
                          />
                        </div>
                      ))}
                    </div>
                    <p className="text-[10px] text-surface-400">
                      Enter partial names — the agent uses fuzzy matching to find the exact QBO account.
                    </p>
                  </div>

                  {/* Preview button */}
                  {!qboPreview && (
                    <button
                      onClick={runQboPreview}
                      disabled={qboPreviewLoading || !qboRealm}
                      className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-primary-300 bg-primary-50 hover:bg-primary-100 text-primary-700 px-3 py-2.5 text-xs font-semibold transition-colors disabled:opacity-50"
                    >
                      {qboPreviewLoading
                        ? <><Loader2 size={12} className="animate-spin" /> Checking QBO…</>
                        : <><Eye size={12} /> Preview QBO Lookups</>
                      }
                    </button>
                  )}

                  {/* Error */}
                  {qboError && (
                    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                      <AlertCircle size={13} className="text-red-500 shrink-0 mt-0.5" />
                      <p className="text-xs text-red-700">{qboError}</p>
                    </div>
                  )}

                  {/* Preview results */}
                  {qboPreview && (
                    <div className="space-y-3">
                      {/* Lookup status */}
                      <div className="rounded-xl border border-surface-200 overflow-hidden">
                        <div className="px-3 py-2 bg-surface-50 border-b border-surface-100">
                          <p className="text-[11px] font-semibold text-surface-600 uppercase tracking-wider">QBO Lookups</p>
                        </div>
                        <div className="divide-y divide-surface-50">
                          {([
                            ['Vendor', qboPreview.qbo_lookups.vendor],
                            ['Bank Account', qboPreview.qbo_lookups.bank_account],
                            ['Expense Account', qboPreview.qbo_lookups.expense_account],
                            ['Tax Liability', qboPreview.qbo_lookups.tax_liability],
                            ['Health Liability', qboPreview.qbo_lookups.health_liability],
                            ['Tax Expense Acct', qboPreview.qbo_lookups.tax_expense],
                            ['Health Expense Acct', qboPreview.qbo_lookups.health_expense],
                            ['Dental Expense Acct', qboPreview.qbo_lookups.dental_expense],
                            ['Dental Vendor', qboPreview.qbo_lookups.dental_vendor],
                          ] as [string, PayrollQBOLookup][]).map(([label, info]) => (
                            <div key={label} className="flex items-center justify-between px-3 py-1.5">
                              <span className="text-[11px] text-surface-500">{label}: <span className="font-medium text-surface-700">"{info.searched}"</span></span>
                              {info.found
                                ? <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5 border border-emerald-200"><CheckCircle2 size={9} /> {info.qbo_name}</span>
                                : <span className="text-[10px] font-semibold text-red-600 bg-red-50 rounded-full px-2 py-0.5 border border-red-200">Not found</span>
                              }
                            </div>
                          ))}
                        </div>
                        {/* Classes */}
                        <div className="px-3 py-2 bg-surface-50/50 border-t border-surface-100">
                          <p className="text-[10px] font-semibold text-surface-400 mb-1.5 uppercase tracking-wider">Classes</p>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(qboPreview.qbo_lookups.classes).map(([cls, info]) => (
                              <span key={cls} className={cn('inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-2 py-0.5 border',
                                info.found ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-600 border-red-200')}>
                                {info.found ? <CheckCircle2 size={9} /> : <X size={9} />}{cls}
                              </span>
                            ))}
                          </div>
                        </div>
                        {/* Grants */}
                        <div className="px-3 py-2 border-t border-surface-100">
                          <p className="text-[10px] font-semibold text-surface-400 mb-1.5 uppercase tracking-wider">Grants (QBO Customers)</p>
                          <div className="flex flex-wrap gap-1.5">
                            {Object.entries(qboPreview.qbo_lookups.customers).map(([g, info]) => (
                              <span key={g} className={cn('inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-2 py-0.5 border',
                                info.found ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-600 border-red-200')}>
                                {info.found ? <CheckCircle2 size={9} /> : <X size={9} />}
                                {g}{info.found && info.qbo_name && info.qbo_name !== g ? ` → ${info.qbo_name}` : ''}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Per-employee expense preview */}
                      <div className="rounded-xl border border-surface-200 overflow-hidden">
                        <div className="px-3 py-2 bg-surface-50 border-b border-surface-100 flex items-center justify-between">
                          <p className="text-[11px] font-semibold text-surface-600 uppercase tracking-wider">
                            {qboPreview.employee_count} Expenses to Create
                          </p>
                          <p className="text-xs font-bold text-surface-900">{fmt(qboPreview.grand_total)}</p>
                        </div>
                        <div className="divide-y divide-surface-50">
                          {qboPreview.expenses_preview.map((ep) => (
                            <div key={ep.employee_name} className="px-3 py-2">
                              <div className="flex items-center justify-between">
                                <p className="text-xs font-semibold text-surface-800">{ep.employee_name}</p>
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] text-surface-400">{ep.total_lines} lines</span>
                                  <span className="text-xs font-bold text-surface-900">{fmt(ep.total)}</span>
                                </div>
                              </div>
                              <p className="text-[10px] text-surface-400 mt-0.5">{ep.doc_number}</p>
                              {/* First 2 lines preview */}
                              {ep.lines.slice(0, 2).map(line => (
                                <div key={line.Id} className="flex items-center justify-between mt-0.5 pl-2">
                                  <p className="text-[10px] text-surface-500 truncate max-w-[280px]">{line.Description}</p>
                                  <p className={cn('text-[10px] font-medium shrink-0 ml-2',
                                    line.Amount < 0 ? 'text-red-500' : 'text-surface-600')}>{fmt(line.Amount)}</p>
                                </div>
                              ))}
                              {ep.total_lines > 2 && (
                                <p className="text-[10px] text-surface-400 pl-2 mt-0.5">+ {ep.total_lines - 2} more…</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Warnings */}
                      {qboPreview.warnings.length > 0 && (
                        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-1">
                          <p className="text-[11px] font-semibold text-amber-700 mb-1">Warnings</p>
                          {qboPreview.warnings.map((w, i) => (
                            <p key={i} className="text-[11px] text-amber-700">⚠ {w}</p>
                          ))}
                        </div>
                      )}

                      {/* Change preview / Confirm */}
                      <div className="flex gap-2">
                        <button
                          onClick={() => { setQboPreview(null) }}
                          className="flex-1 rounded-lg border border-surface-200 px-3 py-2 text-xs font-medium text-surface-600 hover:bg-surface-50"
                        >
                          Change settings
                        </button>
                        <button
                          onClick={confirmQboPost}
                          disabled={!qboPreview.ready_to_post || qboPosting}
                          className={cn(
                            'flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors',
                            qboPreview.ready_to_post
                              ? 'bg-primary-600 hover:bg-primary-700 text-white'
                              : 'bg-surface-200 text-surface-400 cursor-not-allowed',
                          )}
                        >
                          {qboPosting
                            ? <><Loader2 size={12} className="animate-spin" /> Posting…</>
                            : <><ShieldCheck size={12} /> Confirm &amp; Post to QBO</>
                          }
                        </button>
                      </div>

                      {!qboPreview.ready_to_post && (
                        <p className="text-[11px] text-red-600 text-center">
                          Fix the missing vendor or expense account in QBO before posting.
                        </p>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
