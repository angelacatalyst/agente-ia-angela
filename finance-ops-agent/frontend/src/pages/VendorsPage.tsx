import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  UserPlus, Loader2, CheckCircle2, AlertCircle, Plus,
  Building2, Mail, Phone, FileCheck,
} from 'lucide-react'

interface Vendor {
  id: string; name: string; type: string; ein: string
  w9: 'collected' | 'pending' | 'expired'; ytd: string; needs1099: boolean
}

const VENDORS: Vendor[] = [
  { id: 'V001', name: 'Consulting Partners LLC', type: 'LLC',        ein: '**-**1234', w9: 'collected', ytd: '$18,500', needs1099: true  },
  { id: 'V002', name: 'DataSoft Inc.',            type: 'Corp',      ein: '**-**5678', w9: 'collected', ytd: '$6,200',  needs1099: false },
  { id: 'V003', name: 'Jane Doe (Contractor)',    type: 'Individual', ein: 'Pending',  w9: 'pending',   ytd: '$4,800',  needs1099: true  },
]

const w9Style: Record<string, string> = {
  collected: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  pending:   'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  expired:   'bg-red-50 text-red-700 ring-1 ring-red-200',
}

export function VendorsPage() {
  const { t } = useI18n()
  const [name, setName]       = useState('')
  const [email, setEmail]     = useState('')
  const [phone, setPhone]     = useState('')
  const [type, setType]       = useState('LLC')
  const [result, setResult]   = useState<string | null>(null)
  const [selected, setSelected] = useState<Vendor | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Onboard new vendor: Name=${name}, Email=${email}, Phone=${phone}, EntityType=${type}. Generate onboarding checklist.`,
      module: 'vendor_onboarding',
    }),
    onSuccess: (d) => setResult(d.content),
  })

  return (
    <div className="flex h-screen flex-col bg-surface-50">
      <PageHeader
        icon={UserPlus}
        title={t('page.vendors.title')}
        subtitle={t('page.vendors.subtitle')}
        badge="AI"
        actions={
          <button className="btn-primary text-[13px]">
            <Plus size={14} /> {t('common.new')} Vendor
          </button>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-2 gap-5">
          {/* Vendor list */}
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-surface-900 mb-4">Vendor Roster</h2>
            <div className="space-y-2">
              {VENDORS.map(v => (
                <button
                  key={v.id}
                  onClick={() => setSelected(v)}
                  className={cn(
                    'w-full text-left rounded-xl border p-4 transition-all hover:shadow-card-md',
                    selected?.id === v.id
                      ? 'border-primary-400 bg-primary-50 ring-1 ring-primary-200'
                      : 'border-surface-200 hover:border-surface-300',
                  )}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-100 shrink-0">
                        <Building2 size={14} className="text-surface-500" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-surface-900">{v.name}</p>
                        <p className="text-[11px] text-surface-400">{v.type} · EIN: {v.ein}</p>
                      </div>
                    </div>
                    <span className={`badge ${w9Style[v.w9]} capitalize`}>W-9 {v.w9}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-surface-500">YTD Payments: <strong className="text-surface-700">{v.ytd}</strong></span>
                    {v.needs1099 && (
                      <span className="badge bg-blue-50 text-blue-700 ring-1 ring-blue-200 text-[10px]">1099 Required</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Onboarding form + AI */}
          <div className="space-y-5">
            <div className="card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-surface-900">Onboard New Vendor</h2>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Vendor Name</label>
                <div className="relative">
                  <Building2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                  <input className="input pl-8" placeholder="Company or individual name" value={name} onChange={e => setName(e.target.value)} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Email</label>
                  <div className="relative">
                    <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                    <input className="input pl-8" placeholder="vendor@email.com" value={email} onChange={e => setEmail(e.target.value)} />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-surface-600 mb-1.5">Phone</label>
                  <div className="relative">
                    <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
                    <input className="input pl-8" placeholder="+1 (555) 000-0000" value={phone} onChange={e => setPhone(e.target.value)} />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-surface-600 mb-1.5">Entity Type</label>
                <select className="input" value={type} onChange={e => setType(e.target.value)}>
                  {['Individual', 'LLC', 'Corp', 'Partnership', 'Nonprofit'].map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending || !name}
                className="btn-primary w-full justify-center"
              >
                {mutation.isPending
                  ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
                  : <><UserPlus size={14} /> Generate Onboarding Checklist</>
                }
              </button>
            </div>

            {result && (
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <FileCheck size={16} className="text-primary-600" />
                  <h2 className="text-sm font-semibold text-surface-900">AI Onboarding Checklist</h2>
                </div>
                <div className="text-sm text-surface-800 whitespace-pre-wrap leading-relaxed">
                  {result}
                </div>
              </div>
            )}

            {mutation.isError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-500" />
                <p className="text-sm text-red-700">Failed to generate checklist. Check your API key.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
