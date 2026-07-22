import { useEffect, useState } from 'react'
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
} from 'lucide-react'

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
      </div>
    </div>
  )
}
