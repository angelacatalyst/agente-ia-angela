import { useState, useEffect, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PageHeader } from '@/components/layout/PageHeader'
import { useI18n } from '@/lib/i18n'
import { useAppStore } from '@/stores/appStore'
import { api, type QBOVendor } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  UserPlus, Loader2, CheckCircle2, AlertCircle, Plus,
  Building2, Mail, Phone, FileCheck, RefreshCw,
} from 'lucide-react'

export function VendorsPage() {
  const { t } = useI18n()
  const { selectedRealmId } = useAppStore()

  const [vendors, setVendors] = useState<QBOVendor[]>([])
  const [loadingVendors, setLoadingVendors] = useState(false)
  const [vendorError, setVendorError] = useState<string | null>(null)
  const [selected, setSelected] = useState<QBOVendor | null>(null)

  const [name, setName]   = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [type, setType]   = useState('LLC')
  const [result, setResult] = useState<string | null>(null)

  const fetchVendors = useCallback(async () => {
    if (!selectedRealmId) return
    setLoadingVendors(true)
    setVendorError(null)
    try {
      const data = await api.qboData.vendors(selectedRealmId)
      setVendors(data.vendors)
    } catch (e: any) {
      setVendorError(e?.response?.data?.detail || 'Failed to load vendors')
    } finally {
      setLoadingVendors(false)
    }
  }, [selectedRealmId])

  useEffect(() => { fetchVendors() }, [fetchVendors])

  const mutation = useMutation({
    mutationFn: () => api.chat({
      message: `Onboard new vendor: Name=${name}, Email=${email}, Phone=${phone}, EntityType=${type}. Generate onboarding checklist.`,
      module: 'vendor_onboarding',
      qbo_realm_id: selectedRealmId ?? undefined,
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
          <>
            <button onClick={fetchVendors} disabled={loadingVendors} className="btn-ghost text-[13px] gap-1.5">
              <RefreshCw size={14} className={loadingVendors ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button className="btn-primary text-[13px]">
              <Plus size={14} /> {t('common.new')} Vendor
            </button>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-2 gap-5">
          {/* Vendor list */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-surface-900">
                Vendor Roster
                {vendors.length > 0 && (
                  <span className="ml-2 text-[11px] font-normal text-surface-400">({vendors.length} from QBO)</span>
                )}
              </h2>
            </div>

            {!selectedRealmId && (
              <p className="text-sm text-surface-400 text-center py-6">Select a company to load vendors.</p>
            )}

            {loadingVendors && (
              <div className="flex items-center justify-center py-8 gap-2 text-surface-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm">Loading from QuickBooks…</span>
              </div>
            )}

            {vendorError && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-center gap-2">
                <AlertCircle size={14} className="text-red-500" />
                <p className="text-sm text-red-700">{vendorError}</p>
              </div>
            )}

            {!loadingVendors && vendors.length === 0 && selectedRealmId && !vendorError && (
              <p className="text-sm text-surface-400 text-center py-6">No vendors found in QuickBooks.</p>
            )}

            <div className="space-y-2 max-h-[420px] overflow-y-auto">
              {vendors.map(v => (
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
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-100 shrink-0">
                        <Building2 size={14} className="text-surface-500" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-surface-900">{v.name}</p>
                        {v.email && <p className="text-[11px] text-surface-400">{v.email}</p>}
                      </div>
                    </div>
                    {v.vendor_1099 && (
                      <span className="badge bg-blue-50 text-blue-700 ring-1 ring-blue-200 text-[10px] shrink-0">1099</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-surface-500">
                      Balance: <strong className="text-surface-700">{v.balance_formatted}</strong>
                    </span>
                    <span className={`badge text-[10px] ${v.active ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-surface-100 text-surface-500'}`}>
                      {v.active ? 'Active' : 'Inactive'}
                    </span>
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
