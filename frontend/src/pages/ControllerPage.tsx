import { useState } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import {
  LayoutDashboard, TrendingUp, AlertTriangle, CheckCircle2,
  ArrowUpRight, ArrowDownRight, RefreshCw, Download,
} from 'lucide-react'

const KPI = [
  { label: 'Cash Position',      value: '$284,500', delta: '+$12,400', up: true  },
  { label: 'AR Outstanding',     value: '$94,200',  delta: '-$8,300',  up: false },
  { label: 'AP Due (7d)',        value: '$31,750',  delta: '+$4,100',  up: false },
  { label: 'Grant Utilization',  value: '73%',      delta: '+5%',      up: true  },
]

const ALERTS = [
  { level: 'high',   text: 'Invoice #1042 overdue by 14 days — $8,500' },
  { level: 'medium', text: 'Bank rec unreconciled for March' },
  { level: 'low',    text: '2 vendor W-9 forms pending collection' },
]

const PRIORITIES = [
  'Review April grant expenditure report',
  'Approve 3 pending payment requests',
  'Complete EOD reconciliation',
  'Schedule board financial presentation',
]

const levelStyle: Record<string, string> = {
  high:   'bg-red-50 text-red-700 ring-1 ring-red-200',
  medium: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  low:    'bg-blue-50 text-blue-700 ring-1 ring-blue-200',
}

export function ControllerPage() {
  const { t } = useI18n()
  const [spinning, setSpinning] = useState(false)

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={LayoutDashboard}
        title={t('page.controller.title')}
        subtitle={t('page.controller.subtitle')}
        badge="AI"
        actions={
          <>
            <button
              onClick={() => { setSpinning(true); setTimeout(() => setSpinning(false), 1200) }}
              className="btn-ghost text-[13px] gap-1.5"
            >
              <RefreshCw size={14} className={spinning ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button className="btn-primary text-[13px]">
              <Download size={14} />
              {t('common.export')}
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        {/* KPIs */}
        <div className="grid grid-cols-4 gap-4">
          {KPI.map(k => (
            <div key={k.label} className="card p-5 space-y-3">
              <p className="text-[12px] font-medium text-surface-500">{k.label}</p>
              <p className="text-2xl font-bold text-surface-900 tracking-tight">{k.value}</p>
              <div className="flex items-center gap-1.5">
                {k.up
                  ? <ArrowUpRight size={13} className="text-emerald-500" />
                  : <ArrowDownRight size={13} className="text-red-500" />
                }
                <span className={`text-xs font-semibold ${k.up ? 'text-emerald-600' : 'text-red-600'}`}>
                  {k.delta}
                </span>
                <span className="text-[11px] text-surface-400">vs last week</span>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-5">
          {/* Alerts */}
          <div className="col-span-2 card p-5">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={16} className="text-amber-500" />
              <h2 className="text-sm font-semibold text-surface-900">Priority Alerts</h2>
              <span className="badge bg-red-50 text-red-600 ring-1 ring-red-200 ml-auto">
                {ALERTS.filter(a => a.level === 'high').length} High
              </span>
            </div>
            <div className="space-y-2">
              {ALERTS.map((a, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-surface-50 border border-surface-100">
                  <span className={`badge shrink-0 mt-px capitalize ${levelStyle[a.level]}`}>{a.level}</span>
                  <p className="text-sm text-surface-700">{a.text}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Today's Priorities */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle2 size={16} className="text-primary-600" />
              <h2 className="text-sm font-semibold text-surface-900">Today's Priorities</h2>
            </div>
            <div className="space-y-3">
              {PRIORITIES.map((p, i) => (
                <label key={i} className="flex items-start gap-2.5 cursor-pointer group">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded border-surface-300 accent-primary-600 cursor-pointer shrink-0"
                  />
                  <span className="text-sm text-surface-700 group-hover:text-surface-900 leading-snug">
                    {p}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Trend chart placeholder */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={16} className="text-primary-600" />
            <h2 className="text-sm font-semibold text-surface-900">Cash Flow — Last 30 Days</h2>
            <span className="ml-auto text-xs text-surface-400">Connect QBO for live data</span>
          </div>
          <div className="h-44 rounded-xl bg-gradient-to-br from-surface-50 to-primary-50 border border-dashed border-primary-200 flex items-center justify-center">
            <div className="text-center space-y-2">
              <TrendingUp size={28} className="text-primary-300 mx-auto" />
              <p className="text-xs text-surface-400 font-medium">Live chart available after QuickBooks connection</p>
              <button className="btn-primary text-xs px-4 py-1.5">
                {t('common.connect')} QuickBooks
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
