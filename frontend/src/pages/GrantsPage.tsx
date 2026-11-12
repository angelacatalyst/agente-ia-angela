import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api } from '@/lib/api'
import type { QBODonor, QBOProject } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  ShieldCheck, Loader2, AlertTriangle,
  CheckCircle2, TrendingUp, Clock, RefreshCw, FolderOpen,
  Upload, Tag, ArrowRight, XCircle,
} from 'lucide-react'

// ── Types for Grant Tagging ────────────────────────────────────────────────

interface TagChange {
  purchase_id: string
  sync_token: string
  line_id: string
  txn_date: string
  vendor: string
  account_name: string
  class_name: string
  amount: number
  current_grant: string
  expected_grant: string
  expected_customer_id: string
  grant_name: string
}

interface TagPreviewResult {
  summary: {
    changes_needed: number
    already_correct: number
    no_rule_found: number
    multi_grant_lines: number
    grants_in_excel: number
    rules_parsed: number
  }
  changes: TagChange[]
  multi_grant_lines: { program: string; account_num: string; description: string; grants: { name: string; amount: number }[] }[]
}

const ALLAPATTAH_REALM = '9341454010854556'

export function GrantsPage() {
  const { t } = useI18n()
  const { selectedRealmId } = useAppStore()

  const [donors, setDonors] = useState<QBODonor[]>([])
  const [projects, setProjects] = useState<QBOProject[]>([])
  const [loading, setLoading] = useState(false)
  const [fetchedAt, setFetchedAt] = useState<string | null>(null)

  const [selectedItem, setSelectedItem] = useState<QBODonor | QBOProject | null>(null)
  const [result, setResult] = useState<string | null>(null)

  // Grant Tagging state
  const [tagFile, setTagFile] = useState<File | null>(null)
  const [tagPeriodStart, setTagPeriodStart] = useState('2026-01-01')
  const [tagPeriodEnd, setTagPeriodEnd] = useState('2026-12-31')
  const [tagLoading, setTagLoading] = useState(false)
  const [tagPreview, setTagPreview] = useState<TagPreviewResult | null>(null)
  const [tagApplyLoading, setTagApplyLoading] = useState(false)
  const [tagApplyResult, setTagApplyResult] = useState<{ applied: number; errors: number } | null>(null)
  const [tagError, setTagError] = useState<string | null>(null)
  const [selectedChanges, setSelectedChanges] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)

  const isAllapattah = selectedRealmId === ALLAPATTAH_REALM

  const load = async () => {
    if (!selectedRealmId) return
    setLoading(true)
    try {
      const data = await api.qboData.projects(selectedRealmId)
      setDonors(data.donors)
      setProjects(data.projects)
      setFetchedAt(data.fetched_at)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedRealmId) load()
  }, [selectedRealmId])

  const mutation = useMutation({
    mutationFn: () => {
      const name = (selectedItem as any)?.name ?? 'all grants'
      const balance = (selectedItem as any)?.balance_formatted ?? ''
      return api.chat({
        message: `Review grant compliance for: ${name}. ${balance ? `Current balance: ${balance}.` : ''} Pull all transactions, verify spending is allowable, check for any compliance issues, and report on grant status.`,
        module: 'grant_compliance',
        qbo_realm_id: selectedRealmId ?? undefined,
      })
    },
    onSuccess: (d) => setResult(d.content),
  })

  // Grant Tagging handlers
  const runTagPreview = async () => {
    if (!tagFile || !selectedRealmId) return
    setTagLoading(true)
    setTagError(null)
    setTagPreview(null)
    setTagApplyResult(null)
    setSelectedChanges(new Set())
    try {
      const result = await api.grants.tagPreview(tagFile, selectedRealmId, tagPeriodStart, tagPeriodEnd)
      setTagPreview(result)
      // Select all changes by default
      setSelectedChanges(new Set(result.changes.map((c: TagChange) => `${c.purchase_id}:${c.line_id}`)))
    } catch (err: any) {
      setTagError(err?.response?.data?.detail || err?.message || 'Error running preview')
    } finally {
      setTagLoading(false)
    }
  }

  const applyTagChanges = async () => {
    if (!tagPreview || !selectedRealmId) return
    const toApply = tagPreview.changes.filter(c => selectedChanges.has(`${c.purchase_id}:${c.line_id}`))
    if (toApply.length === 0) return
    setTagApplyLoading(true)
    try {
      const result = await api.grants.tagApply(selectedRealmId, toApply)
      setTagApplyResult({ applied: result.applied, errors: result.errors })
    } catch (err: any) {
      setTagError(err?.response?.data?.detail || err?.message || 'Error applying changes')
    } finally {
      setTagApplyLoading(false)
    }
  }

  const toggleChange = (key: string) => {
    setSelectedChanges(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // KPI totals
  const totalBalance = donors.reduce((sum, d) => sum + d.balance, 0)
  const activeGrants = isAllapattah ? projects.filter(p => p.status === 'IN_PROGRESS').length : donors.filter(d => d.active).length
  const withBalance = donors.filter(d => d.balance > 0).length

  // Items to show in list
  const listItems = isAllapattah && projects.length > 0 ? projects : donors

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={ShieldCheck}
        title={t('page.grants.title')}
        subtitle={isAllapattah ? 'Allapattah CDC · Live QBO data' : t('page.grants.subtitle')}
        badge="AI"
        actions={
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-surface-200 bg-white px-3 py-1.5 text-xs font-medium text-surface-600 hover:bg-surface-50 transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* KPIs */}
        <div className="grid grid-cols-3 gap-4">
          {[
            {
              label: isAllapattah ? 'Grant Projects' : 'Active Donors',
              value: loading ? '…' : String(activeGrants || listItems.length),
              icon: <ShieldCheck size={16} className="text-primary-600" />,
              bg: 'bg-primary-50',
            },
            {
              label: 'Total AR Balance',
              value: loading ? '…' : `$${totalBalance.toLocaleString('en-US', { minimumFractionDigits: 0 })}`,
              icon: <TrendingUp size={16} className="text-emerald-600" />,
              bg: 'bg-emerald-50',
            },
            {
              label: 'With Open Balance',
              value: loading ? '…' : String(withBalance),
              icon: <Clock size={16} className="text-amber-600" />,
              bg: 'bg-amber-50',
            },
          ].map(k => (
            <div key={k.label} className="card p-4 flex items-center gap-3">
              <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', k.bg)}>
                {k.icon}
              </div>
              <div>
                <p className="text-[11px] text-surface-500 font-medium">{k.label}</p>
                <p className="text-xl font-bold text-surface-900">{k.value}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-5">
          {/* Grant / Donor list */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-surface-900 mb-1">
              {isAllapattah ? 'Grant Projects & Donors' : 'Donors / Funders'}
            </h2>
            {fetchedAt && (
              <p className="text-[11px] text-surface-400 mb-3">
                Updated {new Date(fetchedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            )}

            {loading ? (
              <div className="flex items-center justify-center h-32 gap-2 text-surface-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-xs">Loading from QBO…</span>
              </div>
            ) : listItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-surface-400 gap-2">
                <FolderOpen size={24} className="text-surface-300" />
                <p className="text-xs">No grant data found in QBO</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                {listItems.map((item: any) => {
                  const balance = item.balance ?? 0
                  const isSelected = (selectedItem as any)?.id === item.id
                  const isProject = item.source === 'sub_customer' || item.source === 'project'

                  return (
                    <button
                      key={item.id}
                      onClick={() => { setSelectedItem(item); setResult(null) }}
                      className={cn(
                        'w-full text-left rounded-xl border p-3.5 transition-all hover:shadow-card-md',
                        isSelected
                          ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                          : 'border-surface-200 hover:border-surface-300',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-surface-900 truncate">{item.name}</p>
                          {item.customer_name && (
                            <p className="text-[11px] text-surface-400 truncate">Funder: {item.customer_name}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {isProject
                            ? <CheckCircle2 size={12} className="text-emerald-500" />
                            : balance > 0
                              ? <AlertTriangle size={12} className="text-amber-500" />
                              : <CheckCircle2 size={12} className="text-surface-300" />
                          }
                          <span className={cn(
                            'text-[10px] font-semibold px-1.5 py-0.5 rounded-full',
                            isProject
                              ? 'bg-emerald-50 text-emerald-700'
                              : balance > 0
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-surface-100 text-surface-500',
                          )}>
                            {isProject ? 'Project' : balance > 0 ? 'Open' : 'Clear'}
                          </span>
                        </div>
                      </div>
                      {balance > 0 && (
                        <p className="text-[11px] text-emerald-700 font-medium mt-1">
                          Balance: ${balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </p>
                      )}
                      {item.sub_projects > 0 && (
                        <p className="text-[11px] text-surface-400 mt-0.5">{item.sub_projects} project(s)</p>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* AI Review */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-surface-900">AI Compliance Review</h2>
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending || loading}
                className="btn-primary text-[13px]"
              >
                {mutation.isPending
                  ? <><Loader2 size={13} className="animate-spin" /> Analyzing…</>
                  : <><ShieldCheck size={13} /> Run Review</>
                }
              </button>
            </div>

            {selectedItem ? (
              <div className="mb-4 p-3 rounded-xl bg-surface-50 border border-surface-200 text-sm">
                <p className="font-medium text-surface-800">{(selectedItem as any).name}</p>
                {(selectedItem as any).balance_formatted && (
                  <p className="text-xs text-surface-500">Balance: {(selectedItem as any).balance_formatted}</p>
                )}
              </div>
            ) : (
              <div className="mb-4 p-3 rounded-xl bg-primary-50 border border-primary-200">
                <p className="text-xs text-primary-700">
                  Select a grant or donor on the left for a targeted review, or run an all-grants review.
                </p>
              </div>
            )}

            {result ? (
              <div className="p-4 rounded-xl bg-surface-50 border border-surface-200 text-sm text-surface-800 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
                {result}
              </div>
            ) : (
              <div className="flex h-40 items-center justify-center rounded-xl bg-surface-50 border border-dashed border-surface-200">
                <div className="text-center">
                  <ShieldCheck size={28} className="mx-auto mb-2 text-surface-300" />
                  <p className="text-sm text-surface-400">AI analysis will appear here</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Grant Tagging from Budget Excel ─────────────────────────────── */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Tag size={16} className="text-primary-600" />
            <h2 className="text-sm font-semibold text-surface-900">Asignar Grants a Gastos de QBO</h2>
          </div>
          <p className="text-xs text-surface-500">
            Sube el archivo Excel con la hoja BUDGET y el agente identifica qué transacciones de QBO
            necesitan que se les asigne o corrija el grant.
          </p>

          {/* File + period inputs */}
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[11px] font-medium text-surface-600 mb-1">Excel (BUDGET)</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={e => setTagFile(e.target.files?.[0] ?? null)}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 rounded-lg border border-dashed border-surface-300 bg-surface-50 px-3 py-2 text-xs text-surface-600 hover:border-primary-400 hover:bg-primary-50 transition-colors"
              >
                <Upload size={13} />
                {tagFile ? tagFile.name : 'Seleccionar archivo'}
              </button>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-surface-600 mb-1">Desde</label>
              <input
                type="date"
                value={tagPeriodStart}
                onChange={e => setTagPeriodStart(e.target.value)}
                className="rounded-lg border border-surface-200 px-2 py-1.5 text-xs text-surface-800 focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-surface-600 mb-1">Hasta</label>
              <input
                type="date"
                value={tagPeriodEnd}
                onChange={e => setTagPeriodEnd(e.target.value)}
                className="rounded-lg border border-surface-200 px-2 py-1.5 text-xs text-surface-800 focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            </div>
            <button
              onClick={runTagPreview}
              disabled={!tagFile || !selectedRealmId || tagLoading}
              className="btn-primary text-[13px]"
            >
              {tagLoading
                ? <><Loader2 size={13} className="animate-spin" /> Analizando…</>
                : <><Tag size={13} /> Ver Preview</>
              }
            </button>
          </div>

          {/* Error */}
          {tagError && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
              <XCircle size={13} />
              {tagError}
            </div>
          )}

          {/* Preview results */}
          {tagPreview && (
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Cambios necesarios', value: tagPreview.summary.changes_needed, color: 'text-amber-700 bg-amber-50 border-amber-200' },
                  { label: 'Ya correctos', value: tagPreview.summary.already_correct, color: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
                  { label: 'Sin regla', value: tagPreview.summary.no_rule_found, color: 'text-surface-600 bg-surface-50 border-surface-200' },
                  { label: 'Multi-grant (manual)', value: tagPreview.summary.multi_grant_lines, color: 'text-purple-700 bg-purple-50 border-purple-200' },
                ].map(s => (
                  <div key={s.label} className={cn('rounded-lg border p-3', s.color)}>
                    <p className="text-[11px] font-medium opacity-75">{s.label}</p>
                    <p className="text-xl font-bold">{s.value}</p>
                  </div>
                ))}
              </div>

              {/* Apply result */}
              {tagApplyResult && (
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-700 font-medium">
                  <CheckCircle2 size={13} />
                  {tagApplyResult.applied} transacciones actualizadas en QBO.
                  {tagApplyResult.errors > 0 && ` (${tagApplyResult.errors} errores)`}
                </div>
              )}

              {/* Changes table */}
              {tagPreview.changes.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-surface-700">
                      {selectedChanges.size} de {tagPreview.changes.length} cambios seleccionados
                    </p>
                    <button
                      onClick={applyTagChanges}
                      disabled={selectedChanges.size === 0 || tagApplyLoading}
                      className="btn-primary text-[12px]"
                    >
                      {tagApplyLoading
                        ? <><Loader2 size={12} className="animate-spin" /> Aplicando…</>
                        : <><CheckCircle2 size={12} /> Aplicar en QBO ({selectedChanges.size})</>
                      }
                    </button>
                  </div>

                  <div className="rounded-xl border border-surface-200 overflow-hidden">
                    <div className="max-h-72 overflow-y-auto">
                      <table className="w-full text-[11px]">
                        <thead className="bg-surface-50 sticky top-0 border-b border-surface-200">
                          <tr>
                            <th className="px-2 py-2 text-left font-medium text-surface-500 w-7">
                              <input
                                type="checkbox"
                                checked={selectedChanges.size === tagPreview.changes.length}
                                onChange={() => {
                                  if (selectedChanges.size === tagPreview.changes.length) {
                                    setSelectedChanges(new Set())
                                  } else {
                                    setSelectedChanges(new Set(tagPreview.changes.map(c => `${c.purchase_id}:${c.line_id}`)))
                                  }
                                }}
                              />
                            </th>
                            <th className="px-2 py-2 text-left font-medium text-surface-500">Fecha</th>
                            <th className="px-2 py-2 text-left font-medium text-surface-500">Proveedor</th>
                            <th className="px-2 py-2 text-left font-medium text-surface-500">Cuenta</th>
                            <th className="px-2 py-2 text-right font-medium text-surface-500">Monto</th>
                            <th className="px-2 py-2 text-left font-medium text-surface-500">Grant actual</th>
                            <th className="px-2 py-2 w-4" />
                            <th className="px-2 py-2 text-left font-medium text-surface-500">Grant correcto</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-surface-100">
                          {tagPreview.changes.map(c => {
                            const key = `${c.purchase_id}:${c.line_id}`
                            const checked = selectedChanges.has(key)
                            return (
                              <tr
                                key={key}
                                onClick={() => toggleChange(key)}
                                className={cn(
                                  'cursor-pointer transition-colors',
                                  checked ? 'bg-primary-50 hover:bg-primary-100' : 'hover:bg-surface-50',
                                )}
                              >
                                <td className="px-2 py-2">
                                  <input type="checkbox" checked={checked} onChange={() => toggleChange(key)} onClick={e => e.stopPropagation()} />
                                </td>
                                <td className="px-2 py-2 text-surface-600 whitespace-nowrap">{c.txn_date}</td>
                                <td className="px-2 py-2 text-surface-800 max-w-[120px] truncate">{c.vendor || '—'}</td>
                                <td className="px-2 py-2 text-surface-500 max-w-[100px] truncate">{c.account_name}</td>
                                <td className="px-2 py-2 text-right text-surface-800 font-medium whitespace-nowrap">
                                  ${c.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                </td>
                                <td className="px-2 py-2 text-red-600 max-w-[120px] truncate">{c.current_grant}</td>
                                <td className="px-2 py-2 text-surface-300"><ArrowRight size={10} /></td>
                                <td className="px-2 py-2 text-emerald-700 font-medium max-w-[140px] truncate">{c.expected_grant}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {tagPreview.changes.length === 0 && (
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-700">
                  <CheckCircle2 size={13} />
                  Todas las transacciones ya tienen el grant correcto.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
