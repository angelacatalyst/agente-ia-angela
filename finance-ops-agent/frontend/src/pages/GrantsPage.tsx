import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  ShieldCheck, Plus, Loader2, AlertTriangle,
  CheckCircle2, TrendingUp, Clock,
} from 'lucide-react'

interface Grant {
  id: string; name: string; funder: string; budget: number; spent: number
  endDate: string; status: 'on_track' | 'at_risk' | 'over_budget'
}

const MOCK_GRANTS: Grant[] = [
  { id: 'G001', name: 'Community Health Initiative', funder: 'HHS',        budget: 250000, spent: 182000, endDate: '2024-09-30', status: 'on_track'   },
  { id: 'G002', name: 'Youth Education Program',     funder: 'Dept of Ed', budget: 120000, spent: 115000, endDate: '2024-06-30', status: 'at_risk'    },
  { id: 'G003', name: 'Housing Stability Fund',      funder: 'HUD',        budget: 85000,  spent: 89200,  endDate: '2024-12-31', status: 'over_budget' },
]

const statusStyle: Record<string, { badge: string; icon: React.ReactNode }> = {
  on_track:   { badge: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200', icon: <CheckCircle2 size={13} className="text-emerald-500" /> },
  at_risk:    { badge: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',       icon: <AlertTriangle size={13} className="text-amber-500" /> },
  over_budget:{ badge: 'bg-red-50 text-red-700 ring-1 ring-red-200',            icon: <AlertTriangle size={13} className="text-red-500" /> },
}

const statusLabel: Record<string, string> = {
  on_track: 'On Track', at_risk: 'At Risk', over_budget: 'Over Budget',
}

function pct(spent: number, budget: number) {
  return Math.round((spent / budget) * 100)
}

export function GrantsPage() {
  const { t } = useI18n()
  const [selected, setSelected] = useState<Grant | null>(null)
  const [result, setResult] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Review grant compliance for: ${selected?.name ?? 'all grants'}. Budget: $${selected?.budget}, Spent: $${selected?.spent}`,
      module: 'grant_compliance',
    }),
    onSuccess: (d) => setResult(d.content),
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={ShieldCheck}
        title={t('page.grants.title')}
        subtitle={t('page.grants.subtitle')}
        badge="AI"
        actions={
          <button className="btn-primary text-[13px]">
            <Plus size={14} /> {t('common.new')} Grant
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* Summary KPIs */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Active Grants',   value: '3',        icon: <ShieldCheck size={16} className="text-primary-600" />, bg: 'bg-primary-50' },
            { label: 'Total Budget',    value: '$455,000', icon: <TrendingUp size={16} className="text-emerald-600" />,  bg: 'bg-emerald-50' },
            { label: 'Expiring Soon',   value: '1',        icon: <Clock size={16} className="text-amber-600" />,         bg: 'bg-amber-50'   },
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
          {/* Grant list */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-surface-900 mb-4">Active Grants</h2>
            <div className="space-y-3">
              {MOCK_GRANTS.map(g => {
                const p = pct(g.spent, g.budget)
                const { badge, icon } = statusStyle[g.status]
                return (
                  <button
                    key={g.id}
                    onClick={() => setSelected(g)}
                    className={cn(
                      'w-full text-left rounded-xl border p-4 transition-all hover:shadow-card-md',
                      selected?.id === g.id
                        ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                        : 'border-surface-200 hover:border-surface-300',
                    )}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="text-sm font-semibold text-surface-900">{g.name}</p>
                        <p className="text-[11px] text-surface-400">{g.funder} · Due {g.endDate}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        {icon}
                        <span className={`badge text-[10px] ${badge}`}>{statusLabel[g.status]}</span>
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs text-surface-600">
                        <span>${g.spent.toLocaleString()} spent</span>
                        <span className="font-medium">{p}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-surface-200 overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all', p > 100 ? 'bg-red-500' : p > 85 ? 'bg-amber-400' : 'bg-primary-500')}
                          style={{ width: `${Math.min(p, 100)}%` }}
                        />
                      </div>
                      <p className="text-[11px] text-surface-400">Budget: ${g.budget.toLocaleString()}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* AI Review */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-surface-900">AI Compliance Review</h2>
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="btn-primary text-[13px]"
              >
                {mutation.isPending
                  ? <><Loader2 size={13} className="animate-spin" /> Analyzing…</>
                  : <><ShieldCheck size={13} /> Run Review</>
                }
              </button>
            </div>

            {selected ? (
              <div className="mb-4 p-3 rounded-xl bg-surface-50 border border-surface-200 text-sm">
                <p className="font-medium text-surface-800">{selected.name}</p>
                <p className="text-xs text-surface-500">{selected.funder} · ${selected.spent.toLocaleString()} / ${selected.budget.toLocaleString()}</p>
              </div>
            ) : (
              <div className="mb-4 p-3 rounded-xl bg-primary-50 border border-primary-200">
                <p className="text-xs text-primary-700">Select a grant on the left to run a targeted review, or leave unselected for an all-grants review.</p>
              </div>
            )}

            {result ? (
              <div className="p-4 rounded-xl bg-surface-50 border border-surface-200 text-sm text-surface-800 whitespace-pre-wrap leading-relaxed">
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
